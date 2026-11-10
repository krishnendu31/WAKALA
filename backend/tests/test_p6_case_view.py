"""Phase 6 · Milestone 3 — Case View is derived from the stored signed chain and live decisions."""

from __future__ import annotations

import dataclasses
import tempfile

import pytest

from app.evaluation.environment import isolated_env
from app.portal import service as P
from app.services import interventions as iv
from app.workflow.case_view import build_case_view
from app.workflow.delegation_scenarios import INSURANCE_TASK


@pytest.fixture()
def lab():
    with isolated_env("memory") as (env, clock, keys), tempfile.TemporaryDirectory() as d:
        env.settings = dataclasses.replace(env.settings, documents_dir=d)
        yield env, keys


def test_normal_case_edges_match_stored_chain(lab):
    env, _ = lab
    cid = P.start_request(env, "C-1001")["case_id"]
    v = build_case_view(env, cid)
    case = env.cases.get(cid)
    res, ins = v["lanes"][0], v["lanes"][1]
    assert res["agent_id"] == "AGT-RES-001" and res["mandate_id"] == case.mandate_refs["AGT-RES-001"]
    (dlg,) = env.mandates.delegations(cid)
    assert ins["mandate_id"] == str(dlg["child_mandate_id"]) and ins["delegated_from"] == res["mandate_id"]
    assert env.mandates.get(ins["mandate_id"]).parent_mandate_id == res["mandate_id"]
    assert ins["technical"]["verification_valid"] and ins["technical"]["chain_length"] == 2
    assert all(a["state"] == "authorized" for l in v["lanes"] for a in l["actions"])
    assert {a["technical"]["event_id"] for l in v["lanes"] for a in l["actions"]} <= {e.event_id for e in env.audit.list(500)}


def test_incident_shows_denied_and_suspended_then_recovered(lab):
    env, keys = lab
    cid = P.start_incident_scene(env)["case_id"]
    v = build_case_view(env, cid)
    ins = next(l for l in v["lanes"] if l["agent_id"] == "AGT-INS-001")
    assert ins["state"] == "suspended" and [a["state"] for a in ins["actions"]] == ["denied"]
    assert "not another citizen's record (C-1003)" in ins["actions"][0]["explanation"]
    assert v["incident"]["severity"] == "high"
    p = env.officers.authenticate(env.officers.login("OFF-0101", keys.officer_password("OFF-0101"))[0])
    inc = env.assurance.incidents.case_has_active(cid)
    iv.guarded(iv.set_incident_status, env, p, inc.incident_id, "under_review", "t")
    iv.guarded(iv.reassign_task, env, p, cid, INSURANCE_TASK, "AGT-INS-002", "t")
    iv.guarded(iv.resume_case, env, p, cid, "t")
    P.continue_request(env, cid)
    assert build_case_view(env, cid)["lanes"][0]["state"] == "pending_approval"  # held delegation visible
    (a,) = [x for x in env.approvals.list("pending") if x.case_id == cid]
    iv.guarded(iv.decide_approval, env, p, a.approval_id, True, "t")
    iv.guarded(iv.set_incident_status, env, p, inc.incident_id, "resolved", "t")
    P.continue_request(env, cid)
    v = build_case_view(env, cid)
    standby = next(l for l in v["lanes"] if l["agent_id"] == "AGT-INS-002")
    assert v["state"] == "COMPLETED" and standby["state"] == "recovered"
