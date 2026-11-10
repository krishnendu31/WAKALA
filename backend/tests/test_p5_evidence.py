"""Phase 5: benchmark reproducibility, metric correctness, isolation, honesty of the evidence and dashboard,
credential hardening and the monitoring fixes found by the benchmark."""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_DEV_KEYS_DIR, DEFAULT_EVIDENCE_DIR, Settings
from app.evaluation import baseline as baseline_mod
from app.evaluation.business import ASSUMPTION_NOTES, BusinessAssumptions, calculate
from app.evaluation.dataset import CATEGORIES, CATEGORY, DatasetConfig, digest, generate
from app.evaluation.environment import IsolatedKeys, isolated_env, stats
from app.evaluation.metrics import rate, summarize
from app.evaluation.security import run_security
from app.evaluation.stress import concurrency

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(DEFAULT_EVIDENCE_DIR)
SMALL = DatasetConfig(seed=7, size=len(CATEGORIES) * 2)


@pytest.fixture(scope="module")
def small_run():
    return run_security(SMALL)


# --- dataset ------------------------------------------------------------------------------------
def test_dataset_is_reproducible_and_labeled_from_categories():
    a, b = generate(DatasetConfig(seed=11, size=1000)), generate(DatasetConfig(seed=11, size=1000))
    assert digest(a) == digest(b) and [asdict(x) for x in a] == [asdict(x) for x in b]
    assert digest(generate(DatasetConfig(seed=12, size=1000))) != digest(a)
    assert len(a) == 1000 and len({x.item_id for x in a}) == 1000
    assert {x.category for x in a} == {c.key for c in CATEGORIES}  # every category present
    assert all(x.label == CATEGORY[x.category].label for x in a)
    assert {x.label for x in a} == {"legitimate", "unauthorized"}
    with pytest.raises(ValueError):
        generate(DatasetConfig(size=3))


def test_default_evidence_dataset_size_is_at_least_1000():
    assert DatasetConfig().size >= 1000


# --- metrics ------------------------------------------------------------------------------------------
def _rec(cat: str, **kw):
    base = {"item_id": "REQ-1", "category": cat, "label": CATEGORY[cat].label, "applicable": True, "allowed": False,
            "executed": False, "held": False, "reason_codes": ["X"], "state_mutated": False, "protective_pause": False,
            "audit_complete": True, "detected_any": False, "detected_specific": False, "rules": []}
    return {**base, **kw}


def test_metric_denominators_exclude_not_applicable_and_errors():
    records = [
        _rec("legitimate_fee_payment", allowed=True, executed=True),
        _rec("legitimate_fee_payment"),  # false denial
        _rec("excessive_payment"), _rec("excessive_payment", allowed=True, executed=True, state_mutated=True),
        _rec("forged_child_mandate", applicable=False),
        _rec("revoked_mandate", harness_error="setup failed"),
    ]
    s = summarize("T", records)
    assert s["requests_in_dataset"] == 6 and s["requests_evaluated"] == 4 and s["not_applicable"] == 1
    assert s["legitimate_incorrectly_denied"] == {"numerator": 1, "denominator": 2, "rate": 0.5}
    assert s["unauthorized_operations_executed"] == {"numerator": 1, "denominator": 2, "rate": 0.5}
    assert s["unauthorized_operations_prevented"]["numerator"] == 1
    assert s["revocation_effectiveness"] == {"numerator": 0, "denominator": 0, "rate": None}  # errored item excluded
    assert len(s["harness_errors"]) == 1 and s["unauthorized_state_mutations"]["numerator"] == 1
    assert rate(0, 0)["rate"] is None and rate(3, 4)["rate"] == 0.75


def test_stats_percentiles():
    s = stats([float(i) for i in range(1, 101)])
    assert (s["n"], s["median_ms"], s["p95_ms"], s["p99_ms"], s["min_ms"], s["max_ms"]) == (100, 50.5, 95.0, 99.0, 1.0, 100.0)


# --- security benchmark behaviour ----------------------------------------------------------------------------
def test_wakala_classifies_every_category_correctly(small_run):
    for cfg in ("C",):
        rows = small_run["outcomes"][cfg]
        assert not [r for r in rows if "harness_error" in r]
        for r in rows:
            if r["label"] == "legitimate":
                assert r["executed"], (r["category"], r["reason_codes"])
            else:
                assert not r["executed"] and not r["allowed"], (r["category"], r["reason_codes"])


def test_b_marks_delegation_only_not_applicable_and_prevents_the_rest(small_run):
    rows = small_run["outcomes"]["B"]
    for r in rows:
        if CATEGORY[r["category"]].delegation_only:
            assert r["applicable"] is False
        elif r["label"] == "unauthorized":
            assert not r["executed"]


def test_no_unauthorized_state_mutation_in_wakala(small_run):
    for cfg in ("B", "C"):
        s = small_run["summaries"][cfg]
        assert s["unauthorized_state_mutations"]["numerator"] == 0
        assert s["audit_evidence_complete"]["numerator"] == s["audit_evidence_complete"]["denominator"]
        assert s["run"]["audit_chain_valid"]


def test_revocation_scenarios_are_measured(small_run):
    rows = small_run["outcomes"]["C"]
    revoked = [r for r in rows if r["category"] == "revoked_mandate"]
    ancestor = [r for r in rows if r["category"] == "revoked_ancestor_mandate"]
    assert revoked and all("DENY_MANDATE_REVOKED" in r["reason_codes"] for r in revoked)
    assert ancestor and all({"DENY_PARENT_MANDATE_REVOKED", "DENY_MANDATE_REVOKED"} & set(r["reason_codes"]) for r in ancestor)
    s = small_run["summaries"]["C"]["revocation_effectiveness"]
    assert s["denominator"] == len(revoked) + len(ancestor) and s["numerator"] == s["denominator"]


def test_summaries_are_recomputed_from_raw_outcomes(small_run):
    for cfg, rows in small_run["outcomes"].items():
        fresh = summarize(cfg, rows)
        stored = {k: v for k, v in small_run["summaries"][cfg].items() if k != "run"}
        assert fresh == stored


def test_prevention_and_detection_are_separate(small_run):
    rows = small_run["outcomes"]["C"]
    expired = [r for r in rows if r["category"] == "expired_mandate"]
    assert expired and all(not r["executed"] for r in expired)  # prevented...
    assert all("REQUEST_RATE" in r["rules"] or not r["detected_any"] for r in expired)  # ...but no specific rule covers expiry
    assert not any(r["detected_specific"] for r in expired)


# --- baseline isolation --------------------------------------------------------------------------------------
def test_baseline_is_isolated_from_wakala():
    tree = ast.parse(Path(baseline_mod.__file__).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in imported if m.startswith(("app.services", "app.core", "app.models", "app.devtools", "sqlite3"))}
    b = baseline_mod.RoleOnlyBaseline()
    out = b.evaluate(generate(SMALL)[0])
    assert set(vars(b)) == {"log", "state"} and out["audit_complete"] is False


def test_isolated_env_never_uses_dev_keystore_or_server_db():
    with isolated_env("memory") as (env, _c, keys):
        assert env.settings.db_path == ":memory:"
        assert Path(env.settings.dev_keys_dir).resolve() != Path(DEFAULT_DEV_KEYS_DIR).resolve()
        assert isinstance(keys, IsolatedKeys)


# --- credentials never leak ----------------------------------------------------------------------------
def test_benchmark_artifacts_contain_no_credentials(small_run, tmp_path):
    with isolated_env("memory") as (_env, _c, keys):
        pw = keys.officer_password("OFF-0101")
    blob = json.dumps({"o": small_run["outcomes"], "s": small_run["summaries"]}, default=str)
    assert pw not in blob and "PRIVATE KEY" not in blob and "password" not in blob.lower()


def test_committed_evidence_contains_no_secrets():
    files = list(EVIDENCE.glob("*")) if EVIDENCE.exists() else []
    assert files, "evidence not generated: run python -m app.evaluation.run"
    dev = Path(DEFAULT_DEV_KEYS_DIR)
    secrets_ = [p.read_text(encoding="utf-8").strip() for p in dev.glob("*.pem")] if dev.exists() else []
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "PRIVATE KEY" not in text and "officer_credentials" not in text
        assert not re.search(r'"password"\s*:', text)
        assert not any(s and s in text for s in secrets_)


# --- committed evidence is genuine -------------------------------------------------------------------------------
def test_committed_evidence_is_consistent_and_reproducible():
    summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    outcomes = json.loads((EVIDENCE / "outcomes.json").read_text(encoding="utf-8"))["outcomes"]
    dataset = json.loads((EVIDENCE / "dataset.json").read_text(encoding="utf-8"))
    cfg = DatasetConfig(**dataset["config"])
    regenerated = generate(cfg)
    assert digest(regenerated) == dataset["sha256"] == summary["dataset_sha256"]
    assert [asdict(i) for i in regenerated] == dataset["items"]
    assert cfg.size >= 1000 and summary["dataset"]["total_requests"] == cfg.size
    for name, rows in outcomes.items():
        assert len(rows) == cfg.size
        stored = {k: v for k, v in summary["configurations"][name].items() if k != "run"}
        assert summarize(name, rows) == stored  # every headline number recomputes from the raw outcomes
    assert summary["label"] == "Synthetic prototype benchmark — not production government statistics."
    report = (EVIDENCE / "REPORT.md").read_text(encoding="utf-8")
    c = summary["configurations"]["C"]["unauthorized_operations_executed"]
    assert f"{c['numerator']}/{c['denominator']}" in report


# --- dashboard / API --------------------------------------------------------------------------------------------
def _client(evidence_dir: Path) -> TestClient:
    from app.main import create_app
    return TestClient(create_app(Settings(db_path=":memory:", evidence_dir=str(evidence_dir), dev_keys_dir=str(evidence_dir / ".keys"),
                                          console_allowed_hosts=("testclient",))))


def test_evidence_api_serves_generated_files_verbatim_and_flags_tampering(tmp_path):
    with _client(tmp_path) as c:
        r = c.get("/api/evidence/summary")
        assert r.status_code == 404 and r.json()["error"]["code"] == "EVIDENCE_NOT_GENERATED"
    import hashlib
    payload = {"schema": "test", "label": "x", "marker": 12345, "business_model_defaults": {"observed_in_synthetic_benchmark": {"k": 1}}}
    (tmp_path / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "REPORT.md").write_text("# report", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {
        "summary.json": hashlib.sha256((tmp_path / "summary.json").read_bytes()).hexdigest()}}), encoding="utf-8")
    with _client(tmp_path) as c:
        body = c.get("/api/evidence/summary").json()
        assert {k: body[k] for k in payload} == payload and body["integrity"]["mismatched"] == []
        assert c.get("/api/evidence/report").text == "# report"
        (tmp_path / "summary.json").write_text(json.dumps({**payload, "marker": 1}), encoding="utf-8")
        assert c.get("/api/evidence/summary").json()["integrity"]["mismatched"] == ["summary.json"]
        calc = c.post("/api/evidence/business-model", json={"annual_agent_operations": 1000}).json()
        assert calc["observed_in_synthetic_benchmark"] == {"k": 1}
        assert c.post("/api/evidence/business-model", json={"surprise": 1}).status_code == 422


def test_dashboard_renders_backend_results_only():
    src = (ROOT / "frontend/src/pages/SecurityEvidence.tsx").read_text(encoding="utf-8")
    assert '"/api/evidence/summary"' in src and "/api/evidence/business-model" in src
    assert "Synthetic prototype benchmark — not production government statistics." in src
    # no hard-coded result figures: no percentages or "n/m" fractions written into the page
    assert not re.search(r">\s*\d+(\.\d+)?\s*%", src) and not re.search(r">\s*\d+\s*/\s*\d+\s*<", src)
    assert "Failures and unexpected results" in src  # failures are surfaced, not hidden
    nav = (ROOT / "frontend/src/lib/navigation.ts").read_text(encoding="utf-8")
    assert '"/evidence"' in nav


# --- business model ----------------------------------------------------------------------------------------------
def test_business_model_separates_assumptions_from_observations():
    a = BusinessAssumptions(annual_agent_operations=10_000, manual_review_pct=20, manual_review_minutes=6,
                            staff_cost_per_fte_year=170_000, productive_hours_per_fte_year=1_700, wakala_exception_review_pct=2,
                            exception_review_minutes=6, annual_platform_and_integration_cost=10_000)
    r = calculate(a, {"observed": "x"})
    assert r["label"].startswith("HYPOTHETICAL")
    assert set(ASSUMPTION_NOTES) == set(BusinessAssumptions.model_fields) - {"currency"}
    assert all(v.startswith("ASSUMPTION") for v in ASSUMPTION_NOTES.values())
    assert r["observed_in_synthetic_benchmark"] == {"observed": "x"} and "observed" not in r["assumptions"]
    # 2000 vs 200 reviews; 200 h vs 20 h at 100/h -> 20,000 vs 2,000 + 10,000
    assert r["routine_manual_reviews_avoided"] == 1800 and r["review_hours_avoided"] == 180
    assert r["hypothetical_annual_cost_difference"] == 8000
    assert r["break_even"]["annual_operations"] == 5556  # 10,000 / (18,000 / 10,000)
    assert any("visa" in x for x in r["limits"])


def test_business_model_never_removes_legally_required_review():
    r = calculate(BusinessAssumptions(manual_review_pct=10, wakala_exception_review_pct=1, legally_required_review_pct=5))
    assert r["wakala_exception_scenario"]["review_pct_applied"] == 5
    assert r["manual_review_scenario"]["review_pct_applied"] == 10


# --- credential hardening --------------------------------------------------------------------------------------------
def test_dev_keystore_no_longer_produces_plaintext_passwords(tmp_path):
    from app.devtools.keystore import DevKeystore
    from app.services.bootstrap import bootstrap
    assert not hasattr(DevKeystore(tmp_path), "officer_password")
    env = bootstrap(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path)))
    try:
        assert not (tmp_path / "officer_credentials.json").exists()
        assert not env.officers.has_password("OFF-0101")
        pw = env.officers.set_password("OFF-0101")
        assert pw not in json.dumps([dict(r) for r in env.db.query("SELECT * FROM officer_credentials")])
        token, _ = env.officers.login("OFF-0101", pw)
        new = env.officers.set_password("OFF-0101")  # rotation ends sessions and invalidates the old password
        from app.services.officers import AuthError
        with pytest.raises(AuthError):
            env.officers.authenticate(token)
        with pytest.raises(AuthError):
            env.officers.login("OFF-0101", pw)
        env.officers.login("OFF-0101", new)
    finally:
        env.close()
    assert not any(pw in p.read_text(errors="ignore") for p in tmp_path.rglob("*") if p.is_file())


def test_legacy_plaintext_credentials_are_migrated_and_deleted(tmp_path):
    from app.services.bootstrap import bootstrap
    (tmp_path / "officer_credentials.json").write_text(json.dumps({"OFF-0900": "legacy-dev-pass-1"}), encoding="utf-8")
    env = bootstrap(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path)))
    try:
        assert not (tmp_path / "officer_credentials.json").exists()
        env.officers.login("OFF-0900", "legacy-dev-pass-1")  # the local demo keeps working
        assert not env.officers.has_password("OFF-0101")
    finally:
        env.close()


# --- fixes found by the benchmark --------------------------------------------------------------------------------------
def test_monitoring_lookback_cap_keeps_rule_firing():
    from app.agents import SimulatedResidencyAgent as RES
    from app.workflow.intake import open_case
    from app.workflow.scenarios import WorkflowRunner
    from app.services.assurance import RECENT_EVENT_CAP
    with isolated_env("memory") as (env, _c, _k):
        r = WorkflowRunner(env, "cap")
        case = open_case(env, "C-1001", "direct")
        res = r.agents["AGT-RES-001"]
        env.gateway.execute(res.sign(RES.register(case), case), origin="t")
        case = env.cases.get(case.case_id)
        for _ in range(RECENT_EVENT_CAP + 30):  # more allowed decisions than the cap
            env.gateway.authorize(res.sign(RES.check_eligibility(case), case), origin="t")
        for _ in range(5):  # then 5 denials (completion before prerequisites)
            env.gateway.authorize(res.sign(RES.complete(case), case), origin="t")
        rules = {i.rule_id for i in env.assurance.incidents.list(limit=1000)}
        assert "REPEATED_DENIALS" in rules


def test_concurrent_decisions_do_not_lose_monitoring_updates(caplog):
    with caplog.at_level(logging.ERROR, logger="wakala.assurance"):
        out = concurrency((4,), 12)
    assert out[0]["errors"] == 0 and out[0]["monitoring_observer_failures"] == 0 and out[0]["audit_chain_valid_after"]


def test_refused_officer_actions_are_audited():
    from app.services import interventions as iv
    from app.services.officers import AuthError
    from app.workflow.intake import open_case
    with isolated_env("memory") as (env, _c, keys):
        case = open_case(env, "C-1001", "delegated")
        token = env.officers.login("OFF-0950", keys.officer_password("OFF-0950"))[0]
        p = env.officers.authenticate(token)
        with pytest.raises(AuthError):
            iv.guarded(iv.suspend_mandate, env, p, case.mandate_refs["AGT-PAY-001"], "should be refused")
        ev = env.audit.list(5)
        assert any(e.action == "officer.action_refused" and e.actor == "OFF-0950"
                   and e.evidence_metadata.get("code") == "PERMISSION_DENIED" for e in ev)
        assert case.mandate_refs["AGT-PAY-001"] not in env.assurance.suspensions.active_ids()


def test_expired_session_measured_with_clock_offset():
    with isolated_env("memory") as (env, clock, keys):
        token = env.officers.login("OFF-0101", keys.officer_password("OFF-0101"))[0]
        from app.services.officers import AuthError
        with clock.shifted(timedelta(minutes=20)):
            with pytest.raises(AuthError) as e:
                env.officers.authenticate(token)
        assert e.value.code == "SESSION_EXPIRED"
