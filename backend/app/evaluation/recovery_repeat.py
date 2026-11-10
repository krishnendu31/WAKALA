"""Phase 7 recovery repeatability: the unchanged recovery benchmark, repeated and lengthened.

    python -m app.evaluation.recovery_repeat [--out ../evidence/phase7]

Each repetition is a fresh isolated environment and identical traffic. Also runs one longer shared run (50 incidents)
and the original policy once more, so the historical 2/20 is re-confirmed rather than only quoted.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .recovery_bench import _condition
from .watch_regression import _git


def _summ(r: dict[str, Any]) -> dict[str, Any]:
    runs = r["runs"]
    return {"recovered": r["recovery_success"], "legitimate_impact": r["legitimate_impact"],
            "containment_actions": r["containment_actions"],
            "unrelated_case_completed": sum(1 for x in runs if x.get("checks", {}).get("9_unrelated_case_unaffected")),
            "attack_denied": sum(1 for x in runs if x.get("checks", {}).get("2_unauthorized_action_denied")),
            "attack_not_executed": sum(1 for x in runs if x.get("checks", {}).get("3_action_not_executed")),
            "failures": r["failures"], "audit_chain_valid": r["audit_chain_valid"], "wall_seconds": r["wall_seconds"]}


def run(repeats: int = 5) -> dict[str, Any]:
    out: dict[str, Any] = {"generated_at": datetime.now(timezone.utc).isoformat(), "git": _git(), "repeats": []}
    for i in range(repeats):
        out["repeats"].append({"repeat": i + 1, "shared_20": _summ(_condition(20, shared=True)),
                               "independent_20": _summ(_condition(20, shared=False))})
    out["long_shared_50"] = _summ(_condition(50, shared=True))
    out["original_policy_shared_20"] = _summ(_condition(20, shared=True, policy="phase5-original"))
    out["note"] = ("Machine-speed, single-process, synthetic. Repeated identical runs show reproducibility of this benchmark, "
                   "not production reliability.")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "evidence" / "phase7"))
    ap.add_argument("--repeats", type=int, default=5)
    a = ap.parse_args()
    d = run(a.repeats)
    p = Path(a.out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "recovery_repeatability.json").write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    for r in d["repeats"]:
        s, i = r["shared_20"], r["independent_20"]
        print(f"repeat {r['repeat']}: shared {s['recovered']['numerator']}/20 (legit denied {s['legitimate_impact']['legitimate_requests_denied']}, "
              f"held {s['legitimate_impact']['legitimate_requests_held_unexpectedly']}, unrelated ok {s['unrelated_case_completed']}, "
              f"attacks denied {s['attack_denied']}, containment {s['containment_actions']}) · independent {i['recovered']['numerator']}/20")
    L, O = d["long_shared_50"], d["original_policy_shared_20"]
    print(f"long shared: {L['recovered']['numerator']}/50 legit denied {L['legitimate_impact']['legitimate_requests_denied']} "
          f"held {L['legitimate_impact']['legitimate_requests_held_unexpectedly']} containment {L['containment_actions']} failures {L['failures'][:3]}")
    print(f"original policy: {O['recovered']['numerator']}/20 legit denied {O['legitimate_impact']['legitimate_requests_denied']}")


if __name__ == "__main__":
    main()
