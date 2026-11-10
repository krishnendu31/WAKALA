"""Phase 1: legitimate and unauthorized operations through the real gateway."""

from __future__ import annotations

import pytest

from app.core.authorization import CHECK_NAMES
from app.schemas import ReasonCode as R


def _decide(h, signed):
    return h.env.gateway.authorize(signed)


# --- legitimate authorization ------------------------------------------------

def test_valid_residency_read_allowed(h):
    out = _decide(h, h.residency_read())
    assert out.decision.allowed is True
    assert out.decision.reason_codes == [R.ALLOW_WITHIN_MANDATE]
    assert [c.status for c in out.evaluation.checks] == ["passed"] * 8
    assert [c.name for c in out.evaluation.checks] == list(CHECK_NAMES)


def test_valid_insurance_verification_allowed(h):
    assert _decide(h, h.insurance_check()).decision.allowed is True


def test_valid_aed_500_payment_to_official_destination_allowed(h):
    out = _decide(h, h.payment("500.00"))
    assert out.decision.allowed is True
    assert out.decision.mandate_id == h.mandate("AGT-PAY-001")
    assert out.decision.decision_latency_ms >= 0


# --- unauthorized operations ----------------------------------------------------

def test_aed_50000_payment_denied(h):
    out = _decide(h, h.payment("50000.00"))
    assert not out.decision.allowed
    assert out.decision.reason_codes == [R.DENY_AMOUNT_EXCEEDS_LIMIT]


@pytest.mark.parametrize("amount, allowed", [("499.99", True), ("500.00", True), ("500.01", False), ("0.01", True)])
def test_amount_boundaries(h, amount, allowed):
    assert _decide(h, h.payment(amount)).decision.allowed is allowed


@pytest.mark.parametrize("amount", ["0.00", "-1.00", "500.001", "abc", "NaN", "Infinity"])
def test_invalid_amounts_denied(h, amount):
    out = _decide(h, h.payment(amount))
    assert not out.decision.allowed
    assert R.DENY_INVALID_PARAMETERS in out.decision.reason_codes


def test_exponent_notation_is_parsed_and_still_limited(h):
    assert _decide(h, h.payment("1e3")).decision.reason_codes == [R.DENY_AMOUNT_EXCEEDS_LIMIT]


def test_wrong_recipient_denied(h):
    out = _decide(h, h.payment("500.00", "SYNTH-EXT-UNVERIFIED-9999"))
    assert out.decision.reason_codes == [R.DENY_RECIPIENT_NOT_ALLOWLISTED]


def test_injected_transfer_violates_both_limits(h):
    out = _decide(h, h.payment("50000.00", "SYNTH-EXT-UNVERIFIED-9999"))
    assert set(out.decision.reason_codes) == {R.DENY_AMOUNT_EXCEEDS_LIMIT, R.DENY_RECIPIENT_NOT_ALLOWLISTED}


def test_another_citizens_record_denied(h):
    out = _decide(h, h.insurance_check("C-1003"))
    assert out.decision.reason_codes == [R.DENY_SCOPE_VIOLATION]


def test_target_resource_must_match_parameters(h):
    out = _decide(h, h.signed("AGT-RES-001", tool_name="residency.read_status",
                              parameters={"citizen_ref": "C-1001"}, target_resource="C-1002"))
    assert R.DENY_SCOPE_VIOLATION in out.decision.reason_codes


def test_other_request_id_denied(h):
    out = _decide(h, h.residency_read(request_id="REQ-2026-OTHER-REQUEST"))
    assert R.DENY_SCOPE_VIOLATION in out.decision.reason_codes


def test_unlisted_tool_denied(h):
    # Known tool, but not in the residency mandate's allow-list.
    out = _decide(h, h.signed("AGT-RES-001", tool_name="insurance.verify_eligibility",
                              parameters={"citizen_ref": "C-1001"}, target_resource="C-1001"))
    assert R.DENY_TOOL_NOT_PERMITTED in out.decision.reason_codes


def test_unknown_tool_denied(h):
    out = _decide(h, h.signed("AGT-PAY-001", tool_name="payment.change_destination",
                              parameters={"citizen_ref": "C-1001"}, target_resource="REQ-2026-C1001-RENEWAL"))
    assert R.DENY_UNKNOWN_TOOL in out.decision.reason_codes
    assert not out.decision.allowed


def test_explicitly_forbidden_operation_denied(h):
    # The insurance mandate explicitly denies payment.request_fee_payment.
    out = _decide(h, h.signed("AGT-INS-001", tool_name="payment.request_fee_payment",
                              parameters={"citizen_ref": "C-1001", "amount": "500.00", "currency": "AED",
                                          "recipient": "SYNTH-GOV-TREASURY-0001"},
                              target_resource="REQ-2026-C1001-RENEWAL"))
    assert R.DENY_TOOL_EXPLICITLY_DENIED in out.decision.reason_codes


def test_unexpected_parameters_denied(h):
    out = _decide(h, h.signed("AGT-RES-001", tool_name="residency.read_status",
                              parameters={"citizen_ref": "C-1001", "include_all_records": True}, target_resource="C-1001"))
    assert R.DENY_INVALID_PARAMETERS in out.decision.reason_codes


def test_missing_parameters_denied(h):
    out = _decide(h, h.signed("AGT-RES-001", tool_name="residency.read_status", parameters={}, target_resource="C-1001"))
    assert not out.decision.allowed


def test_delegated_request_denied_in_phase_1(h):
    signed = h.signed("AGT-PAY-001", tool_name="payment.request_fee_payment",
                      parameters={"citizen_ref": "C-1001", "amount": "500.00", "currency": "AED", "recipient": "SYNTH-GOV-TREASURY-0001"},
                      target_resource="REQ-2026-C1001-RENEWAL")
    req = signed.request.model_copy(update={"delegation_chain": []})
    assert req == signed.request  # sanity: no chain by default
    from app.devtools.agent_client import sign_request
    from app.schemas import ActionRequest
    chained = ActionRequest.model_validate({**signed.request.model_dump(), "delegation_chain": [
        {"from_agent_id": "AGT-RES-001", "to_agent_id": "AGT-PAY-001", "mandate_id": h.mandate("AGT-RES-001")}]})
    out = _decide(h, sign_request(chained, h.keys.private_key("KEY-AGT-PAY-001"), "KEY-AGT-PAY-001"))
    assert R.DENY_DELEGATION_CHAIN_INVALID in out.decision.reason_codes


def test_denial_lists_every_violated_constraint(h):
    out = _decide(h, h.signed("AGT-PAY-001", tool_name="payment.request_fee_payment",
                              parameters={"citizen_ref": "C-1003", "amount": "9000.00", "currency": "AED", "recipient": "SYNTH-EXT-X-001"},
                              target_resource="REQ-2026-C1001-RENEWAL"))
    assert {R.DENY_SCOPE_VIOLATION, R.DENY_AMOUNT_EXCEEDS_LIMIT, R.DENY_RECIPIENT_NOT_ALLOWLISTED} <= set(out.decision.reason_codes)


def test_explanation_is_safe(h):
    out = _decide(h, h.payment("50000.00"))
    text = out.decision.human_readable_explanation
    assert text.startswith("Denied:")
    assert "PRIVATE" not in text and "signature_metadata" not in text
