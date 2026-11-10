"""Mandate-chain verification and the non-expansion rule (pure functions).

The chain is resolved server-side from stored mandates by following
``parent_mandate_id``; agents never supply it. For a mandate used at the
gateway, every ancestor must be authentic, trusted and currently valid, and
every parent→child link must be a strict narrowing:

    effective(child) ⊆ commission grant of parent (task ∈ parent.commissionable_tasks)
                     ∩ task catalogue operations / receivers / resource template
                     ∩ receiving entity's own issuer authority
                     ∩ parent's case, citizen, request, service, money and time bounds
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.mandates import check_mandate_lifecycle, verify_mandate_integrity
from app.schemas import DigitalMandate, ReasonCode, TrustedIssuer

from .tasks import GLOBAL_MAX_DELEGATION_DEPTH, TASK_CATALOG, DelegableTask

R = ReasonCode


def _dedupe(codes: list[ReasonCode]) -> list[ReasonCode]:
    return list(dict.fromkeys(codes))


def task_resources(task: DelegableTask, citizen_ref: str, case_id: str) -> list[dict[str, Any]]:
    return [{"resource_type": t.resource_type, "access": t.access,
             "identifiers": [citizen_ref if t.identifier == "citizen_ref" else case_id]} for t in task.resources]


def check_non_expansion(
    child: DigitalMandate,
    parent: DigitalMandate,
    issuers: Mapping[str, TrustedIssuer],
    catalog: Mapping[str, DelegableTask] = TASK_CATALOG,
) -> list[ReasonCode]:
    """Empty list only if ``child`` is a valid narrowing of ``parent``."""
    codes: list[ReasonCode] = []
    if child.parent_mandate_id != parent.mandate_id:
        return [R.DENY_DELEGATION_CHAIN_INVALID]
    task = catalog.get(child.delegated_task or "")
    if task is None or child.delegated_task not in parent.commissionable_tasks:
        codes.append(R.DENY_DELEGATION_NOT_PERMITTED)
    if child.delegated_by_agent != parent.agent_id or child.agent_id == parent.agent_id:
        codes.append(R.DENY_DELEGATION_CHAIN_INVALID)
    if child.delegation_depth != parent.delegation_depth + 1:
        codes.append(R.DENY_DELEGATION_CHAIN_INVALID)
    if child.delegation_depth > min(parent.max_delegation_depth, GLOBAL_MAX_DELEGATION_DEPTH):
        codes.append(R.DENY_DELEGATION_DEPTH_EXCEEDED)
    expected_root = parent.root_mandate_id or parent.mandate_id
    if child.root_mandate_id != expected_root:
        codes.append(R.DENY_DELEGATION_CHAIN_INVALID)
    if parent.case_id is None or child.case_id != parent.case_id:
        codes.append(R.DENY_DELEGATION_CASE_MISMATCH)

    expands = (
        child.service_id != parent.service_id
        or child.citizen_or_request_scope != parent.citizen_or_request_scope
        or child.issued_at < parent.issued_at
        or child.expires_at > parent.expires_at
        or not set(child.commissionable_tasks) <= set(parent.commissionable_tasks)
        or child.max_delegation_depth > parent.max_delegation_depth
        or not set(parent.denied_tools) - set(child.allowed_tools) <= set(child.denied_tools)
    )
    if parent.amount_limit is None:
        expands = expands or child.amount_limit is not None or bool(child.recipient_allowlist)
    else:
        expands = expands or (child.amount_limit is not None and (
            child.amount_limit.currency != parent.amount_limit.currency or child.amount_limit.amount > parent.amount_limit.amount))
        expands = expands or not set(child.recipient_allowlist) <= set(parent.recipient_allowlist)
    if task is not None:
        if child.agent_id not in task.receivers:
            codes.append(R.DENY_DELEGATION_NOT_PERMITTED)
        expands = expands or not set(child.allowed_tools) <= task.operations
        expands = expands or (child.expires_at - child.issued_at) > task.max_lifetime
        allowed_resources = task_resources(task, parent.citizen_or_request_scope.citizen_ref, parent.case_id or "")
        for rc in child.resource_constraints:
            match = [a for a in allowed_resources if a["resource_type"] == rc.resource_type and a["access"] == rc.access]
            if not match or not set(rc.identifiers) <= set(match[0]["identifiers"]):
                expands = True
        if task.monetary and parent.amount_limit is None:
            expands = True
        # Receiving entity policy: the receiving agent's own entity must authorize these operations.
        receiving = issuers.get(task.receiving_issuer)
        if receiving is None or receiving.status != "active" or child.agent_id not in receiving.authority.agents \
                or not set(child.allowed_tools) <= set(receiving.authority.tools):
            codes.append(R.DENY_DELEGATION_NOT_PERMITTED)
    if expands:
        codes.append(R.DENY_DELEGATION_EXPANDS_AUTHORITY)
    return _dedupe(codes)


def verify_chain(
    leaf: DigitalMandate,
    ancestors: Sequence[DigitalMandate],
    issuers: Mapping[str, TrustedIssuer],
    issuer_public_keys: Mapping[str, Ed25519PublicKey],
    now: datetime,
    revoked_ids: frozenset[str],
    resolution_error: ReasonCode | None = None,
    catalog: Mapping[str, DelegableTask] = TASK_CATALOG,
    suspended_ids: frozenset[str] = frozenset(),
) -> list[ReasonCode]:
    """Verify every ancestor and every link of leaf → … → root. Empty list = verified."""
    if resolution_error is not None:
        return [resolution_error]
    if leaf.parent_mandate_id is None:
        return [] if not ancestors else [R.DENY_DELEGATION_CHAIN_INVALID]
    chain = [leaf, *ancestors]  # child → root
    ids = [m.mandate_id for m in chain]
    if len(set(ids)) != len(ids):
        return [R.DENY_DELEGATION_CYCLE]
    agents = [m.agent_id for m in chain]
    if len(set(agents)) != len(agents):
        return [R.DENY_DELEGATION_CYCLE]
    if len(chain) - 1 > GLOBAL_MAX_DELEGATION_DEPTH:
        return [R.DENY_DELEGATION_DEPTH_EXCEEDED]
    if chain[-1].parent_mandate_id is not None:
        return [R.DENY_DELEGATION_CHAIN_INVALID]
    codes: list[ReasonCode] = []
    for ancestor in ancestors:
        if verify_mandate_integrity(ancestor, issuers, issuer_public_keys):
            codes.append(R.DENY_PARENT_MANDATE_INVALID)
            continue
        life = check_mandate_lifecycle(ancestor, now, revoked_ids, suspended_ids)
        if R.DENY_MANDATE_REVOKED in life:
            codes.append(R.DENY_PARENT_MANDATE_REVOKED)
        elif R.DENY_MANDATE_SUSPENDED in life:
            codes.append(R.DENY_PARENT_MANDATE_SUSPENDED)
        elif life:
            codes.append(R.DENY_PARENT_MANDATE_EXPIRED)
    if codes:
        return _dedupe(codes)
    for child, parent in zip(chain, chain[1:]):
        codes += check_non_expansion(child, parent, issuers, catalog)
    return _dedupe(codes)
