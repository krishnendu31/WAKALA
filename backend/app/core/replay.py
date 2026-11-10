"""Replay protection: each (agent_id, nonce) is accepted at most once.

Nonces are retained for twice the freshness window. A request older than the
window is already rejected as stale, so a nonce can never be replayed after
its record expires.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from app.models.database import Database


class ReplayGuard:
    def __init__(self, db: Database, retention: timedelta) -> None:
        self._db = db
        self._retention = retention

    def check_and_record(self, agent_id: str, nonce: str, now: datetime) -> bool:
        """Record the nonce. Returns True if it had already been seen (a replay)."""
        ts = now.timestamp()
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM request_nonces WHERE expires_at < ?", (ts,))
            try:
                conn.execute(
                    "INSERT INTO request_nonces (agent_id, nonce, seen_at, expires_at) VALUES (?, ?, ?, ?)",
                    (agent_id, nonce, ts, ts + self._retention.total_seconds()),
                )
            except sqlite3.IntegrityError:
                return True
        return False
