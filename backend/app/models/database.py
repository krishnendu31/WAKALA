"""SQLite storage for synthetic prototype records.

Records are stored as validated JSON payloads keyed by their identifier.
PRIMARY KEY constraints give a second, storage-level guarantee against
duplicate identifiers (the seeder checks first and fails with a clear error).

Phase 1 tables:
* ``public_keys``    — registered Ed25519 *public* keys for agents and issuers
* ``issuers``        — trusted mandate issuers and their authority
* ``mandates``       — signed mandates plus server-side revocation state
* ``request_nonces`` — replay protection
* ``audit_events``   — append-only, hash-chained decision log

Private keys are never stored in the database.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id    TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citizens (
    citizen_ref TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS services (
    service_id  TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS issuers (
    issuer_id   TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public_keys (
    key_id      TEXT PRIMARY KEY,
    owner_type  TEXT NOT NULL CHECK (owner_type IN ('agent', 'issuer')),
    owner_id    TEXT NOT NULL,
    public_key  TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    registered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mandates (
    mandate_id  TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    issued_at   TEXT NOT NULL,
    payload     TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0,
    revoked_at  TEXT,
    revocation_reason TEXT
);
CREATE TABLE IF NOT EXISTS request_nonces (
    agent_id    TEXT NOT NULL,
    nonce       TEXT NOT NULL,
    seen_at     REAL NOT NULL,
    expires_at  REAL NOT NULL,
    PRIMARY KEY (agent_id, nonce)
);
CREATE TABLE IF NOT EXISTS renewal_cases (
    case_id     TEXT PRIMARY KEY,
    citizen_ref TEXT NOT NULL,
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS residency_renewals (
    case_id     TEXT PRIMARY KEY,
    citizen_ref TEXT NOT NULL,
    previous_expiry TEXT NOT NULL,
    renewed_expiry  TEXT NOT NULL,
    completed_at    TEXT NOT NULL,
    decision_id     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_ledger (
    transaction_id  TEXT PRIMARY KEY,
    case_id         TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    citizen_ref     TEXT NOT NULL,
    amount          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    recipient       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    decision_id     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS delegations (
    child_mandate_id  TEXT PRIMARY KEY,
    parent_mandate_id TEXT NOT NULL,
    root_mandate_id   TEXT NOT NULL,
    case_id           TEXT NOT NULL,
    from_agent        TEXT NOT NULL,
    to_agent          TEXT NOT NULL,
    task              TEXT NOT NULL,
    depth             INTEGER NOT NULL,
    issued_at         TEXT NOT NULL,
    expires_at        TEXT NOT NULL,
    decision_id       TEXT NOT NULL,
    decision_event    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS delegations_parent ON delegations(parent_mandate_id);
CREATE INDEX IF NOT EXISTS delegations_case ON delegations(case_id);
CREATE TABLE IF NOT EXISTS agent_status_overrides (
    agent_id    TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    reason      TEXT NOT NULL,
    changed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS standby_agents (
    agent_id    TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mandate_suspensions (
    mandate_id   TEXT PRIMARY KEY,
    active       INTEGER NOT NULL,
    suspended_at TEXT NOT NULL,
    reason       TEXT NOT NULL,
    incident_id  TEXT,
    actor        TEXT NOT NULL,
    lifted_at    TEXT,
    lifted_by    TEXT
);
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    dedupe_key  TEXT NOT NULL,
    status      TEXT NOT NULL,
    severity    TEXT NOT NULL,
    case_id     TEXT,
    last_seen   TEXT NOT NULL,
    version     INTEGER NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS incidents_dedupe ON incidents(dedupe_key, status);
CREATE TABLE IF NOT EXISTS pending_approvals (
    approval_id TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    case_id     TEXT,
    payload     TEXT NOT NULL,
    signed_request TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS officers (
    officer_id  TEXT PRIMARY KEY,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS officer_credentials (
    officer_id  TEXT PRIMARY KEY,
    salt        TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portal_runs (run_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS portal_runs_case ON portal_runs(case_id);
CREATE TABLE IF NOT EXISTS portal_documents (case_id TEXT NOT NULL, document_id TEXT NOT NULL, attached_at TEXT NOT NULL,
                                             PRIMARY KEY (case_id, document_id));
CREATE TABLE IF NOT EXISTS portal_demo (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attack_lab_runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS policy_drafts (policy_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch_observations (obs_id TEXT PRIMARY KEY, dedupe_key TEXT NOT NULL, signal TEXT NOT NULL,
    agent_id TEXT, case_id TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, count INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS watch_observations_key ON watch_observations(dedupe_key, last_seen);
CREATE TABLE IF NOT EXISTS shield_documents (
    document_id TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    disposition TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS officer_sessions (
    token_hash  TEXT PRIMARY KEY,
    officer_id  TEXT NOT NULL,
    created_at  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    expires_at  REAL NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS officer_login_failures (
    officer_id  TEXT NOT NULL,
    at          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    seq         INTEGER PRIMARY KEY,
    event_id    TEXT NOT NULL UNIQUE,
    timestamp   TEXT NOT NULL,
    event_hash  TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_actor ON audit_events(json_extract(payload, '$.actor'));
CREATE INDEX IF NOT EXISTS audit_claimed ON audit_events(json_extract(payload, '$.claimed_agent_id'));
CREATE INDEX IF NOT EXISTS audit_actor_seq ON audit_events(json_extract(payload, '$.actor'), seq);
CREATE INDEX IF NOT EXISTS audit_claimed_seq ON audit_events(json_extract(payload, '$.claimed_agent_id'), seq);
CREATE INDEX IF NOT EXISTS audit_case ON audit_events(json_extract(payload, '$.evidence_metadata.case_id'));
"""

SEED_TABLES = ("agents", "citizens", "services", "documents", "scenarios", "issuers", "standby_agents", "officers")


class Database:
    """Thin, thread-safe wrapper around a single sqlite3 connection."""

    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def close(self) -> None:
        with self._lock:
            self._conn.close()
