"""Repository over the SQLite store: registry, environment, public keys, issuers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.crypto import b64url_encode, load_public_key, public_key_bytes, public_key_fingerprint
from app.core.identity import RegisteredKey
from app.models.database import Database
from app.schemas import (
    AgentPassport,
    AuditEvent,
    Citizen,
    DocumentFixture,
    GovernmentService,
    Scenario,
    ScenarioWithDocument,
    TrustedIssuer,
)
from app.schemas.common import AgentStatus

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class Repository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- agents ---------------------------------------------------------------
    def _with_key_state(self, agent: AgentPassport) -> AgentPassport:
        """Reflect the *registered* public key in the passport (never private material)."""
        key = self.get_key(agent.identity_key_reference.key_id)
        if key is None or key.owner_type != "agent" or key.owner_id != agent.agent_id:
            return agent
        ref = agent.identity_key_reference.model_copy(update={
            "provisioning_status": "provisioned" if key.status == "active" else "revoked",
            "public_key_fingerprint": key.fingerprint,
        })
        return AgentPassport.model_validate({**agent.model_dump(), "identity_key_reference": ref.model_dump()})

    def list_agents(self) -> list[AgentPassport]:
        # rowid preserves registry (workflow) order: Residency -> Insurance -> Payment.
        rows = self._db.query("SELECT payload FROM agents ORDER BY rowid")
        return [self._with_key_state(AgentPassport.model_validate_json(r["payload"])) for r in rows]

    def get_agent(self, agent_id: str) -> AgentPassport | None:
        rows = self._db.query("SELECT payload FROM agents WHERE agent_id = ?", (agent_id,))
        return self._with_key_state(AgentPassport.model_validate_json(rows[0]["payload"])) if rows else None

    def set_agent_status(self, agent_id: str, status: AgentStatus) -> AgentPassport:
        rows = self._db.query("SELECT payload FROM agents WHERE agent_id = ?", (agent_id,))
        if not rows:
            raise KeyError(agent_id)
        agent = AgentPassport.model_validate_json(rows[0]["payload"])
        updated = AgentPassport.model_validate({**agent.model_dump(), "status": status})
        with self._db.transaction() as conn:
            conn.execute("UPDATE agents SET payload = ? WHERE agent_id = ?", (updated.model_dump_json(), agent_id))
        return self._with_key_state(updated)

    # --- environment ------------------------------------------------------------
    def list_citizens(self) -> list[Citizen]:
        rows = self._db.query("SELECT payload FROM citizens ORDER BY citizen_ref")
        return [Citizen.model_validate_json(r["payload"]) for r in rows]

    def get_citizen(self, citizen_ref: str) -> Citizen | None:
        rows = self._db.query("SELECT payload FROM citizens WHERE citizen_ref = ?", (citizen_ref,))
        return Citizen.model_validate_json(rows[0]["payload"]) if rows else None

    def list_services(self) -> list[GovernmentService]:
        rows = self._db.query("SELECT payload FROM services ORDER BY service_id")
        return [GovernmentService.model_validate_json(r["payload"]) for r in rows]

    def list_scenarios(self) -> list[ScenarioWithDocument]:
        docs = {
            d.document_id: d
            for d in (DocumentFixture.model_validate_json(r["payload"]) for r in self._db.query("SELECT payload FROM documents"))
        }
        scenarios = [
            Scenario.model_validate_json(r["payload"])
            for r in self._db.query("SELECT payload FROM scenarios ORDER BY scenario_id")
        ]
        return [ScenarioWithDocument(scenario=s, document=docs[s.document_id]) for s in scenarios]

    # --- issuers ------------------------------------------------------------------
    def list_issuers(self) -> list[TrustedIssuer]:
        rows = self._db.query("SELECT payload FROM issuers ORDER BY rowid")
        return [TrustedIssuer.model_validate_json(r["payload"]) for r in rows]

    # --- public key registry (public keys only) ---------------------------------
    def register_public_key(self, key_id: str, owner_type: str, owner_id: str, public_key: Ed25519PublicKey) -> RegisteredKey:
        encoded = b64url_encode(public_key_bytes(public_key))
        fingerprint = public_key_fingerprint(public_key)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO public_keys (key_id, owner_type, owner_id, public_key, fingerprint, status, registered_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?) "
                "ON CONFLICT(key_id) DO UPDATE SET owner_type=excluded.owner_type, owner_id=excluded.owner_id, "
                "public_key=excluded.public_key, fingerprint=excluded.fingerprint, status='active', "
                "registered_at=CASE WHEN public_keys.public_key = excluded.public_key THEN public_keys.registered_at ELSE excluded.registered_at END",
                (key_id, owner_type, owner_id, encoded, fingerprint, datetime.now(timezone.utc).isoformat()),
            )
        return RegisteredKey(key_id, owner_type, owner_id, public_key, fingerprint, "active")

    def set_key_status(self, key_id: str, status: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE public_keys SET status = ? WHERE key_id = ?", (status, key_id))

    @staticmethod
    def _row_to_key(row) -> RegisteredKey:  # type: ignore[no-untyped-def]
        return RegisteredKey(
            key_id=row["key_id"], owner_type=row["owner_type"], owner_id=row["owner_id"],
            public_key=load_public_key(row["public_key"]), fingerprint=row["fingerprint"], status=row["status"],
        )

    def get_key(self, key_id: str) -> RegisteredKey | None:
        rows = self._db.query("SELECT * FROM public_keys WHERE key_id = ?", (key_id,))
        return self._row_to_key(rows[0]) if rows else None

    def get_agent_key(self, agent_id: str) -> RegisteredKey | None:
        """The key the *registry* binds to this agent (passport key_id), if registered."""
        rows = self._db.query("SELECT payload FROM agents WHERE agent_id = ?", (agent_id,))
        if not rows:
            return None
        key_id = AgentPassport.model_validate_json(rows[0]["payload"]).identity_key_reference.key_id
        key = self.get_key(key_id)
        if key is None or key.owner_type != "agent" or key.owner_id != agent_id:
            return None
        return key

    def list_keys(self) -> list[dict[str, str]]:
        rows = self._db.query(
            "SELECT key_id, owner_type, owner_id, fingerprint, status, registered_at FROM public_keys ORDER BY owner_type, key_id"
        )
        return [{k: str(r[k]) for k in r.keys()} for r in rows]

    # --- audit (read side kept for Phase 0 callers) ------------------------------
    def count_audit_events(self) -> int:
        return int(self._db.query("SELECT COUNT(*) AS n FROM audit_events")[0]["n"])

    def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        rows = self._db.query("SELECT payload FROM audit_events ORDER BY seq DESC LIMIT ?", (limit,))
        return [AuditEvent.model_validate_json(r["payload"]) for r in rows]
