"""Officer recovery actions (DEVELOPMENT CLI only — no HTTP endpoint).

There is no officer authentication in the prototype, so these actions are
exposed only through the local CLI. An authenticated officer console is Phase 3.
"""

from __future__ import annotations

import secrets

from app.schemas import AuditEvent
from app.schemas.case import CaseState, RenewalCase
from app.services.bootstrap import WakalaEnvironment
from app.services.cases import CaseStore, InvalidTransition, next_case


def resume_case(env: WakalaEnvironment, case_id: str, *, officer_id: str) -> RenewalCase:
    now = env.clock()
    current = env.cases.get(case_id)
    if current is None:
        raise KeyError(case_id)
    if current.state is not CaseState.PAUSED_FOR_REVIEW or current.paused_from is None:
        raise InvalidTransition("only a paused case can be resumed")
    next_case(current, current.paused_from, actor=officer_id, at=now, detail="validate")  # raises if impossible
    event = env.audit.append(AuditEvent(
        event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=now, actor=officer_id, action="case.resume",
        decision="informational", evidence_metadata={"case_id": case_id, "origin": "officer_cli"},
    ))
    with env.db.transaction() as conn:
        before = CaseStore.load_in(conn, case_id)
        if before is None:
            raise KeyError(case_id)
        after = next_case(before, before.paused_from or CaseState.FAILED, actor=officer_id, at=now,
                          detail="Officer review complete; case resumed", audit_reference=event.event_id)
        CaseStore.save_in(conn, before, after)
    return after
