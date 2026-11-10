"""Phase 7 — consolidated security invariants, exercised through the real gateway in isolated environments.

Each invariant is checked on the protected records themselves (ledger, renewals, case prerequisites/state,
mandates, audit chain), not only on the decision returned to the caller.
"""

from __future__ import annotations

import ast
import dataclasses
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.attack_lab.service import _item
from app.core.config import Settings
from app.documents.samples import hidden_payment_injection
from app.documents.service import DocumentStore
from app.evaluation.dataset import CATEGORIES
from app.evaluation.environment import isolated_env
from app.evaluation.harness import WakalaHarness
from app.main import create_app
from app.portal import agent as A

APP = Path(__file__).resolve().parents[1] / "app"


def _protected(env):  # noqa: ANN001, ANN202
    q = lambda t: env.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]  # noqa: E731
    return {"ledger": q("payment_ledger"), "renewals": q("residency_renewals"),
            "cases": sorted((c.case_id, c.state.value, tuple(c.completed_prerequisites)) for c in env.cases.list(1000))}


UNAUTHORIZED = [(c.key, v) for c in CATEGORIES if c.label == "unauthorized" and c.family == "agent_request" for v in c.variants]


@pytest.mark.parametrize("category,variant", UNAUTHORIZED)
def test_every_unauthorized_variant_is_denied_and_changes_no_protected_record(category, variant):
    """Covers: replay, delegation expansion, wrong citizen, wrong case (isolation), expired, revoked, revoked ancestor,
    forged identity, tampered signature, forged/self-signed child mandates, excessive amounts, wrong recipients."""
    kw = {"target_citizen": variant} if category == "wrong_citizen_access" and variant.startswith("C-") else {}
    if category == "wrong_citizen_access" and not variant.startswith("C-"):
        kw = {"target_citizen": "C-1002"}
    if category in ("excessive_payment",):
        kw["params"] = {"amount": variant}
    if category == "unauthorized_payment_recipient":
        kw["params"] = {"recipient": variant}
    from app.evaluation.dataset import VARIANT_STAGE
    if (category, variant) in VARIANT_STAGE:
        kw["stage"] = VARIANT_STAGE[(category, variant)]
    with isolated_env("memory") as (env, clock, keys):
        h = WakalaHarness(env, clock, keys, "C")
        item = _item(category, variant, **kw)
        # snapshot AFTER staging: stage once, then compare around the attack (harness stages inside evaluate)
        r = h.evaluate(item)
        assert r.get("harness_error") is None, r
        assert r["allowed"] is False and r["executed"] is False, (category, variant, r["reason_codes"])
        assert r["state_mutated"] is False, (category, variant)
        assert r["audit_complete"] and env.audit.verify().valid


def test_agents_cannot_issue_their_own_authority():
    # 1) a child mandate signed with a key that is not a trusted issuer is rejected at use
    with isolated_env("memory") as (env, clock, keys):
        h = WakalaHarness(env, clock, keys, "C")
        r = h.evaluate(_item("forged_child_mandate", "attacker_signed_child"))
        assert not r["allowed"] and {"DENY_ISSUER_UNTRUSTED", "DENY_SIGNATURE_INVALID"} & set(r["reason_codes"])
    # 2) the model-driven agent has no tool that issues/edits mandates, permissions, ownership, gateway or officers
    assert not any(w in name for name in A.TOOL_NAMES for w in ("mandate", "permission", "issue", "officer", "gateway", "owner"))
    # 3) no HTTP route issues mandates for an agent outside developer mode
    with tempfile.TemporaryDirectory() as d:
        app = create_app(Settings(db_path=":memory:", dev_keys_dir=d))
    writable = {(r.path, m) for r in app.routes for m in getattr(r, "methods", set()) if m in ("POST", "PUT", "PATCH", "DELETE")}
    assert not [p for p, _ in writable if "mandate" in p and "/officer/" not in p and "/dev/" not in p], writable


def test_document_shield_quarantine_is_enforced():
    with isolated_env("memory") as (env, _c, _k), tempfile.TemporaryDirectory() as d:
        env.settings = dataclasses.replace(env.settings, documents_dir=d)
        store = DocumentStore(env)
        rec = store.ingest(hidden_payment_injection(), "x.pdf", "test")
        assert rec["disposition"] == "QUARANTINED"
        view = store.agent_view(rec["document_id"])
        assert view["released"] is False and view["content"] is None
        assert "50000" not in str(view)


def test_protected_services_are_reachable_only_through_the_gateway():
    """No API module or agent module calls a protected-service mutation directly."""
    mutations = {"register_renewal_case", "collect_renewal_fee", "complete_renewal", "record_payment", "commission_task"}
    offenders = []
    for path in [*APP.joinpath("api").glob("*.py"), APP / "portal" / "agent.py", APP / "documents" / "agents.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in mutations:
                chain = ast.unparse(n.func.value)
                if "services" in chain or "ProtectedServices" in chain:
                    offenders.append(f"{path.name}: {ast.unparse(n.func)}")
    assert offenders == []


def test_officer_interventions_require_authenticated_authorization(tmp_path):
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        env = c.app.state.env
        env.officers._store_hash("OFF-0950", "pw")
        posts = [r.path for r in c.app.routes if r.path.startswith("/api/officer/") and "POST" in getattr(r, "methods", set())
                 and not r.path.endswith("/session")]
        assert len(posts) >= 10
        fill = lambda p: (p.replace("{incident_id}", "INC-AAAAAAAA").replace("{mandate_id}", "MND-RES-AAAAAAAA")  # noqa: E731
                          .replace("{case_id}", "CASE-AAAAAAAA").replace("{approval_id}", "APR-AAAAAAAA").replace("{agent_id}", "AGT-INS-001"))
        for p in posts:
            assert c.post(fill(p), json={}).status_code == 401, p                       # no session
            assert c.post(fill(p), json={}, headers={"Authorization": "Bearer forged"}).status_code == 401, p
        tok = c.post("/api/officer/session", json={"officer_id": "OFF-0950", "password": "pw"}).json()["token"]
        r = c.post("/api/officer/agents/AGT-INS-001/suspend", json={"reason": "auditor tries"}, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403 and env.repo.get_agent("AGT-INS-001").status == "active"  # auditor is read-only


def test_audit_records_reflect_real_operations():
    """Every ledger row and renewal traces to an allowed decision with an 'executed' outcome; the chain verifies."""
    with isolated_env("memory") as (env, clock, keys), tempfile.TemporaryDirectory() as d:
        env.settings = dataclasses.replace(env.settings, documents_dir=d)
        from app.portal import service as P
        for c in ("C-1001", "C-1002"):
            P.start_request(env, c)
        P.start_incident_scene(env)
        import json
        events = {e["event_id"]: e for e in (json.loads(r["payload"]) for r in env.db.query("SELECT payload FROM audit_events"))}
        executed = [e for e in events.values() if str(e["action"]).endswith(":execution")
                    and e["evidence_metadata"].get("execution_status") == "executed"]
        decision_of = {e["evidence_metadata"]["decision_event"] for e in executed}
        assert all(events[d]["decision"] == "allowed" for d in decision_of)
        for row in env.db.query("SELECT decision_id FROM payment_ledger"):
            assert any(e.get("decision_id") == row["decision_id"] for e in executed)
        pay_exec = [e for e in executed if e["action"] == "payment.collect_renewal_fee:execution"]
        assert len(pay_exec) == env.db.query("SELECT COUNT(*) AS n FROM payment_ledger")[0]["n"]
        assert not any(e["decision"] == "denied" and e["evidence_metadata"].get("execution_status") == "executed" for e in events.values())
        assert env.audit.verify().valid


def test_separate_citizen_cases_remain_isolated():
    with isolated_env("memory") as (env, clock, keys), tempfile.TemporaryDirectory() as d:
        env.settings = dataclasses.replace(env.settings, documents_dir=d)
        from app.portal import service as P
        s = P.start_incident_scene(env)
        other = env.cases.get(s["unrelated_case_id"])
        assert env.assurance.gating_incident(other.case_id) is None
        assert not set(other.mandate_refs.values()) & env.assurance.suspensions.active_ids()
        assert P.continue_request(env, other.case_id)["status"] == "completed"
        assert env.cases.get(s["case_id"]).state.value == "PAUSED_FOR_REVIEW"
