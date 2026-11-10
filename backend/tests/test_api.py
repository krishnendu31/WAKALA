"""HTTP API behaviour, error envelopes, CORS and honesty of capability reporting."""

from __future__ import annotations

import pytest

from app.core.authorization import FailClosedEngine
from app.core.config import ConfigurationError, parse_cors_origins
from app.schemas import ActionRequest, ReasonCode


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["synthetic_data_only"] is True
    assert r.headers["x-content-type-options"] == "nosniff"


def test_list_agents(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["synthetic_data"] is True
    assert [a["agent_id"] for a in body["items"]] == ["AGT-RES-001", "AGT-INS-001", "AGT-PAY-001"]


def test_get_agent(client):
    r = client.get("/api/agents/AGT-PAY-001")
    assert r.status_code == 200
    assert r.json()["risk_level"] == "high"


def test_unknown_agent_404(client):
    r = client.get("/api/agents/AGT-XYZ-999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "AGENT_NOT_FOUND"


@pytest.mark.parametrize("bad", ["payment-agent", "AGT-PAY-1", "AGT-PAY-001;DROP", "agt-pay-001"])
def test_malformed_agent_id_422(client, bad):
    r = client.get(f"/api/agents/{bad}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_citizens(client):
    body = client.get("/api/citizens").json()
    assert body["count"] == 5
    assert body["items"][0]["citizen_ref"] == "C-1001"


def test_services_fee(client):
    (svc,) = client.get("/api/services").json()["items"]
    assert svc["fee"] == {"amount": "500.00", "currency": "AED"}


def test_scenarios_include_documents(client):
    body = client.get("/api/scenarios").json()
    assert body["count"] == 2
    injected = body["items"][1]
    assert injected["scenario"]["category"] == "prompt_injection"
    assert injected["scenario"]["execution_enabled"] is False
    assert injected["document"]["contains_injected_instruction"] is True
    assert len(injected["document"]["sha256"]) == 64


def test_audit_events_are_honestly_empty(client):
    # Startup provisions keys and mandates but makes no authorization decisions.
    body = client.get("/api/audit/events").json()
    assert body == {"items": [], "count": 0, "allowed_count": 0, "denied_count": 0,
                    "synthetic_data": True, "enforcement_engine_connected": True}


def test_capabilities_are_honest(client):
    body = client.get("/api/system/capabilities").json()
    caps = {c["key"]: c for c in body["capabilities"]}
    assert body["current_phase"] == 2
    assert body["enforcement_engine_connected"] is True
    assert body["external_llm_dependency"] is False
    assert body["developer_demo_enabled"] is False
    for implemented in ("authorization_gateway", "signed_mandates", "agent_identity_keys", "audit_trail", "protected_execution",
                        "mock_government_services", "case_bound_authority"):
        assert caps[implemented]["status"] == "implemented"
    for planned in ("non_expanding_delegation", "human_intervention", "attack_simulation", "measured_benchmarks"):
        assert caps[planned]["status"] == "planned"
    assert body["implemented_count"] + body["planned_count"] == len(caps)


def test_contract_schema_endpoint(client):
    assert set(client.get("/api/schemas").json()["contracts"]) == {
        "AgentPassport", "DigitalMandate", "TrustedIssuer", "ActionRequest", "SignedActionRequest",
        "AuthorizationDecision", "AuditEvent"}
    schema = client.get("/api/schemas/DigitalMandate").json()
    assert "recipient_allowlist" in schema["properties"]
    assert schema["additionalProperties"] is False
    assert client.get("/api/schemas/Nope").status_code == 404


def test_cors_allows_local_frontend_only(client):
    ok = client.get("/api/agents", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    evil = client.get("/api/agents", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers


def test_registry_api_rejects_writes(client):
    assert client.post("/api/agents", json={}).status_code == 405
    assert client.delete("/api/agents/AGT-PAY-001").status_code == 405


def test_non_local_cors_configuration_refused():
    with pytest.raises(ConfigurationError):
        parse_cors_origins("https://wakala.example.com")
    assert parse_cors_origins("http://127.0.0.1:3000") == ("http://127.0.0.1:3000",)


def test_fail_closed_fallback_engine_denies(action_payload):
    decision = FailClosedEngine().decide(ActionRequest.model_validate(action_payload), identity=None, mandates=[])
    assert decision.allowed is False
    assert decision.reason_codes == [ReasonCode.DENY_ENGINE_NOT_CONNECTED]
