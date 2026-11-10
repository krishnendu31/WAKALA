"""Phase 6 · Milestone 5 — Shadow Mode is watch-only, uses the real policy, and predicts enforcement."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.shadow import service as S


def test_shadow_never_changes_the_observed_environment():
    r = S.run_shadow()
    assert r["isolation_check"]["source_state_unchanged_during_observation"]
    assert r["isolation_check"]["counts_before"] == r["isolation_check"]["counts_after"]
    assert "counterfactual" in r["note"]


def test_shadow_report_contents():
    rep = S.run_shadow()["report"]
    assert rep["events_observed"] == 11 and rep["would_allow"] + rep["would_deny"] == 11
    assert rep["would_block_source_allowed"] == 3 and rep["false_denial_candidates"] == ["complete_late"]
    assert rep["policy_conflicts"] and "lifetime" in rep["policy_conflicts"][0]["conflict"]
    assert any("do not simply disable expiry" in s for s in rep["next_steps"])


def test_shadow_prediction_matches_separate_enforcement():
    d = S.run_demo()
    assert d["prediction_agreement"] == {"matched": 11, "total": 11, "mismatches": []}
    assert d["enforcement"]["audit_chain_valid"] and "separate" in d["enforcement"]["environment"]
    shadow_codes = [e["reason_codes"] for e in d["shadow"]["events"] if e["wakala_would"] == "deny"]
    enforced_codes = [e["reason_codes"] for e in d["enforcement"]["events"] if not e["allowed"]]
    assert [set(c) for c in shadow_codes] == [set(c) for c in enforced_codes]  # same policy, same reasons


def test_shadow_evaluator_has_no_execution_path():
    src = Path(S.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ShadowEvaluator")
    calls = {n.func.attr for n in ast.walk(cls) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"execute", "dispatch", "append", "check_and_record", "observe", "execute_approved"}
    names = {n.id for n in ast.walk(cls) if isinstance(n, ast.Name)}
    assert "authorize" in names and "authenticate" in names  # the same policy and authentication functions as the gateway


def test_shadow_api_dev_only(tmp_path):
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), console_allowed_hosts=("testclient",)))) as c:
        assert c.post("/api/shadow/demo").status_code in (403, 404)
    s = Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k2"), dev_mode=True, dev_allowed_hosts=("testclient",),
                 console_allowed_hosts=("testclient",))
    with TestClient(create_app(s)) as c:
        env = c.app.state.env
        before = env.audit.verify().event_count
        assert c.post("/api/shadow/demo").json()["prediction_agreement"]["matched"] == 11
        assert env.audit.verify().event_count == before  # live app untouched
