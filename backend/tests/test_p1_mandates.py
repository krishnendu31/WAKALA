"""Phase 1: mandate signatures, issuer trust, issuer authority, lifecycle."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.mandates import verify_mandate, verify_mandate_integrity
from app.devtools.issuance import build_dev_mandate, issue_dev_mandate, sign_mandate
from app.schemas import Money, ReasonCode as R


def _issuers(h):
    return {i.issuer_id: i for i in h.env.repo.list_issuers()}


def _snap(h):
    return h.env.gateway.policy_snapshot(h.clock())


def _integrity(h, m):
    s = _snap(h)
    return verify_mandate_integrity(m, s["issuers"], s["issuer_public_keys"])


def _use(h, mandate, signed_factory):
    """Store a mandate and submit a request that references it."""
    h.env.mandates.put(mandate)
    return h.env.gateway.authorize(signed_factory(mandate_id=mandate.mandate_id)).decision


def _issue(h, agent_id, **kw):
    return issue_dev_mandate(agent_id, _issuers(h), h.keys, kw.pop("issued_at", h.clock() - timedelta(minutes=5)),
                             kw.pop("lifetime", timedelta(hours=1)), **kw)


def test_three_dev_mandates_are_valid(h):
    for agent in ("AGT-RES-001", "AGT-INS-001", "AGT-PAY-001"):
        stored = h.env.mandates.list(agent)
        assert len(stored) == 1
        s = _snap(h)
        assert verify_mandate(stored[0].mandate, s["issuers"], s["issuer_public_keys"], h.clock(), s["revoked_mandate_ids"]).valid


def test_valid_signature_accepted(h):
    assert _integrity(h, _issue(h, "AGT-PAY-001")) == []


def test_unsigned_mandate_rejected(h):
    unsigned = build_dev_mandate("AGT-PAY-001", h.clock() - timedelta(minutes=1), timedelta(hours=1))
    assert _integrity(h, unsigned) == [R.DENY_MANDATE_UNSIGNED]
    assert _use(h, unsigned, h.payment).reason_codes == [R.DENY_MANDATE_UNSIGNED]


@pytest.mark.parametrize("change", [
    {"amount_limit": Money(amount="50000.00", currency="AED")},
    {"recipient_allowlist": ["SYNTH-GOV-TREASURY-0001", "SYNTH-EXT-UNVERIFIED-9999"]},
    {"allowed_tools": ["payment.request_fee_payment", "residency.prepare_renewal"]},
    {"agent_id": "AGT-RES-001"},
    {"version": 2},
    {"purpose": "Something else"},
])
def test_modified_mandate_rejected(h, change):
    m = _issue(h, "AGT-PAY-001")
    tampered = m.model_copy(update=change)
    assert _integrity(h, tampered) == [R.DENY_SIGNATURE_INVALID]


def test_modified_mandate_in_storage_rejected_at_gateway(h):
    mid = h.mandate("AGT-PAY-001")
    m = h.env.mandates.get(mid)
    tampered = m.model_copy(update={"amount_limit": Money(amount="50000.00", currency="AED")})
    h.env.mandates._raw_update_payload_for_tests(mid, tampered.model_dump_json())
    d = h.env.gateway.authorize(h.payment("50000.00", mandate_id=mid)).decision
    assert d.reason_codes == [R.DENY_SIGNATURE_INVALID]


def test_malformed_stored_mandate_rejected(h):
    mid = h.mandate("AGT-PAY-001")
    h.env.mandates._raw_update_payload_for_tests(mid, '{"mandate_id": "broken"}')
    d = h.env.gateway.authorize(h.payment(mandate_id=mid)).decision
    assert d.reason_codes == [R.DENY_MANDATE_MALFORMED]


def test_missing_mandate_rejected(h):
    d = h.env.gateway.authorize(h.payment(mandate_id="MND-DOES-NOT-EXIST")).decision
    assert d.reason_codes == [R.DENY_MANDATE_MISSING]


def test_expired_mandate_rejected(h):
    m = _issue(h, "AGT-PAY-001", issued_at=h.clock() - timedelta(hours=2), lifetime=timedelta(hours=1))
    assert _use(h, m, h.payment).reason_codes == [R.DENY_MANDATE_EXPIRED]


def test_mandate_expiry_boundary(h):
    m = _issue(h, "AGT-PAY-001", issued_at=h.clock() - timedelta(hours=1), lifetime=timedelta(hours=1))
    # now == expires_at -> expired (validity window is [issued_at, expires_at))
    assert _use(h, m, h.payment).reason_codes == [R.DENY_MANDATE_EXPIRED]


def test_not_yet_valid_mandate_rejected(h):
    m = _issue(h, "AGT-PAY-001", issued_at=h.clock() + timedelta(minutes=10))
    assert _use(h, m, h.payment).reason_codes == [R.DENY_MANDATE_NOT_YET_VALID]


def test_revoked_mandate_rejected(h):
    mid = h.mandate("AGT-PAY-001")
    assert h.env.gateway.authorize(h.payment(mandate_id=mid)).decision.allowed
    assert h.env.mandates.revoke(mid, "officer revoked", h.clock())
    assert h.env.gateway.authorize(h.payment(mandate_id=mid)).decision.reason_codes == [R.DENY_MANDATE_REVOKED]


def test_mandate_signed_as_suspended_rejected(h):
    m = _issue(h, "AGT-PAY-001", overrides={"status": "suspended"})
    assert _use(h, m, h.payment).reason_codes == [R.DENY_MANDATE_REVOKED]


def test_untrusted_issuer_rejected(h):
    rogue = Ed25519PrivateKey.generate()
    unsigned = build_dev_mandate("AGT-PAY-001", h.clock() - timedelta(minutes=1), timedelta(hours=1),
                                 overrides={"issuer_id": "ISS-ROGUE-OFFICE"})
    m = sign_mandate(unsigned, rogue, "KEY-ISS-ROGUE-OFFICE", h.clock())
    assert _use(h, m, h.payment).reason_codes == [R.DENY_ISSUER_UNTRUSTED]


def test_issuer_name_field_confers_no_trust(h):
    """Claiming a trusted issuer_id but signing with another key fails."""
    rogue = Ed25519PrivateKey.generate()
    unsigned = build_dev_mandate("AGT-PAY-001", h.clock() - timedelta(minutes=1), timedelta(hours=1))
    m = sign_mandate(unsigned, rogue, "KEY-ISS-PAYMENTS-OFFICE", h.clock())
    assert _use(h, m, h.payment).reason_codes == [R.DENY_SIGNATURE_INVALID]


def test_signed_by_another_trusted_issuers_key_rejected(h):
    unsigned = build_dev_mandate("AGT-PAY-001", h.clock() - timedelta(minutes=1), timedelta(hours=1))
    m = sign_mandate(unsigned, h.keys.private_key("KEY-ISS-RESIDENCY-AUTH"), "KEY-ISS-RESIDENCY-AUTH", h.clock())
    assert _use(h, m, h.payment).reason_codes == [R.DENY_ISSUER_UNTRUSTED]


def test_revoked_issuer_rejected(h):
    from app.schemas import TrustedIssuer
    mid = h.mandate("AGT-PAY-001")
    rows = h.env.db.query("SELECT payload FROM issuers WHERE issuer_id = 'ISS-PAYMENTS-OFFICE'")
    issuer = TrustedIssuer.model_validate_json(rows[0]["payload"]).model_copy(update={"status": "revoked"})
    with h.env.db.transaction() as conn:
        conn.execute("UPDATE issuers SET payload = ? WHERE issuer_id = ?", (issuer.model_dump_json(), issuer.issuer_id))
    assert h.env.gateway.authorize(h.payment(mandate_id=mid)).decision.reason_codes == [R.DENY_ISSUER_UNTRUSTED]


def test_incorrect_agent_binding_rejected(h):
    """A valid insurance mandate cannot be used by the payment agent."""
    ins_mid = h.mandate("AGT-INS-001")
    d = h.env.gateway.authorize(h.payment(mandate_id=ins_mid)).decision
    assert d.reason_codes == [R.DENY_MANDATE_AGENT_MISMATCH]


def test_incorrect_service_scope_rejected(h):
    """Issuer may not grant authority for a service outside its registered scope."""
    m = _issue(h, "AGT-PAY-001", overrides={"service_id": "vehicle_registration"})
    assert _integrity(h, m) == [R.DENY_ISSUER_AUTHORITY_EXCEEDED]
    assert _use(h, m, h.payment).reason_codes == [R.DENY_ISSUER_AUTHORITY_EXCEEDED]


@pytest.mark.parametrize("agent, overrides", [
    ("AGT-PAY-001", {"amount_limit": {"amount": "5000.00", "currency": "AED"}}),
    ("AGT-PAY-001", {"recipient_allowlist": ["SYNTH-EXT-UNVERIFIED-9999"]}),
    ("AGT-PAY-001", {"allowed_tools": ["payment.request_fee_payment", "residency.read_status"], "denied_tools": []}),
    ("AGT-RES-001", {"allowed_tools": ["residency.read_status", "payment.request_fee_payment"], "denied_tools": []}),
    ("AGT-RES-001", {"agent_id": "AGT-PAY-001"}),
])
def test_excessive_issuer_authority_rejected(h, agent, overrides):
    m = _issue(h, agent, overrides=overrides)
    assert _integrity(h, m) == [R.DENY_ISSUER_AUTHORITY_EXCEEDED]


def test_lifetime_beyond_issuer_limit_rejected(h):
    # ISS-PAYMENTS-OFFICE may issue at most 2-hour mandates.
    m = _issue(h, "AGT-PAY-001", lifetime=timedelta(hours=3))
    assert _integrity(h, m) == [R.DENY_ISSUER_AUTHORITY_EXCEEDED]


def test_residency_issuer_cannot_grant_money(h):
    m = _issue(h, "AGT-RES-001", overrides={"amount_limit": {"amount": "1.00", "currency": "AED"},
                                            "recipient_allowlist": ["SYNTH-GOV-TREASURY-0001"]})
    assert _integrity(h, m) == [R.DENY_ISSUER_AUTHORITY_EXCEEDED]


def test_contradictory_constraints_unrepresentable():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        build_dev_mandate("AGT-PAY-001", __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                          timedelta(hours=1), overrides={"denied_tools": ["payment.request_fee_payment"]})
