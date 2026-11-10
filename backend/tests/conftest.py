from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.devtools.agent_client import build_request, sign_request
from app.devtools.issuance import DEV_CITIZEN_REF, DEV_REQUEST_ID, TREASURY
from app.main import create_app
from app.schemas import SignedActionRequest
from app.services.bootstrap import WakalaEnvironment, bootstrap, current_mandate_id
from app.services.seed import SyntheticDataset, load_dataset

ISSUED = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)


class DeterministicKeystore:
    """Reproducible test keys derived from a fixed seed per key id."""

    def __init__(self, seed: str = "wakala-tests") -> None:
        self._seed = seed

    def private_key(self, key_id: str) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(f"{self._seed}:{key_id}".encode()).digest())


@dataclass
class FrozenClock:
    now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now = self.now + timedelta(**kw)


@dataclass
class Harness:
    env: WakalaEnvironment
    clock: FrozenClock
    keys: DeterministicKeystore
    calls: list[str] = field(default_factory=list)

    def mandate(self, agent_id: str) -> str:
        mid = current_mandate_id(self.env, agent_id)
        assert mid is not None
        return mid

    def signed(self, agent_id: str, *, key_id: str | None = None, private_key: Ed25519PrivateKey | None = None, **spec: Any) -> SignedActionRequest:
        passport = self.env.repo.get_agent(agent_id)
        kid = key_id or (passport.identity_key_reference.key_id if passport else f"KEY-{agent_id}")
        pk = private_key or self.keys.private_key(kid)
        spec.setdefault("request_id", DEV_REQUEST_ID)
        spec.setdefault("timestamp", self.clock())
        if "mandate_id" not in spec:
            spec["mandate_id"] = self.mandate(agent_id) if passport else "MND-UNKNOWN-0000"
        return sign_request(build_request(agent_id=agent_id, **spec), pk, kid)

    # Ready-made requests matching the dev mandates.
    def residency_read(self, citizen: str = DEV_CITIZEN_REF, **kw: Any) -> SignedActionRequest:
        return self.signed("AGT-RES-001", tool_name="residency.read_status",
                           parameters={"citizen_ref": citizen}, target_resource=citizen, **kw)

    def insurance_check(self, citizen: str = DEV_CITIZEN_REF, **kw: Any) -> SignedActionRequest:
        return self.signed("AGT-INS-001", tool_name="insurance.verify_eligibility",
                           parameters={"citizen_ref": citizen}, target_resource=citizen, **kw)

    def payment(self, amount: str = "500.00", recipient: str = TREASURY, **kw: Any) -> SignedActionRequest:
        return self.signed("AGT-PAY-001", tool_name="payment.request_fee_payment",
                           parameters={"citizen_ref": DEV_CITIZEN_REF, "amount": amount, "currency": "AED", "recipient": recipient},
                           target_resource=DEV_REQUEST_ID, **kw)


def make_harness(settings: Settings | None = None, **bootstrap_kwargs: Any) -> Harness:
    clock = FrozenClock()
    keys = DeterministicKeystore()
    env = bootstrap(settings or Settings(db_path=":memory:"), keystore=keys, clock=clock, **bootstrap_kwargs)
    return Harness(env, clock, keys)


@pytest.fixture()
def h() -> Iterator[Harness]:
    harness = make_harness()
    yield harness
    harness.env.close()


@pytest.fixture(scope="session")
def dataset() -> SyntheticDataset:
    return load_dataset()


def _settings(tmp_path, **kw: Any) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "keys"), **kw)


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(create_app(_settings(tmp_path))) as c:
        yield c


@pytest.fixture()
def dev_client(tmp_path) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(create_app(_settings(tmp_path, dev_mode=True, dev_allowed_hosts=("testclient",)))) as c:
        yield c


@pytest.fixture()
def harness_client(tmp_path) -> Iterator[tuple[TestClient, Harness]]:  # type: ignore[no-untyped-def]
    """HTTP client whose environment is a deterministic, frozen-clock harness."""
    holder: dict[str, Harness] = {}

    def factory(settings: Settings) -> WakalaEnvironment:
        holder["h"] = make_harness()
        return holder["h"].env

    with TestClient(create_app(_settings(tmp_path), env_factory=factory)) as c:
        yield c, holder["h"]


@pytest.fixture()
def mandate_payload() -> dict[str, Any]:
    """A structurally valid (unsigned) payment mandate for Mariam's renewal."""
    return {
        "mandate_id": "MND-PAY0001",
        "version": 1,
        "agent_id": "AGT-PAY-001",
        "issuer_id": "ISS-PAYMENTS-OFFICE",
        "service_id": "residency_renewal",
        "purpose": "Pay the synthetic residency renewal fee for request REQ-2026-0001.",
        "citizen_or_request_scope": {"citizen_ref": "C-1001", "request_id": "REQ-2026-0001"},
        "allowed_tools": ["payment.request_fee_payment"],
        "denied_tools": ["payment.change_destination"],
        "resource_constraints": [{"resource_type": "payment", "access": "execute", "identifiers": ["REQ-2026-0001"]}],
        "amount_limit": {"amount": "500.00", "currency": "AED"},
        "recipient_allowlist": ["SYNTH-GOV-TREASURY-0001"],
        "issued_at": ISSUED.isoformat(),
        "expires_at": (ISSUED + timedelta(hours=1)).isoformat(),
        "status": "active",
        "parent_mandate_id": "MND-RES0001",
        "signature_metadata": None,
    }


@pytest.fixture()
def action_payload() -> dict[str, Any]:
    return {
        "action_id": "ACT-0001",
        "request_id": "REQ-2026-0001",
        "agent_id": "AGT-PAY-001",
        "mandate_id": "MND-PAY0001",
        "tool_name": "payment.request_fee_payment",
        "parameters": {"amount": "500.00", "currency": "AED", "recipient": "SYNTH-GOV-TREASURY-0001"},
        "target_resource": "REQ-2026-0001",
        "purpose": "Pay renewal fee",
        "delegation_chain": [{"from_agent_id": "AGT-RES-001", "to_agent_id": "AGT-PAY-001", "mandate_id": "MND-PAY0001"}],
        "timestamp": ISSUED.isoformat(),
        "nonce": "n0nce-0000000000000001",
    }
