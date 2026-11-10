"""Phase 2: weak baseline isolation, agent adapters and workflow API protection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents import HttpGatewayTransport, LLMToolUseAdapter, export_tool_definitions
from app.agents.interface import AgentIdentity, SigningAgentAdapter
from app.agents.simulated import SimulatedResidencyAgent
from app.core.config import Settings
from app.main import create_app
from app.workflow.baseline import WeakRoleBaseline
from app.workflow.intake import open_case
from app.workflow.scenarios import run_workflow
from tests.conftest import make_harness


def test_baseline_and_wakala_differ_on_same_request(h):
    run = run_workflow(h.env, "baseline_comparison")
    b = run.baseline
    assert b.label == "INTENTIONALLY WEAK TEST-ONLY BASELINE"
    assert b.baseline_allowed is True and b.baseline_returned_data["citizen_ref"] == "C-1003"
    assert b.wakala_allowed is False and b.wakala_returned_data is None
    assert set(b.wakala_reason_codes) == {"DENY_SCOPE_VIOLATION", "DENY_CASE_SCOPE_VIOLATION"}
    assert b.wakala_audit_reference in {e.event_id for e in run.audit_events}


def test_baseline_is_isolated_from_wakala_state(h):
    tables = [r["name"] for r in h.env.db.query("SELECT name FROM sqlite_master WHERE type='table'")]
    before = {t: h.env.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in tables}
    head = h.env.audit.verify().head_hash
    baseline = WeakRoleBaseline()
    baseline.read_insurance("AGT-INS-001", "C-1003", h.clock())
    baseline.read_insurance("AGT-PAY-001", "C-1003", h.clock())  # no role -> refused by baseline
    after = {t: h.env.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in tables}
    assert before == after and h.env.audit.verify().head_hash == head
    assert [e["allowed"] for e in baseline.log] == [True, False]


def test_baseline_cannot_reach_wakala_services():
    import inspect

    import app.workflow.baseline as mod
    src = inspect.getsource(mod)
    for forbidden in ("gateway", "ProtectedServices", "Database(", "mandates", "audit"):
        assert forbidden not in src.split('"""', 2)[2], forbidden


def test_http_transport_gets_identical_enforcement(harness_client):
    c, h = harness_client
    case = open_case(h.env, "C-1001")

    def post(url, body):
        r = c.post(url.replace("http://testserver", ""), json=body)
        return r.status_code, r.json()

    agent = SigningAgentAdapter(AgentIdentity("AGT-RES-001", "KEY-AGT-RES-001"), h.keys.private_key("KEY-AGT-RES-001"),
                                HttpGatewayTransport("http://testserver", post), h.clock)
    _, ok = agent.submit(SimulatedResidencyAgent.register(case), case, origin="http")
    assert ok.decision.allowed and ok.executed and ok.result["case_state"] == "VERIFYING"
    _, bad = agent.submit(SimulatedResidencyAgent.complete(case), case, origin="http")
    assert not bad.decision.allowed and "DENY_CASE_STATE_INVALID" in [c.value for c in bad.decision.reason_codes]


def test_llm_adapter_is_interface_only(h):
    tools = export_tool_definitions(h.env.tools)
    assert {t["name"] for t in tools} == {"residency.register_renewal_case", "residency.check_eligibility",
                                          "insurance.verify_case_eligibility", "payment.collect_renewal_fee",
                                          "residency.complete_renewal"}
    with pytest.raises(NotImplementedError):
        LLMToolUseAdapter().next_call(open_case(h.env, "C-1001"), tools, [])


# --- API protection --------------------------------------------------------------------------

def _app(tmp_path, **kw):
    holder = {}

    def factory(settings):
        holder["h"] = make_harness(settings)
        return holder["h"].env

    settings = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path), **kw)
    return create_app(settings, env_factory=factory), holder


def test_workflow_run_requires_dev_mode(tmp_path):
    app, _ = _app(tmp_path, console_allowed_hosts=("testclient",))
    with TestClient(app) as c:
        r = c.post("/api/workflow/scenarios/legitimate_renewal/run")
        assert r.status_code == 404 and r.json()["error"]["code"] == "DEV_MODE_DISABLED"
        assert c.get("/api/workflow/cases").json() == []


def test_workflow_endpoints_local_clients_only(tmp_path):
    app, _ = _app(tmp_path, dev_mode=True, dev_allowed_hosts=("testclient",))  # console hosts = loopback only
    with TestClient(app) as c:
        assert c.get("/api/workflow/cases").status_code == 403
        assert c.post("/api/workflow/scenarios/legitimate_renewal/run").status_code == 403


def test_workflow_run_rejects_cross_site_origin(tmp_path):
    app, _ = _app(tmp_path, dev_mode=True, dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(app) as c:
        r = c.post("/api/workflow/scenarios/legitimate_renewal/run", headers={"Origin": "https://evil.example"})
        assert r.status_code == 403


def test_workflow_api_end_to_end(tmp_path):
    app, holder = _app(tmp_path, dev_mode=True, dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(app) as c:
        run = c.post("/api/workflow/scenarios/legitimate_renewal/run", json={"citizen_ref": "C-1001"}).json()
        assert run["case"]["state"] == "COMPLETED" and run["simulated_agents"] is True
        detail = c.get(f"/api/workflow/cases/{run['case']['case_id']}").json()
        assert detail["case"]["state"] == "COMPLETED" and len(detail["ledger"]) == 1
        assert {e["event_id"] for e in detail["audit_events"]} == {e["event_id"] for e in run["audit_events"]}
        b = c.post("/api/workflow/scenarios/wrong_citizen/run").json()
        assert b["steps"][2]["decision"]["allowed"] is False and b["steps"][2]["result"] is None
        assert "SYNTH-INS-200301" not in c.get(f"/api/workflow/cases/{b['case']['case_id']}").text
        assert c.post("/api/workflow/scenarios/nope_nope/run").status_code == 404
        assert c.post("/api/workflow/scenarios/legitimate_renewal/run", json={"citizen_ref": "C-9999"}).status_code == 404
        assert c.post("/api/workflow/scenarios/legitimate_renewal/run", json={"citizen_ref": "Mariam"}).status_code == 422
        assert c.get("/api/workflow/cases/CASE-NOPE0000").status_code == 404
        assert len(c.get("/api/workflow/tools").json()) == 5
        assert holder["h"].env.audit.verify().valid


def test_no_direct_service_endpoints(client):
    paths = {r.path for r in client.app.routes}
    assert not [p for p in paths if p.startswith("/api/services/") or "collect" in p or "ledger/" in p]
