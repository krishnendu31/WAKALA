"""Phase 4: deterministic detection rules, graduated responses, approvals, suspension."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.assurance import DEFAULT_RULES, RULES_BY_ID, plan_response
from app.core.assurance.rules import Finding
from app.core.config import Settings
from app.schemas import ReasonCode as R
from app.schemas.assurance import ResponseAction
from app.schemas.case import CaseState
from app.services import interventions as iv
from app.services.bootstrap import bootstrap
from app.services.revocation import revoke_mandate
from app.workflow.delegation_scenarios import commission_call, prepare
from app.workflow.intake import open_case
from app.workflow.scenarios import WorkflowRunner, run_workflow
from tests.conftest import DeterministicKeystore, FrozenClock

S = CaseState


class OfficerKeys(DeterministicKeystore):
    def officer_password(self, officer_id: str) -> str:
        return f"test-pass-{officer_id}"


class P4:
    def __init__(self, db: str = ":memory:", clock: FrozenClock | None = None):
        self.clock = clock or FrozenClock()
        self.keys = OfficerKeys()
        self.env = bootstrap(Settings(db_path=db), keystore=self.keys, clock=self.clock)
        self.r = WorkflowRunner(self.env, "test")

    def officer(self, oid: str = "OFF-0101"):
        return self.env.officers.login(oid, f"test-pass-{oid}")[1]

    def case(self, citizen="C-1001", policy="contain"):
        case = open_case(self.env, citizen, "delegated", policy)
        child = prepare(self.r, case)
        assert child
        return case, child

    def exe(self, agent, call, case, **kw):
        return self.env.gateway.execute(self.r.agents[agent].sign(call, case, **kw), origin="test")

    def fresh(self, case):
        return self.env.cases.get(case.case_id)


@pytest.fixture()
def p():
    x = P4()
    yield x
    x.env.close()


def incidents(p, rule=None):
    return [i for i in p.env.assurance.incidents.list() if rule is None or i.rule_id == rule]


# --- detection thresholds ------------------------------------------------------------

def test_rules_are_explicit_configuration():
    assert {r.rule_id for r in DEFAULT_RULES} == {"REPEATED_DENIALS", "REQUEST_RATE", "CROSS_CITIZEN_ACCESS",
                                                  "UNAUTHORIZED_DELEGATION", "ACTION_AFTER_REVOCATION", "CREDENTIAL_FAILURES"}
    for r in DEFAULT_RULES:
        assert r.threshold >= 1 and r.window.total_seconds() > 0 and r.severity in ("low", "medium", "high", "critical")


def test_cross_citizen_on_contain_case_contains_only_affected_authority(p):
    case, child = p.case()
    other, other_child = p.case("C-1002")
    out = p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)
    assert not out.decision.allowed
    (inc,) = incidents(p, "CROSS_CITIZEN_ACCESS")
    assert inc.severity == "high" and inc.classification == "policy_violation" and inc.case_id == case.case_id
    assert "not by itself evidence that the agent is malicious" in inc.interpretation
    assert p.env.assurance.suspensions.active_ids() == {child}
    assert p.fresh(case).state is S.PAUSED_FOR_REVIEW
    assert p.env.repo.get_agent("AGT-INS-001").status == "active"  # never agent-wide
    # Unrelated case: same agent, its own child mandate, unaffected.
    assert p.exe("AGT-INS-001", INS.verify(other), other, mandate_id=other_child).executed
    actions = {(r.action, r.applied) for r in inc.responses}
    assert (ResponseAction.SUSPEND_MANDATE, True) in actions and (ResponseAction.ESCALATE_INCIDENT, True) in actions


def test_cross_citizen_on_monitor_case_escalates_without_containment(p):
    case, child = p.case(policy="monitor")
    p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)
    (inc,) = incidents(p, "CROSS_CITIZEN_ACCESS")
    assert not p.env.assurance.suspensions.active_ids() and p.fresh(case).state is S.VERIFYING
    assert any(r.action is ResponseAction.SUSPEND_MANDATE and not r.applied for r in inc.responses)
    assert p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child).executed


def test_repeated_denials_threshold_and_escalation(p):
    h_case = p.env.dataset  # Phase 1 dev mandate path: payment over limit, not case-bound
    del h_case
    from tests.conftest import Harness
    hh = Harness(p.env, p.clock, p.keys)
    for i in range(4):
        p.env.gateway.authorize(hh.payment("50000.00"))
    assert incidents(p, "REPEATED_DENIALS") == []
    p.env.gateway.authorize(hh.payment("50000.00"))
    (inc,) = incidents(p, "REPEATED_DENIALS")
    assert inc.severity == "medium" and inc.occurrences == 5
    for i in range(5):
        p.env.gateway.authorize(hh.payment("50000.00"))
    (inc,) = incidents(p, "REPEATED_DENIALS")  # de-duplicated, not 6 incidents
    assert inc.severity == "high" and inc.occurrences == 10
    assert p.env.repo.get_agent("AGT-PAY-001").status == "active"


def test_request_rate_threshold(p):
    from tests.conftest import Harness
    hh = Harness(p.env, p.clock, p.keys)
    for _ in range(29):
        assert p.env.gateway.authorize(hh.residency_read()).decision.allowed
    assert incidents(p, "REQUEST_RATE") == []
    p.env.gateway.authorize(hh.residency_read())
    (inc,) = incidents(p, "REQUEST_RATE")
    assert inc.classification == "operational_anomaly" and inc.severity == "medium"
    p.clock.advance(seconds=61)  # window rolls over
    assert p.env.gateway.authorize(hh.residency_read()).decision.allowed


def test_unauthorized_delegation_rule(p):
    case, child = p.case()
    p.exe("AGT-INS-001", commission_call(case, "renewal_fee_collection", "AGT-PAY-001", "payment.collect_renewal_fee"), case,
          mandate_id=child)
    assert incidents(p, "UNAUTHORIZED_DELEGATION")[0].severity == "medium"


def test_action_after_revocation_rule(p):
    case, child = p.case(policy="monitor")
    revoke_mandate(p.env, child, "test")
    p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child)
    (inc,) = incidents(p, "ACTION_AFTER_REVOCATION")
    assert inc.severity == "medium"


def test_credential_failures_rule(p):
    case, child = p.case()
    bad = Ed25519PrivateKey.generate()
    for i in range(2):
        signed = p.r.agents["AGT-INS-001"].sign(INS.verify(case), case, mandate_id=child)
        from app.devtools.agent_client import sign_request
        p.env.gateway.execute(sign_request(signed.request, bad, "KEY-AGT-INS-001"))
    assert incidents(p, "CREDENTIAL_FAILURES") == []
    signed = p.r.agents["AGT-INS-001"].sign(INS.verify(case), case, mandate_id=child)
    from app.devtools.agent_client import sign_request
    p.env.gateway.execute(sign_request(signed.request, bad, "KEY-AGT-INS-001"))
    (inc,) = incidents(p, "CREDENTIAL_FAILURES")
    assert inc.classification == "possible_credential_misuse" and inc.severity == "high"
    assert "says nothing about the genuine agent's intent" in inc.interpretation
    assert not p.env.assurance.suspensions.active_ids()  # unauthenticated: nothing of the agent's to contain
    assert p.fresh(case).state is S.VERIFYING
    assert p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child).executed  # genuine agent unaffected


# --- false escalation ----------------------------------------------------------------------

def test_legitimate_workflow_raises_no_incident(p):
    run = run_workflow(p.env, "delegated_renewal")
    assert run.case.state is S.COMPLETED and incidents(p) == []


def test_single_ordinary_denial_does_not_escalate_or_revoke(p):
    case, child = p.case()
    for a, c in (("AGT-INS-001", INS.verify(case)),):
        assert p.exe(a, c, case, mandate_id=child).executed
    out = p.exe("AGT-PAY-001", PAY.collect(case, "50000.00"), case)
    assert not out.decision.allowed and incidents(p) == []
    assert p.env.repo.get_agent("AGT-PAY-001").status == "active" and not p.env.mandates.revoked_ids()


def test_allowed_requests_do_not_reraise_old_findings(p):
    case, child = p.case(policy="monitor")
    p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)
    before = incidents(p)[0].version
    p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child)
    assert incidents(p)[0].version == before and len(incidents(p)) == 1


def test_agents_never_receive_incident_details(p):
    case, child = p.case()
    out = p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)
    blob = out.decision.model_dump_json()
    assert "INC-" not in blob and "CROSS_CITIZEN" not in blob and "incident" not in blob.lower()


def test_repeated_alerts_deduplicate_and_escalate(p):
    case, child = p.case(policy="monitor")
    for _ in range(3):
        p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)
    (inc,) = incidents(p, "CROSS_CITIZEN_ACCESS")
    assert inc.occurrences == 3 and inc.severity == "critical" and len(inc.evidence_event_ids) == 3


def test_response_plan_never_agent_wide():
    rule = RULES_BY_ID["CROSS_CITIZEN_ACCESS"]
    for sev in ("low", "medium", "high", "critical"):
        f = Finding(rule, sev, "AGT-INS-001", "CASE-AAAAAAAA", "MND-DLG-AAAA0000", 1, ("EVT-AAAA",), "x")
        actions = [s.action for s in plan_response(f)]
        assert ResponseAction.DENY in actions
        assert all(a.value in {"DENY", "ESCALATE_INCIDENT", "SUSPEND_MANDATE", "REVOKE_MANDATE", "REQUIRE_HUMAN_APPROVAL"} for a in actions)
    high = plan_response(Finding(rule, "high", "A", "CASE-AAAAAAAA", "MND-DLG-AAAA0000", 1, (), "x"))
    assert [s.target for s in high if s.action is ResponseAction.SUSPEND_MANDATE] == ["MND-DLG-AAAA0000"]


# --- suspension ----------------------------------------------------------------------------------

def test_suspension_reinstate_and_chain(p):
    case, child = p.case(policy="monitor")
    off = p.officer("OFF-0101")
    iv.suspend_mandate(p.env, off, child, "investigate")
    assert p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child).decision.reason_codes == [R.DENY_MANDATE_SUSPENDED]
    iv.reinstate_mandate(p.env, off, child, "cleared")
    iv.suspend_mandate(p.env, off, case.mandate_refs["AGT-RES-001"], "parent under review")
    assert p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child).decision.reason_codes == [R.DENY_PARENT_MANDATE_SUSPENDED]
    iv.reinstate_mandate(p.env, off, case.mandate_refs["AGT-RES-001"], "cleared")
    assert p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child).executed


def test_revoked_mandate_cannot_be_reinstated(p):
    case, child = p.case(policy="monitor")
    sup = p.officer("OFF-0900")
    iv.revoke_mandate_as_officer(p.env, sup, child, "compromised")
    with pytest.raises(iv.InterventionError) as e:
        iv.reinstate_mandate(p.env, sup, child, "oops")
    assert e.value.code == "MANDATE_REVOKED_CANNOT_REINSTATE"


# --- approvals ---------------------------------------------------------------------------------------

def _held_payment(p):
    case, child = p.case()
    p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)  # incident → case paused
    off = p.officer("OFF-0101")
    inc = incidents(p, "CROSS_CITIZEN_ACCESS")[0]
    iv.set_incident_status(p.env, off, inc.incident_id, "under_review", "x")
    iv.reassign_task(p.env, off, case.case_id, "insurance_eligibility_check", "AGT-INS-002", "replace")
    iv.resume_case(p.env, off, case.case_id, "x")
    out = p.exe("AGT-RES-001", commission_call(case, receiver="AGT-INS-002"), case)
    assert out.status == "pending_approval" and out.decision.pending_approval_id
    return case, off, out


def test_pending_approval_never_executes(p):
    case, off, out = _held_payment(p)
    assert not out.executed and out.result is None
    assert [d["to_agent"] for d in p.env.mandates.delegations(case.case_id)] == ["AGT-INS-001"]  # nothing issued
    (a,) = p.env.approvals.list("pending")
    assert a.approval_id == out.decision.pending_approval_id and a.tool_name == "delegation.commission_task"
    assert R.ESCALATE_HUMAN_REVIEW in out.decision.reason_codes


def test_approval_reauthorizes_and_executes_once(p):
    case, off, out = _held_payment(p)
    res = iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "ok")
    assert res["executed"] and res["approval"]["status"] == "approved_executed"
    assert res["decision"]["decision_id"] != out.decision.decision_id  # a NEW, current decision
    with pytest.raises(iv.InterventionError):
        iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "again")
    assert len(p.env.mandates.delegations(case.case_id)) == 2


def test_rejected_approval_never_executes(p):
    case, off, out = _held_payment(p)
    iv.decide_approval(p.env, off, out.decision.pending_approval_id, False, "no")
    with pytest.raises(iv.InterventionError):
        iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "changed mind")
    assert len(p.env.mandates.delegations(case.case_id)) == 1


def test_approval_cannot_override_revoked_authority(p):
    case, off, out = _held_payment(p)
    revoke_mandate(p.env, case.mandate_refs["AGT-RES-001"], "withdrawn while pending")
    res = iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "ok")
    assert not res["executed"] and res["approval"]["status"] == "approved_denied"
    assert "DENY_MANDATE_REVOKED" in res["approval"]["reauthorization_codes"]


def test_expired_approval_cannot_execute(p):
    """A held request whose approval window (30 min) has passed can never run, even if approved later."""
    case, off, out = _held_payment(p)
    p.clock.advance(minutes=29)
    assert p.env.approvals.get(out.decision.pending_approval_id)[0].status == "pending"
    p.clock.advance(minutes=2)
    with pytest.raises(iv.InterventionError) as e:
        iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "late")
    assert e.value.code == "APPROVAL_EXPIRED"
    assert len(p.env.mandates.delegations(case.case_id)) == 1


def test_expired_mandate_blocks_approval_even_if_approval_fresh(p):
    case, child = p.case()
    p.exe("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=child)
    off = p.officer("OFF-0101")
    iv.reassign_task(p.env, off, case.case_id, "insurance_eligibility_check", "AGT-INS-002", "replace")
    iv.resume_case(p.env, off, case.case_id, "x")
    p.clock.advance(hours=1, minutes=50)  # root mandate (2 h) still valid for 10 min
    out = p.exe("AGT-RES-001", commission_call(case, receiver="AGT-INS-002"), case)
    assert out.status == "pending_approval"
    p.clock.advance(minutes=11)  # mandate expired; approval (30 min TTL) still fresh
    res = iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "ok")
    assert not res["executed"] and "DENY_MANDATE_EXPIRED" in res["approval"]["reauthorization_codes"]


def test_gateway_failure_during_approval_fails_closed(p, monkeypatch):
    case, off, out = _held_payment(p)
    monkeypatch.setattr(p.env.gateway, "_policy", lambda *a: (_ for _ in ()).throw(RuntimeError("gateway down")))
    res = iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "ok")
    assert not res["executed"] and res["approval"]["status"] == "approved_denied"
    monkeypatch.undo()
    # Gateway is back: the held action does NOT run by itself and cannot be re-approved.
    with pytest.raises(iv.InterventionError):
        iv.decide_approval(p.env, off, out.decision.pending_approval_id, True, "retry")
    assert len(p.env.mandates.delegations(case.case_id)) == 1


def test_revocation_during_execution_refused_by_service(p, monkeypatch):
    case, child = p.case(policy="monitor")
    original = p.env.gateway._dispatcher.dispatch

    def revoke_then_dispatch(grant, request, ctx=None):
        revoke_mandate(p.env, request.mandate_id, "revoked mid-flight")
        return original(grant, request, ctx)

    monkeypatch.setattr(p.env.gateway._dispatcher, "dispatch", revoke_then_dispatch)
    out = p.exe("AGT-INS-001", INS.verify(case), case, mandate_id=child)
    assert out.decision.allowed and out.status == "refused_by_service" and out.result == {"refusal_code": "AUTHORITY_WITHDRAWN"}
    assert "insurance_verified" not in p.fresh(case).completed_prerequisites


def test_gateway_unavailable_http_transport_fails_closed(p):
    from app.agents import HttpGatewayTransport

    def down(url, body):
        raise ConnectionError("gateway unreachable")

    case, child = p.case(policy="monitor")
    adapter = p.r.agents["AGT-INS-001"]
    adapter.transport = HttpGatewayTransport("http://127.0.0.1:9", down)
    with pytest.raises(ConnectionError):
        adapter.submit(INS.verify(case), case, origin="test")
    assert "insurance_verified" not in p.fresh(case).completed_prerequisites
