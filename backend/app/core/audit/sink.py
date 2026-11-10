"""Append-only SQLite audit sink with hash chaining."""

from __future__ import annotations

from app.models.database import Database
from app.schemas import AuditEvent

from .chain import GENESIS_HASH, IntegrityReport, compute_event_hash, verify_chain


class AuditUnavailableError(RuntimeError):
    """Raised when an event cannot be recorded. Callers must fail closed."""


class SqliteAuditSink:
    def __init__(self, db: Database) -> None:
        self._db = db

    def append(self, draft: AuditEvent) -> AuditEvent:
        """Assign sequence + chain hashes atomically and persist. Never updates rows."""
        try:
            with self._db.transaction() as conn:
                row = conn.execute("SELECT seq, event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
                seq = 1 if row is None else int(row["seq"]) + 1
                prev = GENESIS_HASH if row is None else str(row["event_hash"])
                event = draft.model_copy(update={"sequence": seq, "previous_event_hash": prev, "event_hash": None})
                event = AuditEvent.model_validate(event.model_dump())  # re-validate the completed event
                final = event.model_copy(update={"event_hash": compute_event_hash(event)})
                conn.execute(
                    "INSERT INTO audit_events (seq, event_id, timestamp, event_hash, payload) VALUES (?, ?, ?, ?, ?)",
                    (seq, final.event_id, final.timestamp.isoformat(), final.event_hash, final.model_dump_json()),
                )
            return final
        except Exception as exc:  # any storage failure must stop the action
            raise AuditUnavailableError("audit event could not be recorded") from exc

    def count(self) -> int:
        return int(self._db.query("SELECT COUNT(*) AS n FROM audit_events")[0]["n"])

    def decision_counts(self) -> dict[str, int]:
        rows = self._db.query(
            "SELECT json_extract(payload, '$.decision') AS d, COUNT(*) AS n FROM audit_events GROUP BY d"
        )
        return {str(r["d"]): int(r["n"]) for r in rows}

    def list(self, limit: int = 100) -> list[AuditEvent]:
        rows = self._db.query("SELECT payload FROM audit_events ORDER BY seq DESC LIMIT ?", (limit,))
        return [AuditEvent.model_validate_json(r["payload"]) for r in rows]

    def verify(self) -> IntegrityReport:
        rows = self._db.query("SELECT seq, event_hash, payload FROM audit_events ORDER BY seq ASC")
        return verify_chain([(int(r["seq"]), str(r["event_hash"]), str(r["payload"])) for r in rows])
