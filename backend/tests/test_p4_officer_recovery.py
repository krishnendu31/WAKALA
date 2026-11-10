"""Phase 4: officer authentication/authorization (HTTP) and safe recovery end to end."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.case import CaseState
from tests.test_p4_assurance import P4


@pytest.fixture()
def api(tmp_path):
    holder = {}

    def factory(settings):
        holder["p"] = P4()
        holder["p"].env.settings = settings
        return holder["p"].env

    settings = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path), dev_mode=True,
                        dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(create_app(settings, env_factory=factory)) as c:
        yield c, holder["p"]


def login(c, oid="OFF-0101"):
    r = c.post("/api/officer/session", json={"officer_id": oid, "password": f"test-pass-{oid}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --- authentication ---------------------------------------------------------------------

def test_login_and_me(api):
    c, p = api
    h = login(c)
    me = c.get("/api/officer/me", headers=h).json()
    assert me["officer_id"] == "OFF-0101" and me["role"] == "case_officer" and "approvals.decide" in me["permissions"]


def test_unauthenticated_and_wrong_password_rejected(api):
    c, p = api
    assert c.get("/api/officer/incidents").status_code == 401
    assert c.get("/api/officer/incidents", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    r = c.post("/api/officer/session", json={"officer_id": "OFF-0101", "password": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert c.post("/api/officer/session", json={"officer_id": "OFF-9999", "password": "x"}).status_code == 401


def test_login_lockout(api):
    c, p = api
    for _ in range(5):
        c.post("/api/officer/session", json={"officer_id": "OFF-0101", "password": "wrong"})
    r = c.post("/api/officer/session", json={"officer_id": "OFF-0101", "password": "test-pass-OFF-0101"})
    assert r.status_code == 429


def test_session_idle_and_absolute_expiry_and_logout(api):
    c, p = api
    h = login(c)
    p.clock.advance(minutes=16)
    assert c.get("/api/officer/me", headers=h).json()["error"]["code"] == "SESSION_EXPIRED"
    h = login(c)
    for _ in range(4):
        p.clock.advance(minutes=14)  # active use keeps the idle timer fresh …
        assert c.get("/api/officer/me", headers=h).status_code == 200
    p.clock.advance(minutes=5)  # … but 61 min after login the absolute lifetime (60 min) ends it
    assert c.get("/api/officer/me", headers=h).status_code == 401
    h = login(c)
    assert c.delete("/api/officer/session", headers=h).status_code == 200
    assert c.get("/api/officer/me", headers=h).status_code == 401


def test_tokens_and_passwords_never_stored_in_clear(api):
    c, p = api
    r = c.post("/api/officer/session", json={"officer_id": "OFF-0101", "password": "test-pass-OFF-0101"})
    token = r.json()["token"]
    blob = "".join(str(tuple(row)) for t in ("officer_sessions", "officer_credentials", "audit_events")
                   for row in p.env.db.query(f"SELECT * FROM {t}"))
    assert token not in blob and "test-pass-OFF-0101" not in blob


def test_identity_cannot_be_changed_via_request_data(api):
    c, p = api
    h = login(c, "OFF-0950")  # auditor: read-only
    run = c.post("/api/workflow/scenarios/safe_recovery/run").json()
    case_id = run["case"]["case_id"]
    # Adding an officer_id to the body is rejected outright (strict schema) …
    r = c.post(f"/api/officer/cases/{case_id}/resume", headers=h, json={"note": "x", "officer_id": "OFF-0900"})
    assert r.status_code == 422
    # … and without it the auditor is simply not permitted.
    r = c.post(f"/api/officer/cases/{case_id}/resume", headers=h, json={"note": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_entity_scope_enforced(api):
    c, p = api
    run = c.post("/api/workflow/scenarios/safe_recovery/run").json()
    case_id = run["case"]["case_id"]
    h_ins = login(c, "OFF-0202")  # insurance registry officer, not the residency case owner
    r = c.post(f"/api/officer/cases/{case_id}/resume", headers=h_ins, json={"note": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "OUT_OF_ENTITY_SCOPE"
    h_case = login(c, "OFF-0101")
    r = c.post(f"/api/officer/mandates/{run['delegations'][0]['child_mandate_id']}/revoke", headers=h_case, json={"reason": "x y z"})
    assert r.status_code == 403  # case officers may suspend, only supervisors revoke


def test_every_officer_action_is_audited(api):
    c, p = api
    run = c.post("/api/workflow/scenarios/safe_recovery/run").json()
    h = login(c)
    c.post(f"/api/officer/cases/{run['case']['case_id']}/resume", headers=h, json={"note": "reviewed"})
    actions = {e["action"] for e in c.get("/api/officer/audit", headers=h).json() if e["actor"] == "OFF-0101"}
    assert {"officer.login", "officer.case_resume"} <= actions


# --- full recovery through the API ----------------------------------------------------------------

def test_safe_recovery_end_to_end(api):
    c, p = api
    run = c.post("/api/workflow/scenarios/safe_recovery/run").json()
    mariam, omar = run["case"], run["related_cases"][0]
    assert mariam["state"] == "PAUSED_FOR_REVIEW" and omar["state"] == "AWAITING_PAYMENT"
    h = login(c)
    ov = c.get("/api/officer/overview", headers=h).json()
    assert ov["incidents"]["total"] == 1 and ov["suspended_mandates"] == 1 and ov["cases"]["under_review"] == 1

    (inc,) = c.get("/api/officer/incidents", headers=h).json()
    detail = c.get(f"/api/officer/incidents/{inc['incident_id']}", headers=h).json()
    assert detail["citizen_request"]["citizen_ref"] == "C-1001"
    assert {"DENY_SCOPE_VIOLATION", "DENY_CASE_SCOPE_VIOLATION"} <= set(detail["violated_rules"])
    assert detail["incomplete_requirements"] == ["insurance_verified", "fee_paid"]
    assert any(a["kind"] == "delegation_issued" for a in detail["completed_actions"])
    statuses = {n["id"]: n["status"] for n in detail["authority_graph"]["nodes"]}
    child = [v for k, v in statuses.items() if k.startswith("mandate:MND-DLG")]
    roots = [v for k, v in statuses.items() if k.startswith("mandate:MND-") and not k.startswith("mandate:MND-DLG")]
    assert child == ["suspended"] and roots and all(v == "active" for v in roots)  # only the affected authority
    # Only genuine alternatives are offered: the standby insurance agent, nothing for the single-receiver fee task.
    assert detail["reassignable_tasks"] == {"insurance_eligibility_check": ["AGT-INS-002"]}

    cid = mariam["case_id"]
    assert c.post(f"/api/officer/incidents/{inc['incident_id']}/status", headers=h,
                  json={"status": "under_review", "note": "investigating"}).status_code == 200
    # Continuing BEFORE the officer acts changes nothing: the case is paused.
    stuck = c.post(f"/api/workflow/recovery/{cid}/continue").json()
    assert stuck["case"]["state"] == "PAUSED_FOR_REVIEW" and stuck["steps"] == []
    assert c.post(f"/api/officer/cases/{cid}/reassign", headers=h,
                  json={"task": "insurance_eligibility_check", "receiving_agent_id": "AGT-INS-002", "note": "standby"}).status_code == 200
    assert c.post(f"/api/officer/cases/{cid}/resume", headers=h, json={"note": "contained"}).status_code == 200

    step1 = c.post(f"/api/workflow/recovery/{cid}/continue").json()
    assert step1["steps"][-1]["execution_status"] == "pending_approval"  # commission to the standby agent is held
    (apr,) = [a for a in c.get("/api/officer/approvals", headers=h).json() if a["status"] == "pending"]
    res = c.post(f"/api/officer/approvals/{apr['approval_id']}/approve", headers=h, json={"note": "standby agent ok"}).json()
    assert res["executed"] and res["approval"]["status"] == "approved_executed"
    assert c.post(f"/api/officer/incidents/{inc['incident_id']}/status", headers=h,
                  json={"status": "resolved", "note": "recovered"}).status_code == 200

    final = c.post(f"/api/workflow/recovery/{cid}/continue").json()
    tools = [s["tool_name"] for s in final["steps"]]
    assert tools == ["insurance.verify_case_eligibility", "payment.collect_renewal_fee", "residency.complete_renewal"]
    assert all(s["decision"]["allowed"] and s["executed"] for s in final["steps"])
    assert final["steps"][0]["agent_id"] == "AGT-INS-002"
    end = p.env.cases.get(cid)
    assert end.state is CaseState.COMPLETED and end.recovery_status == "recovered"
    assert set(end.completed_prerequisites) == {"residency_eligibility", "insurance_verified", "fee_paid"}
    assert len(p.env.services.ledger(cid)) == 1 and len(p.env.services.renewals(cid)) == 1
    # Omar's independent case was never paused and its authority never touched.
    o = p.env.cases.get(omar["case_id"])
    assert o.state is CaseState.AWAITING_PAYMENT and not o.authority_revoked
    assert not (set(o.mandate_refs.values()) & p.env.assurance.suspensions.active_ids())
    assert p.env.audit.verify().valid


def test_no_bypass_during_manual_recovery(api):
    c, p = api
    run = c.post("/api/workflow/scenarios/safe_recovery/run").json()
    cid = run["case"]["case_id"]
    sup = login(c, "OFF-0900")
    paths = {r.path for r in c.app.routes if r.path.startswith("/api/officer/")}
    assert not [x for x in paths if re.search(r"/(complete|execute|set[-_]state|state)(/|$)", x)]  # no direct completion route
    c.post(f"/api/officer/cases/{cid}/reassign", headers=sup,
           json={"task": "insurance_eligibility_check", "receiving_agent_id": "AGT-INS-002", "note": "x"})
    c.post(f"/api/officer/cases/{cid}/resume", headers=sup, json={"note": "x"})
    p_env = p.env
    case = p_env.cases.get(cid)
    # Reassignment grants nothing by itself: the standby agent has no mandate for this case yet.
    r = p.r.agents["AGT-INS-002"].sign(__import__("app.agents", fromlist=["x"]).SimulatedInsuranceAgent.verify(case), case)
    out = p_env.gateway.execute(r)
    assert not out.decision.allowed
    # The original (suspended) child cannot be used after reassignment, even if reinstated.
    child = run["delegations"][0]["child_mandate_id"]
    c.post(f"/api/officer/mandates/{child}/reinstate", headers=sup, json={"reason": "test reinstate"})
    r = p.r.agents["AGT-INS-001"].sign(__import__("app.agents", fromlist=["x"]).SimulatedInsuranceAgent.verify(case), case,
                                       mandate_id=child)
    assert "DENY_CASE_AGENT_NOT_ASSIGNED" in [x.value for x in p_env.gateway.execute(r).decision.reason_codes]
    # Reassignment to an agent outside the task catalogue is refused.
    r = c.post(f"/api/officer/cases/{cid}/reassign", headers=sup,
               json={"task": "insurance_eligibility_check", "receiving_agent_id": "AGT-PAY-001", "note": "x"})
    assert r.status_code == 422


def test_held_request_returns_202_over_http(api):
    c, p = api
    run = c.post("/api/workflow/scenarios/safe_recovery/run").json()
    cid = run["case"]["case_id"]
    h = login(c)
    c.post(f"/api/officer/cases/{cid}/reassign", headers=h,
           json={"task": "insurance_eligibility_check", "receiving_agent_id": "AGT-INS-002", "note": "x"})
    c.post(f"/api/officer/cases/{cid}/resume", headers=h, json={"note": "x"})
    from app.workflow.delegation_scenarios import commission_call
    case = p.env.cases.get(cid)
    signed = p.r.agents["AGT-RES-001"].sign(commission_call(case, receiver="AGT-INS-002"), case)
    r = c.post("/api/gateway/execute", json=signed.model_dump(mode="json"))
    assert r.status_code == 202 and r.json()["execution_status"] == "pending_approval" and r.json()["executed"] is False


# --- persistence & oversight ----------------------------------------------------------------------

def test_state_persists_across_restart(tmp_path):
    db = str(tmp_path / "w.db")
    from tests.conftest import FrozenClock
    clock = FrozenClock()
    a = P4(db, clock)
    from app.workflow.recovery import setup_recovery
    run = setup_recovery(a.env)
    off = a.officer()
    token, _ = a.env.officers.login("OFF-0101", "test-pass-OFF-0101")
    inc_id = a.env.assurance.incidents.list()[0].incident_id
    susp = a.env.assurance.suspensions.active_ids()
    a.env.close()
    b = P4(db, clock)
    assert b.env.assurance.incidents.get(inc_id) is not None
    assert b.env.assurance.suspensions.active_ids() == susp
    assert b.env.cases.get(run.case.case_id).state is CaseState.PAUSED_FOR_REVIEW
    assert b.env.officers.authenticate(token).officer_id == "OFF-0101"  # session survives, still bounded by expiry
    child = run.delegations[0]["child_mandate_id"]
    case = b.env.cases.get(run.case.case_id)
    from app.agents import SimulatedInsuranceAgent as INS
    out = b.env.gateway.execute(b.r.agents["AGT-INS-001"].sign(INS.verify(case), case, mandate_id=child))
    assert not out.decision.allowed  # suspension still enforced after restart
    del off
    b.env.close()


def test_pending_approvals_expire_on_restart(tmp_path):
    db = str(tmp_path / "w.db")
    from tests.conftest import FrozenClock
    clock = FrozenClock()
    a = P4(db, clock)
    from tests.test_p4_assurance import _held_payment
    case, off, out = _held_payment(a)
    a.env.close()
    clock.advance(minutes=31)
    b = P4(db, clock)
    assert b.env.approvals.get(out.decision.pending_approval_id)[0].status == "expired"
    b.env.close()


def test_oversight_comparison_is_measured_and_labelled():
    from app.workflow.oversight import run_oversight_comparison
    r = run_oversight_comparison(clean_cases=2, violating_cases=1, minutes_per_review=2.0)
    A, B = r["A_manual_review_heavy"], r["B_wakala_automatic_with_exceptions"]
    assert "HYPOTHETICAL" in r["assumptions"]["baseline_A"] and "Not verified current UAE government practice" in r["assumptions"]["baseline_A"]
    assert A["requests_processed"] == B["requests_processed"] > 0
    assert A["requests_requiring_officer_review"] == A["requests_processed"]
    assert B["requests_requiring_officer_review"] < A["requests_requiring_officer_review"]
    assert B["cases_completed"] == 3 and B["legitimate_actions_completed"] == A["legitimate_actions_completed"]
    assert B["incidents_escalated"] >= 1 and r["audit_chain_valid"]
    assert B["review_workflow_minutes_assumed"] == round(B["requests_requiring_officer_review"] * 2.0, 1)
