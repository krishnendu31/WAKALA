"""Latency measurement (wall-clock, ``time.perf_counter``) on this machine.

Two kinds of numbers, never mixed:
* MICROBENCHMARKS — pure in-process functions on in-memory objects (signature verification, chain verification).
* INTEGRATION — the real gateway with SQLite, both ``:memory:`` and a temporary FILE database (persisted),
  including the hash-chained audit write and the monitoring observer.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.delegation import verify_chain
from app.core.identity.authentication import authenticate
from app.workflow.delegation_scenarios import commission_call
from app.workflow.intake import open_case
from app.workflow.scenarios import WorkflowRunner

from .environment import isolated_env, stats as _stats

SAMPLES: dict[str, list[float]] = {}  # raw samples (ms) of the latest run, saved as evidence


def rec(name: str, samples: list[float]) -> dict[str, Any]:
    SAMPLES[name] = [round(x, 5) for x in samples]
    return _stats(samples)


def _ms(t: float) -> float:
    return (time.perf_counter() - t) * 1000


def _prepared(env: Any, r: WorkflowRunner) -> tuple[Any, str]:
    case = open_case(env, "C-1001", "delegated")
    for call in (RES.register(case), RES.check_eligibility(env.cases.get(case.case_id))):
        assert r.agents["AGT-RES-001"].transport.execute(r.agents["AGT-RES-001"].sign(call, env.cases.get(case.case_id)),
                                                         origin="latency:setup").executed
    out = env.gateway.execute(r.agents["AGT-RES-001"].sign(commission_call(env.cases.get(case.case_id)), env.cases.get(case.case_id)),
                              origin="latency:setup")
    assert out.executed
    return env.cases.get(case.case_id), str(out.result["child_mandate_id"])


def integration(storage: str, n: int, cases: int) -> dict[str, Any]:
    with isolated_env(storage) as (env, _clock, _keys):
        r = WorkflowRunner(env, f"latency-{storage}")
        res, ins, pay = r.agents["AGT-RES-001"], r.agents["AGT-INS-001"], r.agents["AGT-PAY-001"]
        case, child = _prepared(env, r)
        direct_wall, direct_dec, deleg_wall, deleg_dec = [], [], [], []
        for _ in range(n):  # authorize only (no execution): the request is still fully authenticated, checked and audited
            s = res.sign(RES.check_eligibility(case), case)
            t = time.perf_counter()
            o = env.gateway.authorize(s, origin="latency")
            direct_wall.append(_ms(t))
            direct_dec.append(o.decision.decision_latency_ms)
            assert o.decision.allowed
            s = ins.sign(INS.verify(case), case, mandate_id=child)
            t = time.perf_counter()
            o = env.gateway.authorize(s, origin="latency")
            deleg_wall.append(_ms(t))
            deleg_dec.append(o.decision.decision_latency_ms)
            assert o.decision.allowed
        # protected tool execution (authorize + dispatch + transactional outcome audit) and end-to-end cases
        execute_wall, e2e = [], []
        for _ in range(cases):
            t0 = time.perf_counter()
            c = open_case(env, "C-1002", "delegated")
            steps = 0
            for agent, call, kw in ((res, RES.register, {}), (res, RES.check_eligibility, {})):
                o = env.gateway.execute(agent.sign(call(env.cases.get(c.case_id)), env.cases.get(c.case_id)), origin="latency")
                steps += o.executed
            o = env.gateway.execute(res.sign(commission_call(env.cases.get(c.case_id)), env.cases.get(c.case_id)), origin="latency")
            kid = str(o.result["child_mandate_id"])
            cur = env.cases.get(c.case_id)
            s = ins.sign(INS.verify(cur), cur, mandate_id=kid)
            t = time.perf_counter()
            o = env.gateway.execute(s, origin="latency")
            execute_wall.append(_ms(t))
            for agent, call in ((pay, PAY.collect), (res, RES.complete)):
                cur = env.cases.get(c.case_id)
                o = env.gateway.execute(agent.sign(call(cur), cur), origin="latency")
            if env.cases.get(c.case_id).state.value == "COMPLETED":
                e2e.append(_ms(t0))
        return {
            "storage": "SQLite :memory:" if storage == "memory" else "SQLite temporary file (persisted, on local disk)",
            "concurrency": 1,
            "direct_mandate_authorization": {"gateway_wall": rec(f"{storage}.direct.gateway_wall", direct_wall), "decision_only": rec(f"{storage}.direct.decision_only", direct_dec)},
            "delegated_mandate_authorization": {"gateway_wall": rec(f"{storage}.delegated.gateway_wall", deleg_wall), "decision_only": rec(f"{storage}.delegated.decision_only", deleg_dec)},
            "protected_tool_execution": {"gateway_execute_wall": rec(f"{storage}.protected_tool_execution", execute_wall),
                                         "operation": "insurance.verify_case_eligibility under a child mandate"},
            "end_to_end_case": {"wall": rec(f"{storage}.end_to_end_case", e2e), "cases_started": cases, "cases_completed": len(e2e),
                                "steps": "intake + 6 signed requests (register, eligibility, commission, insurance, fee, complete)"},
        }


def microbench(n: int) -> dict[str, Any]:
    with isolated_env("memory") as (env, _c, _k):
        r = WorkflowRunner(env, "latency-micro")
        case, child = _prepared(env, r)
        signed = r.agents["AGT-INS-001"].sign(INS.verify(case), case, mandate_id=child)
        key = env.repo.get_agent_key("AGT-INS-001")
        sig = []
        for _ in range(n):
            t = time.perf_counter()
            out = authenticate(signed, lambda _a: key)
            sig.append(_ms(t))
            assert out.principal is not None
        leaf = env.mandates.get(child)
        ancestors, _ = env.gateway.resolve_ancestors(leaf)
        snap = env.gateway.policy_snapshot(env.clock())
        chain = []
        for _ in range(n):
            t = time.perf_counter()
            codes = verify_chain(leaf, ancestors, snap["issuers"], snap["issuer_public_keys"], env.clock(), snap["revoked_mandate_ids"])
            chain.append(_ms(t))
            assert not codes
        return {
            "authentication_and_signature_verification": {**rec("micro.signature_verification", sig), "scope": "request canonicalisation + digest + Ed25519 verify (key cached in memory)"},
            "delegation_chain_verification": {**rec("micro.chain_verification", chain), "scope": "child + root: 2 Ed25519 mandate signatures + narrowing checks"},
        }


def run_latency(n: int = 500, cases: int = 40) -> dict[str, Any]:
    SAMPLES.clear()
    return {
        "method": "time.perf_counter wall-clock on this machine, single thread; percentiles are nearest-rank",
        "microbenchmarks_in_memory": microbench(n),
        "integration_in_memory_sqlite": integration("memory", n, cases),
        "integration_persisted_sqlite_file": integration("file", n, cases),
        "definitions": {
            "decision_only": "Gateway-measured time for authentication + policy + approval gate (excludes audit write and monitoring).",
            "gateway_wall": "Full Gateway.authorize call: decision + hash-chained audit write + monitoring observer.",
            "gateway_execute_wall": "Gateway.execute: authorization + protected service dispatch + transactional outcome audit.",
            "end_to_end_case": "Machine time from intake to COMPLETED with simulated agents; no human time, no network.",
        },
    }
