"""Reproducible service-continuity benchmark: N independent eligible incidents, every step checked.

Per incident, in one shared isolated environment (incident policy "contain"):
 1 initiate a valid delegated case (plus an unrelated case for another citizen)
 2 trigger an unauthorized cross-citizen request
 3 verify it did not execute (no data, no state change)
 4 verify incident state (CROSS_CITIZEN_ACCESS, affected child suspended, case paused)
 5 authenticated officer intervention (under review, reassign to standby agent, resume)
 6 resume with valid authority (held commission approved and re-authorized by the gateway)
 7 all legitimate prerequisites satisfied
 8 case completed through signed gateway requests
 9 unrelated case completes without officer involvement
Officer actions are automated calls to the real intervention functions; times exclude human think time.
A failed or incomplete recovery is counted, never retried.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents import SimulatedInsuranceAgent as INS
from app.services import interventions as iv
from app.workflow.delegation_scenarios import INSURANCE_TASK, prepare
from app.workflow.intake import open_case
from app.workflow.recovery import continue_case
from app.workflow.scenarios import WorkflowRunner

from .environment import isolated_env, stats
from .metrics import rate

STEPS = ("1_valid_case_initiated", "2_unauthorized_action_denied", "3_action_not_executed", "4_incident_and_containment",
         "5_officer_intervention_applied", "6_resumed_with_valid_authority", "7_prerequisites_complete", "8_case_completed",
         "9_unrelated_case_unaffected")
REQUIRED = {"residency_eligibility", "insurance_verified", "fee_paid"}


def _one(env: Any, r: WorkflowRunner, token: str) -> dict[str, Any]:
    checks: dict[str, bool] = dict.fromkeys(STEPS, False)
    officer_actions = 0
    m = open_case(env, "C-1001", "delegated", "contain")
    o = open_case(env, "C-1002", "delegated", "contain")
    km, ko = prepare(r, m), prepare(r, o)
    checks["1_valid_case_initiated"] = km is not None and ko is not None
    if not checks["1_valid_case_initiated"]:
        held = [st for st in r.steps[-6:] if st.execution_status == "pending_approval"]
        return {"checks": checks, "failed_at": "1_valid_case_initiated",
                "cause": "legitimate setup request held for approval: " + ", ".join(
                    sorted({i.rule_id for cid in (m.case_id, o.case_id) if (i := env.assurance.incidents.case_has_active(cid))}))
                if held else "setup request denied"}
    before = env.cases.get(m.case_id)
    t0 = time.perf_counter()
    step = r.run("AGT-INS-001", INS.verify(before, "C-1003"), before, "cross-citizen attempt", "out_of_scope", mandate_id=km)
    t_contained = (time.perf_counter() - t0) * 1000
    after = env.cases.get(m.case_id)
    checks["2_unauthorized_action_denied"] = step.decision is not None and not step.decision.allowed
    checks["3_action_not_executed"] = (not step.executed and step.result is None
                                       and set(after.completed_prerequisites) == set(before.completed_prerequisites)
                                       and not env.services.ledger(m.case_id))
    inc = env.assurance.incidents.case_has_active(m.case_id)
    # Containment of the affected child is a suspension at "high" and a revocation at "critical" (the same agent's
    # third cross-citizen attempt within 30 min escalates by design). Either counts; which one is recorded.
    suspended, revoked = km in env.assurance.suspensions.active_ids(), env.mandates.is_revoked(km)
    containment = "suspended" if suspended else "revoked" if revoked else "none"
    checks["4_incident_and_containment"] = (inc is not None and inc.rule_id == "CROSS_CITIZEN_ACCESS"
                                            and containment != "none" and after.state.value == "PAUSED_FOR_REVIEW"
                                            and ko not in env.assurance.suspensions.active_ids() and not env.mandates.is_revoked(ko))
    if inc is None:
        return {"checks": checks, "failed_at": "4_incident_and_containment", "containment": containment}
    p = env.officers.authenticate(token)
    iv.guarded(iv.set_incident_status, env, p, inc.incident_id, "under_review", "benchmark triage")
    iv.guarded(iv.reassign_task, env, p, m.case_id, INSURANCE_TASK, "AGT-INS-002", "benchmark replacement")
    iv.guarded(iv.resume_case, env, p, m.case_id, "benchmark: affected authority contained")
    officer_actions += 3
    checks["5_officer_intervention_applied"] = env.cases.get(m.case_id).state.value != "PAUSED_FOR_REVIEW"
    continue_case(env, m.case_id)
    approved = []
    for a in env.approvals.list("pending"):
        if a.case_id == m.case_id:
            res = iv.guarded(iv.decide_approval, env, p, a.approval_id, True, "benchmark: standby commission approved")
            officer_actions += 1
            approved.append(bool(res.get("executed")))
    checks["6_resumed_with_valid_authority"] = bool(approved) and all(approved)
    iv.guarded(iv.set_incident_status, env, p, inc.incident_id, "resolved", "benchmark: recovered")
    officer_actions += 1
    continue_case(env, m.case_id)
    final = env.cases.get(m.case_id)
    t_recovered = (time.perf_counter() - t0) * 1000
    checks["7_prerequisites_complete"] = REQUIRED <= set(final.completed_prerequisites)
    checks["8_case_completed"] = final.state.value == "COMPLETED" and len(env.services.renewals(m.case_id)) == 1
    continue_case(env, o.case_id)
    other = env.cases.get(o.case_id)
    checks["9_unrelated_case_unaffected"] = (other.state.value == "COMPLETED"
                                             and not any(a.case_id == o.case_id for a in env.approvals.list())
                                             and env.assurance.incidents.case_has_active(o.case_id) is None)
    failed = next((s for s in STEPS if not checks[s]), None)
    return {"checks": checks, "failed_at": failed, "containment": containment, "incident_severity": inc.severity,
            "containment_ms": round(t_contained, 3),
            "denial_to_completion_ms": round(t_recovered, 3) if checks["8_case_completed"] else None,
            "officer_actions": officer_actions, "incident_id": inc.incident_id, "case_id": m.case_id,
            "unrelated_case_id": o.case_id, "final_state": final.state.value, "recovery_status": final.recovery_status}


ATTACK_CODES = {"DENY_SCOPE_VIOLATION", "DENY_CASE_SCOPE_VIOLATION"}


def _decisions(env: Any) -> dict[str, int]:
    """Counted from the audit trail: every denial / hold the gateway actually recorded during the run."""
    rows = env.db.query("SELECT payload FROM audit_events WHERE json_extract(payload, '$.decision') IN ('denied','escalated')")
    import json
    out = {"denied_attack": 0, "denied_other": 0, "held": 0}
    for r in rows:
        p = json.loads(r["payload"])
        if p["decision"] == "escalated":
            out["held"] += 1
        elif set(p.get("reason_codes", [])) & ATTACK_CODES:
            out["denied_attack"] += 1
        else:
            out["denied_other"] += 1
    return out


def _condition(n: int, shared: bool, policy: str = "watch-2.0") -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    rate_hits = 0
    chains_valid = True
    t0 = time.perf_counter()
    counts = {"denied_attack": 0, "denied_other": 0, "held": 0}

    def one(env: Any, keys: Any, r: WorkflowRunner, token: str, i: int) -> None:
        try:
            runs.append({"incident": i + 1, **_one(env, r, token)})
        except Exception as e:  # noqa: BLE001 — a crash is a failed recovery, counted
            runs.append({"incident": i + 1, "checks": {}, "failed_at": "exception", "error": f"{type(e).__name__}: {e}"[:300]})

    if shared:
        with isolated_env("memory") as (env, _c, keys):
            env.assurance.policy = policy
            token = env.officers.login("OFF-0101", keys.officer_password("OFF-0101"))[0]
            r = WorkflowRunner(env, "recovery-benchmark")
            for i in range(n):
                one(env, keys, r, token, i)
            chains_valid = env.audit.verify().valid
            counts = _decisions(env)
            rate_hits = len([x for x in env.assurance.incidents.list(limit=100000) if x.rule_id == "REQUEST_RATE"])
    else:
        for i in range(n):
            with isolated_env("memory") as (env, _c, keys):
                env.assurance.policy = policy
                token = env.officers.login("OFF-0101", keys.officer_password("OFF-0101"))[0]
                one(env, keys, WorkflowRunner(env, "recovery-benchmark"), token, i)
                chains_valid = chains_valid and env.audit.verify().valid
                for k, v in _decisions(env).items():
                    counts[k] += v
                rate_hits += len([x for x in env.assurance.incidents.list(limit=100000) if x.rule_id == "REQUEST_RATE"])
    ok = [x for x in runs if x.get("failed_at") is None]
    attacks = sum(1 for x in runs if x.get("checks", {}).get("1_valid_case_initiated"))
    designed_holds = sum(1 for x in runs if x.get("checks", {}).get("5_officer_intervention_applied"))
    return {
        "policy": policy,
        "legitimate_impact": {
            "attack_requests_sent": attacks, "attack_requests_denied": counts["denied_attack"],
            "designed_holds_expected": designed_holds, "holds_recorded": counts["held"],
            "legitimate_requests_held_unexpectedly": max(0, counts["held"] - designed_holds),
            "legitimate_requests_denied": counts["denied_other"],
            "note": "From the audit trail. One hold per recovery is by design (the resumed delegation needs officer approval).",
        },
        "eligible_incidents": n,
        "recovery_success": rate(len(ok), n),
        "per_step_success": {s: rate(sum(1 for x in runs if x.get("checks", {}).get(s)), n) for s in STEPS},
        "failures": [{"incident": x["incident"], "failed_at": x["failed_at"], "cause": x.get("cause") or x.get("error")}
                     for x in runs if x.get("failed_at")],
        "containment_actions": {k: sum(1 for x in runs if x.get("containment") == k) for k in ("suspended", "revoked", "none")},
        "containment_latency": stats([x["containment_ms"] for x in runs if "containment_ms" in x]),
        "denial_to_completion": stats([x["denial_to_completion_ms"] for x in runs if x.get("denial_to_completion_ms")]),
        "officer_actions_per_recovery": [x["officer_actions"] for x in runs if "officer_actions" in x],
        "request_rate_incidents_during_run": rate_hits,
        "audit_chain_valid": chains_valid, "wall_seconds": round(time.perf_counter() - t0, 2),
        "runs": runs,
    }


def run_recovery(n: int = 20, policy: str = "watch-2.0") -> dict[str, Any]:
    return {
        "independent_incidents": {**_condition(n, shared=False, policy=policy),
                                  "condition": "Each incident in its own fresh isolated environment (no cross-incident history)."},
        "back_to_back_shared": {**_condition(n, shared=True, policy=policy),
                                "condition": "All incidents back-to-back at machine speed in ONE environment: same agents, "
                                             "rules see the accumulated history (stress condition)."},
        "note": "Times are machine time with automated officer calls; real recoveries are dominated by human review time.",
    }
