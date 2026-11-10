"""Delegation service: issues narrowed child mandates (handler of ``delegation.commission_task``).

Runs ONLY as a trusted tool-registry handler, i.e. after the gateway has
authenticated the delegating agent and verified its mandate, the commission
grant, the case and the requested task. Inside one database transaction it:

1. re-loads the parent mandate and case and re-checks them (defence in depth),
2. builds the child as the intersection of parent ∩ task catalogue ∩ receiving
   entity authority (never more than the receiver could normally do, and never
   more than the parent was allowed to commission),
3. verifies the built child with the same non-expansion function the gateway
   uses at use-time, then signs it with the delegation-authority key,
4. stores the child mandate + a trusted delegation record + a case event, and
5. writes the mandatory outcome audit event — all commit together or not at all.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

from app.core.delegation import TASK_CATALOG, check_non_expansion, task_resources
from app.core.execution.tools import CommissionParams, ExecutionContext, Scalar, ServiceRefusal, ToolSpec
from app.models.database import Database
from app.schemas import DigitalMandate, TrustedIssuer
from app.schemas.case import CaseEvent, CaseState
from app.services.cases import CaseStore, with_event
from app.services.mandate_store import MandateStore

DELEGATION_ISSUER = "ISS-WAKALA-DELEGATION"
MandateSigner = Callable[[DigitalMandate], DigitalMandate]


class DelegationService:
    def __init__(self, db: Database, signer: MandateSigner, issuers: Callable[[], dict[str, TrustedIssuer]]) -> None:
        self._db = db
        self._sign = signer
        self._issuers = issuers

    def build_child(self, parent: DigitalMandate, task_id: str, receiver: str, requested: set[str],
                    case_id: str, now: Any) -> DigitalMandate:
        task = TASK_CATALOG[task_id]
        allowed = sorted(requested & task.operations)
        expires = min(parent.expires_at, now + task.max_lifetime)
        body: dict[str, Any] = {
            "mandate_id": f"MND-DLG-{secrets.token_hex(4).upper()}",
            "version": 1,
            "agent_id": receiver,
            "issuer_id": DELEGATION_ISSUER,
            "service_id": parent.service_id,
            "purpose": f"Delegated by {parent.agent_id}: {task.title} (case {case_id}).",
            "citizen_or_request_scope": parent.citizen_or_request_scope.model_dump(),
            "allowed_tools": allowed,
            "denied_tools": sorted(t for t in parent.denied_tools if t not in allowed),
            "resource_constraints": task_resources(task, parent.citizen_or_request_scope.citizen_ref, case_id),
            "issued_at": now,
            "expires_at": expires,
            "status": "active",
            "parent_mandate_id": parent.mandate_id,
            "case_id": case_id,
            "root_mandate_id": parent.root_mandate_id or parent.mandate_id,
            "delegation_depth": parent.delegation_depth + 1,
            "delegated_by_agent": parent.agent_id,
            "delegated_task": task_id,
            "commissionable_tasks": [],
            "max_delegation_depth": parent.max_delegation_depth,
        }
        return DigitalMandate.model_validate(body)

    def commission(self, params: CommissionParams, ctx: ExecutionContext) -> dict[str, Scalar]:
        if ctx.mandate_id is None or params.task not in TASK_CATALOG:
            raise ServiceRefusal("COMMISSION_CONTEXT_INVALID")
        # Snapshot BEFORE the transaction: the DB lock is not re-entrant.
        issuers = self._issuers()
        with self._db.transaction() as conn:
            loaded = MandateStore.get_in(conn, ctx.mandate_id)
            if loaded is None:
                raise ServiceRefusal("PARENT_NOT_FOUND")
            parent, revoked = loaded
            if revoked or parent.agent_id != ctx.agent_id or parent.case_id != params.case_id:
                raise ServiceRefusal("PARENT_NOT_USABLE")
            case = CaseStore.load_in(conn, params.case_id)
            if case is None or case.authority_revoked or case.citizen_ref != params.citizen_ref \
                    or case.state not in {CaseState.VERIFYING}:
                raise ServiceRefusal("CASE_NOT_USABLE")
            requested = {op for op in params.requested_operations.split(",") if op}
            child = self.build_child(parent, params.task, params.receiving_agent_id, requested, case.case_id, ctx.now)
            if check_non_expansion(child, parent, issuers):  # same rule as use-time verification
                raise ServiceRefusal("DELEGATION_WOULD_EXPAND")
            signed = self._sign(child)
            MandateStore.put_in(conn, signed)
            conn.execute(
                "INSERT INTO delegations (child_mandate_id, parent_mandate_id, root_mandate_id, case_id, from_agent, to_agent, "
                "task, depth, issued_at, expires_at, decision_id, decision_event) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (signed.mandate_id, parent.mandate_id, signed.root_mandate_id, case.case_id, parent.agent_id, signed.agent_id,
                 params.task, signed.delegation_depth, signed.issued_at.isoformat(), signed.expires_at.isoformat(),
                 ctx.decision_id, ctx.audit_reference),
            )
            after = with_event(case, CaseEvent(
                at=ctx.now, actor=ctx.agent_id, kind="delegation_issued", audit_reference=ctx.audit_reference,
                detail=f"{params.task} delegated to {signed.agent_id} under child mandate {signed.mandate_id}"))
            CaseStore.save_in(conn, case, after)
            result: dict[str, Scalar] = {
                "child_mandate_id": signed.mandate_id, "parent_mandate_id": parent.mandate_id,
                "root_mandate_id": signed.root_mandate_id, "task": params.task, "receiving_agent_id": signed.agent_id,
                "allowed_operations": ",".join(signed.allowed_tools), "delegation_depth": signed.delegation_depth,
                "expires_at": signed.expires_at.isoformat(), "case_state": after.state.value,
            }
            ctx.record_outcome(conn, result)
        return result

    def tool_spec(self) -> ToolSpec:
        return ToolSpec(
            "delegation.commission_task", service_id="residency_renewal", resource_type="renewal_case", access="write",
            target="case_id", params_model=CommissionParams, monetary=False, handler=self.commission,
            description="Commission a catalogued task from another agent; WAKALA issues a narrowed, signed child mandate.",
            case_states=frozenset({CaseState.VERIFYING.value}), needs_context=True, audit_execution=True, commission=True,
        )
