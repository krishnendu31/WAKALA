"""Security contract validation: mandates, passports, requests, decisions, audit."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.mandates import canonical_mandate_bytes
from app.schemas import ActionRequest, AgentPassport, AuditEvent, AuthorizationDecision, DigitalMandate
from tests.conftest import ISSUED


def test_valid_mandate(mandate_payload):
    m = DigitalMandate.model_validate(mandate_payload)
    assert m.amount_limit.amount == 500
    assert m.signature_metadata is None
    assert not m.is_expired_at(ISSUED)
    assert m.is_expired_at(ISSUED + timedelta(hours=2))


def test_mandate_expiry_before_issue_rejected(mandate_payload):
    mandate_payload["expires_at"] = (ISSUED - timedelta(minutes=1)).isoformat()
    with pytest.raises(ValidationError, match="expires_at must be later"):
        DigitalMandate.model_validate(mandate_payload)


def test_mandate_naive_timestamp_rejected(mandate_payload):
    mandate_payload["issued_at"] = "2026-11-09T09:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        DigitalMandate.model_validate(mandate_payload)


def test_mandate_unparseable_timestamp_rejected(mandate_payload):
    mandate_payload["expires_at"] = "tomorrow-ish"
    with pytest.raises(ValidationError):
        DigitalMandate.model_validate(mandate_payload)


def test_mandate_lifetime_capped(mandate_payload):
    mandate_payload["expires_at"] = (ISSUED + timedelta(days=30)).isoformat()
    with pytest.raises(ValidationError, match="lifetime exceeds"):
        DigitalMandate.model_validate(mandate_payload)


def test_tool_cannot_be_allowed_and_denied(mandate_payload):
    mandate_payload["denied_tools"] = ["payment.request_fee_payment"]
    with pytest.raises(ValidationError, match="both allowed and denied"):
        DigitalMandate.model_validate(mandate_payload)


@pytest.mark.parametrize(
    "amount, currency",
    [("-1.00", "AED"), ("500.001", "AED"), ("500.00", "USD"), ("not-a-number", "AED")],
)
def test_invalid_money_rejected(mandate_payload, amount, currency):
    mandate_payload["amount_limit"] = {"amount": amount, "currency": currency}
    with pytest.raises(ValidationError):
        DigitalMandate.model_validate(mandate_payload)


def test_non_synthetic_recipient_rejected(mandate_payload):
    mandate_payload["recipient_allowlist"] = ["AE070331234567890123456"]
    with pytest.raises(ValidationError):
        DigitalMandate.model_validate(mandate_payload)


def test_amount_limit_requires_recipient(mandate_payload):
    mandate_payload["recipient_allowlist"] = []
    with pytest.raises(ValidationError, match="requires a non-empty recipient_allowlist"):
        DigitalMandate.model_validate(mandate_payload)


def test_wildcard_resource_rejected(mandate_payload):
    mandate_payload["resource_constraints"][0]["identifiers"] = ["*"]
    with pytest.raises(ValidationError, match="wildcards"):
        DigitalMandate.model_validate(mandate_payload)


def test_unknown_field_rejected(mandate_payload):
    mandate_payload["grant_all"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DigitalMandate.model_validate(mandate_payload)


def test_self_parent_rejected(mandate_payload):
    mandate_payload["parent_mandate_id"] = mandate_payload["mandate_id"]
    with pytest.raises(ValidationError, match="own parent"):
        DigitalMandate.model_validate(mandate_payload)


@pytest.mark.parametrize("field, value", [
    ("mandate_id", "mandate-1"),
    ("agent_id", "payment-agent"),
    ("status", "maybe"),
    ("version", 0),
    ("issuer_id", "Government Officer"),
    ("allowed_tools", []),
    ("allowed_tools", ["PAY EVERYONE"]),
])
def test_malformed_mandate_fields_rejected(mandate_payload, field, value):
    mandate_payload[field] = value
    with pytest.raises(ValidationError):
        DigitalMandate.model_validate(mandate_payload)


def test_mandate_is_immutable(mandate_payload):
    m = DigitalMandate.model_validate(mandate_payload)
    with pytest.raises(ValidationError):
        m.amount_limit = None  # type: ignore[misc]


def test_canonical_bytes_deterministic_and_tamper_sensitive(mandate_payload):
    a = DigitalMandate.model_validate(mandate_payload)
    reordered = dict(reversed(list(copy.deepcopy(mandate_payload).items())))
    b = DigitalMandate.model_validate(reordered)
    assert canonical_mandate_bytes(a) == canonical_mandate_bytes(b)

    tampered = copy.deepcopy(mandate_payload)
    tampered["amount_limit"]["amount"] = "50000.00"
    assert canonical_mandate_bytes(DigitalMandate.model_validate(tampered)) != canonical_mandate_bytes(a)


def test_passport_rejects_fingerprint_without_key(dataset):
    raw = dataset.agents[0].model_dump(mode="json")
    raw["identity_key_reference"]["public_key_fingerprint"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="not provisioned"):
        AgentPassport.model_validate(raw)


@pytest.mark.parametrize("field, value", [
    ("agent_id", "AGT-res-1"), ("risk_level", "extreme"), ("status", "online"), ("declared_tools", []),
])
def test_passport_malformed_fields_rejected(dataset, field, value):
    raw = dataset.agents[0].model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        AgentPassport.model_validate(raw)


def test_valid_action_request(action_payload):
    req = ActionRequest.model_validate(action_payload)
    assert req.delegation_chain[-1].to_agent_id == req.agent_id


def test_action_request_nested_parameters_rejected(action_payload):
    action_payload["parameters"] = {"payload": {"nested": "object"}}
    with pytest.raises(ValidationError):
        ActionRequest.model_validate(action_payload)


def test_action_request_chain_must_end_at_requester(action_payload):
    action_payload["delegation_chain"][0]["to_agent_id"] = "AGT-INS-001"
    with pytest.raises(ValidationError, match="must end at the requesting agent"):
        ActionRequest.model_validate(action_payload)


def test_action_request_self_delegation_rejected(action_payload):
    action_payload["delegation_chain"] = [{"from_agent_id": "AGT-PAY-001", "to_agent_id": "AGT-PAY-001", "mandate_id": "MND-PAY0001"}]
    with pytest.raises(ValidationError, match="delegate to itself"):
        ActionRequest.model_validate(action_payload)


def test_action_request_naive_timestamp_rejected(action_payload):
    action_payload["timestamp"] = datetime(2026, 11, 9, 9, 0).isoformat()
    with pytest.raises(ValidationError):
        ActionRequest.model_validate(action_payload)


def _decision(**overrides):
    base = {
        "decision_id": "DEC-0001",
        "allowed": False,
        "reason_codes": ["DENY_DEFAULT"],
        "human_readable_explanation": "Denied by default.",
        "policy_version": "1.0.0",
        "decision_latency_ms": 0.4,
        "audit_reference": "EVT-0001",
    }
    return {**base, **overrides}


def test_decision_codes_must_match_outcome():
    AuthorizationDecision.model_validate(_decision())
    AuthorizationDecision.model_validate(_decision(allowed=True, reason_codes=["ALLOW_WITHIN_MANDATE"]))
    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(_decision(allowed=True, reason_codes=["DENY_DEFAULT"]))
    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(_decision(reason_codes=["ALLOW_WITHIN_MANDATE"]))
    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(_decision(reason_codes=[]))
    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(_decision(reason_codes=["ALLOW_EVERYTHING"]))
    with pytest.raises(ValidationError):
        AuthorizationDecision.model_validate(_decision(decision_latency_ms=-1))


def test_audit_event_actor_and_timestamp():
    ok = {"event_id": "EVT-0001", "timestamp": ISSUED.isoformat(), "actor": "WAKALA-GATEWAY",
          "action": "payment.request_fee_payment", "decision": "denied"}
    AuditEvent.model_validate(ok)
    with pytest.raises(ValidationError):
        AuditEvent.model_validate({**ok, "actor": "anonymous"})
    with pytest.raises(ValidationError):
        AuditEvent.model_validate({**ok, "timestamp": "2026-11-09T09:00:00"})
    with pytest.raises(ValidationError):
        AuditEvent.model_validate({**ok, "decision": "probably-fine"})
