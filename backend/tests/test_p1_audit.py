"""Phase 1: audit events and hash-chain integrity."""

from __future__ import annotations

import json

from app.core.audit import GENESIS_HASH
from app.schemas import ReasonCode as R


def test_allowed_action_generates_audit_event(h):
    out = h.env.gateway.execute(h.residency_read())
    (event,) = h.env.audit.list()
    assert event.event_id == out.decision.audit_reference
    assert event.decision == "allowed" and event.actor == "AGT-RES-001" and event.authenticated
    assert event.action == "residency.read_status"
    assert event.related_mandate == out.decision.mandate_id and event.mandate_version == 1
    assert event.reason_codes == [R.ALLOW_WITHIN_MANDATE]
    assert event.policy_version == out.decision.policy_version
    assert event.decision_latency_ms == out.decision.decision_latency_ms
    assert event.timestamp.utcoffset().total_seconds() == 0
    assert event.sequence == 1 and event.previous_event_hash == GENESIS_HASH


def test_denied_action_generates_audit_event(h):
    out = h.env.gateway.execute(h.payment("50000.00"))
    (event,) = h.env.audit.list()
    assert event.decision == "denied" and event.reason_codes == [R.DENY_AMOUNT_EXCEEDS_LIMIT]
    assert event.decision_id == out.decision.decision_id


def test_unauthenticated_attempt_is_audited_as_such(h):
    h.env.gateway.authorize(h.payment(private_key=h.keys.private_key("KEY-AGT-INS-001")))
    (event,) = h.env.audit.list()
    assert event.actor == "UNAUTHENTICATED" and not event.authenticated
    assert event.claimed_agent_id == "AGT-PAY-001"
    assert event.mandate_version is None


def test_one_event_per_decision(h):
    for _ in range(3):
        h.env.gateway.authorize(h.residency_read())
    assert h.env.audit.count() == 3
    assert h.env.audit.decision_counts() == {"allowed": 3}


def test_logs_do_not_contain_secrets_or_records(h):
    h.env.gateway.execute(h.residency_read())
    h.env.gateway.execute(h.payment("500.00"))
    signed = h.payment("50000.00")
    h.env.gateway.execute(signed)
    blob = "\n".join(r["payload"] for r in h.env.db.query("SELECT payload FROM audit_events"))
    from app.core.crypto import b64url_encode
    for key_id in ("KEY-AGT-PAY-001", "KEY-AGT-RES-001", "KEY-ISS-PAYMENTS-OFFICE"):
        assert b64url_encode(h.keys.private_key(key_id).private_bytes_raw()) not in blob
    assert signed.signature.value not in blob           # no signatures
    assert "PRIVATE KEY" not in blob
    assert "Mariam" not in blob and "SYNTH-ACCT" not in blob  # no personal record content
    assert "50000" not in blob and "SYNTH-GOV-TREASURY" not in blob  # no parameter values
    assert "SYNTHETIC DOCUMENT" not in blob


def test_chain_verifies_after_mixed_decisions(h):
    h.env.gateway.execute(h.residency_read())
    h.env.gateway.execute(h.payment("50000.00"))
    h.env.gateway.authorize(h.insurance_check("C-1003"))
    report = h.env.audit.verify()
    assert report.valid and report.event_count == 3 and report.first_broken_sequence is None


def _populate(h, n=3):
    for _ in range(n):
        h.env.gateway.authorize(h.residency_read())


def test_modified_event_detected(h):
    _populate(h)
    row = h.env.db.query("SELECT payload FROM audit_events WHERE seq = 2")[0]
    payload = json.loads(row["payload"])
    payload["decision"] = "denied"
    with h.env.db.transaction() as conn:
        conn.execute("UPDATE audit_events SET payload = ? WHERE seq = 2", (json.dumps(payload),))
    report = h.env.audit.verify()
    assert not report.valid and report.first_broken_sequence == 2


def test_rehashed_event_still_breaks_chain(h):
    """Recomputing the edited event's own hash is not enough: its successor commits to the old hash."""
    from app.core.audit import compute_event_hash
    from app.schemas import AuditEvent
    _populate(h)
    row = h.env.db.query("SELECT payload FROM audit_events WHERE seq = 2")[0]
    event = AuditEvent.model_validate_json(row["payload"]).model_copy(update={"decision": "denied", "event_hash": None})
    new_hash = compute_event_hash(event)
    event = event.model_copy(update={"event_hash": new_hash})
    with h.env.db.transaction() as conn:
        conn.execute("UPDATE audit_events SET payload = ?, event_hash = ? WHERE seq = 2", (event.model_dump_json(), new_hash))
    report = h.env.audit.verify()
    assert not report.valid and report.first_broken_sequence == 3


def test_deleted_middle_event_detected(h):
    _populate(h)
    with h.env.db.transaction() as conn:
        conn.execute("DELETE FROM audit_events WHERE seq = 2")
    assert h.env.audit.verify().first_broken_sequence == 3


def test_tail_truncation_is_a_documented_limit(h):
    """Within the implemented model, dropping the newest event is NOT detectable without an external checkpoint."""
    _populate(h)
    head_before = h.env.audit.verify().head_hash
    with h.env.db.transaction() as conn:
        conn.execute("DELETE FROM audit_events WHERE seq = 3")
    report = h.env.audit.verify()
    assert report.valid and report.head_hash != head_before  # only an external head checkpoint would reveal this
