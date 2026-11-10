"""Officer interventions — the ONLY code path for human administrative actions.

Every function takes an authenticated ``OfficerPrincipal`` (derived from the
server-side session, never from request data), checks role permission and
entity scope, performs one narrowly scoped change, and writes an audit event
with the officer as actor. None of them executes a protected service directly:
recovery always continues through signed agent requests and ``Gateway.execute()``.
"""

from __future__ import annotations

import secrets
from typing import Any

from app.core.delegation import TASK_CATALOG
from app.schemas import AuditEvent
from app.schemas.case import CaseEvent, CaseState, RenewalCase
from app.services.bootstrap import WakalaEnvironment
from app.services.cases import CaseStore, InvalidTransition, next_case, with_event
from app.services.officers import AuthError, OfficerPrincipal


class InterventionError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _require(p: OfficerPrincipal, permission: str) -> None:
    if not p.can(permission):
        raise AuthError("PERMISSION_DENIED", 403)


def _case_scope(env: WakalaEnvironment, p: OfficerPrincipal, case_id: str) -> RenewalCase:
    case = env.cases.get(case_id)
    if case is None:
        raise InterventionError("CASE_NOT_FOUND", 404)
    if not p.can_act_on_entity(case.service_owner):
        raise AuthError("OUT_OF_ENTITY_SCOPE", 403)
    return case


def _mandate_scope(env: WakalaEnvironment, p: OfficerPrincipal, mandate_id: str) -> Any:
    m = env.mandates.get(mandate_id)
    if m is None:
        raise InterventionError("MANDATE_NOT_FOUND", 404)
    if m.case_id:
        _case_scope(env, p, m.case_id)
    elif not p.can("all_entities"):
        raise AuthError("OUT_OF_ENTITY_SCOPE", 403)
    return m


def _audit(env: WakalaEnvironment, p: OfficerPrincipal, action: str, evidence: dict[str, Any],
           related_mandate: str | None = None) -> AuditEvent:
    return env.audit.append(AuditEvent(
        event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor=p.officer_id, action=f"officer.{action}",
        decision="informational", related_mandate=related_mandate,
        evidence_metadata={**{k: v for k, v in evidence.items() if isinstance(v, (str, int, float, bool)) or v is None},
                           "officer_role": p.officer.role, "origin": "officer_console"}))


def _case_event(env: WakalaEnvironment, case_id: str, p: OfficerPrincipal, kind: str, detail: str, ref: str,
                update: dict[str, Any] | None = None) -> RenewalCase:
    with env.db.transaction() as conn:
        before = CaseStore.load_in(conn, case_id)
        if before is None:
            raise InterventionError("CASE_NOT_FOUND", 404)
        after = with_event(before, CaseEvent(at=env.clock(), actor=p.officer_id, kind=kind, detail=detail,  # type: ignore[arg-type]
                                             audit_reference=ref))
        if update:
            after = after.model_copy(update=update)
        CaseStore.save_in(conn, before, after)
    return after


# --- incidents -----------------------------------------------------------------
def guarded(fn: Any, env: WakalaEnvironment, p: OfficerPrincipal, *args: Any, **kw: Any) -> Any:
    """Run an intervention; a refused attempt by an authenticated officer is itself audited (Phase 5:
    previously only successful officer actions reached the hash-chained audit trail)."""
    try:
        return fn(env, p, *args, **kw)
    except (AuthError, InterventionError) as e:
        target = next((a for a in args if isinstance(a, str)), None)
        _audit(env, p, "action_refused", {"attempted": getattr(fn, "__name__", "unknown"), "code": e.code,
                                          "target": target[:64] if target else None})
        raise


def audit_session_rejection(env: WakalaEnvironment, code: str) -> None:
    """Unauthenticated officer requests carry no trustworthy identity; record the rejection without one."""
    env.audit.append(AuditEvent(
        event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor="UNAUTHENTICATED",
        action="officer.session_rejected", decision="informational",
        evidence_metadata={"code": code, "origin": "officer_console"}))


def set_incident_status(env: WakalaEnvironment, p: OfficerPrincipal, incident_id: str, status: str, note: str) -> Any:
    _require(p, "incidents.close" if status in ("resolved", "dismissed") and not p.can("incidents.update") else "incidents.update")
    inc = env.assurance.incidents.get(incident_id)
    if inc is None:
        raise InterventionError("INCIDENT_NOT_FOUND", 404)
    if inc.case_id:
        _case_scope(env, p, inc.case_id)
    elif not p.can("all_entities"):
        raise AuthError("OUT_OF_ENTITY_SCOPE", 403)
    try:
        updated = env.assurance.set_status(incident_id, status, p.officer_id, note, env.clock())
    except ValueError:
        raise InterventionError("INVALID_INCIDENT_TRANSITION") from None
    _audit(env, p, "incident_status", {"incident_id": incident_id, "status": status, "case_id": inc.case_id, "note": note[:200]})
    return updated


# --- mandates ------------------------------------------------------------------------
def suspend_mandate(env: WakalaEnvironment, p: OfficerPrincipal, mandate_id: str, reason: str, incident_id: str | None = None) -> bool:
    _require(p, "mandates.suspend")
    m = _mandate_scope(env, p, mandate_id)
    changed = env.assurance.suspensions.suspend(mandate_id, reason, p.officer_id, env.clock(), incident_id)
    _audit(env, p, "mandate_suspend", {"mandate_id": mandate_id, "changed": changed, "case_id": m.case_id, "reason": reason[:200]},
           mandate_id)
    return changed


def reinstate_mandate(env: WakalaEnvironment, p: OfficerPrincipal, mandate_id: str, reason: str) -> bool:
    _require(p, "mandates.reinstate")
    m = _mandate_scope(env, p, mandate_id)
    if env.mandates.is_revoked(mandate_id):
        raise InterventionError("MANDATE_REVOKED_CANNOT_REINSTATE")  # revocation is irreversible
    changed = env.assurance.suspensions.lift(mandate_id, p.officer_id, env.clock())
    _audit(env, p, "mandate_reinstate", {"mandate_id": mandate_id, "changed": changed, "case_id": m.case_id, "reason": reason[:200]},
           mandate_id)
    return changed


def revoke_mandate_as_officer(env: WakalaEnvironment, p: OfficerPrincipal, mandate_id: str, reason: str) -> list[str]:
    _require(p, "mandates.revoke")
    m = _mandate_scope(env, p, mandate_id)
    from app.services.revocation import revoke_mandate
    revoked = revoke_mandate(env, mandate_id, reason, actor=p.officer_id)
    _audit(env, p, "mandate_revoke", {"mandate_id": mandate_id, "revoked_count": len(revoked), "case_id": m.case_id,
                                      "reason": reason[:200]}, mandate_id)
    return revoked


# --- cases ---------------------------------------------------------------------------------
def resume_case(env: WakalaEnvironment, p: OfficerPrincipal, case_id: str, note: str) -> RenewalCase:
    _require(p, "cases.resume")
    case = _case_scope(env, p, case_id)
    if case.state is not CaseState.PAUSED_FOR_REVIEW or case.paused_from is None:
        raise InterventionError("CASE_NOT_PAUSED")
    if case.authority_revoked:
        raise InterventionError("CASE_AUTHORITY_REVOKED")
    ev = _audit(env, p, "case_resume", {"case_id": case_id, "note": note[:200]})
    with env.db.transaction() as conn:
        before = CaseStore.load_in(conn, case_id)
        if before is None or before.state is not CaseState.PAUSED_FOR_REVIEW or before.paused_from is None:
            raise InterventionError("CASE_NOT_PAUSED")
        try:
            after = next_case(before, before.paused_from, actor=p.officer_id, at=env.clock(),
                              detail=f"Officer review complete: {note[:120] or 'resumed'}", audit_reference=ev.event_id)
        except InvalidTransition:
            raise InterventionError("INVALID_TRANSITION") from None
        CaseStore.save_in(conn, before, after)
    return after


def reassign_task(env: WakalaEnvironment, p: OfficerPrincipal, case_id: str, task: str, receiving_agent_id: str,
                  note: str) -> RenewalCase:
    """Reassign a delegable task for ONE case. Grants nothing by itself: the delegating agent must
    still commission the task through the gateway, and the new receiver gets a narrowed child mandate."""
    _require(p, "cases.reassign")
    case = _case_scope(env, p, case_id)
    spec = TASK_CATALOG.get(task)
    if spec is None or receiving_agent_id not in spec.receivers:
        raise InterventionError("RECEIVER_NOT_PERMITTED_FOR_TASK", 422)
    agent = env.repo.get_agent(receiving_agent_id)
    if agent is None or agent.status != "active" or agent.identity_key_reference.provisioning_status != "provisioned":
        raise InterventionError("RECEIVER_NOT_ACTIVE", 422)
    if case.state in (CaseState.COMPLETED, CaseState.FAILED) or case.authority_revoked:
        raise InterventionError("CASE_NOT_RECOVERABLE")
    ev = _audit(env, p, "task_reassign", {"case_id": case_id, "task": task, "receiving_agent_id": receiving_agent_id,
                                          "previous": case.task_assignments.get(task), "note": note[:200]})
    return _case_event(env, case_id, p, "task_reassigned",
                       f"{task} reassigned to {receiving_agent_id} by {p.officer_id}: {note[:120] or 'recovery'}", ev.event_id,
                       {"task_assignments": {**case.task_assignments, task: receiving_agent_id}})


# --- approvals ----------------------------------------------------------------------------------
def decide_approval(env: WakalaEnvironment, p: OfficerPrincipal, approval_id: str, approve: bool, note: str) -> dict[str, Any]:
    _require(p, "approvals.decide")
    found = env.approvals.get(approval_id)
    if found is None:
        raise InterventionError("APPROVAL_NOT_FOUND", 404)
    approval, _ = found
    if approval.case_id:
        _case_scope(env, p, approval.case_id)
    elif not p.can("all_entities"):
        raise AuthError("OUT_OF_ENTITY_SCOPE", 403)
    if not approve:
        updated = env.approvals.transition(approval_id, "pending", {"status": "rejected", "decided_by": p.officer_id,
                                                                    "decided_at": env.clock(), "decision_note": note[:500] or None})
        if updated is None:
            raise InterventionError("APPROVAL_NOT_PENDING")
        _audit(env, p, "approval_reject", {"approval_id": approval_id, "case_id": approval.case_id, "note": note[:200]},
               approval.mandate_id)
        return {"approval": updated.model_dump(mode="json"), "executed": False}
    _audit(env, p, "approval_approve", {"approval_id": approval_id, "case_id": approval.case_id, "note": note[:200]},
           approval.mandate_id)
    final, outcome = env.gateway.execute_approved(approval_id, p.officer_id, note)
    if outcome is None:
        raise InterventionError("APPROVAL_NOT_PENDING" if final.status != "expired" else "APPROVAL_EXPIRED")
    return {"approval": final.model_dump(mode="json"), "executed": outcome.executed,
            "decision": outcome.decision.model_dump(mode="json"), "execution_status": outcome.status, "result": outcome.result}
