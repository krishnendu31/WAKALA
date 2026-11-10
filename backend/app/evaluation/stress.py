"""Scalability stress tests: one dimension at a time, everything else held constant.

Each point reports latency of the same probe request (a direct-mandate authorization, fully audited and
monitored) plus errors. Bottlenecks are reported as measured — nothing is tuned per point.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agents import SimulatedInsuranceAgent as INS, SimulatedResidencyAgent as RES
from app.core.delegation.tasks import GLOBAL_MAX_DELEGATION_DEPTH
from app.schemas import AuditEvent
from app.workflow.delegation_scenarios import INSURANCE_TASK, commission_call
from app.workflow.intake import COMMISSION_GRANTS, open_case
from app.workflow.scenarios import WorkflowRunner

from .environment import isolated_env, stats


def _probe(env: Any, r: WorkflowRunner, n: int) -> dict[str, Any]:
    case = open_case(env, "C-1001", "direct")
    res = r.agents["AGT-RES-001"]
    env.gateway.execute(res.sign(RES.register(case), case), origin="stress:setup")
    case = env.cases.get(case.case_id)
    samples, errors = [], 0
    for _ in range(n):
        s = res.sign(RES.check_eligibility(case), case)
        t = time.perf_counter()
        try:
            ok = env.gateway.authorize(s, origin="stress").decision.allowed
        except Exception:  # noqa: BLE001 — counted, not hidden
            ok = False
        samples.append((time.perf_counter() - t) * 1000)
        errors += not ok
    return {"latency": stats(samples), "errors_or_unexpected_denials": errors}


def active_cases(points: tuple[int, ...], n: int) -> list[dict[str, Any]]:
    out = []
    with isolated_env("file") as (env, _c, _k):
        r = WorkflowRunner(env, "stress-cases")
        opened = 0
        for p in points:
            t = time.perf_counter()
            while opened < p:
                open_case(env, "C-1002" if opened % 2 else "C-1001", "direct")
                opened += 1
            out.append({"active_cases": opened + 1, "intake_seconds_for_increment": round(time.perf_counter() - t, 2), **_probe(env, r, n)})
    return out


def registered_agents(points: tuple[int, ...], n: int) -> list[dict[str, Any]]:
    out = []
    with isolated_env("file") as (env, _c, _k):
        r = WorkflowRunner(env, "stress-agents")
        template = env.repo.get_agent("AGT-RES-001")
        added = 0
        for p in points:
            while added < p:
                prefix = "SYN" + chr(65 + added // 999)
                aid = f"AGT-{prefix}-{added % 999 + 1:03d}"
                kid = f"KEY-{aid}"
                passport = template.model_copy(update={
                    "agent_id": aid, "name": f"Synthetic load agent {added}", "status": "active",
                    "identity_key_reference": template.identity_key_reference.model_copy(update={"key_id": kid})})
                with env.db.transaction() as conn:
                    conn.execute("INSERT INTO agents (agent_id, payload) VALUES (?, ?)", (aid, passport.model_dump_json()))
                env.repo.register_public_key(kid, "agent", aid, Ed25519PrivateKey.generate().public_key())
                added += 1
            out.append({"registered_agents": len(env.repo.list_agents()), **_probe(env, r, n)})
    return out


def audit_records(points: tuple[int, ...], n: int) -> list[dict[str, Any]]:
    out = []
    with isolated_env("file") as (env, _c, _k):
        r = WorkflowRunner(env, "stress-audit")
        for p in points:
            have = env.audit.verify().event_count
            for _ in range(max(0, p - have)):
                env.audit.append(AuditEvent(event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(),
                                            actor="WAKALA-GATEWAY", action="benchmark.filler", decision="informational",
                                            evidence_metadata={"synthetic": True}))
            t = time.perf_counter()
            v = env.audit.verify()
            verify_ms = (time.perf_counter() - t) * 1000
            out.append({"audit_records": v.event_count, "full_chain_verification_ms": round(verify_ms, 1), "chain_valid": v.valid,
                        **_probe(env, r, n)})
    return out


def agent_history(points: tuple[int, ...], n: int) -> list[dict[str, Any]]:
    """Same agent, growing number of its own recent decisions: exercises the monitoring observer's lookback."""
    out = []
    with isolated_env("file") as (env, _c, _k):
        r = WorkflowRunner(env, "stress-history")
        case = open_case(env, "C-1001", "direct")
        res = r.agents["AGT-RES-001"]
        env.gateway.execute(res.sign(RES.register(case), case), origin="stress:setup")
        case = env.cases.get(case.case_id)
        made = 1
        for p in points:
            while made < p:
                env.gateway.authorize(res.sign(RES.check_eligibility(case), case), origin="stress:history")
                made += 1
            res_probe = _probe(env, r, n)
            made += n + 1
            out.append({"prior_decisions_by_same_agent": p, **res_probe})
    return out


class _Count(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.n = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.n += 1


def concurrency(threads: tuple[int, ...], per_thread: int) -> list[dict[str, Any]]:
    out = []
    counter = _Count()
    log = logging.getLogger("wakala.assurance")
    log.addHandler(counter)
    log.propagate, prev = False, log.propagate  # counted below instead of printed
    try:
        return _concurrency(threads, per_thread, counter, out)
    finally:
        log.removeHandler(counter)
        log.propagate = prev


def _concurrency(threads: tuple[int, ...], per_thread: int, counter: "_Count", out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for t_count in threads:
        counter.n = 0
        with isolated_env("file") as (env, _c, _k):
            r = WorkflowRunner(env, f"stress-conc-{t_count}")
            res = r.agents["AGT-RES-001"]
            cases = []
            for i in range(t_count):
                c = open_case(env, "C-1001" if i % 2 == 0 else "C-1002", "direct")
                env.gateway.execute(res.sign(RES.register(c), c), origin="stress:setup")
                cases.append(env.cases.get(c.case_id))
            lat: list[float] = []
            errors: list[str] = []
            lock = threading.Lock()
            barrier = threading.Barrier(t_count)

            def worker(c: Any) -> None:
                barrier.wait()
                for _ in range(per_thread):
                    s = res.sign(RES.check_eligibility(c), c)
                    t = time.perf_counter()
                    try:
                        ok = env.gateway.authorize(s, origin="stress:concurrent").decision.allowed
                        err = None if ok else "unexpected_denial"
                    except Exception as e:  # noqa: BLE001
                        err = type(e).__name__
                    ms = (time.perf_counter() - t) * 1000
                    with lock:
                        lat.append(ms)
                        if err:
                            errors.append(err)

            ts = [threading.Thread(target=worker, args=(c,)) for c in cases]
            t0 = time.perf_counter()
            for th in ts:
                th.start()
            for th in ts:
                th.join()
            wall = time.perf_counter() - t0
            chain = env.audit.verify()
            out.append({"threads": t_count, "requests": len(lat), "wall_seconds": round(wall, 3),
                        "throughput_rps": round(len(lat) / wall, 1), "latency": stats(lat), "errors": len(errors),
                        "error_types": sorted(set(errors)), "audit_chain_valid_after": chain.valid,
                        "monitoring_observer_failures": counter.n,
                        "incidents_after": len(env.assurance.incidents.list(limit=100000))})
    return out


def delegation_depth(n: int) -> dict[str, Any]:
    with isolated_env("file") as (env, _c, _k):
        r = WorkflowRunner(env, "stress-depth")
        res, ins = r.agents["AGT-RES-001"], r.agents["AGT-INS-001"]
        case = open_case(env, "C-1001", "delegated")
        for call in (RES.register, RES.check_eligibility):
            cur = env.cases.get(case.case_id)
            env.gateway.execute(res.sign(call(cur), cur), origin="stress:setup")
        cur = env.cases.get(case.case_id)
        child = str(env.gateway.execute(res.sign(commission_call(cur), cur), origin="stress:setup").result["child_mandate_id"])
        d1 = []
        for _ in range(n):
            s = ins.sign(INS.verify(cur), cur, mandate_id=child)
            t = time.perf_counter()
            assert env.gateway.authorize(s, origin="stress:depth").decision.allowed
            d1.append((time.perf_counter() - t) * 1000)
        attempt = env.gateway.authorize(ins.sign(commission_call(cur, INSURANCE_TASK, "AGT-INS-002"), cur, mandate_id=child),
                                        origin="stress:depth")
        return {
            "global_max_depth": GLOBAL_MAX_DELEGATION_DEPTH,
            "depth_permitted_by_current_grant": COMMISSION_GRANTS["AGT-RES-001"][1],
            "depth_1_delegated_authorization": stats(d1),
            "depth_2_attempt": {"allowed": attempt.decision.allowed, "reason_codes": [c.value for c in attempt.decision.reason_codes]},
            "note": "Depths 2-3 are not permitted by the current synthetic grant (max_delegation_depth=1), so they cannot be "
                    "measured as authorized chains; the attempt above is measured as a denial.",
        }


def run_stress(quick: bool = False) -> dict[str, Any]:
    n = 30 if quick else 100
    return {
        "probe": "direct-mandate residency.check_eligibility via Gateway.authorize (decision + audit + monitoring), file SQLite",
        "active_cases": active_cases((0, 50) if quick else (0, 500, 2000), n),
        "registered_agents": registered_agents((0, 100) if quick else (0, 1000, 5000), n),
        "audit_records": audit_records((0, 2000) if quick else (0, 10000, 40000), n),
        "agent_history": agent_history((1, 200) if quick else (1, 500, 2000), n),
        "concurrency": concurrency((1, 4) if quick else (1, 2, 4, 8), 20 if quick else 60),
        "delegation_depth": delegation_depth(n),
        "dimensions_held_constant": "Each series varies one dimension in a fresh isolated environment; same probe request.",
    }
