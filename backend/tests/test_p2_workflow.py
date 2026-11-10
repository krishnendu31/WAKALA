"""Phase 2: protected government workflow, case-bound authority, services."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.agents.interface import ToolCall
from app.core.audit import AuditUnavailableError
from app.core.authorization import PolicyEvaluation
from app.core.execution.gateway import AuthorizationBindingError, ExecutionGrant, ToolDispatcher
from app.core.identity import request_digest
from app.schemas import ReasonCode as R, SignedActionRequest
from app.schemas.case import CaseState
from app.services.cases import InvalidTransition, next_case
from app.workflow.intake import open_case
from app.workflow.officer import resume_case
from app.workflow.scenarios import WorkflowRunner, run_workflow

S = CaseState


class Flow:
    """Opens a real case and drives signed requests through the gateway."""

    def __init__(self, h, citizen="C-1001"):
        self.h = h
        self.case = open_case(h.env, citizen)
        self.r = WorkflowRunner(h.env, "test")

    def sign(self, agent, call, **overrides):
        return self.r.agents[agent].sign(call, self.case, **overrides)

    def exe(self, agent, call):
        return self.h.env.gateway.execute(self.sign(agent, call), origin="test")

    def state(self):
        return self.h.env.cases.get(self.case.case_id).state

    def to_awaiting_payment(self):
        for agent, call in (("AGT-RES-001", RES.register(self.case)), ("AGT-RES-001", RES.check_eligibility(self.case)),
                            ("AGT-INS-001", INS.verify(self.case))):
            assert self.exe(agent, call).executed
        assert self.state() is S.AWAITING_PAYMENT


def snapshot(h):
    tables = ("renewal_cases", "payment_ledger", "residency_renewals", "citizens", "mandates")
    return {t: [tuple(r) for r in h.env.db.query(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}


# --- Scenario A ---------------------------------------------------------------------

def test_successful_normal_renewal(h):
    run = run_workflow(h.env, "legitimate_renewal", "C-1001")
    assert [s.tool_name for s in run.steps] == [
        "residency.register_renewal_case", "residency.check_eligibility", "insurance.verify_case_eligibility",
        "payment.collect_renewal_fee", "residency.complete_renewal"]
    assert all(s.decision.allowed and s.executed for s in run.steps)
    assert run.case.state is S.COMPLETED
    assert set(run.case.completed_prerequisites) == {"residency_eligibility", "insurance_verified", "fee_paid"}
    assert len(run.ledger) == 1 and run.ledger[0]["amount"] == "500.00" and run.ledger[0]["recipient"] == "SYNTH-GOV-TREASURY-0001"
    assert len(run.renewals) == 1 and run.renewals[0]["renewed_expiry"] == "2027-12-15"
    assert [s.case_state_after for s in run.steps] == ["VERIFYING", "VERIFYING", "AWAITING_PAYMENT", "READY_TO_COMPLETE", "COMPLETED"]


def test_every_action_has_authentic_audit_records(h):
    run = run_workflow(h.env, "legitimate_renewal")
    ids = {e.event_id: e for e in run.audit_events}
    for step in run.steps:
        decision_event = ids[step.decision.audit_reference]
        assert decision_event.decision == "allowed" and decision_event.decision_id == step.decision.decision_id
        assert decision_event.evidence_metadata["case_id"] == run.case.case_id
        execution_event = ids[step.execution_audit_reference]
        assert execution_event.decision == "informational"
        assert execution_event.evidence_metadata["decision_event"] == step.decision.audit_reference
        assert execution_event.evidence_metadata["execution_status"] == "executed"
    # Case history links back to the decisions that changed it.
    linked = {ev.audit_reference for ev in run.case.history if ev.audit_reference}
    assert {s.decision.audit_reference for s in run.steps} <= linked
    assert h.env.audit.verify().valid


def test_case_mandates_are_case_scoped_and_valid(h):
    from app.core.mandates import verify_mandate
    case = open_case(h.env, "C-1001")
    snap = h.env.gateway.policy_snapshot(h.clock())
    for agent, mid in case.mandate_refs.items():
        m = h.env.mandates.get(mid)
        assert m.agent_id == agent and m.citizen_or_request_scope.request_id == case.request_id
        assert m.expires_at == case.expires_at
        assert verify_mandate(m, snap["issuers"], snap["issuer_public_keys"], h.clock(), frozenset()).valid


# --- case binding ---------------------------------------------------------------------

def test_authenticated_request_is_bound_to_its_case(h):
    a, b = Flow(h), Flow(h)
    # Agent signs a request naming case B but using case A's mandate and request.
    signed = a.sign("AGT-RES-001", RES.register(a.case), case_id=None)
    req = signed.request.model_copy(update={"case_id": b.case.case_id, "parameters": {"case_id": b.case.case_id, "citizen_ref": "C-1001"},
                                            "target_resource": b.case.case_id})
    from app.devtools.agent_client import sign_request
    resigned = sign_request(req, h.keys.private_key("KEY-AGT-RES-001"), "KEY-AGT-RES-001")
    out = h.env.gateway.execute(resigned)
    assert not out.decision.allowed
    assert {R.DENY_SCOPE_VIOLATION, R.DENY_CASE_SCOPE_VIOLATION, R.DENY_CASE_AGENT_NOT_ASSIGNED} & set(out.decision.reason_codes)
    assert b.state() is S.CREATED and a.state() is S.CREATED


def test_case_tool_without_case_denied(h):
    f = Flow(h)
    signed = f.sign("AGT-RES-001", RES.register(f.case))
    req = signed.request.model_copy(update={"case_id": None})
    from app.devtools.agent_client import sign_request
    out = h.env.gateway.execute(sign_request(req, h.keys.private_key("KEY-AGT-RES-001"), "KEY-AGT-RES-001"))
    assert R.DENY_CASE_REQUIRED in out.decision.reason_codes and f.state() is S.CREATED


def test_unknown_case_denied(h):
    f = Flow(h)
    signed = f.sign("AGT-RES-001", RES.register(f.case))
    req = signed.request.model_copy(update={"case_id": "CASE-DEADBEEF"})
    from app.devtools.agent_client import sign_request
    out = h.env.gateway.execute(sign_request(req, h.keys.private_key("KEY-AGT-RES-001"), "KEY-AGT-RES-001"))
    assert R.DENY_CASE_NOT_FOUND in out.decision.reason_codes


def test_phase1_mandate_cannot_act_on_case(h):
    f = Flow(h)
    signed = f.sign("AGT-RES-001", RES.register(f.case), mandate_id=h.mandate("AGT-RES-001"))
    out = h.env.gateway.execute(signed)
    assert not out.decision.allowed and f.state() is S.CREATED


def test_agent_cannot_use_another_agents_case_operation(h):
    f = Flow(h)
    out = f.exe("AGT-INS-001", RES.register(f.case))
    assert not out.decision.allowed
    assert R.DENY_TOOL_EXPLICITLY_DENIED in out.decision.reason_codes or R.DENY_TOOL_NOT_PERMITTED in out.decision.reason_codes


# --- Scenario B: wrong citizen ------------------------------------------------------------

def test_wrong_citizen_request_denied_without_data(h):
    f = Flow(h)
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    before = snapshot(h)
    out = f.exe("AGT-INS-001", INS.verify(f.case, "C-1003"))
    assert not out.decision.allowed and not out.executed and out.result is None
    assert set(out.decision.reason_codes) == {R.DENY_SCOPE_VIOLATION, R.DENY_CASE_SCOPE_VIOLATION}
    failed = [c for c in out.evaluation.checks if c.status == "failed"]
    assert [c.name for c in failed] == ["resource_scope"]
    assert out.decision.mandate_id == f.case.mandate_refs["AGT-INS-001"]
    assert snapshot(h) == before


def test_denial_contains_no_confidential_data(h):
    run = run_workflow(h.env, "wrong_citizen")
    denied = run.steps[2]
    blob = json.dumps(denied.decision.model_dump(mode="json")) + json.dumps(
        [e.model_dump(mode="json") for e in run.audit_events])
    for secret in ("SYNTH-INS-200301", "Fatima", "Demo Mutual", "2026-10-01", "SYNTH-ACCT-C1003", "expired"):
        assert secret not in blob, secret


def test_same_operation_within_case_is_allowed(h):
    run = run_workflow(h.env, "wrong_citizen")
    assert not run.steps[2].decision.allowed and run.steps[3].decision.allowed
    assert run.steps[3].result == {"citizen_ref": "C-1001", "insurance_valid": True, "valid_until": "2027-06-30",
                                   "case_state": "AWAITING_PAYMENT"}


# --- Scenario C: payments --------------------------------------------------------------------

def test_unauthorized_payment_denied_and_never_executes(h):
    f = Flow(h)
    f.to_awaiting_payment()
    before = snapshot(h)
    out = f.exe("AGT-PAY-001", PAY.collect(f.case, "50000.00", "SYNTH-EXT-UNVERIFIED-9999"))
    assert set(out.decision.reason_codes) == {R.DENY_AMOUNT_EXCEEDS_LIMIT, R.DENY_RECIPIENT_NOT_ALLOWLISTED}
    assert not out.executed and snapshot(h) == before
    assert h.env.services.ledger() == []


def test_wrong_payment_destination_denied(h):
    f = Flow(h)
    f.to_awaiting_payment()
    out = f.exe("AGT-PAY-001", PAY.collect(f.case, "500.00", "SYNTH-EXT-UNVERIFIED-9999"))
    assert out.decision.reason_codes == [R.DENY_RECIPIENT_NOT_ALLOWLISTED] and h.env.services.ledger() == []


def test_payment_service_independently_rejects_non_fee_amount(h):
    """Within the mandate (≤ 500) but not the official fee: the service itself refuses and rolls back."""
    f = Flow(h)
    f.to_awaiting_payment()
    before = snapshot(h)
    out = f.exe("AGT-PAY-001", PAY.collect(f.case, "499.00"))
    assert out.decision.allowed and out.status == "refused_by_service" and out.result == {"refusal_code": "AMOUNT_NOT_OFFICIAL_FEE"}
    assert snapshot(h) == before


def test_payment_before_verification_denied(h):
    f = Flow(h)
    f.exe("AGT-RES-001", RES.register(f.case))
    out = f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert R.DENY_CASE_STATE_INVALID in out.decision.reason_codes and h.env.services.ledger() == []


def test_idempotent_payment_execution(h):
    f = Flow(h)
    f.to_awaiting_payment()
    first = f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert first.executed and first.result["idempotent_replay"] is False
    # A retry: new signed request (fresh nonce), same idempotency key.
    retry = f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert retry.decision.allowed and retry.executed and retry.result["idempotent_replay"] is True
    assert retry.result["transaction_id"] == first.result["transaction_id"]
    assert len(h.env.services.ledger()) == 1
    # Different idempotency key for an already-paid case: refused, still one ledger row.
    call = PAY.collect(f.case)
    other = ToolCall(call.tool_name, {**call.parameters, "idempotency_key": "IDEM-SOMETHING-ELSE"}, call.target_resource, call.purpose)
    refused = f.exe("AGT-PAY-001", other)
    assert refused.status == "refused_by_service" and refused.result == {"refusal_code": "FEE_ALREADY_COLLECTED"}
    assert len(h.env.services.ledger()) == 1


def test_replayed_payment_denied(h):
    f = Flow(h)
    f.to_awaiting_payment()
    signed = f.sign("AGT-PAY-001", PAY.collect(f.case))
    assert h.env.gateway.execute(signed).executed
    again = h.env.gateway.execute(signed)
    assert again.decision.reason_codes == [R.DENY_REPLAYED_REQUEST] and not again.executed
    assert len(h.env.services.ledger()) == 1


def test_tampered_signature_denied(h):
    f = Flow(h)
    f.to_awaiting_payment()
    signed = f.sign("AGT-PAY-001", PAY.collect(f.case))
    for change in ({"parameters": {**signed.request.parameters, "recipient": "SYNTH-EXT-UNVERIFIED-9999"}},
                   {"case_id": "CASE-00000000"}):
        tampered = SignedActionRequest(request=signed.request.model_copy(update=change), signature=signed.signature)
        out = h.env.gateway.execute(tampered)
        assert out.decision.reason_codes == [R.DENY_REQUEST_SIGNATURE_INVALID] and not out.executed
    assert h.env.services.ledger() == []


def test_expired_mandate_denied(h):
    f = Flow(h)
    f.exe("AGT-RES-001", RES.register(f.case))
    h.clock.advance(hours=2, seconds=1)
    out = f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    assert out.decision.reason_codes == [R.DENY_MANDATE_EXPIRED] and f.state() is S.VERIFYING


def test_expired_case_denied(h):
    f = Flow(h)
    stored = h.env.cases.get(f.case.case_id)
    h.env.cases.save(stored, stored.model_copy(update={"expires_at": h.clock() - timedelta(seconds=1), "version": stored.version + 1}))
    out = f.exe("AGT-RES-001", RES.register(f.case))
    assert R.DENY_CASE_EXPIRED in out.decision.reason_codes


def test_revoked_identity_denied(h):
    f = Flow(h)
    h.env.repo.set_agent_status("AGT-RES-001", "revoked")
    before = snapshot(h)
    out = f.exe("AGT-RES-001", RES.register(f.case))
    assert out.decision.reason_codes == [R.DENY_AGENT_NOT_ACTIVE] and snapshot(h) == before


def test_revoked_case_mandate_denied(h):
    f = Flow(h)
    h.env.mandates.revoke(f.case.mandate_refs["AGT-RES-001"], "officer", h.clock())
    assert f.exe("AGT-RES-001", RES.register(f.case)).decision.reason_codes == [R.DENY_MANDATE_REVOKED]


# --- prerequisites and state machine ---------------------------------------------------------

def test_failed_prerequisites_prevent_completion(h):
    run = run_workflow(h.env, "legitimate_renewal", "C-1003")  # synthetic citizen not eligible for renewal
    assert run.case.state is S.FAILED and run.case.recovery_status == "manual_review_required"
    last = run.steps[-1]
    assert last.tool_name == "residency.complete_renewal" and not last.decision.allowed
    assert R.DENY_CASE_STATE_INVALID in last.decision.reason_codes
    assert run.renewals == [] and run.ledger == []


def test_completion_before_payment_denied(h):
    f = Flow(h)
    f.to_awaiting_payment()
    out = f.exe("AGT-RES-001", RES.complete(f.case))
    assert R.DENY_CASE_STATE_INVALID in out.decision.reason_codes and f.state() is S.AWAITING_PAYMENT


@pytest.mark.parametrize("start, prereqs, to", [
    (S.CREATED, [], S.COMPLETED),
    (S.CREATED, [], S.AWAITING_PAYMENT),
    (S.VERIFYING, ["residency_eligibility"], S.AWAITING_PAYMENT),
    (S.AWAITING_PAYMENT, ["residency_eligibility", "insurance_verified"], S.READY_TO_COMPLETE),
    (S.AWAITING_PAYMENT, ["residency_eligibility", "insurance_verified", "fee_paid"], S.COMPLETED),
    (S.COMPLETED, ["residency_eligibility", "insurance_verified", "fee_paid"], S.VERIFYING),
    (S.FAILED, [], S.CREATED),
    (S.VERIFYING, [], S.CREATED),
])
def test_invalid_state_transitions_rejected(h, start, prereqs, to):
    case = open_case(h.env, "C-1001").model_copy(update={"state": start, "completed_prerequisites": prereqs})
    with pytest.raises(InvalidTransition):
        next_case(case, to, actor="test", at=h.clock(), detail="x")


def test_paused_case_resumes_only_to_previous_state(h):
    case = open_case(h.env, "C-1001").model_copy(update={"state": S.VERIFYING})
    paused = next_case(case, S.PAUSED_FOR_REVIEW, actor="t", at=h.clock(), detail="x")
    assert paused.paused_from is S.VERIFYING
    with pytest.raises(InvalidTransition):
        next_case(paused, S.CREATED, actor="t", at=h.clock(), detail="x")
    resumed = next_case(paused, S.VERIFYING, actor="t", at=h.clock(), detail="x")
    assert resumed.recovery_status == "recovered" and resumed.paused_from is None


def test_unauthorized_payment_scenario_pauses_then_officer_recovery(h):
    run = run_workflow(h.env, "unauthorized_payment")
    assert run.case.state is S.PAUSED_FOR_REVIEW and run.ledger == []
    case_id = run.case.case_id
    # While paused, even the legitimate fee is refused by the gateway.
    f = Flow.__new__(Flow)
    f.h, f.case, f.r = h, h.env.cases.get(case_id), WorkflowRunner(h.env, "test")
    assert R.DENY_CASE_STATE_INVALID in f.exe("AGT-PAY-001", PAY.collect(f.case)).decision.reason_codes
    resumed = resume_case(h.env, case_id, officer_id="OFF-0101")
    assert resumed.state is S.AWAITING_PAYMENT and resumed.recovery_status == "recovered"
    assert f.exe("AGT-PAY-001", PAY.collect(resumed)).executed
    assert len(h.env.services.ledger(case_id)) == 1


# --- denied operations never mutate; gateway failures fail closed ----------------------------

def test_denied_operations_never_mutate_state(h):
    f = Flow(h)
    f.exe("AGT-RES-001", RES.register(f.case))
    before = snapshot(h)
    denied = [
        f.exe("AGT-INS-001", INS.verify(f.case, "C-1003")),
        f.exe("AGT-PAY-001", PAY.collect(f.case, "50000.00")),
        f.exe("AGT-RES-001", RES.complete(f.case)),
        f.exe("AGT-INS-001", RES.register(f.case)),
        f.exe("AGT-PAY-001", PAY.collect(f.case)),  # wrong state
    ]
    assert all(not d.decision.allowed and not d.executed and d.result is None for d in denied)
    assert snapshot(h) == before


def test_gateway_failure_does_not_authorize_sensitive_operation(h, monkeypatch):
    f = Flow(h)
    f.to_awaiting_payment()
    before = snapshot(h)
    monkeypatch.setattr(h.env.gateway, "_policy", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    out = f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert out.decision.reason_codes == [R.DENY_POLICY_EVALUATION_ERROR] and not out.executed
    monkeypatch.setattr(h.env.gateway, "_policy", lambda *a: PolicyEvaluation(True, (R.DENY_DEFAULT,), ()))
    assert not f.exe("AGT-PAY-001", PAY.collect(f.case)).executed
    monkeypatch.setattr(h.env.cases, "get", lambda *_: (_ for _ in ()).throw(OSError("case store down")))
    assert f.exe("AGT-PAY-001", PAY.collect(f.case)).decision.reason_codes == [R.DENY_POLICY_EVALUATION_ERROR]
    assert snapshot(h) == before


def test_audit_failure_blocks_payment(h, monkeypatch):
    f = Flow(h)
    f.to_awaiting_payment()
    before = snapshot(h)
    monkeypatch.setattr(h.env.audit, "append", lambda *_: (_ for _ in ()).throw(AuditUnavailableError("disk")))
    with pytest.raises(AuditUnavailableError):
        f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert snapshot(h) == before


def test_case_tools_require_gateway_context(h):
    f = Flow(h)
    signed = f.sign("AGT-RES-001", RES.register(f.case))
    grant = ExecutionGrant("DEC-X", request_digest(signed.request), signed.request.tool_name)
    with pytest.raises(AuthorizationBindingError):
        ToolDispatcher(h.env.tools).dispatch(grant, signed.request)  # no ExecutionContext
    assert f.state() is S.CREATED


def test_service_rechecks_case_state_at_execution(h):
    """If the case changes between authorization and execution, the service refuses and rolls back."""
    from app.core.execution.tools import CaseOperationParams, ExecutionContext
    f = Flow(h)
    ctx = ExecutionContext("AGT-RES-001", f.case.request_id, f.case.case_id, "DEC-X", "EVT-X", h.clock())
    from app.core.execution.tools import ServiceRefusal
    with pytest.raises(ServiceRefusal):
        h.env.services.complete_renewal(CaseOperationParams(case_id=f.case.case_id, citizen_ref="C-1001"), ctx)
    with pytest.raises(ServiceRefusal):
        h.env.services.verify_insurance(CaseOperationParams(case_id=f.case.case_id, citizen_ref="C-1003"), ctx)
    assert f.state() is S.CREATED and h.env.services.renewals(f.case.case_id) == []
