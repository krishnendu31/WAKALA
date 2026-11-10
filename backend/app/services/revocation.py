"""Persistent, selective revocation.

* ``revoke_mandate``        one mandate and (by default) every mandate delegated from it
* ``revoke_case_authority`` every mandate rooted in one case, plus the case flag
* ``revoke_agent``          agent-wide (registry status), only by explicit decision

All state lives in SQLite and survives restart. Dependent mandates are
revoked explicitly (cascade) AND are rejected at use-time anyway, because the
chain verifier checks every ancestor. Nothing here is triggered automatically
by a routine denied request.
"""

from __future__ import annotations

import secrets

from app.schemas import AuditEvent
from app.schemas.case import CaseEvent
from app.services.bootstrap import WakalaEnvironment
from app.services.cases import CaseStore, with_event


def _audit(env: WakalaEnvironment, actor: str, action: str, evidence: dict) -> AuditEvent:  # type: ignore[type-arg]
    return env.audit.append(AuditEvent(
        event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor=actor, action=action,
        decision="informational", evidence_metadata={**evidence, "origin": "revocation"},
    ))


def revoke_mandate(env: WakalaEnvironment, mandate_id: str, reason: str, *, actor: str = "OFF-0101",
                   cascade: bool = True) -> list[str]:
    if env.mandates.get(mandate_id) is None:
        raise KeyError(mandate_id)
    now = env.clock()
    targets = [mandate_id, *(env.mandates.descendants(mandate_id) if cascade else [])]
    revoked = [m for m in targets if env.mandates.revoke(m, reason if m == mandate_id else f"parent {mandate_id} revoked: {reason}", now)]
    _audit(env, actor, "mandate.revoke", {"mandate_id": mandate_id, "cascade": cascade,
                                          "revoked_count": len(revoked), "revoked": ",".join(revoked)[:1500],
                                          "reason": reason[:200]})
    return revoked


def revoke_case_authority(env: WakalaEnvironment, case_id: str, reason: str, *, actor: str = "OFF-0101") -> list[str]:
    case = env.cases.get(case_id)
    if case is None:
        raise KeyError(case_id)
    now = env.clock()
    revoked: list[str] = []
    for root in case.mandate_refs.values():
        for m in [root, *env.mandates.descendants(root)]:
            if env.mandates.revoke(m, f"case {case_id} authority revoked: {reason}", now):
                revoked.append(m)
    event = _audit(env, actor, "case.revoke_authority", {"case_id": case_id, "revoked_count": len(revoked),
                                                          "revoked": ",".join(revoked)[:1500], "reason": reason[:200]})
    with env.db.transaction() as conn:
        before = CaseStore.load_in(conn, case_id)
        if before is not None and not before.authority_revoked:
            after = with_event(before, CaseEvent(at=now, actor=actor, kind="authority_revoked", audit_reference=event.event_id,
                                                 detail=f"Case authority revoked: {reason}"))
            CaseStore.save_in(conn, before, after.model_copy(update={"authority_revoked": True}))
    return revoked


def revoke_agent(env: WakalaEnvironment, agent_id: str, reason: str, *, actor: str = "OFF-0101") -> None:
    env.repo.set_agent_status(agent_id, "revoked", reason)
    _audit(env, actor, "agent.revoke", {"agent_id": agent_id, "reason": reason[:200]})
