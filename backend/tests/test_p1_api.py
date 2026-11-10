"""Phase 1: HTTP gateway, mandate/audit read APIs and dev-endpoint protection."""

from __future__ import annotations

import pytest

from app.core.config import ConfigurationError, Settings


def _post(c, path, signed):
    return c.post(path, json=signed.model_dump(mode="json"))


def test_authorize_endpoint_allows_signed_request(harness_client):
    c, h = harness_client
    r = _post(c, "/api/gateway/authorize", h.payment("500.00"))
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is True and body["reason_codes"] == ["ALLOW_WITHIN_MANDATE"]
    for f in ("decision_id", "human_readable_explanation", "policy_version", "mandate_id", "decision_latency_ms", "audit_reference"):
        assert body[f] is not None


def test_authorize_endpoint_denies_unauthorized_payment(harness_client):
    c, h = harness_client
    body = _post(c, "/api/gateway/authorize", h.payment("50000.00")).json()
    assert body["allowed"] is False and body["reason_codes"] == ["DENY_AMOUNT_EXCEEDS_LIMIT"]


def test_execute_endpoint_executes_allowed_read(harness_client):
    c, h = harness_client
    r = _post(c, "/api/gateway/execute", h.residency_read())
    assert r.status_code == 200
    assert r.json()["executed"] is True and r.json()["result"]["residency_status"] == "expiring_soon"


def test_execute_endpoint_returns_403_and_no_result_for_denial(harness_client):
    c, h = harness_client
    r = _post(c, "/api/gateway/execute", h.residency_read("C-1003"))
    assert r.status_code == 403
    assert r.json()["executed"] is False and r.json()["result"] is None


def test_browser_cannot_impersonate_agent_with_claimed_id(harness_client):
    """An unsigned or garbage-signed body with agent_id=AGT-PAY-001 gets nothing."""
    c, h = harness_client
    body = h.payment().model_dump(mode="json")
    body["signature"]["value"] = "A" * 86
    r = c.post("/api/gateway/execute", json=body)
    assert r.status_code == 403 and r.json()["decision"]["reason_codes"] == ["DENY_REQUEST_SIGNATURE_INVALID"]
    del body["signature"]
    assert c.post("/api/gateway/execute", json=body).status_code == 422


@pytest.mark.parametrize("mutate", [
    lambda b: b["request"].update(agent_id="payment-agent"),
    lambda b: b["request"].update(timestamp="2026-11-10T08:00:00"),       # naive timestamp
    lambda b: b["request"].update(nonce="short"),
    lambda b: b["request"].update(parameters={"amount": {"nested": 1}}),
    lambda b: b["request"].update(tool_name="__import__('os').system"),
    lambda b: b["request"].update(grant_all=True),
    lambda b: b["signature"].update(algorithm="RS256"),
    lambda b: b.update(request="not an object"),
])
def test_malformed_requests_rejected_with_422(harness_client, mutate):
    c, h = harness_client
    body = h.payment().model_dump(mode="json")
    mutate(body)
    r = c.post("/api/gateway/authorize", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_non_json_body_rejected(harness_client):
    c, _ = harness_client
    assert c.post("/api/gateway/authorize", content=b"{not json", headers={"Content-Type": "application/json"}).status_code == 422


def test_audit_endpoints_reflect_real_decisions(harness_client):
    c, h = harness_client
    _post(c, "/api/gateway/execute", h.residency_read())
    _post(c, "/api/gateway/execute", h.payment("50000.00"))
    events = c.get("/api/audit/events").json()
    assert events["count"] == 2 and events["allowed_count"] == 1 and events["denied_count"] == 1
    assert c.get("/api/audit/integrity").json()["valid"] is True


def test_mandates_endpoint_shows_verification(harness_client):
    c, h = harness_client
    items = c.get("/api/mandates").json()["items"]
    assert len(items) == 3 and all(i["verification"]["valid"] for i in items)
    pay = c.get("/api/mandates", params={"agent_id": "AGT-PAY-001"}).json()["items"][0]
    assert pay["mandate"]["amount_limit"] == {"amount": "500.00", "currency": "AED"}
    h.env.mandates.revoke(pay["mandate"]["mandate_id"], "test", h.clock())
    one = c.get(f"/api/mandates/{pay['mandate']['mandate_id']}").json()
    assert one["verification"]["effective_status"] == "revoked" and one["revoked"] is True
    assert c.get("/api/mandates/MND-NOPE-0000").status_code == 404


def test_public_endpoints_expose_no_private_keys(harness_client):
    c, h = harness_client
    from app.core.crypto import b64url_encode
    blob = "".join(c.get(p).text for p in ("/api/identity/keys", "/api/issuers", "/api/agents", "/api/mandates"))
    for key_id in ("KEY-AGT-PAY-001", "KEY-ISS-PAYMENTS-OFFICE"):
        assert b64url_encode(h.keys.private_key(key_id).private_bytes_raw()) not in blob
    assert "PRIVATE" not in blob
    agent = c.get("/api/agents/AGT-PAY-001").json()
    assert agent["identity_key_reference"]["provisioning_status"] == "provisioned"
    assert agent["identity_key_reference"]["public_key_fingerprint"].startswith("sha256:")


def test_no_key_generation_or_signing_endpoints(client):
    import re
    paths = {r.path for r in client.app.routes}
    # Key generation, signing, issuing and tampering are never exposed over HTTP.
    assert not [p for p in paths if re.search(r"/(sign|keygen|keys/generate|issue|tamper)(/|$)", p)], paths
    # Phase 4: revocation exists ONLY as an authenticated officer action.
    revoke_routes = [p for p in paths if re.search(r"/revoke(/|$)", p)]
    assert revoke_routes and all(p.startswith("/api/officer/") for p in revoke_routes), revoke_routes
    writable = {(r.path, m) for r in client.app.routes for m in getattr(r, "methods", set()) if m in {"POST", "PUT", "PATCH", "DELETE"}}
    non_officer = {w for w in writable if not w[0].startswith("/api/officer/")}
    assert non_officer == {("/api/gateway/authorize", "POST"), ("/api/gateway/execute", "POST"), ("/api/dev/scenarios/{key}/run", "POST"),
                           ("/api/workflow/scenarios/{key}/run", "POST"), ("/api/workflow/recovery/{case_id}/continue", "POST"),
                           ("/api/workflow/oversight-comparison", "POST"),
                           ("/api/evidence/business-model", "POST"),  # Phase 5: stateless assumption calculator
                           # Document Shield: dev-only upload/sample/adversarial test; officer-authenticated review
                           ("/api/documents", "POST"), ("/api/documents/samples/{key}", "POST"),
                           ("/api/documents/{doc_id}/adversarial-test", "POST"), ("/api/documents/{doc_id}/review", "POST"),
                           # Government AI Portal (fictional): all developer-mode only
                           ("/api/portal/requests", "POST"), ("/api/portal/scenes/incident", "POST"), ("/api/portal/demo/reset", "POST"),
                           ("/api/portal/cases/{case_id}/continue", "POST"), ("/api/portal/cases/{case_id}/documents", "POST"),
                           ("/api/portal/cases/{case_id}/documents/samples/{key}", "POST"),
                           ("/api/portal/cases/{case_id}/documents/{doc_id}/injection-test", "POST"),
                           # Phase 6 Attack Lab (dev-only, isolated environments)
                           ("/api/attack-lab/run", "POST"), ("/api/attack-lab/reset", "POST")}


# --- developer endpoints ---------------------------------------------------------

def test_dev_endpoints_disabled_by_default(client):
    r = client.post("/api/dev/scenarios/valid_authorization/run")
    assert r.status_code == 404 and r.json()["error"]["code"] == "DEV_MODE_DISABLED"
    assert client.get("/api/system/capabilities").json()["developer_demo_enabled"] is False


def test_dev_endpoints_loopback_only(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    # TestClient's host is "testclient", which is not in the default loopback list.
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path), dev_mode=True))) as c:
        assert c.get("/api/dev/scenarios").status_code == 403


def test_dev_endpoints_reject_cross_site_origin(dev_client):
    r = dev_client.post("/api/dev/scenarios/valid_authorization/run", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "DEV_ORIGIN_REJECTED"


@pytest.mark.parametrize("key, allowed, codes, executed", [
    ("valid_authorization", True, ["ALLOW_WITHIN_MANDATE"], True),
    ("valid_payment", True, ["ALLOW_WITHIN_MANDATE"], False),
    ("invalid_amount", False, ["DENY_AMOUNT_EXCEEDS_LIMIT"], False),
    ("wrong_recipient", False, ["DENY_RECIPIENT_NOT_ALLOWLISTED"], False),
    ("modified_mandate", False, ["DENY_SIGNATURE_INVALID"], False),
    ("expired_mandate", False, ["DENY_MANDATE_EXPIRED"], False),
    ("cross_citizen_record", False, ["DENY_SCOPE_VIOLATION"], False),
    ("replayed_request", False, ["DENY_REPLAYED_REQUEST"], False),
])
def test_dev_scenarios_use_real_gateway(dev_client, key, allowed, codes, executed):
    r = dev_client.post(f"/api/dev/scenarios/{key}/run", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["allowed"] is allowed and body["decision"]["reason_codes"] == codes
    assert body["executed"] is executed
    assert body["development_only"] is True
    events = dev_client.get("/api/audit/events").json()["items"]
    assert events[0]["event_id"] == body["decision"]["audit_reference"]
    assert events[0]["evidence_metadata"]["origin"] == f"dev_scenario:{key}"


def test_dev_scenario_unknown_key(dev_client):
    assert dev_client.post("/api/dev/scenarios/nope_nope/run").status_code == 404


def test_production_mode_refused():
    with pytest.raises(ConfigurationError):
        Settings(environment="production")


def test_cors_allows_post_from_local_frontend_only(client):
    ok = client.options("/api/gateway/authorize", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/gateway/authorize", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
