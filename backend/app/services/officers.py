"""DEVELOPMENT-ONLY officer authentication and server-side authorization.

* Credentials: one random password per synthetic officer, generated at first
  start into the git-ignored dev keystore directory
  (``officer_credentials.json``). Only a salted scrypt hash is stored in the
  database; nothing is shipped in the frontend.
* Sessions: an opaque random bearer token (256-bit). Only its SHA-256 is
  stored. Idle timeout 15 min, absolute lifetime 60 min, explicit logout.
* Lockout: 5 failed logins within 10 minutes block that officer ID for 10 minutes.
* Authorization: every officer endpoint derives the officer from the session —
  never from request data — and checks role permissions plus entity scope.

Production replacement: the government identity provider (e.g. SSO with MFA)
and short-lived signed officer assertions; see docs/SECURITY_MODEL.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.models.database import Database
from app.schemas.assurance import Officer

IDLE_TIMEOUT = timedelta(minutes=15)
ABSOLUTE_LIFETIME = timedelta(minutes=60)
LOCKOUT_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=10)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "auditor": frozenset({"incidents.read", "cases.read", "approvals.read", "evidence.read"}),
    "case_officer": frozenset({"incidents.read", "cases.read", "approvals.read", "evidence.read", "incidents.update",
                               "approvals.decide", "mandates.suspend", "mandates.reinstate", "cases.resume", "cases.reassign"}),
    "security_supervisor": frozenset({"incidents.read", "cases.read", "approvals.read", "evidence.read", "incidents.update",
                                      "approvals.decide", "mandates.suspend", "mandates.reinstate", "mandates.revoke",
                                      "cases.resume", "cases.reassign", "cases.revoke_authority", "agents.suspend",
                                      "agents.revoke", "incidents.close", "all_entities"}),
}


class AuthError(Exception):
    def __init__(self, code: str, status: int = 401) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class OfficerPrincipal:
    officer: Officer
    session_expires_at: datetime

    @property
    def officer_id(self) -> str:
        return self.officer.officer_id

    def can(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.officer.role, frozenset())

    def can_act_on_entity(self, entity: str) -> bool:
        return self.can("all_entities") or self.officer.entity == entity


def _hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


class DevOfficerCredentials:
    """Generates and stores development passwords in the git-ignored keystore dir."""

    def __init__(self, directory: str | Path) -> None:
        self._path = Path(directory) / "officer_credentials.json"

    def password(self, officer_id: str) -> str:
        data: dict[str, str] = {}
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
        if officer_id not in data:
            data[officer_id] = secrets.token_urlsafe(12)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, self._path)
        return data[officer_id]


class OfficerAuth:
    def __init__(self, db: Database, clock: Callable[[], datetime], password_source: Callable[[str], str] | None) -> None:
        self._db = db
        self._clock = clock
        self._passwords = password_source

    # --- directory ------------------------------------------------------------
    def officers(self) -> list[Officer]:
        return [Officer.model_validate_json(r["payload"]) for r in self._db.query("SELECT payload FROM officers ORDER BY officer_id")]

    def officer(self, officer_id: str) -> Officer | None:
        rows = self._db.query("SELECT payload FROM officers WHERE officer_id = ?", (officer_id,))
        return Officer.model_validate_json(rows[0]["payload"]) if rows else None

    def provision(self) -> None:
        """Store salted hashes for every officer (passwords come from the dev credential source)."""
        if self._passwords is None:
            return
        for off in self.officers():
            pw = self._passwords(off.officer_id)
            existing = self._db.query("SELECT salt, password_hash FROM officer_credentials WHERE officer_id = ?", (off.officer_id,))
            if existing and hmac.compare_digest(_hash(pw, bytes.fromhex(existing[0]["salt"])), existing[0]["password_hash"]):
                continue
            salt = secrets.token_bytes(16)
            with self._db.transaction() as conn:
                conn.execute("INSERT INTO officer_credentials (officer_id, salt, password_hash, updated_at) VALUES (?, ?, ?, ?) "
                             "ON CONFLICT(officer_id) DO UPDATE SET salt=excluded.salt, password_hash=excluded.password_hash, "
                             "updated_at=excluded.updated_at",
                             (off.officer_id, salt.hex(), _hash(pw, salt), self._clock().isoformat()))

    # --- login / sessions ----------------------------------------------------------
    def login(self, officer_id: str, password: str) -> tuple[str, OfficerPrincipal]:
        now = self._clock()
        ts = now.timestamp()
        recent = self._db.query("SELECT COUNT(*) AS n FROM officer_login_failures WHERE officer_id = ? AND at >= ?",
                                (officer_id, ts - LOCKOUT_WINDOW.total_seconds()))[0]["n"]
        if recent >= LOCKOUT_FAILURES:
            raise AuthError("LOGIN_LOCKED", 429)
        off = self.officer(officer_id)
        row = self._db.query("SELECT salt, password_hash FROM officer_credentials WHERE officer_id = ?", (officer_id,))
        # Always compute a hash so unknown IDs and wrong passwords take similar time.
        salt = bytes.fromhex(row[0]["salt"]) if row else b"\x00" * 16
        ok = bool(row) and hmac.compare_digest(_hash(password, salt), row[0]["password_hash"])
        if not ok or off is None or off.status != "active":
            with self._db.transaction() as conn:
                conn.execute("INSERT INTO officer_login_failures (officer_id, at) VALUES (?, ?)", (officer_id[:20], ts))
            raise AuthError("INVALID_CREDENTIALS")
        token = secrets.token_urlsafe(32)
        expires = ts + ABSOLUTE_LIFETIME.total_seconds()
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM officer_login_failures WHERE officer_id = ?", (officer_id,))
            conn.execute("INSERT INTO officer_sessions (token_hash, officer_id, created_at, last_seen, expires_at) VALUES (?, ?, ?, ?, ?)",
                         (hashlib.sha256(token.encode()).hexdigest(), officer_id, ts, ts, expires))
        return token, OfficerPrincipal(off, datetime.fromtimestamp(expires, tz=now.tzinfo))

    def authenticate(self, token: str | None) -> OfficerPrincipal:
        if not token:
            raise AuthError("NOT_AUTHENTICATED")
        now = self._clock()
        ts = now.timestamp()
        th = hashlib.sha256(token.encode()).hexdigest()
        rows = self._db.query("SELECT * FROM officer_sessions WHERE token_hash = ?", (th,))
        if not rows or rows[0]["revoked"]:
            raise AuthError("SESSION_INVALID")
        s = rows[0]
        if ts >= s["expires_at"] or ts - s["last_seen"] > IDLE_TIMEOUT.total_seconds():
            with self._db.transaction() as conn:
                conn.execute("UPDATE officer_sessions SET revoked = 1 WHERE token_hash = ?", (th,))
            raise AuthError("SESSION_EXPIRED")
        off = self.officer(s["officer_id"])
        if off is None or off.status != "active":
            raise AuthError("SESSION_INVALID")
        with self._db.transaction() as conn:
            conn.execute("UPDATE officer_sessions SET last_seen = ? WHERE token_hash = ?", (ts, th))
        return OfficerPrincipal(off, datetime.fromtimestamp(s["expires_at"], tz=now.tzinfo))

    def logout(self, token: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE officer_sessions SET revoked = 1 WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))


def officer_view(p: OfficerPrincipal) -> dict[str, Any]:
    o = p.officer
    return {"officer_id": o.officer_id, "name": o.name, "title": o.title, "entity": o.entity, "role": o.role,
            "permissions": sorted(ROLE_PERMISSIONS[o.role] - {"all_entities"}), "all_entities": p.can("all_entities"),
            "session_expires_at": p.session_expires_at.isoformat()}
