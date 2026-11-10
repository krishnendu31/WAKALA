"""Server-side mandate store with revocation state.

Agents reference mandates by ID; they never submit mandate bodies. The
gateway still verifies every stored mandate's signature on every use, so a
modified row in this table is rejected, not trusted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from app.models.database import Database
from app.schemas import DigitalMandate

logger = logging.getLogger("wakala.mandates")


class MandateMalformedError(ValueError):
    """The stored payload is not a structurally valid mandate."""


@dataclass(frozen=True)
class StoredMandate:
    mandate: DigitalMandate
    revoked: bool
    revoked_at: str | None
    revocation_reason: str | None


class MandateStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def put(self, mandate: DigitalMandate) -> None:
        with self._db.transaction() as conn:
            self.put_in(conn, mandate)

    @staticmethod
    def put_in(conn, mandate: DigitalMandate) -> None:  # type: ignore[no-untyped-def]
        conn.execute(
            "INSERT INTO mandates (mandate_id, agent_id, issued_at, payload) VALUES (?, ?, ?, ?)",
            (mandate.mandate_id, mandate.agent_id, mandate.issued_at.isoformat(), mandate.model_dump_json()),
        )

    @staticmethod
    def get_in(conn, mandate_id: str) -> tuple[DigitalMandate, bool] | None:  # type: ignore[no-untyped-def]
        row = conn.execute("SELECT payload, revoked FROM mandates WHERE mandate_id = ?", (mandate_id,)).fetchone()
        if row is None:
            return None
        return DigitalMandate.model_validate_json(row["payload"]), bool(row["revoked"])

    def descendants(self, mandate_id: str) -> list[str]:
        """All mandates delegated (transitively) from ``mandate_id``, via trusted delegation records."""
        out: list[str] = []
        frontier = [mandate_id]
        while frontier and len(out) < 1000:
            marks = ",".join("?" for _ in frontier)
            rows = self._db.query(f"SELECT child_mandate_id FROM delegations WHERE parent_mandate_id IN ({marks})", tuple(frontier))
            frontier = [r["child_mandate_id"] for r in rows if r["child_mandate_id"] not in out]
            out += frontier
        return out

    def delegations(self, case_id: str | None = None) -> list[dict[str, object]]:
        sql, args = "SELECT * FROM delegations", ()
        if case_id:
            sql, args = sql + " WHERE case_id = ?", (case_id,)
        return [{k: r[k] for k in r.keys()} for r in self._db.query(sql + " ORDER BY issued_at", args)]

    def is_revoked(self, mandate_id: str) -> bool:
        rows = self._db.query("SELECT revoked FROM mandates WHERE mandate_id = ?", (mandate_id,))
        return bool(rows and rows[0]["revoked"])

    def get(self, mandate_id: str) -> DigitalMandate | None:
        """Raises MandateMalformedError if the stored row does not parse."""
        rows = self._db.query("SELECT payload FROM mandates WHERE mandate_id = ?", (mandate_id,))
        if not rows:
            return None
        try:
            return DigitalMandate.model_validate_json(rows[0]["payload"])
        except ValidationError as exc:
            logger.warning("stored mandate %s is malformed", mandate_id)
            raise MandateMalformedError(mandate_id) from exc

    def list(self, agent_id: str | None = None) -> list[StoredMandate]:
        sql = "SELECT payload, revoked, revoked_at, revocation_reason FROM mandates"
        params: tuple = ()
        if agent_id:
            sql += " WHERE agent_id = ?"
            params = (agent_id,)
        out = []
        for r in self._db.query(sql + " ORDER BY issued_at DESC, mandate_id", params):
            try:
                m = DigitalMandate.model_validate_json(r["payload"])
            except ValidationError:
                continue
            out.append(StoredMandate(m, bool(r["revoked"]), r["revoked_at"], r["revocation_reason"]))
        return out

    def revoke(self, mandate_id: str, reason: str, now: datetime) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE mandates SET revoked = 1, revoked_at = ?, revocation_reason = ? WHERE mandate_id = ? AND revoked = 0",
                (now.isoformat(), reason[:200], mandate_id),
            )
            return cur.rowcount == 1

    def revoked_ids(self) -> frozenset[str]:
        return frozenset(r["mandate_id"] for r in self._db.query("SELECT mandate_id FROM mandates WHERE revoked = 1"))

    def _raw_update_payload_for_tests(self, mandate_id: str, payload: str) -> None:
        """Simulates storage tampering. Used only by tests and the CLI demo."""
        with self._db.transaction() as conn:
            conn.execute("UPDATE mandates SET payload = ? WHERE mandate_id = ?", (payload, mandate_id))
