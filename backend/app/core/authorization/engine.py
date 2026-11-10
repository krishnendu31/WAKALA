"""Deterministic, default-deny policy engine.

``authorize()`` is a pure function of its inputs: the request, the principal
produced by signature verification (or None), the mandate loaded from the
server-side store (or None) and a ``PolicyContext`` snapshot. It performs no
I/O, calls no external service and uses no LLM.

Eight checks, in order:

  1 identity            request signature verified, principal matches claim
  2 agent_status        passport exists, is active, key is the registered one
  3 mandate_integrity   mandate exists, signed by a trusted issuer, within
                        that issuer's authority, bound to this agent
  4 mandate_validity    active, not revoked, inside its validity window
  5 tool_permission     tool known, not denied, explicitly allowed, same service
  6 resource_scope      citizen, request and target resource inside the mandate
  7 action_constraints  strict parameters; amount and recipient limits
  8 request_context     timestamp freshness, nonce not replayed, no delegation

Checks 1-4 short-circuit: nothing about a mandate is evaluated for an
unauthenticated caller. Checks 5-8 are all evaluated so a denial lists every
violated constraint. ``allowed`` is True only if all eight checks positively
pass. Any exception yields DENY_POLICY_EVALUATION_ERROR.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ValidationError

from app.core.delegation.chain import verify_chain
from app.core.delegation.tasks import GLOBAL_MAX_DELEGATION_DEPTH, TASK_CATALOG, DelegableTask
from app.core.execution.tools import CommissionParams, FeePaymentParams, ToolSpec
from app.core.identity import AuthenticatedPrincipal, VerifiedIdentity
from app.core.mandates import check_mandate_lifecycle, verify_mandate_integrity
from app.schemas import ActionRequest, AgentPassport, AuthorizationDecision, DigitalMandate, ReasonCode, TrustedIssuer
from app.schemas.case import RenewalCase

logger = logging.getLogger("wakala.policy")
R = ReasonCode

POLICY_VERSION = "1.0.0"

CHECK_NAMES: tuple[str, ...] = (
    "identity",
    "agent_status",
    "mandate_integrity",
    "mandate_validity",
    "tool_permission",
    "resource_scope",
    "action_constraints",
    "request_context",
)

CheckStatus = Literal["passed", "failed", "not_evaluated"]


@dataclass(frozen=True)
class PolicyContext:
    now: datetime
    passport: AgentPassport | None
    issuers: Mapping[str, TrustedIssuer]
    issuer_public_keys: Mapping[str, Ed25519PublicKey]
    revoked_mandate_ids: frozenset[str]
    tools: Mapping[str, ToolSpec]
    known_services: frozenset[str]
    max_request_skew: timedelta
    replay_detected: bool = False
    authentication_failure: ReasonCode | None = None
    mandate_malformed: bool = False
    # Phase 2: snapshot of the case named by the signed request (None if absent/unknown).
    case: RenewalCase | None = None
    # Phase 3: ancestors of the presented mandate, resolved server-side (parent → root).
    mandate_ancestors: tuple[DigitalMandate, ...] = ()
    chain_resolution_error: ReasonCode | None = None
    task_catalog: Mapping[str, DelegableTask] = TASK_CATALOG
    # Phase 4
    suspended_mandate_ids: frozenset[str] = frozenset()
    # True only when re-authorizing a stored request an officer approved: freshness and
    # nonce were checked when it was first submitted; EVERY other check runs again now.
    approved_reauthorization: bool = False


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    reason_codes: tuple[ReasonCode, ...] = ()


@dataclass(frozen=True)
class PolicyEvaluation:
    allowed: bool
    reason_codes: tuple[ReasonCode, ...]
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)


_NOT_EVALUATED = None  # sentinel returned by checks that cannot run


def _dedupe(codes: list[ReasonCode]) -> list[ReasonCode]:
    return list(dict.fromkeys(codes))


# --- individual checks -------------------------------------------------------
# Each returns a list of reason codes (empty = passed) or _NOT_EVALUATED.

def check_identity(req: ActionRequest, principal: AuthenticatedPrincipal | None, ctx: PolicyContext) -> list[ReasonCode]:
    if principal is None:
        return [ctx.authentication_failure or R.DENY_IDENTITY_UNVERIFIED]
    if principal.agent_id != req.agent_id:
        return [R.DENY_IDENTITY_MISMATCH]
    return []


def check_agent_status(req: ActionRequest, principal: AuthenticatedPrincipal, ctx: PolicyContext) -> list[ReasonCode]:
    p = ctx.passport
    if p is None or p.agent_id != req.agent_id:
        return [R.DENY_UNKNOWN_AGENT]
    if p.status != "active":
        return [R.DENY_AGENT_NOT_ACTIVE]
    key = p.identity_key_reference
    if key.provisioning_status != "provisioned" or key.key_id != principal.key_id:
        return [R.DENY_IDENTITY_UNVERIFIED]
    return []


def check_mandate_integrity(req: ActionRequest, mandate: DigitalMandate | None, ctx: PolicyContext) -> list[ReasonCode]:
    if ctx.mandate_malformed:
        return [R.DENY_MANDATE_MALFORMED]
    if mandate is None or mandate.mandate_id != req.mandate_id:
        return [R.DENY_MANDATE_MISSING]
    codes = verify_mandate_integrity(mandate, ctx.issuers, ctx.issuer_public_keys)
    if codes:
        return codes
    if mandate.agent_id != req.agent_id:
        return [R.DENY_MANDATE_AGENT_MISMATCH]
    if mandate.parent_mandate_id is not None or ctx.mandate_ancestors or ctx.chain_resolution_error:
        # Delegated authority: every ancestor and every link must verify.
        return verify_chain(mandate, ctx.mandate_ancestors, ctx.issuers, ctx.issuer_public_keys, ctx.now,
                            ctx.revoked_mandate_ids, ctx.chain_resolution_error, ctx.task_catalog, ctx.suspended_mandate_ids)
    return []


def check_mandate_validity(mandate: DigitalMandate, ctx: PolicyContext) -> list[ReasonCode]:
    return check_mandate_lifecycle(mandate, ctx.now, ctx.revoked_mandate_ids, ctx.suspended_mandate_ids)


def check_tool_permission(req: ActionRequest, mandate: DigitalMandate, ctx: PolicyContext) -> list[ReasonCode]:
    codes: list[ReasonCode] = []
    spec = ctx.tools.get(req.tool_name)
    if req.tool_name in mandate.denied_tools:
        codes.append(R.DENY_TOOL_EXPLICITLY_DENIED)
    if spec is None:
        codes.append(R.DENY_UNKNOWN_TOOL)
        return codes
    if spec.commission:
        # Commissioning is authorized by the commission grant, never by allowed_tools.
        if req.parameters.get("task") not in mandate.commissionable_tasks:
            codes.append(R.DENY_DELEGATION_NOT_PERMITTED)
    elif req.tool_name not in mandate.allowed_tools and R.DENY_TOOL_EXPLICITLY_DENIED not in codes:
        codes.append(R.DENY_TOOL_NOT_PERMITTED)
    if spec.service_id != mandate.service_id or mandate.service_id not in ctx.known_services:
        codes.append(R.DENY_SERVICE_SCOPE_VIOLATION)
    return codes


def check_resource_scope(req: ActionRequest, mandate: DigitalMandate, ctx: PolicyContext) -> list[ReasonCode] | None:
    spec = ctx.tools.get(req.tool_name)
    if spec is None:
        return _NOT_EVALUATED
    scope = mandate.citizen_or_request_scope
    violated = (
        req.request_id != scope.request_id
        or req.parameters.get("citizen_ref") != scope.citizen_ref
    )
    expected_target = {
        "citizen_ref": req.parameters.get("citizen_ref"),
        "request_id": req.request_id,
        "case_id": req.parameters.get("case_id"),
    }[spec.target]
    if req.target_resource != expected_target:
        violated = True
    covered = any(
        rc.resource_type == spec.resource_type and rc.access == spec.access and req.target_resource in rc.identifiers
        for rc in mandate.resource_constraints
    )
    codes = [R.DENY_SCOPE_VIOLATION] if violated or not covered else []
    if spec.case_states is not None:
        codes += check_case_binding(req, mandate, spec, ctx)
    return codes


def check_case_binding(req: ActionRequest, mandate: DigitalMandate, spec: ToolSpec, ctx: PolicyContext) -> list[ReasonCode]:
    """Case-specific authority: the signed case must own this exact action."""
    if req.case_id is None:
        return [R.DENY_CASE_REQUIRED]
    case = ctx.case
    if case is None or case.case_id != req.case_id:
        return [R.DENY_CASE_NOT_FOUND]
    codes: list[ReasonCode] = []
    scope = mandate.citizen_or_request_scope
    if (
        req.parameters.get("case_id") != case.case_id
        or req.parameters.get("citizen_ref") != case.citizen_ref
        or case.citizen_ref != scope.citizen_ref
        or case.request_id != scope.request_id
        or req.request_id != case.request_id
    ):
        codes.append(R.DENY_CASE_SCOPE_VIOLATION)
    if case.authority_revoked:
        codes.append(R.DENY_CASE_AUTHORITY_REVOKED)
    direct = req.agent_id in case.assigned_agents and case.mandate_refs.get(req.agent_id) == req.mandate_id
    root = ctx.mandate_ancestors[-1] if ctx.mandate_ancestors else None
    delegated = (
        mandate.parent_mandate_id is not None and root is not None
        and root.mandate_id in case.mandate_refs.values() and root.agent_id in case.assigned_agents
        and case.mandate_refs.get(root.agent_id) == root.mandate_id
    )
    if mandate.parent_mandate_id is not None and mandate.case_id != case.case_id:
        codes.append(R.DENY_DELEGATION_CASE_MISMATCH)
    if mandate.delegated_task and case.task_assignments.get(mandate.delegated_task, mandate.agent_id) != mandate.agent_id:
        delegated = False  # the task was reassigned away from this agent for this case
    if not (direct or delegated):
        codes.append(R.DENY_CASE_AGENT_NOT_ASSIGNED)
    if req.tool_name not in case.authorized_operations:
        codes.append(R.DENY_CASE_OPERATION_NOT_AUTHORIZED)
    if case.service_id != mandate.service_id or case.service_id != spec.service_id:
        codes.append(R.DENY_CASE_PURPOSE_MISMATCH)
    if case.state.value not in spec.case_states:  # type: ignore[operator]
        codes.append(R.DENY_CASE_STATE_INVALID)
    if ctx.now >= case.expires_at:
        codes.append(R.DENY_CASE_EXPIRED)
    return codes


def check_action_constraints(req: ActionRequest, mandate: DigitalMandate, ctx: PolicyContext) -> list[ReasonCode] | None:
    spec = ctx.tools.get(req.tool_name)
    if spec is None:
        return _NOT_EVALUATED
    try:
        params = spec.params_model.model_validate(req.parameters)
    except ValidationError:
        return [R.DENY_INVALID_PARAMETERS]
    if spec.commission:
        return check_commission_request(req, mandate, params, ctx)
    if not spec.monetary:
        return []
    if not isinstance(params, FeePaymentParams):  # monetary tools must use the payment model
        return [R.DENY_INVALID_PARAMETERS]
    limit = mandate.amount_limit
    if limit is None or not mandate.recipient_allowlist:
        return [R.DENY_CONSTRAINT_MISSING]
    codes: list[ReasonCode] = []
    if params.currency != limit.currency or params.amount > limit.amount:
        codes.append(R.DENY_AMOUNT_EXCEEDS_LIMIT)
    if params.recipient not in mandate.recipient_allowlist:
        codes.append(R.DENY_RECIPIENT_NOT_ALLOWLISTED)
    return codes


def check_commission_request(req: ActionRequest, mandate: DigitalMandate, params: object, ctx: PolicyContext) -> list[ReasonCode]:
    """What a commission may ask for: a catalogued task, a permitted receiver,
    only that task's operations, within depth, without cycles."""
    if not isinstance(params, CommissionParams):
        return [R.DENY_INVALID_PARAMETERS]
    codes: list[ReasonCode] = []
    task = ctx.task_catalog.get(params.task)
    if task is None:
        return [R.DENY_DELEGATION_NOT_PERMITTED]
    assignments = ctx.case.task_assignments if ctx.case is not None and ctx.case.case_id == req.case_id else {}
    if params.receiving_agent_id not in task.receivers_for(assignments) or params.receiving_agent_id == req.agent_id:
        codes.append(R.DENY_DELEGATION_NOT_PERMITTED)
    requested = {op for op in params.requested_operations.split(",") if op}
    if not requested or not requested <= task.operations:
        codes.append(R.DENY_DELEGATION_EXPANDS_AUTHORITY)
    if task.monetary and mandate.amount_limit is None:
        codes.append(R.DENY_DELEGATION_EXPANDS_AUTHORITY)
    new_depth = mandate.delegation_depth + 1
    if new_depth > min(mandate.max_delegation_depth, GLOBAL_MAX_DELEGATION_DEPTH):
        codes.append(R.DENY_DELEGATION_DEPTH_EXCEEDED)
    chain_agents = {mandate.agent_id, *(m.agent_id for m in ctx.mandate_ancestors)}
    if params.receiving_agent_id in chain_agents:
        codes.append(R.DENY_DELEGATION_CYCLE)
    if mandate.case_id is None or mandate.case_id != req.case_id:
        codes.append(R.DENY_DELEGATION_CASE_MISMATCH)
    return codes


def check_request_context(req: ActionRequest, ctx: PolicyContext) -> list[ReasonCode]:
    codes: list[ReasonCode] = []
    if not ctx.approved_reauthorization:
        if abs(ctx.now - req.timestamp) > ctx.max_request_skew:
            codes.append(R.DENY_REQUEST_STALE)
        if ctx.replay_detected:
            codes.append(R.DENY_REPLAYED_REQUEST)
    if req.delegation_chain:
        # Delegated execution is verified from Phase 2; until then it is refused.
        codes.append(R.DENY_DELEGATION_CHAIN_INVALID)
    return codes


# --- evaluation ----------------------------------------------------------------

def _result(name: str, codes: list[ReasonCode] | None) -> CheckResult:
    if codes is None:
        return CheckResult(name, "not_evaluated")
    return CheckResult(name, "failed" if codes else "passed", tuple(_dedupe(codes)))


def _deny(checks: list[CheckResult]) -> PolicyEvaluation:
    done = {c.name for c in checks}
    padded = checks + [CheckResult(n, "not_evaluated") for n in CHECK_NAMES if n not in done]
    codes = _dedupe([code for c in padded for code in c.reason_codes]) or [R.DENY_DEFAULT]
    return PolicyEvaluation(False, tuple(codes), tuple(padded))


def _evaluate(
    req: ActionRequest, principal: AuthenticatedPrincipal | None, mandate: DigitalMandate | None, ctx: PolicyContext
) -> PolicyEvaluation:
    checks: list[CheckResult] = []

    checks.append(_result("identity", check_identity(req, principal, ctx)))
    if checks[-1].status != "passed" or principal is None:
        return _deny(checks)
    checks.append(_result("agent_status", check_agent_status(req, principal, ctx)))
    if checks[-1].status != "passed":
        return _deny(checks)
    checks.append(_result("mandate_integrity", check_mandate_integrity(req, mandate, ctx)))
    if checks[-1].status != "passed" or mandate is None:
        return _deny(checks)
    checks.append(_result("mandate_validity", check_mandate_validity(mandate, ctx)))
    if checks[-1].status != "passed":
        return _deny(checks)

    checks.append(_result("tool_permission", check_tool_permission(req, mandate, ctx)))
    checks.append(_result("resource_scope", check_resource_scope(req, mandate, ctx)))
    checks.append(_result("action_constraints", check_action_constraints(req, mandate, ctx)))
    checks.append(_result("request_context", check_request_context(req, ctx)))

    all_passed = len(checks) == len(CHECK_NAMES) and all(c.status == "passed" for c in checks)
    if not all_passed:
        return _deny(checks)
    return PolicyEvaluation(True, (R.ALLOW_WITHIN_MANDATE,), tuple(checks))


def authorize(
    request: ActionRequest,
    principal: AuthenticatedPrincipal | None,
    mandate: DigitalMandate | None,
    ctx: PolicyContext,
) -> PolicyEvaluation:
    """Pure default-deny evaluation. Never raises; never allows on error."""
    try:
        return _evaluate(request, principal, mandate, ctx)
    except Exception:  # noqa: BLE001 — deliberate fail-closed boundary
        logger.exception("policy evaluation error; denying")
        return PolicyEvaluation(False, (R.DENY_POLICY_EVALUATION_ERROR,), ())


PolicyFunction = Callable[
    [ActionRequest, AuthenticatedPrincipal | None, DigitalMandate | None, PolicyContext], PolicyEvaluation
]


# --- explanations -------------------------------------------------------------
# Safe, generic sentences: no keys, no mandate internals beyond the reason.

EXPLANATIONS: dict[ReasonCode, str] = {
    R.ALLOW_WITHIN_MANDATE: "The action is within the agent's signed mandate.",
    R.DENY_DEFAULT: "The action was not positively authorized.",
    R.DENY_POLICY_EVALUATION_ERROR: "The policy could not be evaluated, so the action was refused.",
    R.DENY_UNKNOWN_AGENT: "The requesting agent is not registered.",
    R.DENY_IDENTITY_UNVERIFIED: "The agent's identity could not be verified.",
    R.DENY_REQUEST_SIGNATURE_INVALID: "The request signature is not valid for the registered agent key.",
    R.DENY_IDENTITY_MISMATCH: "The authenticated identity does not match the requesting agent.",
    R.DENY_AGENT_NOT_ACTIVE: "The agent is not active in the registry.",
    R.DENY_MANDATE_MISSING: "No mandate with this identifier exists.",
    R.DENY_MANDATE_MALFORMED: "The stored mandate is malformed.",
    R.DENY_MANDATE_UNSIGNED: "The mandate is not signed.",
    R.DENY_SIGNATURE_INVALID: "The mandate signature does not verify; it may have been modified.",
    R.DENY_ISSUER_UNTRUSTED: "The mandate was not issued by a trusted issuer.",
    R.DENY_ISSUER_AUTHORITY_EXCEEDED: "The mandate grants more than its issuer is authorized to grant.",
    R.DENY_MANDATE_AGENT_MISMATCH: "The mandate was issued to a different agent.",
    R.DENY_MANDATE_EXPIRED: "The mandate has expired.",
    R.DENY_MANDATE_NOT_YET_VALID: "The mandate is not yet valid.",
    R.DENY_MANDATE_REVOKED: "The mandate has been revoked.",
    R.DENY_UNKNOWN_TOOL: "The requested tool is not registered with the gateway.",
    R.DENY_TOOL_NOT_PERMITTED: "The mandate does not permit this tool.",
    R.DENY_TOOL_EXPLICITLY_DENIED: "The mandate explicitly forbids this tool.",
    R.DENY_SERVICE_SCOPE_VIOLATION: "The tool belongs to a service outside the mandate.",
    R.DENY_SCOPE_VIOLATION: "The target citizen, request or resource is outside the mandate's scope.",
    R.DENY_CASE_REQUIRED: "This operation must be performed within a renewal case.",
    R.DENY_CASE_NOT_FOUND: "The referenced case does not exist.",
    R.DENY_CASE_SCOPE_VIOLATION: "The request does not match the citizen and request of the active case.",
    R.DENY_CASE_AGENT_NOT_ASSIGNED: "The agent or mandate is not assigned to this case.",
    R.DENY_CASE_OPERATION_NOT_AUTHORIZED: "The case does not authorize this operation.",
    R.DENY_CASE_PURPOSE_MISMATCH: "The operation does not serve the case's authorized purpose.",
    R.DENY_CASE_STATE_INVALID: "The case is not in a state that permits this operation.",
    R.DENY_CASE_EXPIRED: "The case has expired.",
    R.DENY_INVALID_PARAMETERS: "The tool parameters are invalid.",
    R.DENY_CONSTRAINT_MISSING: "A required mandate constraint for this action is missing.",
    R.DENY_AMOUNT_EXCEEDS_LIMIT: "The amount exceeds the mandate's limit.",
    R.DENY_RECIPIENT_NOT_ALLOWLISTED: "The recipient is not on the mandate's allow-list.",
    R.DENY_REQUEST_STALE: "The request timestamp is outside the accepted freshness window.",
    R.DENY_REPLAYED_REQUEST: "This request has already been submitted.",
    R.DENY_DELEGATION_CHAIN_INVALID: "The delegation chain is invalid (client-supplied chains are never accepted).",
    R.DENY_DELEGATION_EXPANDS_AUTHORITY: "The delegation would expand authority beyond what was granted.",
    R.DENY_DELEGATION_NOT_PERMITTED: "The mandate does not permit commissioning this task from this agent.",
    R.DENY_DELEGATION_DEPTH_EXCEEDED: "The delegation chain would exceed its permitted depth.",
    R.DENY_DELEGATION_CYCLE: "The delegation would create a cycle.",
    R.DENY_DELEGATION_CASE_MISMATCH: "The delegated mandate belongs to a different case.",
    R.DENY_PARENT_MANDATE_INVALID: "A mandate higher in the delegation chain is not authentic or trusted.",
    R.DENY_PARENT_MANDATE_EXPIRED: "A mandate higher in the delegation chain has expired.",
    R.DENY_PARENT_MANDATE_REVOKED: "A mandate higher in the delegation chain has been revoked.",
    R.DENY_CASE_AUTHORITY_REVOKED: "Authority for this case has been revoked.",
    R.DENY_MANDATE_SUSPENDED: "The mandate is suspended pending review.",
    R.DENY_PARENT_MANDATE_SUSPENDED: "A mandate higher in the delegation chain is suspended pending review.",
    R.DENY_ENGINE_NOT_CONNECTED: "The enforcement engine is not connected.",
    R.ESCALATE_HUMAN_REVIEW: "The action is held for human approval and has not been executed.",
}


def explain(allowed: bool, codes: tuple[ReasonCode, ...]) -> str:
    sentences = " ".join(EXPLANATIONS.get(c, c.value) for c in codes)
    return f"{'Allowed' if allowed else 'Denied'}: {sentences}"[:500]


class FailClosedEngine:
    """Fallback decision point that denies everything (Phase 0 placeholder)."""

    def decide(
        self,
        request: ActionRequest,
        identity: VerifiedIdentity | None,
        mandates: list[DigitalMandate],
    ) -> AuthorizationDecision:
        import time
        import uuid

        start = time.perf_counter()
        suffix = uuid.uuid4().hex[:12].upper()
        return AuthorizationDecision(
            decision_id=f"DEC-{suffix}",
            allowed=False,
            reason_codes=[ReasonCode.DENY_ENGINE_NOT_CONNECTED],
            human_readable_explanation=(
                f"Denied: the WAKALA enforcement engine is not connected, so {request.tool_name} "
                "cannot be independently authorized."
            ),
            policy_version="0.0.0",
            decision_latency_ms=(time.perf_counter() - start) * 1000,
            audit_reference=f"EVT-{suffix}",
        )
