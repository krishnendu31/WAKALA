"""Phase 1: agent identity — signatures, key binding, freshness, replay."""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.crypto import ACTION_REQUEST_TAG, sign
from app.core.identity import canonical_request_bytes, request_digest
from app.schemas import ActionRequest, ReasonCode as R, RequestSignature, SignedActionRequest


def _decide(h, signed):
    return h.env.gateway.authorize(signed).decision


def test_agent_id_alone_is_not_identity(h):
    """A request claiming AGT-PAY-001 but signed by someone else is unauthenticated."""
    attacker = Ed25519PrivateKey.generate()
    d = _decide(h, h.payment(private_key=attacker))
    assert not d.allowed and d.reason_codes == [R.DENY_REQUEST_SIGNATURE_INVALID]


def test_unknown_agent_denied(h):
    d = _decide(h, h.signed("AGT-XYZ-999", key_id="KEY-AGT-XYZ-999", tool_name="residency.read_status",
                            parameters={"citizen_ref": "C-1001"}, target_resource="C-1001"))
    assert d.reason_codes == [R.DENY_UNKNOWN_AGENT]


def test_revoked_agent_denied(h):
    h.env.repo.set_agent_status("AGT-RES-001", "revoked")
    assert _decide(h, h.residency_read()).reason_codes == [R.DENY_AGENT_NOT_ACTIVE]


def test_suspended_agent_denied(h):
    h.env.repo.set_agent_status("AGT-PAY-001", "suspended")
    assert _decide(h, h.payment()).reason_codes == [R.DENY_AGENT_NOT_ACTIVE]


def test_revoked_key_denied(h):
    h.env.repo.set_key_status("KEY-AGT-RES-001", "revoked")
    assert _decide(h, h.residency_read()).reason_codes == [R.DENY_IDENTITY_UNVERIFIED]


def test_incorrect_signing_key_denied(h):
    """Signed with the Insurance Agent's real key while claiming to be the Payment Agent."""
    d = _decide(h, h.payment(private_key=h.keys.private_key("KEY-AGT-INS-001")))
    assert d.reason_codes == [R.DENY_REQUEST_SIGNATURE_INVALID]


def test_key_id_of_another_agent_denied(h):
    d = _decide(h, h.payment(key_id="KEY-AGT-INS-001", private_key=h.keys.private_key("KEY-AGT-INS-001")))
    assert d.reason_codes == [R.DENY_IDENTITY_UNVERIFIED]


def test_tampered_action_request_denied(h):
    signed = h.payment("500.00")
    tampered = signed.request.model_copy(update={"parameters": {**signed.request.parameters, "amount": "50000.00"}})
    d = _decide(h, SignedActionRequest(request=tampered, signature=signed.signature))
    assert d.reason_codes == [R.DENY_REQUEST_SIGNATURE_INVALID]


def test_tampered_agent_claim_denied(h):
    signed = h.residency_read()
    swapped = signed.request.model_copy(update={"agent_id": "AGT-INS-001"})
    assert not _decide(h, SignedActionRequest(request=swapped, signature=signed.signature)).allowed


def test_signature_does_not_cross_domains(h):
    """A signature over the request bytes without the domain tag is rejected."""
    signed = h.residency_read()
    bare = sign(h.keys.private_key("KEY-AGT-RES-001"), b"", canonical_request_bytes(signed.request))
    d = _decide(h, SignedActionRequest(request=signed.request, signature=RequestSignature(key_id="KEY-AGT-RES-001", value=bare)))
    assert d.reason_codes == [R.DENY_REQUEST_SIGNATURE_INVALID]


def test_replayed_request_denied(h):
    signed = h.residency_read()
    assert _decide(h, signed).allowed
    assert _decide(h, signed).reason_codes == [R.DENY_REPLAYED_REQUEST]


def test_nonce_reuse_with_new_content_denied(h):
    first = h.residency_read(nonce="fixed-nonce-0000000001")
    assert _decide(h, first).allowed
    second = h.residency_read(nonce="fixed-nonce-0000000001", purpose="different purpose")
    assert R.DENY_REPLAYED_REQUEST in _decide(h, second).reason_codes


def test_same_nonce_different_agents_is_not_replay(h):
    assert _decide(h, h.residency_read(nonce="shared-nonce-000000001")).allowed
    assert _decide(h, h.insurance_check(nonce="shared-nonce-000000001")).allowed


def test_unauthenticated_request_does_not_burn_nonce(h):
    real = h.residency_read(nonce="victim-nonce-000000001")
    forged = SignedActionRequest(request=real.request, signature=RequestSignature(key_id="KEY-AGT-RES-001", value="A" * 86))
    assert not _decide(h, forged).allowed
    assert _decide(h, real).allowed


def test_stale_signed_request_denied(h):
    old = h.residency_read(timestamp=h.clock() - __import__("datetime").timedelta(seconds=61))
    assert R.DENY_REQUEST_STALE in _decide(h, old).reason_codes


def test_future_dated_request_denied(h):
    future = h.residency_read(timestamp=h.clock() + __import__("datetime").timedelta(seconds=61))
    assert R.DENY_REQUEST_STALE in _decide(h, future).reason_codes


def test_request_within_skew_accepted(h):
    assert _decide(h, h.residency_read(timestamp=h.clock() - __import__("datetime").timedelta(seconds=59))).allowed


def test_canonical_bytes_independent_of_field_order(h):
    signed = h.residency_read()
    reordered = ActionRequest.model_validate(dict(reversed(list(signed.request.model_dump(mode="json").items()))))
    assert canonical_request_bytes(reordered) == canonical_request_bytes(signed.request)
    assert request_digest(reordered) == request_digest(signed.request)
    assert _decide(h, SignedActionRequest(request=reordered, signature=signed.signature)).allowed


def test_private_keys_never_reach_database(h):
    dumped = "\n".join(h.env.db.query("SELECT group_concat(public_key) AS k FROM public_keys")[0]["k"].split(","))
    for key_id in ("KEY-AGT-RES-001", "KEY-ISS-PAYMENTS-OFFICE"):
        raw_private = h.keys.private_key(key_id).private_bytes_raw()
        from app.core.crypto import b64url_encode
        assert b64url_encode(raw_private) not in dumped
    tables = [r["name"] for r in h.env.db.query("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        for row in h.env.db.query(f"SELECT * FROM {t}"):
            assert "PRIVATE KEY" not in " ".join(str(v) for v in tuple(row))


def test_gateway_core_does_not_import_dev_keystore():
    import pathlib
    import re
    core = pathlib.Path(__file__).resolve().parents[1] / "app" / "core"
    for path in core.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+app\.devtools", source, re.M), path
