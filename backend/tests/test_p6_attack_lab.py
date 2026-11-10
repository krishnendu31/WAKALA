"""Phase 6 · Milestone 2 — Attack Lab: real isolated execution, baseline isolation, honest outcomes, determinism."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.attack_lab import service as L
from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def api(tmp_path):
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), documents_dir=str(tmp_path / "d"), dev_mode=True,
                 dev_allowed_hosts=("testclient",), console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        yield c, c.app.state.env


@pytest.fixture(scope="module")
def all_results():
    return {s.key: L.run_scenario(s.key) for s in L.SCENARIOS}


def test_eight_scenarios_a_to_h():
    assert [s.letter for s in L.SCENARIOS] == list("ABCDEFGH")


def test_wakala_executes_none_of_the_attacks(all_results):
    for key, r in all_results.items():
        for a in r["wakala"]["attempts"]:
            assert a["allowed"] is False and a["executed"] is False, key
            assert not a["data_returned"] and not a["state_modified"], key
            assert a["reason_codes"] and a["plain_english"].startswith("Blocked"), key
        assert r["evidence"]["audit_chain_valid"] and r["evidence"]["events"], key
        assert {e["event_id"] for e in r["evidence"]["events"]} >= {a["audit_reference"] for a in r["wakala"]["attempts"]}


def test_exact_reasons(all_results):
    codes = {k: {c for a in r["wakala"]["attempts"] for c in a["reason_codes"]} for k, r in all_results.items()}
    assert "DENY_CASE_SCOPE_VIOLATION" in codes["cross_citizen"]
    assert "DENY_DELEGATION_EXPANDS_AUTHORITY" in codes["delegation_escalation"]
    assert codes["replay"] == {"DENY_REPLAYED_REQUEST"}
    assert "DENY_MANDATE_EXPIRED" in codes["expired"]
    assert "DENY_REQUEST_SIGNATURE_INVALID" in codes["tampered_signature"]
    assert {"DENY_AMOUNT_EXCEEDS_LIMIT", "DENY_RECIPIENT_NOT_ALLOWLISTED"} <= codes["large_transfer"]
    assert "DENY_PARENT_MANDATE_REVOKED" in codes["revoked_parent"]
    assert "not another citizen's record (C-1003)" in all_results["cross_citizen"]["wakala"]["attempts"][0]["plain_english"]
    assert "more authority" in all_results["delegation_escalation"]["wakala"]["attempts"][0]["plain_english"]


def test_baseline_outcomes_are_reported_honestly(all_results):
    executed = {k for k, r in all_results.items() if r["outcome"]["baseline_executed"]}
    assert executed == {"cross_citizen", "replay", "expired", "tampered_signature", "large_transfer", "pdf_injection", "revoked_parent"}
    b = all_results["delegation_escalation"]
    assert b["verdict"] == "Denied in both environments." and not b["outcome"]["baseline_executed"]
    assert all_results["cross_citizen"]["baseline"]["attempts"][0]["data_returned"]  # baseline returned another citizen's record
    g = all_results["pdf_injection"]
    assert [a["executed"] for a in g["baseline"]["attempts"]] == [True, False]  # role check stops the Residency Agent's attempt
    ds = g["wakala"]["document_shield"]
    assert ds["document_disposition"] == "QUARANTINED" and not ds["agent_received_content"]
    assert ds["ledger_rows_before"] == ds["ledger_rows_after"]


def test_same_seed_same_outcome():
    a, b = L.run_scenario("large_transfer", seed=7), L.run_scenario("large_transfer", seed=7)
    assert a["outcome_fingerprint"] == b["outcome_fingerprint"] and a["outcome"] == b["outcome"]


def test_lab_never_touches_the_live_environment(api):
    c, env = api
    counts = lambda: {t: env.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]  # noqa: E731
                      for t in ("audit_events", "renewal_cases", "payment_ledger", "mandates", "incidents", "delegations")}
    before = counts()
    r = c.post("/api/attack-lab/run", json={"scenarios": "all", "seed": 2026}).json()
    assert counts() == before  # only attack_lab_runs gained a row
    assert r["summary"] == {"scenarios": 8, "baseline_executed": 7, "wakala_executed": 0, "denied_in_both": 1}
    got = c.get(f"/api/attack-lab/runs/{r['run_id']}").json()
    assert got["run_id"] == r["run_id"] and len(got["results"]) == 8
    s1 = c.get("/api/attack-lab/runs").json()["session_id"]
    assert c.post("/api/attack-lab/reset").json()["session_id"] != s1
    assert c.get("/api/attack-lab/runs").json()["runs"]  # reset deletes nothing


def test_lab_requires_dev_mode_and_local_client(tmp_path):
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), console_allowed_hosts=("testclient",)))) as c:
        assert c.post("/api/attack-lab/run", json={}).status_code in (403, 404)
        assert c.get("/api/attack-lab/scenarios").status_code in (403, 404)
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k2"), dev_mode=True,
                                        dev_allowed_hosts=("testclient",)))) as c:
        assert c.get("/api/attack-lab/scenarios").status_code == 403  # not a local console client


def test_lab_does_not_reimplement_authorization():
    src = Path(L.__file__).read_text(encoding="utf-8")
    mods = {n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom) and n.module}
    assert "app.evaluation.harness" in mods and "app.evaluation.baseline" in mods
    assert "verify_signature" not in src and "check_scope" not in src and "def authorize" not in src
