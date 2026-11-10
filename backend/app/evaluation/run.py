"""Run the full Phase 5 evidence suite and write JSON + Markdown evidence files.

    cd backend
    .venv\\Scripts\\python -m app.evaluation.run --seed 20260 --size 1200 --out ../evidence/phase5

Every number in the output files is computed from what the isolated runs returned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import latency as latency_mod
from .business import BusinessAssumptions, calculate
from .dataset import DatasetConfig, breakdown, digest
from .environment import environment_info
from .latency import run_latency
from .recovery_bench import run_recovery
from .report import render_report
from .security import run_security
from .stress import run_stress

SCHEMA = "wakala-phase5-evidence-v1"
LABEL = "Synthetic prototype benchmark — not production government statistics."


def _git() -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""
    return {"commit": run("rev-parse", "HEAD") or None, "branch": run("rev-parse", "--abbrev-ref", "HEAD") or None,
            "working_tree_dirty": bool(run("status", "--porcelain"))}


def observed_exception_reference(c: dict[str, Any]) -> dict[str, Any]:
    m = c["monitoring"]
    return {
        "source": "configuration C of this synthetic run (attack-heavy mix; NOT a forecast of real traffic)",
        "unauthorized_escalated_to_officer_queue": m["unauthorized_escalated_to_officer_queue"],
        "legitimate_with_specific_rule_alert": m["legitimate_with_specific_rule_alert"],
        "legitimate_held_for_approval": c["legitimate_held_for_approval"],
    }


def run_all(seed: int, size: int, out: Path, quick: bool = False, progress: Any = print) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    git = _git()  # captured before anything is written, so it describes the code that produced the evidence
    cfg = DatasetConfig(seed=seed, size=size)
    timings: dict[str, float] = {}

    t = time.perf_counter()
    progress("security benchmark (A, B, C)...")
    sec = run_security(cfg, progress=progress)
    timings["security_seconds"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    progress("latency...")
    lat = run_latency(100 if quick else 500, 8 if quick else 40)
    timings["latency_seconds"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    progress("stress...")
    stress = run_stress(quick=quick)
    timings["stress_seconds"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    progress("recovery...")
    rec = run_recovery(5 if quick else 20)
    timings["recovery_seconds"] = round(time.perf_counter() - t, 1)

    items = sec["items"]
    config = {
        "schema": SCHEMA, "label": LABEL, "dataset": asdict(cfg), "dataset_sha256": digest(items),
        "quick_mode": quick, "git": git, "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(), "phase_timings": timings,
        "reproduce": [
            "cd backend",
            f".venv\\Scripts\\python -m app.evaluation.run --seed {seed} --size {size} --out ../evidence/phase5" + (" --quick" if quick else ""),
        ],
        "isolation": "Every configuration runs in its own temporary environment (fresh dev keys in a temp dir, in-memory or "
                     "temp-file SQLite, random in-memory officer passwords). The server database and backend/.dev_keys are never used.",
    }
    business_defaults = calculate(BusinessAssumptions(), observed_exception_reference(sec["summaries"]["C"]))
    recovery_summary = {k: ({kk: vv for kk, vv in v.items() if kk != "runs"} if isinstance(v, dict) else v) for k, v in rec.items()}
    summary = {
        "schema": SCHEMA, "label": LABEL, "dataset": breakdown(items), "dataset_sha256": config["dataset_sha256"],
        "configurations": sec["summaries"], "latency": lat, "stress": stress, "recovery": recovery_summary,
        "environment": environment_info(), "business_model_defaults": business_defaults, "run": config,
    }
    files = {
        "config.json": config,
        "dataset.json": {"schema": SCHEMA, "label": LABEL, "config": asdict(cfg), "sha256": config["dataset_sha256"],
                         "items": [asdict(i) for i in items]},
        "outcomes.json": {"schema": SCHEMA, "label": LABEL, "outcomes": sec["outcomes"]},
        "latency_samples.json": {"schema": SCHEMA, "label": LABEL, "unit": "ms", "samples": latency_mod.SAMPLES},
        "recovery_runs.json": {"schema": SCHEMA, "label": LABEL, "runs": {k: v["runs"] for k, v in rec.items() if isinstance(v, dict)}},
        "environment.json": summary["environment"],
        "summary.json": summary,
    }
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, indent=1, sort_keys=False, default=str) + "\n", encoding="utf-8")
    (out / "REPORT.md").write_text(render_report(summary), encoding="utf-8")
    manifest = {"schema": SCHEMA, "label": LABEL, "generated_at": config["finished_at"],
                "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())
                          if p.is_file() and p.name != "manifest.json"}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="WAKALA Phase 5 evidence suite")
    ap.add_argument("--seed", type=int, default=20260)
    ap.add_argument("--size", type=int, default=1200)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[3] / "evidence" / "phase5")
    ap.add_argument("--quick", action="store_true", help="smaller latency/stress/recovery samples (development only)")
    a = ap.parse_args(argv)
    if a.size < 1000 and not a.quick:
        ap.error("the evidence run requires --size >= 1000 (use --quick for development)")
    s = run_all(a.seed, a.size, a.out, a.quick)
    for k, c in s["configurations"].items():
        print(k, "unauthorized executed", c["unauthorized_operations_executed"], "| legit denied", c["legitimate_incorrectly_denied"])
    print("written to", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
