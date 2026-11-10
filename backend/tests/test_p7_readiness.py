"""Phase 7 — demo-readiness checks: evidence endpoint, offline default, config hygiene."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_recovery_regression_evidence_is_served_with_history(tmp_path):
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), console_allowed_hosts=("testclient",)))) as c:
        d = c.get("/api/evidence/recovery-regression").json()
        shared = {p: v["back_to_back_shared"]["recovery_success"]["numerator"] for p, v in d["policies"].items()}
        assert shared == {"phase5-original": 2, "watch-2.0": 20} and not d["dirty"]
        assert c.get("/api/evidence/summary").json()["recovery"]["back_to_back_shared"]["recovery_success"]["numerator"] == 2  # history kept


def test_default_is_offline_deterministic(tmp_path, monkeypatch):
    for k in ("WAKALA_AGENT_MODEL_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(create_app(Settings(db_path=":memory:", dev_keys_dir=str(tmp_path / "k"), console_allowed_hosts=("testclient",)))) as c:
        cfg = c.get("/api/portal/config").json()
        assert cfg["model_configured"] is False and "deterministic" in cfg["agent_mode"]


def test_env_example_holds_no_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "sk-ant-" not in text and "PRIVATE KEY" not in text
    assert "# ANTHROPIC_API_KEY=<set in your shell, not here>" in text


def test_dev_keys_and_database_are_git_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".dev_keys" in ignore and "backend/var/" in ignore
