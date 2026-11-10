"""Renewal case store and state machine.

    CREATED → VERIFYING → AWAITING_PAYMENT → READY_TO_COMPLETE → COMPLETED
    any non-terminal state → PAUSED_FOR_REVIEW → (back to the paused state)
    any non-terminal state → FAILED

Transitions are validated by ``next_case`` (pure). Prerequisite guards make it
impossible to reach AWAITING_PAYMENT without both verifications, or
READY_TO_COMPLETE / COMPLETED without the fee. Writes use optimistic
concurrency on ``version`` so two concurrent operations cannot both apply.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from app.models.database import Database
from app.schemas.case import CaseEvent, CaseState, Prerequisite, RenewalCase

S = CaseState
TERMINAL = frozenset({S.COMPLETED, S.FAILED})

ALLOWED_TRANSITIONS: dict[CaseState, frozenset[CaseState]] = {
    S.CREATED: frozenset({S.VERIFYING, S.PAUSED_FOR_REVIEW, S.FAILED}),
    S.VERIFYING: frozenset({S.AWAITING_PAYMENT, S.PAUSED_FOR_REVIEW, S.FAILED}),
    S.AWAITING_PAYMENT: frozenset({S.READY_TO_COMPLETE, S.PAUSED_FOR_REVIEW, S.FAILED}),
    S.READY_TO_COMPLETE: frozenset({S.COMPLETED, S.PAUSED_FOR_REVIEW, S.FAILED}),
    S.PAUSED_FOR_REVIEW: frozenset({S.CREATED, S.VERIFYING, S.AWAITING_PAYMENT, S.READY_TO_COMPLETE, S.FAILED}),
    S.COMPLETED: frozenset(),
    S.FAILED: frozenset(),
}

REQUIRED_PREREQUISITES: dict[CaseState, frozenset[str]] = {
    S.AWAITING_PAYMENT: frozenset({"residency_eligibility", "insurance_verified"}),
    S.READY_TO_COMPLETE: frozenset({"residency_eligibility", "insurance_verified", "fee_paid"}),
    S.COMPLETED: frozenset({"residency_eligibility", "insurance_verified", "fee_paid"}),
}


class InvalidTransition(ValueError):
    pass


class CaseConflict(RuntimeError):
    """The case changed concurrently; the caller must not assume its write applied."""


def next_case(case: RenewalCase, to: CaseState, *, actor: str, at: datetime, detail: str,
              audit_reference: str | None = None) -> RenewalCase:
    """Return the case moved to ``to``, or raise InvalidTransition."""
    if to not in ALLOWED_TRANSITIONS[case.state]:
        raise InvalidTransition(f"{case.state.value} → {to.value} is not a permitted transition")
    if case.state is S.PAUSED_FOR_REVIEW and to is not S.FAILED and to is not case.paused_from:
        raise InvalidTransition("a paused case can only resume to the state it was paused from")
    missing = REQUIRED_PREREQUISITES.get(to, frozenset()) - set(case.completed_prerequisites)
    if missing:
        raise InvalidTransition(f"prerequisites not met for {to.value}: {sorted(missing)}")
    if to is S.PAUSED_FOR_REVIEW:
        kind, paused_from, recovery = "paused_for_review", case.state, "paused_for_review"
    elif case.state is S.PAUSED_FOR_REVIEW:
        kind, paused_from, recovery = ("state_transition" if to is S.FAILED else "resumed"), None, (
            case.recovery_status if to is S.FAILED else "recovered")
    else:
        kind, paused_from, recovery = "state_transition", case.paused_from, case.recovery_status
    if to is S.FAILED and recovery == "none":
        recovery = "manual_review_required"
    event = CaseEvent(at=at, actor=actor, kind=kind, detail=detail, audit_reference=audit_reference,  # type: ignore[arg-type]
                      from_state=case.state, to_state=to)
    return case.model_copy(update={
        "state": to, "paused_from": paused_from, "recovery_status": recovery,
        "version": case.version + 1, "history": [*case.history, event],
    })


def with_prerequisite(case: RenewalCase, prerequisite: Prerequisite, *, actor: str, at: datetime,
                      detail: str, audit_reference: str | None) -> RenewalCase:
    if prerequisite in case.completed_prerequisites:
        return case
    event = CaseEvent(at=at, actor=actor, kind="prerequisite_completed", detail=detail, audit_reference=audit_reference)
    return case.model_copy(update={
        "completed_prerequisites": [*case.completed_prerequisites, prerequisite],
        "version": case.version + 1, "history": [*case.history, event],
    })


def with_event(case: RenewalCase, event: CaseEvent) -> RenewalCase:
    return case.model_copy(update={"version": case.version + 1, "history": [*case.history, event]})


class CaseStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, case: RenewalCase) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO renewal_cases (case_id, citizen_ref, state, version, created_at, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (case.case_id, case.citizen_ref, case.state.value, case.version, case.created_at.isoformat(), case.model_dump_json()),
            )

    def get(self, case_id: str) -> RenewalCase | None:
        rows = self._db.query("SELECT payload FROM renewal_cases WHERE case_id = ?", (case_id,))
        return RenewalCase.model_validate_json(rows[0]["payload"]) if rows else None

    def list(self, limit: int = 50) -> list[RenewalCase]:
        rows = self._db.query("SELECT payload FROM renewal_cases ORDER BY created_at DESC, case_id LIMIT ?", (limit,))
        return [RenewalCase.model_validate_json(r["payload"]) for r in rows]

    @staticmethod
    def save_in(conn: sqlite3.Connection, before: RenewalCase, after: RenewalCase) -> None:
        """Compare-and-swap inside an existing transaction."""
        RenewalCase.model_validate(after.model_dump())  # never persist an invalid case
        cur = conn.execute(
            "UPDATE renewal_cases SET state = ?, version = ?, payload = ? WHERE case_id = ? AND version = ?",
            (after.state.value, after.version, after.model_dump_json(), before.case_id, before.version),
        )
        if cur.rowcount != 1:
            raise CaseConflict(f"case {before.case_id} changed concurrently")

    @staticmethod
    def load_in(conn: sqlite3.Connection, case_id: str) -> RenewalCase | None:
        row = conn.execute("SELECT payload FROM renewal_cases WHERE case_id = ?", (case_id,)).fetchone()
        return RenewalCase.model_validate_json(row["payload"]) if row else None

    def save(self, before: RenewalCase, after: RenewalCase) -> None:
        with self._db.transaction() as conn:
            self.save_in(conn, before, after)
