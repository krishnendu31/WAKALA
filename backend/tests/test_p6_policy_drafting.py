"""Phase 6 · Milestone 6 — Policy drafting: validation, owner approval, issuer signature, never enforced or replacing."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

GOOD = "The insurance agent may verify coverage only for the citizen in the current case, and no more than five times."


@pytest.fixture()
def api(tmp_path):
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), documents_dir=str(tmp_path / "d"), dev_mode=True,
                 dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        env = c.app.state.env
        for oid in ("OFF-0101", "OFF-0202", "OFF-0900", "OFF-0950"):
            env.officers._store_hash(oid, f"pw-{oid}")
        yield c, env


def h(c, oid):
    tok = c.post("/api/officer/session", json={"officer_id": oid, "password": f"pw-{oid}"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_structured_draft_from_plain_language(api):
    c, _ = api
    r = c.post("/api/policies/drafts", json={"text": GOOD}).json()
    assert r["valid"] and r["status"] == "draft" and r["drafted_by"].startswith("deterministic")
    assert r["draft"] | {} == {**r["draft"], "agent_role": "insurance", "permitted_action": "insurance.verify_case_eligibility",
                               "citizen_scope": "current_case_citizen", "case_scope": "current_case_only", "action_limit": 5,
                               "receiving_service": "insurance"}
    assert "at most 5 times" in r["human_summary"] and "NOT ENFORCED" in r["enforcement"]


@pytest.mark.parametrize("text,needle", [
    ("The insurance agent may collect the fee for any citizen, no more than two times.", "case-bound"),
    ("The insurance agent may verify coverage only for the citizen in the current case, no more than five times, and email the results.",
     "Unrecognised wording"),
    ("The payment agent may collect the fee only for the citizen in the current case, no more than one time.", "approval"),
    ("The insurance agent may verify coverage only for the citizen in the current case, no more than 50 times.", "between 1 and 20"),
    ("The insurance agent may verify coverage only for the citizen in the current case, no more than five times, within 6 hours.",
     "exceeds the 120-min"),
])
def test_invalid_or_conflicting_drafts_are_refused(api, text, needle):
    c, _ = api
    r = c.post("/api/policies/drafts", json={"text": text}).json()
    assert r["status"] == "draft_invalid" and not r["valid"]
    assert any(needle in m for m in r["validation"]["errors"] + r["validation"]["conflicts"])


def test_only_the_owning_entity_officer_can_approve_and_it_is_signed(api):
    c, env = api
    pid = c.post("/api/policies/drafts", json={"text": GOOD}).json()["policy_id"]
    assert c.post(f"/api/policies/{pid}/decision", json={"approve": True}).status_code == 401  # unauthenticated
    assert c.post(f"/api/policies/{pid}/decision", json={"approve": True}, headers=h(c, "OFF-0950")).status_code == 403  # auditor
    r = c.post(f"/api/policies/{pid}/decision", json={"approve": True}, headers=h(c, "OFF-0101"))  # residency entity, wrong owner
    assert r.status_code == 403 and r.json()["error"]["code"] == "OUT_OF_ENTITY_SCOPE"
    r = c.post(f"/api/policies/{pid}/decision", json={"approve": True, "note": "ok"}, headers=h(c, "OFF-0202")).json()
    assert r["status"] == "approved_signed_not_enforced" and r["signature"]["issuer_id"] == "ISS-INSURANCE-REG"
    v = c.get(f"/api/policies/{pid}/verify").json()
    assert v["valid"] and v["signature_valid"] and v["body_matches_stored_draft"]
    # tampering with the stored draft breaks verification
    rec = json.loads(env.db.query("SELECT payload FROM policy_drafts WHERE policy_id = ?", (pid,))[0]["payload"])
    rec["draft"]["action_limit"] = 20
    with env.db.transaction() as conn:
        conn.execute("UPDATE policy_drafts SET payload = ? WHERE policy_id = ?", (json.dumps(rec), pid))
    assert c.get(f"/api/policies/{pid}/verify").json()["valid"] is False
    assert {"officer.policy_decision", "officer.action_refused"} <= {e.action for e in env.audit.list(50)}


def test_invalid_draft_cannot_be_approved_and_approved_is_never_replaced(api):
    c, _ = api
    bad = c.post("/api/policies/drafts", json={"text": "The insurance agent may collect the fee for any citizen."}).json()
    assert c.post(f"/api/policies/{bad['policy_id']}/decision", json={"approve": True}, headers=h(c, "OFF-0202")).status_code == 409
    pid = c.post("/api/policies/drafts", json={"text": GOOD}).json()["policy_id"]
    c.post(f"/api/policies/{pid}/decision", json={"approve": True}, headers=h(c, "OFF-0202"))
    again = c.post("/api/policies/drafts", json={"text": GOOD}).json()
    assert again["status"] == "draft_invalid" and any("never silently replace" in x for x in again["validation"]["conflicts"])


def test_approval_does_not_change_live_authorization(api):
    c, env = api
    snap = lambda: (env.gateway.policy_snapshot(env.clock()), env.db.query("SELECT COUNT(*) AS n FROM mandates")[0]["n"])  # noqa: E731
    before = snap()
    pid = c.post("/api/policies/drafts", json={"text": GOOD}).json()["policy_id"]
    c.post(f"/api/policies/{pid}/decision", json={"approve": True}, headers=h(c, "OFF-0202"))
    assert snap() == before


def test_drafting_requires_dev_mode(tmp_path):
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), console_allowed_hosts=("testclient",)))) as c:
        assert c.post("/api/policies/drafts", json={"text": GOOD}).status_code == 404
