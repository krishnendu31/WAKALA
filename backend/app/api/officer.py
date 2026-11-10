"""Officer console API — authenticated, server-side authorized.

The officer is identified ONLY by the bearer session token issued at login.
No endpoint accepts an officer ID for authorization; request bodies are strict
(unknown fields → 422), so adding ``officer_id`` to a body changes nothing.
Every state-changing action is delegated to ``app.services.interventions``,
which re-checks role permission and entity scope and writes an audit event.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from pydantic import Field

from app.api.routes import Env, ErrorResponse
from app.api.workflow import require_local_client
from app.core.delegation import TASK_CATALOG
from app.schemas import AuditEvent
from app.schemas.common import StrictModel
from app.services import interventions as iv
from app.services.officers import AuthError, OfficerPrincipal, officer_view

router = APIRouter(prefix="/api/officer", tags=["officer console"], dependencies=[Depends(require_local_client)],
                   responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})

MandatePath = Annotated[str, Path(pattern=r"^MND-[A-Z0-9-]{4,40}$")]
CasePath = Annotated[str, Path(pattern=r"^CASE-[A-Z0-9]{6,12}$")]
IncidentPath = Annotated[str, Path(pattern=r"^INC-[A-Z0-9]{6,16}$")]
ApprovalPath = Annotated[str, Path(pattern=r"^APR-[A-Z0-9]{6,16}$")]


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def current_officer(request: Request, authorization: Annotated[str | None, Header()] = None) -> OfficerPrincipal:
    env = request.app.state.env
    try:
        return env.officers.authenticate(_bearer(authorization))
    except AuthError as e:
        if authorization:  # a presented-but-invalid credential is audited; a missing header is just a 401
            iv.audit_session_rejection(env, e.code)
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": "Officer authentication required."}) from None


Officer = Annotated[OfficerPrincipal, Depends(current_officer)]


def need(p: OfficerPrincipal, permission: str) -> None:
    if not p.can(permission):
        raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": f"Requires {permission}."})


def _run(fn, *args: Any, **kw: Any) -> Any:  # type: ignore[no-untyped-def]
    try:
        return iv.guarded(fn, *args, **kw)  # refused attempts are audited
    except AuthError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": "Not permitted."}) from None
    except iv.InterventionError as e:
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": "Intervention refused."}) from None


class LoginBody(StrictModel):
    officer_id: str = Field(pattern=r"^OFF-\d{4}$")
    password: str = Field(min_length=1, max_length=200)


class NoteBody(StrictModel):
    note: str = Field(default="", max_length=500)


class ReasonBody(StrictModel):
    reason: str = Field(min_length=3, max_length=200)
    incident_id: str | None = Field(default=None, pattern=r"^INC-[A-Z0-9]{6,16}$")


class StatusBody(StrictModel):
    status: Literal["under_review", "contained", "resolved", "dismissed"]
    note: str = Field(default="", max_length=500)


class ReassignBody(StrictModel):
    task: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    receiving_agent_id: str = Field(pattern=r"^AGT-[A-Z]{3,8}-\d{3}$")
    note: str = Field(default="", max_length=500)


# --- session -------------------------------------------------------------------------------
@router.post("/session")
def login(body: LoginBody, env: Env) -> dict[str, Any]:
    try:
        token, principal = env.officers.login(body.officer_id, body.password)
    except AuthError as e:
        env.audit.append(AuditEvent(
            event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor="UNAUTHENTICATED",
            action="officer.login_failed", decision="informational",
            evidence_metadata={"claimed_officer_id": body.officer_id, "code": e.code, "origin": "officer_console"}))
        raise HTTPException(status_code=e.status, detail={"code": e.code, "message": "Sign-in failed."}) from None
    env.audit.append(AuditEvent(
        event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor=principal.officer_id,
        action="officer.login", decision="informational", evidence_metadata={"role": principal.officer.role, "origin": "officer_console"}))
    return {"token": token, "officer": officer_view(principal)}


@router.delete("/session")
def logout(env: Env, p: Officer, authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    token = _bearer(authorization)
    if token:
        env.officers.logout(token)
    return {"status": "signed_out", "officer_id": p.officer_id}


@router.get("/me")
def me(p: Officer) -> dict[str, Any]:
    return officer_view(p)


# --- overview -------------------------------------------------------------------------------
@router.get("/overview")
def overview(env: Env, p: Officer) -> dict[str, Any]:
    need(p, "incidents.read")
    env.approvals.expire_due(env.clock())
    incidents = env.assurance.incidents.list()
    cases = env.cases.list(200)
    counts = env.audit.decision_counts()
    by = lambda items, key: {k: sum(1 for i in items if getattr(i, key) == k) for k in sorted({getattr(i, key) for i in items})}  # noqa: E731
    return {
        "incidents": {"total": len(incidents), "by_status": by(incidents, "status"), "by_severity": by(incidents, "severity")},
        "approvals_pending": len(env.approvals.list("pending")),
        "suspended_mandates": len(env.assurance.suspensions.active_ids()),
        "revoked_mandates": len(env.mandates.revoked_ids()),
        "cases": {"total": len(cases), "by_state": {s: sum(1 for c in cases if c.state.value == s)
                                                    for s in sorted({c.state.value for c in cases})},
                  "under_review": sum(1 for c in cases if c.state.value == "PAUSED_FOR_REVIEW"),
                  "recovered": sum(1 for c in cases if c.recovery_status == "recovered"),
                  "authority_revoked": sum(1 for c in cases if c.authority_revoked)},
        "decisions": {"allowed": counts.get("allowed", 0), "denied": counts.get("denied", 0), "escalated": counts.get("escalated", 0)},
        "audit_chain_valid": env.audit.verify().valid,
        "detection": "deterministic rules over audited gateway events (not machine learning)",
    }


# --- incidents ------------------------------------------------------------------------------------
@router.get("/incidents")
def list_incidents(env: Env, p: Officer) -> list[dict[str, Any]]:
    need(p, "incidents.read")
    return [i.model_dump(mode="json") for i in env.assurance.incidents.list()]


@router.get("/incidents/{incident_id}")
def investigate(incident_id: IncidentPath, env: Env, p: Officer) -> dict[str, Any]:
    need(p, "evidence.read")
    inc = env.assurance.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail={"code": "INCIDENT_NOT_FOUND", "message": "No such incident."})
    evidence = []
    for eid in inc.evidence_event_ids[-30:]:
        rows = env.db.query("SELECT payload FROM audit_events WHERE event_id = ?", (eid,))
        if rows:
            evidence.append(AuditEvent.model_validate_json(rows[0]["payload"]).model_dump(mode="json"))
    out: dict[str, Any] = {"incident": inc.model_dump(mode="json"), "evidence": evidence,
                           "violated_rules": sorted({c for e in evidence for c in e["reason_codes"]})}
    if inc.case_id:
        case = env.cases.get(inc.case_id)
        if case is not None:
            from app.workflow.authority_graph import build_authority_graph
            citizen = env.repo.get_citizen(case.citizen_ref)
            required = ["residency_eligibility", "insurance_verified", "fee_paid"]
            out.update({
                "case": case.model_dump(mode="json"),
                "citizen_request": {"citizen_ref": case.citizen_ref, "citizen_name": citizen.full_name if citizen else None,
                                    "service": case.service_id, "purpose": case.authorized_purpose, "request_id": case.request_id,
                                    "opened_at": case.created_at.isoformat()},
                "completed_actions": [h.model_dump(mode="json") for h in case.history
                                      if h.kind in ("operation_executed", "prerequisite_completed", "delegation_issued")],
                "incomplete_requirements": [r for r in required if r not in case.completed_prerequisites],
                "authority_graph": build_authority_graph(env, case.case_id),
                "approvals": [a.model_dump(mode="json") for a in env.approvals.list() if a.case_id == case.case_id],
                "reassignable_tasks": {t: alt for t, spec in TASK_CATALOG.items()
                                       if (alt := sorted(spec.receivers - spec.receivers_for(case.task_assignments)))},
            })
    return out


@router.post("/incidents/{incident_id}/status")
def incident_status(incident_id: IncidentPath, body: StatusBody, env: Env, p: Officer) -> dict[str, Any]:
    return _run(iv.set_incident_status, env, p, incident_id, body.status, body.note).model_dump(mode="json")


# --- mandates -------------------------------------------------------------------------------------------
@router.post("/mandates/{mandate_id}/suspend")
def suspend(mandate_id: MandatePath, body: ReasonBody, env: Env, p: Officer) -> dict[str, Any]:
    return {"suspended": _run(iv.suspend_mandate, env, p, mandate_id, body.reason, body.incident_id)}


@router.post("/mandates/{mandate_id}/reinstate")
def reinstate(mandate_id: MandatePath, body: ReasonBody, env: Env, p: Officer) -> dict[str, Any]:
    return {"reinstated": _run(iv.reinstate_mandate, env, p, mandate_id, body.reason)}


@router.post("/mandates/{mandate_id}/revoke")
def revoke(mandate_id: MandatePath, body: ReasonBody, env: Env, p: Officer) -> dict[str, Any]:
    return {"revoked": _run(iv.revoke_mandate_as_officer, env, p, mandate_id, body.reason)}


# --- cases ------------------------------------------------------------------------------------------------
@router.get("/cases")
def cases(env: Env, p: Officer) -> list[dict[str, Any]]:
    need(p, "cases.read")
    out = []
    for c in env.cases.list(100):
        inc = env.assurance.incidents.case_has_active(c.case_id)
        out.append({"case_id": c.case_id, "citizen_ref": c.citizen_ref, "state": c.state.value, "service_owner": c.service_owner,
                    "incident_policy": c.incident_policy, "authority_model": c.authority_model,
                    "recovery_status": c.recovery_status, "authority_revoked": c.authority_revoked,
                    "task_assignments": c.task_assignments, "completed_prerequisites": c.completed_prerequisites,
                    "active_incident": inc.incident_id if inc else None})
    return out


@router.post("/cases/{case_id}/resume")
def resume(case_id: CasePath, body: NoteBody, env: Env, p: Officer) -> dict[str, Any]:
    return _run(iv.resume_case, env, p, case_id, body.note).model_dump(mode="json")


@router.post("/cases/{case_id}/reassign")
def reassign(case_id: CasePath, body: ReassignBody, env: Env, p: Officer) -> dict[str, Any]:
    return _run(iv.reassign_task, env, p, case_id, body.task, body.receiving_agent_id, body.note).model_dump(mode="json")


# --- approvals -----------------------------------------------------------------------------------------------
@router.get("/approvals")
def approvals(env: Env, p: Officer) -> list[dict[str, Any]]:
    need(p, "approvals.read")
    env.approvals.expire_due(env.clock())
    return [a.model_dump(mode="json") for a in env.approvals.list()]


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: ApprovalPath, body: NoteBody, env: Env, p: Officer) -> dict[str, Any]:
    from app.core.audit import AuditUnavailableError
    try:
        return _run(iv.decide_approval, env, p, approval_id, True, body.note)
    except AuditUnavailableError as exc:
        from app.api.gateway import audit_failure
        raise audit_failure(exc) from None


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: ApprovalPath, body: NoteBody, env: Env, p: Officer) -> dict[str, Any]:
    return _run(iv.decide_approval, env, p, approval_id, False, body.note)


@router.get("/audit")
def officer_audit(env: Env, p: Officer) -> list[dict[str, Any]]:
    need(p, "evidence.read")
    rows = env.db.query("SELECT payload FROM audit_events WHERE json_extract(payload, '$.actor') LIKE 'OFF-%' "
                        "OR json_extract(payload, '$.action') LIKE 'assurance.%' ORDER BY seq DESC LIMIT 200")
    return [AuditEvent.model_validate_json(r["payload"]).model_dump(mode="json") for r in rows]
