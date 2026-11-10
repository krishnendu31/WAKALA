"""Composition root: builds the database, registry, keys, mandates and gateway.

Development provisioning (this prototype only):
1. seed synthetic registry data (agents, citizens, services, issuers, fixtures)
2. load-or-generate each agent's and issuer's Ed25519 key in the dev keystore
   and register only the PUBLIC key in the database
3. issue a signed mandate for each agent unless a valid one already exists
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.audit import SqliteAuditSink
from app.core.authorization import PolicyFunction, authorize
from app.core.config import Settings
from app.core.execution import ToolRegistry, build_default_tool_registry
from app.core.execution.gateway import Gateway
from app.core.replay import ReplayGuard
from app.devtools.issuance import ensure_dev_mandates
from app.devtools.keystore import DevKeystore, PrivateKeyProvider
from app.models.database import Database

from app.services.cases import CaseStore
from app.services.delegation import DELEGATION_ISSUER, DelegationService
from app.services.government import ProtectedServices
from app.services.mandate_store import MandateStore
from app.services.repository import Repository
from app.services.seed import SyntheticDataset, load_dataset, seed_database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WakalaEnvironment:
    settings: Settings
    db: Database
    dataset: SyntheticDataset
    repo: Repository
    mandates: MandateStore
    audit: SqliteAuditSink
    replay: ReplayGuard
    tools: ToolRegistry
    gateway: Gateway
    keystore: PrivateKeyProvider
    clock: Callable[[], datetime]
    cases: CaseStore
    services: ProtectedServices
    delegation: DelegationService | None = None

    def close(self) -> None:
        self.db.close()


def _residency_view(repo: Repository) -> Callable[[str], dict | None]:
    def lookup(citizen_ref: str) -> dict | None:
        c = repo.get_citizen(citizen_ref)
        if c is None:
            return None
        # Minimal fields only — never the full record.
        return {
            "citizen_ref": c.citizen_ref,
            "residency_status": c.residency.status,
            "permit_expiry": c.residency.expiry_date.isoformat(),
            "renewal_eligible": c.service_attributes.renewal_eligible,
            "synthetic": True,
        }
    return lookup


def _insurance_view(repo: Repository) -> Callable[[str], dict | None]:
    def lookup(citizen_ref: str) -> dict | None:
        c = repo.get_citizen(citizen_ref)
        if c is None:
            return None
        return {
            "citizen_ref": c.citizen_ref,
            "insurance_valid": c.insurance.status == "valid",
            "valid_until": c.insurance.valid_until.isoformat() if c.insurance.valid_until else None,
            "synthetic": True,
        }
    return lookup


def provision_identities(repo: Repository, dataset: SyntheticDataset, keystore: PrivateKeyProvider) -> None:
    for agent in dataset.agents:
        key_id = agent.identity_key_reference.key_id
        repo.register_public_key(key_id, "agent", agent.agent_id, keystore.private_key(key_id).public_key())
    for issuer in dataset.issuers:
        repo.register_public_key(issuer.key_id, "issuer", issuer.issuer_id, keystore.private_key(issuer.key_id).public_key())


def bootstrap(
    settings: Settings,
    *,
    keystore: PrivateKeyProvider | None = None,
    clock: Callable[[], datetime] = utc_now,
    tools: ToolRegistry | None = None,
    policy: PolicyFunction = authorize,
    reseed: bool = True,
    issue_mandates: bool = True,
) -> WakalaEnvironment:
    db = Database(settings.db_path)
    dataset = load_dataset()
    if reseed or not db.query("SELECT 1 FROM agents LIMIT 1"):
        seed_database(db, dataset)
    repo = Repository(db)
    repo.apply_status_overrides()  # persistent agent revocations survive the reseed
    keystore = keystore or DevKeystore(settings.dev_keys_dir)
    provision_identities(repo, dataset, keystore)

    skew = timedelta(seconds=settings.max_request_skew_seconds)
    mandates = MandateStore(db)
    audit = SqliteAuditSink(db)
    replay = ReplayGuard(db, retention=skew * 2)
    cases = CaseStore(db)
    services = ProtectedServices(db, dataset.services[0])
    from app.devtools.issuance import sign_mandate

    delegation_issuer = next(i for i in dataset.issuers if i.issuer_id == DELEGATION_ISSUER)
    delegation = DelegationService(
        db,
        # Development signer for the delegation authority. Production: an HSM/KMS-backed signing service.
        signer=lambda m: sign_mandate(m, keystore.private_key(delegation_issuer.key_id), delegation_issuer.key_id, m.issued_at),
        issuers=lambda: {i.issuer_id: i for i in repo.list_issuers()},
    )
    if tools is None:
        phase1 = build_default_tool_registry(_residency_view(repo), _insurance_view(repo))
        tools = ToolRegistry([*phase1.specs.values(), *services.tool_specs(), delegation.tool_spec()])
    gateway = Gateway(
        repo=repo, mandates=mandates, cases=cases, audit=audit, replay=replay, tools=tools,
        clock=clock, max_request_skew=skew, policy=policy,
    )
    env = WakalaEnvironment(settings, db, dataset, repo, mandates, audit, replay, tools, gateway, keystore, clock, cases, services,
                            delegation)
    if issue_mandates:
        ensure_dev_mandates(
            gateway, mandates, keystore, {i.issuer_id: i for i in dataset.issuers}, clock(),
            timedelta(minutes=settings.dev_mandate_lifetime_minutes),
        )
    if issue_mandates:
        # Startup recovery: record outcomes for any authorized-but-unrecorded executions.
        from app.services.reconciliation import reconcile_outcomes
        reconcile_outcomes(env)
    return env


def current_mandate_id(env: WakalaEnvironment, agent_id: str) -> str | None:
    """Most recent Phase 1 development mandate (not a case mandate) that verifies as valid."""
    from app.core.mandates import verify_mandate
    from app.devtools.issuance import DEV_REQUEST_ID

    now = env.clock()
    snap = env.gateway.policy_snapshot(now)
    for stored in env.mandates.list(agent_id):
        if stored.mandate.citizen_or_request_scope.request_id != DEV_REQUEST_ID:
            continue
        if verify_mandate(stored.mandate, snap["issuers"], snap["issuer_public_keys"], now, snap["revoked_mandate_ids"]).valid:
            return stored.mandate.mandate_id
    return None
