"""Phase 6 · Milestone 1 — Behaviour Watch 2.0: context-aware, scoped signals, graduated intervention, and the
shared-environment recovery regression (before/after on identical traffic)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents import SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.assurance import ALL_RULES, DEFAULT_RULES, LEVELS
from app.core.config import Settings
from app.evaluation.recovery_bench import _condition
from app.main import create_app
from app.services.bootstrap import bootstrap
from app.workflow.intake import open_case
from app.workflow.scenarios import WorkflowRunner
from tests.conftest import FrozenClock, Harness
from tests.test_p4_assurance import P4, OfficerKeys


@pytest.fixture()
def p():
    x = P4()
    yield x
    x.env.close()


def incidents(p, rule=None):
    return [i for i in p.env.assurance.incidents.list() if rule is None or i.rule_id == rule]


def test_ladder_and_policy_are_explicit():
    assert LEVELS == ("NORMAL", "OBSERVE", "ALERT", "REQUIRE_APPROVAL", "SUSPEND_SPECIFIC_AUTHORITY", "REVOKE")
    assert len(DEFAULT_RULES) == 6 and {r.rule_id for r in ALL_RULES} - {r.rule_id for r in DEFAULT_RULES} == {
        "AGENT_REQUEST_VOLUME", "UNEXPECTED_DATA_CATEGORY", "OFF_SCHEDULE", "EXPIRED_AUTHORITY_REUSE"}
    assert all(r.expected for r in ALL_RULES)  # every signal states its expected pattern


def test_legitimate_batch_across_many_citizens_is_observed_not_contained(p):
    """One Residency Agent serving many independent cases quickly: no REQUEST_RATE incident, no case held."""
    cases = [open_case(p.env, c, "delegated", "contain") for c in ("C-1001", "C-1002", "C-1004", "C-1005", "C-1001") * 6]
    for case in cases:  # 30 independent cases x 2 legitimate steps = 60 requests in the same minute
        for call in (RES.register, RES.check_eligibility):
            out = p.exe("AGT-RES-001", call(p.fresh(case)), p.fresh(case))
            assert out.decision.allowed and out.status != "pending_approval", [c.value for c in out.decision.reason_codes]
    assert incidents(p, "REQUEST_RATE") == []
    vol = [o for o in p.env.assurance.observations() if o["signal"] == "AGENT_REQUEST_VOLUME"]
    assert vol and "legitimate batch" in vol[0]["observed"] and vol[0]["case_id"] is None
    assert all(p.env.assurance.gating_incident(c.case_id) is None for c in cases)


def test_burst_inside_one_case_is_scoped_to_that_case(p):
    case = open_case(p.env, "C-1001", "delegated", "contain")
    other = open_case(p.env, "C-1002", "delegated", "contain")
    p.exe("AGT-RES-001", RES.register(p.fresh(case)), p.fresh(case))
    for _ in range(29):
        p.exe("AGT-RES-001", RES.check_eligibility(p.fresh(case)), p.fresh(case))
    (inc,) = incidents(p, "REQUEST_RATE")
    assert inc.case_id == case.case_id and inc.intervention_level == "REQUIRE_APPROVAL"
    assert "in case" in inc.observed and inc.expected.startswith("fewer than 30")
    assert p.env.assurance.gating_incident(case.case_id) == inc.incident_id
    assert p.env.assurance.gating_incident(other.case_id) is None  # unrelated case untouched
    out = p.exe("AGT-RES-001", RES.register(p.fresh(other)), p.fresh(other))
    assert out.decision.allowed and out.executed and out.status != "pending_approval"


def test_repeated_denials_across_cases_are_an_agent_level_alert(p):
    targets = [p.case(c) for c in ("C-1001", "C-1002", "C-1001", "C-1002", "C-1001")]
    for case, _child in targets:  # Residency Agent tries the payment tool on five different cases
        assert not p.exe("AGT-RES-001", PAY.collect(p.fresh(case)), p.fresh(case)).decision.allowed
    (inc,) = incidents(p, "REPEATED_DENIALS")
    assert inc.case_id is None and inc.intervention_level == "ALERT" and "across 5 cases" in inc.observed
    assert not any(r.applied and r.action.value in ("SUSPEND_MANDATE", "REVOKE_MANDATE", "REQUIRE_HUMAN_APPROVAL")
                   for r in inc.responses)
    assert all(p.env.assurance.gating_incident(c.case_id) is None or
               p.env.assurance.incidents.get(p.env.assurance.gating_incident(c.case_id)).rule_id != "REPEATED_DENIALS"
               for c, _ in targets)


def test_unexpected_data_category_is_flagged_while_gateway_still_blocks(p):
    case, _ = p.case()
    out = p.exe("AGT-RES-001", PAY.collect(p.fresh(case), "50000.00", "SYNTH-EXT-UNVERIFIED-9999"), p.fresh(case))
    assert not out.decision.allowed and not out.executed  # authorization is independent of monitoring
    (inc,) = incidents(p, "UNEXPECTED_DATA_CATEGORY")
    assert inc.intervention_level == "ALERT" and "payment.collect_renewal_fee" in inc.observed
    assert inc.concern and inc.expected


def test_single_off_hours_event_is_observed_repeated_off_hours_denials_alert():
    clock = FrozenClock()  # 08:00 UTC = 12:00 UAE
    env = bootstrap(Settings(db_path=":memory:", watch_operating_hours="13:00-22:00"), keystore=OfficerKeys(), clock=clock)
    try:
        h = Harness(env, clock, OfficerKeys())
        assert env.gateway.authorize(h.residency_read()).decision.allowed
        assert [o["signal"] for o in env.assurance.observations()] == ["OFF_SCHEDULE"]
        assert [i for i in env.assurance.incidents.list() if i.rule_id == "OFF_SCHEDULE"] == []
        for _ in range(3):
            env.gateway.authorize(h.payment("50000.00"))
        (inc,) = [i for i in env.assurance.incidents.list() if i.rule_id == "OFF_SCHEDULE"]
        assert inc.intervention_level == "ALERT" and not any(r.action.value == "SUSPEND_MANDATE" for r in inc.responses)
    finally:
        env.close()


def test_expired_authority_single_use_observed_repeated_use_alerts(p):
    hh = Harness(p.env, p.clock, p.keys)
    mid = hh.mandate("AGT-PAY-001")
    req = lambda: hh.payment(mandate_id=mid)  # noqa: E731
    p.clock.advance(days=400)  # the dev payment mandate is long expired by now
    first = p.env.gateway.authorize(req())
    assert not first.decision.allowed and "DENY_MANDATE_EXPIRED" in [c.value for c in first.decision.reason_codes]
    assert [o for o in p.env.assurance.observations() if o["signal"] == "EXPIRED_AUTHORITY_REUSE"]
    assert incidents(p, "EXPIRED_AUTHORITY_REUSE") == []
    p.env.gateway.authorize(req())
    p.env.gateway.authorize(req())
    (inc,) = incidents(p, "EXPIRED_AUTHORITY_REUSE")
    assert inc.intervention_level == "ALERT"


def test_high_confidence_violation_still_contains_specific_authority(p):
    from app.agents import SimulatedInsuranceAgent as INS
    case, child = p.case()
    other, other_child = p.case("C-1002")
    out = p.exe("AGT-INS-001", INS.verify(p.fresh(case), "C-1003"), p.fresh(case), mandate_id=child)
    assert not out.decision.allowed
    (inc,) = incidents(p, "CROSS_CITIZEN_ACCESS")
    assert inc.intervention_level == "SUSPEND_SPECIFIC_AUTHORITY" and child in p.env.assurance.suspensions.active_ids()
    assert other_child not in p.env.assurance.suspensions.active_ids()
    assert p.fresh(other).state.value != "PAUSED_FOR_REVIEW"


def test_original_policy_remains_reproducible(p):
    p.env.assurance.policy = "phase5-original"
    cases = [open_case(p.env, c, "delegated", "contain") for c in ("C-1001", "C-1002", "C-1003")]
    for i in range(30):
        c = cases[i % 3]
        p.exe("AGT-RES-001", RES.check_eligibility(p.fresh(c)), p.fresh(c))
    (inc,) = incidents(p, "REQUEST_RATE")  # agent-wide counter: an incident lands on whichever case was latest
    assert inc.case_id in {c.case_id for c in cases} and p.env.assurance.observations() == []


@pytest.mark.parametrize("policy,expected", [("phase5-original", 2), ("watch-2.0", 20)])
def test_shared_back_to_back_recovery_before_and_after(policy, expected):
    r = _condition(20, shared=True, policy=policy)
    assert r["recovery_success"]["numerator"] == expected and r["audit_chain_valid"]
    li = r["legitimate_impact"]
    if policy == "watch-2.0":
        assert li["legitimate_requests_denied"] == 0 and li["legitimate_requests_held_unexpectedly"] == 0
        assert r["request_rate_incidents_during_run"] == 0 and r["failures"] == []
        assert li["attack_requests_denied"] == li["attack_requests_sent"] == 20
    else:
        assert li["legitimate_requests_denied"] > 0  # the regression, preserved as evidence


def test_independent_recovery_unchanged():
    assert _condition(20, shared=False)["recovery_success"]["numerator"] == 20


def test_watch_api_requires_officer_and_explains_findings(tmp_path):
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), documents_dir=str(tmp_path / "d"), dev_mode=True,
                 dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        assert c.get("/api/officer/watch").status_code == 401
        env = c.app.state.env
        c.post("/api/portal/scenes/incident")
        env.officers._store_hash("OFF-0101", "pw")
        tok = c.post("/api/officer/session", json={"officer_id": "OFF-0101", "password": "pw"}).json()["token"]
        body = c.get("/api/officer/watch", headers={"Authorization": f"Bearer {tok}"}).json()
        assert body["policy"] == "watch-2.0" and "not AI threat prediction" in body["note"]
        f = next(x for x in body["findings"] if x["signal"] == "CROSS_CITIZEN_ACCESS")
        for k in ("agent_id", "case_id", "observed", "expected", "concern", "severity", "level", "action_taken", "evidence_event_ids"):
            assert f[k], k
