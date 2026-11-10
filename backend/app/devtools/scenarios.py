"""DEVELOPMENT-ONLY predefined demonstration scenarios.

Each scenario is a fixed, server-side script: it signs a request with a
dedicated development agent identity and submits it to the REAL gateway
``execute()`` path. Callers choose a scenario key only — they cannot choose
the agent, tool, parameters or mandate. Outcomes are whatever the gateway
decides; nothing here sets ``allowed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from app.core.execution.gateway import ExecutionOutcome
from app.devtools.agent_client import build_request, sign_request
from app.devtools.issuance import DEV_CITIZEN_REF, DEV_REQUEST_ID, TREASURY, issue_dev_mandate
from app.schemas import DigitalMandate, Money, SignedActionRequest
from app.services.bootstrap import WakalaEnvironment, current_mandate_id


@dataclass(frozen=True)
class DevScenario:
    key: str
    title: str
    description: str
    designed_to_test: str


DEV_SCENARIOS: tuple[DevScenario, ...] = (
    DevScenario("valid_authorization", "Valid authorization",
                "Residency Agent reads Mariam's residency status under its signed mandate.",
                "A legitimate, in-scope read should pass all eight checks and execute."),
    DevScenario("valid_payment", "Valid AED 500 fee request",
                "Payment Agent requests the AED 500 synthetic fee to SYNTH-GOV-TREASURY-0001.",
                "An in-limit payment to the allow-listed destination should be authorized."),
    DevScenario("invalid_amount", "Invalid amount (AED 50,000)",
                "Payment Agent requests AED 50,000 — the amount from the injected document fixture.",
                "Amount above the mandate limit must be denied."),
    DevScenario("wrong_recipient", "Wrong recipient",
                "Payment Agent requests AED 500 to SYNTH-EXT-UNVERIFIED-9999.",
                "A recipient outside the allow-list must be denied."),
    DevScenario("modified_mandate", "Modified mandate",
                "The payment mandate's amount_limit is altered to AED 50,000 after signing; the agent then requests AED 50,000.",
                "Any post-signature modification must break signature verification."),
    DevScenario("expired_mandate", "Expired mandate",
                "Residency Agent uses a correctly signed mandate whose validity ended an hour ago.",
                "Expired mandates must be denied even with a valid signature."),
    DevScenario("cross_citizen_record", "Another citizen's record",
                "Insurance Agent, mandated for C-1001, asks about C-1003.",
                "Requests outside the mandated citizen must be denied."),
    DevScenario("replayed_request", "Replayed request",
                "A valid signed request is submitted twice with the same nonce.",
                "The second, identical submission must be denied as a replay."),
)
SCENARIOS_BY_KEY = {s.key: s for s in DEV_SCENARIOS}


class ScenarioUnavailable(RuntimeError):
    pass


def _signer(env: WakalaEnvironment, agent_id: str) -> Callable[[dict[str, Any]], SignedActionRequest]:
    passport = env.repo.get_agent(agent_id)
    if passport is None:
        raise ScenarioUnavailable(f"agent {agent_id} not registered")
    key_id = passport.identity_key_reference.key_id
    private_key = env.keystore.private_key(key_id)

    def make(spec: dict[str, Any]) -> SignedActionRequest:
        req = build_request(agent_id=agent_id, request_id=DEV_REQUEST_ID, timestamp=env.clock(), **spec)
        return sign_request(req, private_key, key_id)
    return make


def _mandate(env: WakalaEnvironment, agent_id: str) -> str:
    mid = current_mandate_id(env, agent_id)
    if mid is None:
        raise ScenarioUnavailable(f"no valid mandate for {agent_id}; run `python -m app.devtools.cli mandates issue`")
    return mid


def _payment(env: WakalaEnvironment, amount: str, recipient: str, mandate_id: str | None = None) -> dict[str, Any]:
    return {
        "mandate_id": mandate_id or _mandate(env, "AGT-PAY-001"),
        "tool_name": "payment.request_fee_payment",
        "parameters": {"citizen_ref": DEV_CITIZEN_REF, "amount": amount, "currency": "AED", "recipient": recipient},
        "target_resource": DEV_REQUEST_ID,
    }


def run_scenario(env: WakalaEnvironment, key: str) -> tuple[ExecutionOutcome, SignedActionRequest, str | None]:
    """Returns (final outcome, the signed request submitted, optional note)."""
    gw = env.gateway
    origin = f"dev_scenario:{key}"
    note: str | None = None
    if key not in SCENARIOS_BY_KEY:
        raise KeyError(key)

    if key in ("valid_authorization", "replayed_request"):
        signed = _signer(env, "AGT-RES-001")({
            "mandate_id": _mandate(env, "AGT-RES-001"), "tool_name": "residency.read_status",
            "parameters": {"citizen_ref": DEV_CITIZEN_REF}, "target_resource": DEV_CITIZEN_REF,
        })
        if key == "replayed_request":
            first = gw.execute(signed, origin=origin)
            note = (f"First submission: {'ALLOW' if first.decision.allowed else 'DENY'} "
                    f"({first.decision.decision_id}, executed={first.executed}). The identical resubmission follows.")
        return gw.execute(signed, origin=origin), signed, note

    if key == "valid_payment":
        signed = _signer(env, "AGT-PAY-001")(_payment(env, "500.00", TREASURY))
        return gw.execute(signed, origin=origin), signed, None

    if key == "invalid_amount":
        signed = _signer(env, "AGT-PAY-001")(_payment(env, "50000.00", TREASURY))
        return gw.execute(signed, origin=origin), signed, None

    if key == "wrong_recipient":
        signed = _signer(env, "AGT-PAY-001")(_payment(env, "500.00", "SYNTH-EXT-UNVERIFIED-9999"))
        return gw.execute(signed, origin=origin), signed, None

    if key == "modified_mandate":
        original = env.mandates.get(_mandate(env, "AGT-PAY-001"))
        if original is None:
            raise ScenarioUnavailable("payment mandate not found")
        # Simulates tampering with the stored mandate after it was signed.
        tampered: DigitalMandate = original.model_copy(update={"amount_limit": Money(amount="50000.00", currency="AED")})
        signed = _signer(env, "AGT-PAY-001")(_payment(env, "50000.00", TREASURY, tampered.mandate_id))
        source = lambda mid: tampered if mid == tampered.mandate_id else env.mandates.get(mid)  # noqa: E731
        note = "The mandate presented to the gateway differs from the signed original only in amount_limit (500.00 → 50000.00)."
        return gw.execute(signed, origin=origin, mandate_source=source), signed, note

    if key == "expired_mandate":
        now = env.clock()
        issuers = {i.issuer_id: i for i in env.repo.list_issuers()}
        expired = issue_dev_mandate("AGT-RES-001", issuers, env.keystore, now - timedelta(hours=3), timedelta(hours=2), suffix="EXPIRED-DEMO")
        signed = _signer(env, "AGT-RES-001")({
            "mandate_id": expired.mandate_id, "tool_name": "residency.read_status",
            "parameters": {"citizen_ref": DEV_CITIZEN_REF}, "target_resource": DEV_CITIZEN_REF,
        })
        source = lambda mid: expired if mid == expired.mandate_id else env.mandates.get(mid)  # noqa: E731
        note = f"Mandate {expired.mandate_id} is validly signed by ISS-RESIDENCY-AUTH but expired at {expired.expires_at.isoformat()}."
        return gw.execute(signed, origin=origin, mandate_source=source), signed, note

    # cross_citizen_record
    signed = _signer(env, "AGT-INS-001")({
        "mandate_id": _mandate(env, "AGT-INS-001"), "tool_name": "insurance.verify_eligibility",
        "parameters": {"citizen_ref": "C-1003"}, "target_resource": "C-1003",
    })
    return gw.execute(signed, origin=origin), signed, None
