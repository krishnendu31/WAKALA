"""Phase 6 · Milestone 7 — precise revocation: mandate, case, agent identity, dependent delegations; no collateral."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents import SimulatedInsuranceAgent as INS, SimulatedResidencyAgent as RES
from app.core.config import Settings
from app.main import create_app
from app.workflow.delegation_scenarios import prepare
from app.workflow.intake import open_case
from app.workflow.recovery import continue_case
from app.workflow.scenarios import WorkflowRunner


@pytest.fixture()
def api(tmp_path):
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), documents_dir=str(tmp_path / "d"), dev_mode=True,
                 dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        env = c.app.state.env
        for oid in ("OFF-0101", "OFF-0900", "OFF-0950"):
            env.officers._store_hash(oid, f"pw-{oid}")
        r = WorkflowRunner(env, "test")
        mariam = open_case(env, "C-1001", "delegated", "contain")
        omar = open_case(env, "C-1002", "delegated", "contain")
        km, ko = prepare(r, mariam), prepare(r, omar)
        yield c, env, r, mariam, omar, km, ko


def h(c, oid):
    return {"Authorization": "Bearer " + c.post("/api/officer/session", json={"officer_id": oid, "password": f"pw-{oid}"}).json()["token"]}


def test_preview_shows_blast_radius_before_change(api):
    c, env, _, mariam, omar, km, ko = api
    before = env.mandates.revoked_ids()
    p = c.get("/api/officer/revocation/preview", params={"scope": "case", "target": mariam.case_id}, headers=h(c, "OFF-0900")).json()
    assert {x["case_id"] for x in p["affected_cases"]} == {mariam.case_id}
    assert km in {m["mandate_id"] for m in p["mandates"]} and ko not in {m["mandate_id"] for m in p["mandates"]}
    assert p["unaffected_active_cases"] >= 1 and "not available" in p["version_scope"]
    single = c.get("/api/officer/revocation/preview", params={"scope": "mandate", "target": mariam.mandate_refs["AGT-RES-001"],
                                                               "cascade": "false"}, headers=h(c, "OFF-0900")).json()
    assert [m["mandate_id"] for m in single["mandates"]] == [mariam.mandate_refs["AGT-RES-001"]]
    assert env.mandates.revoked_ids() == before  # preview is read-only


def test_case_revocation_for_mariam_does_not_interrupt_omar(api):
    c, env, r, mariam, omar, km, ko = api
    assert c.post(f"/api/officer/cases/{mariam.case_id}/revoke-authority", json={"reason": "compromise drill"},
                  headers=h(c, "OFF-0101")).status_code == 403  # case officer lacks cases.revoke_authority
    out = c.post(f"/api/officer/cases/{mariam.case_id}/revoke-authority", json={"reason": "compromise drill"},
                 headers=h(c, "OFF-0900")).json()
    assert km in out["revoked"] and ko not in out["revoked"]
    m = env.cases.get(mariam.case_id)
    step = r.run("AGT-INS-001", INS.verify(m), m, "after revocation", "legitimate", mandate_id=km)
    assert not step.decision.allowed and not step.executed
    continue_case(env, omar.case_id)
    assert env.cases.get(omar.case_id).state.value == "COMPLETED"
    assert env.cases.get(mariam.case_id).authority_revoked


def test_single_mandate_vs_dependent_delegations(api):
    c, env, r, mariam, omar, km, ko = api
    root = mariam.mandate_refs["AGT-RES-001"]
    out = c.post(f"/api/officer/mandates/{root}/revoke", json={"reason": "root only", "cascade": False}, headers=h(c, "OFF-0900")).json()
    assert out["revoked"] == [root] and not env.mandates.is_revoked(km)  # child record untouched...
    m = env.cases.get(mariam.case_id)
    step = r.run("AGT-INS-001", INS.verify(m), m, "child of revoked root", "legitimate", mandate_id=km)
    assert "DENY_PARENT_MANDATE_REVOKED" in [x.value for x in step.decision.reason_codes]  # ...but unusable (chain check)
    root2 = omar.mandate_refs["AGT-RES-001"]
    out = c.post(f"/api/officer/mandates/{root2}/revoke", json={"reason": "with delegations"}, headers=h(c, "OFF-0900")).json()
    assert set(out["revoked"]) == {root2, ko}


def test_agent_identity_suspension_is_explicit_and_scoped_to_that_agent(api):
    c, env, r, mariam, omar, km, ko = api
    assert c.post("/api/officer/agents/AGT-INS-001/suspend", json={"reason": "drill"}, headers=h(c, "OFF-0101")).status_code == 403
    assert c.post("/api/officer/agents/AGT-INS-001/suspend", json={"reason": "drill"}, headers=h(c, "OFF-0900")).json()["status"] == "suspended"
    o = env.cases.get(omar.case_id)
    assert not r.run("AGT-INS-001", INS.verify(o), o, "suspended identity", "legitimate", mandate_id=ko).decision.allowed
    assert r.run("AGT-RES-001", RES.check_eligibility(env.cases.get(mariam.case_id)), env.cases.get(mariam.case_id), "other agent",
                 "legitimate").decision is not None  # other agents' identities unaffected
    assert env.repo.get_agent("AGT-RES-001").status == "active"
    assert {"officer.agent_suspend"} <= {e.action for e in env.audit.list(30)}
