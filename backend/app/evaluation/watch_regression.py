"""Behaviour Watch 2.0 recovery regression: the IDENTICAL recovery benchmark under both monitoring policies.

    python -m app.evaluation.watch_regression [--out ../evidence/phase6]

Same code, same traffic, same seedless deterministic workflow, fresh isolated environments; only
``env.assurance.policy`` differs. Phase 5 evidence files are never touched.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .recovery_bench import run_recovery

KEYS = ("recovery_success", "legitimate_impact", "containment_actions", "request_rate_incidents_during_run", "failures",
        "audit_chain_valid", "wall_seconds")


def _git() -> dict[str, Any]:
    def g(*a: str) -> str:
        try:
            return subprocess.run(["git", *a], capture_output=True, text=True, timeout=10, check=False).stdout.strip()
        except OSError:
            return ""
    return {"commit": g("rev-parse", "HEAD"), "branch": g("rev-parse", "--abbrev-ref", "HEAD"), "dirty": bool(g("status", "--porcelain"))}


def run(n: int = 20) -> dict[str, Any]:
    out: dict[str, Any] = {"generated_at": datetime.now(timezone.utc).isoformat(), "git": _git(), "incidents_per_condition": n,
                           "policies": {}}
    for policy in ("phase5-original", "watch-2.0"):
        r = run_recovery(n, policy)
        out["policies"][policy] = {cond: {k: r[cond][k] for k in KEYS} | {"condition": r[cond]["condition"]}
                                   for cond in ("independent_incidents", "back_to_back_shared")}
    out["changes"] = [
        "REQUEST_RATE counts one agent's requests within ONE case (threshold unchanged: 30 per 60 s). Agent-wide volume is a "
        "separate AGENT_REQUEST_VOLUME signal (60 per 60 s) that never contains a case; spread over >=5 cases with <=10% "
        "denials it is recorded as OBSERVE (legitimate batch).",
        "REPEATED_DENIALS spread over several cases becomes an agent-level ALERT instead of being attached to the latest "
        "case; inside one case the Phase 5 behaviour is unchanged.",
        "ALERT-level incidents never require approval or contain anything; approval gating considers only incidents at "
        "REQUIRE_APPROVAL or above.",
    ]
    return out


def to_markdown(d: dict[str, Any]) -> str:
    L = ["# Behaviour Watch 2.0 — recovery regression (before / after)", "",
         f"Generated {d['generated_at']} · commit `{d['git']['commit'][:10]}` ({d['git']['branch']}, dirty={d['git']['dirty']}) · "
         f"{d['incidents_per_condition']} incidents per condition, identical traffic.", "",
         "| Policy | Condition | Recovered | Legit. denied | Legit. held unexpectedly | REQUEST_RATE incidents | Containment |",
         "|---|---|---|---|---|---|---|"]
    for pol, conds in d["policies"].items():
        for cond, v in conds.items():
            rs, li = v["recovery_success"], v["legitimate_impact"]
            L.append(f"| {pol} | {cond} | {rs['numerator']}/{rs['denominator']} | {li['legitimate_requests_denied']} | "
                     f"{li['legitimate_requests_held_unexpectedly']} | {v['request_rate_incidents_during_run']} | {v['containment_actions']} |")
    L += ["", "## What changed", *[f"- {c}" for c in d["changes"]], "",
          "## Failures under the original policy (shared condition)"]
    for f in d["policies"]["phase5-original"]["back_to_back_shared"]["failures"]:
        L.append(f"- incident {f['incident']}: failed at `{f['failed_at']}` — {f['cause']}")
    L += ["", "Escalation note: under watch-2.0 the same attacking agent's third cross-citizen attempt within 30 min escalates to "
          "critical, so most affected child mandates are revoked rather than suspended. Recovery still completes through a "
          "replacement agent. Times are machine time with automated officer calls.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "evidence" / "phase6"))
    ap.add_argument("-n", type=int, default=20)
    a = ap.parse_args()
    d = run(a.n)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "recovery_regression.json").write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    (out / "RECOVERY_REGRESSION.md").write_text(to_markdown(d), encoding="utf-8")
    print(to_markdown(d))


if __name__ == "__main__":
    main()
