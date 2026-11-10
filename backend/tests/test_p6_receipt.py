"""Phase 6 · Milestone 4 — My AI Activity receipt: accuracy and citizen privacy filtering."""

from __future__ import annotations

import dataclasses
import json
import tempfile

import pytest

from app.evaluation.environment import isolated_env
from app.portal import service as P
from app.portal.receipt import build_receipt
from app.services import interventions as iv
from app.workflow.delegation_scenarios import INSURANCE_TASK


@pytest.fixture()
def lab():
    with isolated_env("memory") as (env, clock, keys), tempfile.TemporaryDirectory() as d:
        env.settings = dataclasses.replace(env.settings, documents_dir=d)
        yield env, keys


def test_normal_case_receipt_counts_only_executed_actions(lab):
    env, _ = lab
    cid = P.start_request(env, "C-1001")["case_id"]
    r = build_receipt(env, cid)
    assert r["final_status"] == "Completed" and r["synthetic"] and "SYNTHETIC RECEIPT" in r["label"]
    assert len(r["actions"]) == 6 and all(a["completed"] and a["authorized"] for a in r["actions"])
    assert r["agents_with_completed_actions"] == ["Insurance Agent", "Payment Agent", "Residency Agent"]
    assert r["summary"][0].startswith("3 government AI agents completed actions")
    assert [a["purpose"] for a in r["actions"] if a["delegated"]] == ["Confirm your health insurance is valid"]
    assert r["blocked"] == [] and not r["interrupted_by_security_check"] and r["officer_review"] == []


def test_authorized_but_not_executed_is_not_claimed_as_done(lab):
    env, _ = lab
    cid = P.start_request(env, "C-1001")["case_id"]
    # remove the execution outcome of the payment from the receipt's view: the decision alone must not count as "completed"
    from app.portal import receipt as R
    real = R.case_audit_events
    R.case_audit_events = lambda e, c: [x for x in real(e, c) if x.action != "payment.collect_renewal_fee:execution"]
    try:
        r = build_receipt(env, cid)
    finally:
        R.case_audit_events = real
    pay = next(a for a in r["actions"] if a["purpose"].startswith("Collect"))
    assert pay["authorized"] and not pay["completed"] and "did not complete" in pay["status"]


def test_blocked_incident_and_officer_review_without_leaks(lab):
    env, keys = lab
    cid = P.start_incident_scene(env)["case_id"]
    r = build_receipt(env, cid)
    assert r["final_status"] == "Paused for security review" and r["interrupted_by_security_check"]
    (b,) = r["blocked"]
    assert "outside your case" in b["why"] and "no data was returned" in b["status"]
    assert not r["officer_review_completed"]
    p = env.officers.authenticate(env.officers.login("OFF-0101", keys.officer_password("OFF-0101"))[0])
    inc = env.assurance.incidents.case_has_active(cid)
    iv.guarded(iv.set_incident_status, env, p, inc.incident_id, "under_review", "t")
    iv.guarded(iv.reassign_task, env, p, cid, INSURANCE_TASK, "AGT-INS-002", "t")
    iv.guarded(iv.resume_case, env, p, cid, "t")
    P.continue_request(env, cid)
    (a,) = [x for x in env.approvals.list("pending") if x.case_id == cid]
    iv.guarded(iv.decide_approval, env, p, a.approval_id, True, "t")
    iv.guarded(iv.set_incident_status, env, p, inc.incident_id, "resolved", "t")
    P.continue_request(env, cid)
    r = build_receipt(env, cid)
    assert r["final_status"] == "Completed" and r["recovered_after_review"] and r["officer_review_completed"]
    assert r["held"] and any("replacement AI agent" in o["what"] for o in r["officer_review"])
    text = json.dumps(r)
    other = env.repo.get_citizen("C-1003")
    for secret in ("C-1003", other.full_name, "OFF-0101", "Khalid", "CROSS_CITIZEN", "MND-", "DENY_", "EVT-", "PRIVATE KEY",
                   inc.incident_id, "threshold", "rule_id"):
        assert secret not in text, secret


def test_receipt_api(tmp_path):
    from fastapi.testclient import TestClient
    from app.core.config import Settings
    from app.main import create_app
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), documents_dir=str(tmp_path / "d"), dev_mode=True,
                 dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        cid = c.post("/api/portal/requests", json={}).json()["case_id"]
        assert c.get(f"/api/portal/cases/{cid}/receipt").json()["case_id"] == cid
        assert c.get("/api/portal/cases/CASE-NOPE0000/receipt").status_code == 404
