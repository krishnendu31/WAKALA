"""Measured (not estimated) authorization latency: direct vs delegated mandates.

Runs on an isolated in-memory environment with fresh development keys, so it
never touches the server's database. Numbers depend on the machine; they are
reported as measured, with sample size, and are not a performance claim.
"""

from __future__ import annotations

import statistics
import tempfile
import time

from app.agents import SimulatedInsuranceAgent as INS, SimulatedResidencyAgent as RES
from app.core.config import Settings
from app.core.delegation import verify_chain
from app.services.bootstrap import bootstrap

from .delegation_scenarios import prepare
from .intake import open_case
from .scenarios import WorkflowRunner


def _stats(samples: list[float]) -> dict[str, float]:
    s = sorted(samples)
    return {"n": len(s), "median_ms": round(statistics.median(s), 3), "p95_ms": round(s[int(0.95 * (len(s) - 1))], 3),
            "max_ms": round(s[-1], 3)}


def run_delegation_benchmark(n: int = 200) -> dict[str, object]:
    n = max(10, min(n, 5000))
    with tempfile.TemporaryDirectory() as keys:
        env = bootstrap(Settings(db_path=":memory:", dev_keys_dir=keys))
        try:
            r = WorkflowRunner(env, "benchmark")
            case = open_case(env, "C-1001", "delegated")
            child = prepare(r, case)
            if child is None:
                raise RuntimeError("benchmark setup failed")
            res, ins = r.agents["AGT-RES-001"], r.agents["AGT-INS-001"]
            direct, delegated, chain = [], [], []
            for _ in range(n):
                signed = res.sign(RES.check_eligibility(case), case)
                direct.append(env.gateway.authorize(signed, origin="benchmark").decision.decision_latency_ms)
                signed = ins.sign(INS.verify(case), case, mandate_id=child)
                out = env.gateway.authorize(signed, origin="benchmark")
                if not out.decision.allowed:
                    raise RuntimeError(f"delegated request unexpectedly denied: {out.decision.reason_codes}")
                delegated.append(out.decision.decision_latency_ms)
            leaf = env.mandates.get(child)
            ancestors, _ = env.gateway.resolve_ancestors(leaf)
            snap = env.gateway.policy_snapshot(env.clock())
            for _ in range(n):
                t = time.perf_counter()
                codes = verify_chain(leaf, ancestors, snap["issuers"], snap["issuer_public_keys"], env.clock(),
                                     snap["revoked_mandate_ids"])
                chain.append((time.perf_counter() - t) * 1000)
                if codes:
                    raise RuntimeError(f"chain unexpectedly invalid: {codes}")
            return {
                "measured_on": "this machine, in-memory SQLite, single process",
                "direct_mandate_authorize": _stats(direct),
                "delegated_mandate_authorize": _stats(delegated),
                "chain_verification_only (2 links, 2 Ed25519 verifies + narrowing)": _stats(chain),
            }
        finally:
            env.close()
