"""WAKALA gateway: the single enforcement boundary in front of protected tools.

    authenticate -> replay record -> load mandate -> authorize (pure)
      -> audit (must succeed) -> [allowed only] dispatch via ToolRegistry

* ``authorize()`` answers a policy query. It never executes anything.
* ``execute()`` performs authentication, authorization, auditing and dispatch
  in one call on one immutable request object, so the parameters that were
  authorized are exactly the parameters the handler receives (no
  time-of-check/time-of-use gap, no reusable "allowed" token).
* If auditing fails, the call raises ``AuditUnavailableError`` and nothing
  is executed.

This is a software boundary. It does not stop an agent that holds direct
credentials or network access to a real backend; in production the protected
service must itself require gateway authorization (see SECURITY_MODEL.md).
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.audit import AuditUnavailableError, OutcomeAuditUnavailable, SqliteAuditSink
from app.core.authorization import POLICY_VERSION, PolicyContext, PolicyEvaluation, PolicyFunction, authorize, explain
from app.core.crypto import canonical_json, sha256_hex
from app.core.identity import authenticate, request_digest
from app.schemas import ActionRequest, AuditEvent, AuthorizationDecision, DigitalMandate, ReasonCode, SignedActionRequest
from app.schemas.authorization import ExecutionStatus
from app.services.mandate_store import MandateMalformedError, MandateStore
from app.services.repository import Repository

from .tools import ExecutionContext, Scalar, ServiceRefusal, ToolRegistry

logger = logging.getLogger("wakala.gateway")

MandateSource = Callable[[str], DigitalMandate | None]


class AuthorizationBindingError(RuntimeError):
    """Raised if dispatch is attempted for a request other than the one authorized."""


@dataclass(frozen=True)
class ExecutionGrant:
    """Internal, non-serialisable proof that one exact request was allowed."""

    decision_id: str
    request_digest: str
    tool_name: str


@dataclass(frozen=True)
class GatewayOutcome:
    decision: AuthorizationDecision
    evaluation: PolicyEvaluation
    request: ActionRequest
    audit_event: AuditEvent


@dataclass(frozen=True)
class ExecutionOutcome:
    decision: AuthorizationDecision
    evaluation: PolicyEvaluation
    executed: bool
    status: ExecutionStatus
    result: dict[str, Scalar] | None
    execution_event: AuditEvent | None = None


class ToolDispatcher:
    """Calls handlers from the trusted registry only, only with a matching grant."""

    def __init__(self, tools: ToolRegistry) -> None:
        self._tools = tools

    def dispatch(
        self, grant: ExecutionGrant, request: ActionRequest, ctx: ExecutionContext | None = None
    ) -> tuple[ExecutionStatus, dict[str, Scalar] | None]:
        if request_digest(request) != grant.request_digest or request.tool_name != grant.tool_name:
            raise AuthorizationBindingError("request does not match the authorized request")
        spec = self._tools.get(request.tool_name)
        if spec is None:
            raise AuthorizationBindingError("tool is not registered")
        if spec.handler is None:
            return "no_handler_registered", None
        if spec.needs_context and (ctx is None or ctx.decision_id != grant.decision_id):
            raise AuthorizationBindingError("case-bound tools require the gateway execution context")
        params = spec.params_model.model_validate(request.parameters)
        try:
            result = spec.handler(params, ctx) if spec.needs_context else spec.handler(params)  # type: ignore[call-arg]
            return "executed", result
        except AuditUnavailableError:
            # The outcome record failed inside the service transaction, which
            # therefore rolled back. Propagate: this is not a service error.
            raise
        except ServiceRefusal as refusal:  # business rule; transaction rolled back, nothing changed
            return "refused_by_service", {"refusal_code": refusal.code}
        except Exception:  # handler failure is reported, never retried or escalated
            logger.exception("tool %s failed", spec.name)
            return "execution_failed", None


class Gateway:
    def __init__(
        self,
        *,
        repo: Repository,
        mandates: MandateStore,
        cases: Any = None,
        audit: SqliteAuditSink,
        replay: Any,
        tools: ToolRegistry,
        clock: Callable[[], datetime],
        max_request_skew: timedelta,
        policy: PolicyFunction = authorize,
    ) -> None:
        self._repo = repo
        self._mandates = mandates
        self._cases = cases
        self._audit = audit
        self._replay = replay
        self._tools = tools
        self._dispatcher = ToolDispatcher(tools)
        self._clock = clock
        self._skew = max_request_skew
        self._policy = policy

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    # --- context ------------------------------------------------------------------
    def policy_snapshot(self, now: datetime) -> dict[str, Any]:
        issuers = {i.issuer_id: i for i in self._repo.list_issuers()}
        issuer_keys = {}
        for issuer in issuers.values():
            key = self._repo.get_key(issuer.key_id)
            if key is not None and key.owner_type == "issuer" and key.owner_id == issuer.issuer_id and key.status == "active":
                issuer_keys[issuer.key_id] = key.public_key
        return {
            "issuers": issuers,
            "issuer_public_keys": issuer_keys,
            "revoked_mandate_ids": self._mandates.revoked_ids(),
            "known_services": frozenset(s.service_id for s in self._repo.list_services()),
        }

    def resolve_ancestors(
        self, leaf: DigitalMandate, mandate_source: MandateSource | None = None
    ) -> tuple[tuple[DigitalMandate, ...], ReasonCode | None]:
        """Follow parent links through the SERVER-SIDE store (never agent input).

        Returns (parent → root ancestors, resolution error). Bounded and cycle-safe."""
        source = mandate_source or self._mandates.get
        ancestors: list[DigitalMandate] = []
        seen = {leaf.mandate_id}
        current = leaf
        while current.parent_mandate_id is not None:
            if len(ancestors) >= 8:
                return tuple(ancestors), ReasonCode.DENY_DELEGATION_DEPTH_EXCEEDED
            if current.parent_mandate_id in seen:
                return tuple(ancestors), ReasonCode.DENY_DELEGATION_CYCLE
            try:
                parent = source(current.parent_mandate_id)
            except MandateMalformedError:
                parent = None
            if parent is None:
                return tuple(ancestors), ReasonCode.DENY_DELEGATION_CHAIN_INVALID
            ancestors.append(parent)
            seen.add(parent.mandate_id)
            current = parent
        return tuple(ancestors), None

    # --- decision -------------------------------------------------------------------
    def _decide(self, signed: SignedActionRequest, origin: str, mandate_source: MandateSource | None) -> GatewayOutcome:
        start = time.perf_counter()
        request = signed.request
        now = self._clock()
        event_id = f"EVT-{secrets.token_hex(8).upper()}"
        decision_id = f"DEC-{secrets.token_hex(8).upper()}"
        principal = None
        digest = request_digest(request)
        try:
            auth = authenticate(signed, self._repo.get_agent_key)
            principal = auth.principal
            replayed = False
            if principal is not None:
                # Only authenticated requests consume a nonce: an attacker
                # cannot burn another agent's nonces without its key.
                replayed = self._replay.check_and_record(principal.agent_id, request.nonce, now)
            mandate: DigitalMandate | None = None
            malformed = False
            if principal is not None:
                try:
                    mandate = (mandate_source or self._mandates.get)(request.mandate_id)
                except MandateMalformedError:
                    malformed = True
            case = None
            if principal is not None and request.case_id is not None and self._cases is not None:
                case = self._cases.get(request.case_id)
            ancestors: tuple[DigitalMandate, ...] = ()
            chain_error = None
            if mandate is not None:
                ancestors, chain_error = self.resolve_ancestors(mandate, mandate_source)
            ctx = PolicyContext(
                case=case,
                mandate_ancestors=ancestors,
                chain_resolution_error=chain_error,
                now=now,
                passport=self._repo.get_agent(request.agent_id) if principal is not None else None,
                tools=self._tools.specs,
                max_request_skew=self._skew,
                replay_detected=replayed,
                authentication_failure=auth.failure,
                mandate_malformed=malformed,
                **self.policy_snapshot(now),
            )
            evaluation = self._policy(request, principal, mandate, ctx)
        except Exception:  # noqa: BLE001 — any failure before/inside policy denies
            logger.exception("gateway evaluation error; denying")
            mandate = None
            evaluation = PolicyEvaluation(False, (ReasonCode.DENY_POLICY_EVALUATION_ERROR,), ())

        allowed = evaluation.allowed is True and evaluation.reason_codes == (ReasonCode.ALLOW_WITHIN_MANDATE,)
        codes = evaluation.reason_codes if allowed else tuple(c for c in evaluation.reason_codes if c is not ReasonCode.ALLOW_WITHIN_MANDATE) or (ReasonCode.DENY_DEFAULT,)
        latency_ms = (time.perf_counter() - start) * 1000
        decision = AuthorizationDecision(
            decision_id=decision_id,
            allowed=allowed,
            reason_codes=list(codes),
            human_readable_explanation=explain(allowed, codes),
            policy_version=POLICY_VERSION,
            decision_latency_ms=round(latency_ms, 3),
            audit_reference=event_id,
            mandate_id=request.mandate_id,
            request_digest=digest,
        )
        event = self._audit.append(AuditEvent(
            event_id=event_id,
            timestamp=now,
            actor=principal.agent_id if principal else "UNAUTHENTICATED",
            action=request.tool_name,
            decision="allowed" if allowed else "denied",
            request_id=request.request_id,
            related_mandate=request.mandate_id,
            authenticated=principal is not None,
            claimed_agent_id=request.agent_id,
            mandate_version=mandate.version if (mandate is not None and principal is not None) else None,
            decision_id=decision_id,
            reason_codes=list(codes),
            policy_version=POLICY_VERSION,
            decision_latency_ms=round(latency_ms, 3),
            # Minimal evidence: digests and keys, never parameter values,
            # personal records, document text or key material.
            evidence_metadata={
                "request_digest": digest,
                "action_id": request.action_id,
                "nonce": request.nonce,
                "parameter_keys": ",".join(sorted(request.parameters)),
                "target_resource": request.target_resource,
                "case_id": request.case_id,
                "origin": origin,
            },
        ))
        return GatewayOutcome(decision, evaluation, request, event)

    def authorize(self, signed: SignedActionRequest, *, origin: str = "api", mandate_source: MandateSource | None = None) -> GatewayOutcome:
        """Policy query only. Never invokes a tool."""
        return self._decide(signed, origin, mandate_source)

    def execute(self, signed: SignedActionRequest, *, origin: str = "api", mandate_source: MandateSource | None = None) -> ExecutionOutcome:
        outcome = self._decide(signed, origin, mandate_source)  # raises if audit fails -> nothing executes
        if not outcome.decision.allowed:
            return ExecutionOutcome(outcome.decision, outcome.evaluation, False, "denied", None)
        decision = outcome.decision
        spec = self._tools.get(outcome.request.tool_name)
        recorder = _OutcomeRecorder(self, outcome, origin) if spec is not None and spec.audit_execution else None
        grant = ExecutionGrant(decision.decision_id, decision.request_digest or "", outcome.request.tool_name)
        exec_ctx = ExecutionContext(
            agent_id=outcome.request.agent_id, request_id=outcome.request.request_id, case_id=outcome.request.case_id,
            decision_id=decision.decision_id, audit_reference=decision.audit_reference, now=outcome.audit_event.timestamp,
            mandate_id=outcome.request.mandate_id, outcome=recorder,
        )
        try:
            status, result = self._dispatcher.dispatch(grant, outcome.request, exec_ctx)
        except AuditUnavailableError:
            # Service writes and outcome record were in one transaction: both rolled back.
            try:
                self._audit.append(self._execution_draft(outcome, "rolled_back_outcome_not_recorded", None, origin, atomic=False))
            except AuditUnavailableError:
                pass  # reconciliation will record "authorized, not executed"
            raise OutcomeAuditUnavailable("outcome not recorded; operation rolled back", committed=False) from None
        execution_event = None
        if recorder is not None:
            if recorder.event is not None:
                execution_event = recorder.event  # committed atomically with the service change
            else:
                # Refused / failed / no-handler (nothing committed), or a handler that
                # does not use the transactional recorder (committed, recorded after).
                committed = status == "executed"
                try:
                    execution_event = self._audit.append(self._execution_draft(outcome, status, result, origin, atomic=False))
                except AuditUnavailableError:
                    raise OutcomeAuditUnavailable("outcome not recorded", committed=committed) from None
        return ExecutionOutcome(outcome.decision, outcome.evaluation, status == "executed", status, result, execution_event)

    def _execution_draft(self, outcome: GatewayOutcome, status: str, result: dict[str, Scalar] | None, origin: str,
                         *, atomic: bool) -> AuditEvent:
        """Second, informational event: what the protected service actually did."""
        req = outcome.request
        return AuditEvent(
            event_id=f"EVT-{secrets.token_hex(8).upper()}",
            timestamp=self._clock(),
            actor=req.agent_id,
            action=f"{req.tool_name}:execution"[:120],
            decision="informational",
            request_id=req.request_id,
            related_mandate=req.mandate_id,
            authenticated=True,
            claimed_agent_id=req.agent_id,
            decision_id=outcome.decision.decision_id,
            policy_version=POLICY_VERSION,
            evidence_metadata={
                "decision_event": outcome.decision.audit_reference,
                "execution_status": status,
                "case_id": req.case_id,
                "case_state_after": (result or {}).get("case_state"),
                "refusal_code": (result or {}).get("refusal_code"),
                # A digest of the result, never the result itself (it may contain record data).
                "result_digest": sha256_hex(canonical_json(result)) if result is not None else None,
                "outcome_recorded_atomically": atomic,
                "origin": origin,
            },
        )


class _OutcomeRecorder:
    """Lets a service write its mandatory outcome event inside its own DB transaction."""

    def __init__(self, gateway: Gateway, outcome: GatewayOutcome, origin: str) -> None:
        self._gateway = gateway
        self._outcome = outcome
        self._origin = origin
        self.event: AuditEvent | None = None

    def record(self, conn: Any, status: str, result: dict[str, Scalar]) -> None:
        if self.event is not None:
            raise RuntimeError("outcome already recorded")
        draft = self._gateway._execution_draft(self._outcome, status, result, self._origin, atomic=True)
        self.event = self._gateway._audit.append_in(conn, draft)
