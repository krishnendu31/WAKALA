"""Controlled comparison of two review workflows on the SAME synthetic workload.

A · HYPOTHETICAL manual-review-heavy process: every protected request waits for
    an officer. Its outcomes are assumed (a perfect reviewer) — this is NOT a
    description of current UAE government practice.
B · WAKALA: every request is evaluated automatically by the real gateway in an
    isolated in-memory environment; officers handle only escalated exceptions
    (incidents and held approvals), using the real intervention functions.

Measured: request counts, decisions, executions, escalations, gateway time.
Assumed (and labelled): minutes per human review, applied equally to A and B.
No staffing, budget or approval-rate claims are made.
"""

from __future__ import annotations

import tempfile
import time
from typing import Any

from app.core.config import Settings
from app.services.bootstrap import bootstrap

from .delegation_scenarios import prepare
from .intake import open_case
from .recovery import continue_case
from .scenarios import WorkflowRunner


class _Keys:
    """Isolated keystore with a known officer password for the simulated supervisor."""

    def __init__(self, directory: str) -> None:
        from app.devtools.keystore import DevKeystore
        self._ks = DevKeystore(directory)

    def private_key(self, key_id: str):  # type: ignore[no-untyped-def]
        return self._ks.private_key(key_id)

    def officer_password(self, officer_id: str) -> str:
        return f"oversight-sim-{officer_id}"


def run_oversight_comparison(clean_cases: int = 4, violating_cases: int = 1, minutes_per_review: float = 2.0) -> dict[str, Any]:
    clean_cases = max(1, min(clean_cases, 20))
    violating_cases = max(0, min(violating_cases, 10))
    with tempfile.TemporaryDirectory() as d:
        env = bootstrap(Settings(db_path=":memory:", dev_keys_dir=d), keystore=_Keys(d))
        try:
            from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY
            from app.services import interventions as iv

            token, officer = env.officers.login("OFF-0900", "oversight-sim-OFF-0900")
            del token
            runs, interventions, violation_attempts = [], 0, 0
            t0 = time.perf_counter()
            for i in range(clean_cases + violating_cases):
                citizen = "C-1001" if i % 2 == 0 else "C-1002"
                case = open_case(env, citizen, "delegated", "contain")
                r = WorkflowRunner(env, "oversight")
                child = prepare(r, case)
                if i >= clean_cases and child:
                    # Exception: cross-citizen attempt and an over-limit payment attempt.
                    r.run("AGT-INS-001", INS.verify(case, "C-1003"), case, "violation: other citizen", "out_of_scope", mandate_id=child)
                    violation_attempts += 1
                    inc = env.assurance.incidents.case_has_active(case.case_id)
                    if inc is not None:
                        iv.set_incident_status(env, officer, inc.incident_id, "under_review", "triage")
                        iv.reassign_task(env, officer, case.case_id, "insurance_eligibility_check", "AGT-INS-002", "replace agent")
                        iv.resume_case(env, officer, case.case_id, "reviewed")
                        interventions += 3
                runs += r.steps
                cont = continue_case(env, case.case_id)
                runs += cont.steps
                if i >= clean_cases:
                    cur = env.cases.get(case.case_id)
                    if cur.state.value == "AWAITING_PAYMENT" or any(s.execution_status == "pending_approval" for s in cont.steps):
                        r2 = WorkflowRunner(env, "oversight")
                        r2.run("AGT-PAY-001", PAY.collect(cur, "50000.00", "SYNTH-EXT-UNVERIFIED-9999"), cur,
                               "violation: over-limit transfer", "unauthorized")
                        violation_attempts += 1
                        runs += r2.steps
                    for a in env.approvals.list("pending"):
                        if a.case_id == case.case_id:
                            iv.decide_approval(env, officer, a.approval_id, True, "legitimate fee after review")
                            interventions += 1
                    inc = env.assurance.incidents.case_has_active(case.case_id)
                    if inc is not None:
                        iv.set_incident_status(env, officer, inc.incident_id, "resolved", "recovered")
                        interventions += 1
                    runs += continue_case(env, case.case_id).steps
            elapsed_ms = (time.perf_counter() - t0) * 1000
            decisions = [s for s in runs if s.decision is not None]
            executed = [s for s in decisions if s.executed]
            denied = [s for s in decisions if not s.decision.allowed and s.execution_status != "pending_approval"]
            held = [s for s in decisions if s.execution_status == "pending_approval"]
            incidents = env.assurance.incidents.list()
            completed = [c for c in env.cases.list() if c.state.value == "COMPLETED"]
            gateway_ms = sum(s.decision.decision_latency_ms for s in decisions)
            b_reviews = len(incidents) + len(held)
            return {
                "workload": {"cases": clean_cases + violating_cases, "clean_cases": clean_cases, "violating_cases": violating_cases,
                             "requests_processed": len(decisions), "violation_attempts": violation_attempts},
                "assumptions": {
                    "minutes_per_human_review": minutes_per_review,
                    "baseline_A": "HYPOTHETICAL manual process in which every protected request waits for an officer and the "
                                  "officer decides perfectly. Not verified current UAE government practice.",
                    "note": "The same per-review time is applied to A and B; only review COUNTS are compared.",
                },
                "A_manual_review_heavy": {
                    "requests_processed": len(decisions),
                    "requests_requiring_officer_review": len(decisions),
                    "officer_interventions": len(decisions),
                    "legitimate_actions_completed": len(executed),
                    "security_decisions_preserved": f"{len(denied)} of {len(denied)} (assumed: perfect human reviewer)",
                    "review_workflow_minutes_assumed": round(len(decisions) * minutes_per_review, 1),
                },
                "B_wakala_automatic_with_exceptions": {
                    "requests_processed": len(decisions),
                    "requests_requiring_officer_review": b_reviews,
                    "incidents_escalated": len(incidents),
                    "approvals_held": len(held),
                    "officer_interventions": interventions,
                    "legitimate_actions_completed": len(executed),
                    "cases_completed": len(completed),
                    "security_decisions_preserved": f"{len(denied)} denials enforced by the gateway (measured)",
                    "review_workflow_minutes_assumed": round(b_reviews * minutes_per_review, 1),
                    "measured_gateway_decision_ms_total": round(gateway_ms, 1),
                    "measured_wall_clock_ms_total": round(elapsed_ms, 1),
                },
                "audit_chain_valid": env.audit.verify().valid,
            }
        finally:
            env.close()
