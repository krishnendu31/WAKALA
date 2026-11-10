"""Phase 4 safe-recovery workflow (simulated agents; real gateway; real officer actions).

``setup_recovery``   Mariam's and Omar's delegated cases (incident policy "contain").
                     The Insurance Agent requests another citizen's record on
                     Mariam's case → DENY → CROSS_CITIZEN_ACCESS incident → only
                     the affected child mandate is suspended and Mariam's case is
                     paused. Omar's case continues with the same agent.
``continue_case``    After an AUTHENTICATED officer has reviewed and acted (via the
                     officer API), advances the case only with signed agent
                     requests through ``Gateway.execute()``. It never sets a state
                     directly; it stops at any denial or pending approval.
"""

from __future__ import annotations

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.delegation import TASK_CATALOG
from app.schemas.case import CaseState
from app.schemas.workflow import WorkflowRun
from app.services.bootstrap import WakalaEnvironment

from .delegation_scenarios import INSURANCE_TASK, commission_call, prepare
from .intake import open_case
from .scenarios import WorkflowRunner


def usable_child(env: WakalaEnvironment, case_id: str, agent_id: str) -> str | None:
    suspended = env.assurance.suspensions.active_ids()
    for d in reversed(env.mandates.delegations(case_id)):
        mid = str(d["child_mandate_id"])
        if d["to_agent"] == agent_id and d["task"] == INSURANCE_TASK and not env.mandates.is_revoked(mid) and mid not in suspended:
            return mid
    return None


def setup_recovery(env: WakalaEnvironment) -> WorkflowRun:
    r = WorkflowRunner(env, "safe_recovery")
    mariam = open_case(env, "C-1001", "delegated", "contain")
    omar = open_case(env, "C-1002", "delegated", "contain")
    km = prepare(r, mariam, "Mariam · ")
    ko = prepare(r, omar, "Omar · ")
    if km:
        r.run("AGT-INS-001", INS.verify(mariam, "C-1003"), mariam, "Mariam · Insurance Agent requests ANOTHER citizen's record",
              "out_of_scope", mandate_id=km,
              note="Denied before any data is read. The deterministic CROSS_CITIZEN_ACCESS rule opens an incident; the case "
                   "incident policy 'contain' suspends only this child mandate and pauses this case for officer review.")
    if ko:
        r.run("AGT-INS-001", INS.verify(omar), omar, "Omar · Same agent continues on an unrelated case", "legitimate",
              mandate_id=ko, note="Independent case: its own child mandate was not suspended, so service continues.")
    return r.finish("safe_recovery", mariam.case_id, related=[omar.case_id])


def continue_case(env: WakalaEnvironment, case_id: str, max_steps: int = 8) -> WorkflowRun:
    r = WorkflowRunner(env, "recovery_continue")
    for _ in range(max_steps):
        case = r.case(case_id)
        before = (case.state, tuple(case.completed_prerequisites), len(r.steps))
        if case.state is CaseState.VERIFYING and "residency_eligibility" not in case.completed_prerequisites:
            r.run("AGT-RES-001", RES.check_eligibility(case), case, "Check residency eligibility", "legitimate")
        elif case.state is CaseState.VERIFYING and "insurance_verified" not in case.completed_prerequisites:
            receiver = case.task_assignments.get(INSURANCE_TASK) or sorted(TASK_CATALOG[INSURANCE_TASK].default_receivers)[0]
            child = usable_child(env, case_id, receiver)
            if child is None:
                step = r.run("AGT-RES-001", commission_call(case, receiver=receiver), case,
                             f"Residency Agent commissions insurance check to {receiver}", "legitimate")
                child = str(step.result["child_mandate_id"]) if step.executed and step.result else None
                if child is None:
                    break
            r.run(receiver, INS.verify(case), case, f"{receiver} verifies insurance with its child mandate", "legitimate",
                  mandate_id=child)
        elif case.state is CaseState.AWAITING_PAYMENT:
            r.run("AGT-PAY-001", PAY.collect(case), case, "Collect AED 500 renewal fee", "legitimate")
        elif case.state is CaseState.READY_TO_COMPLETE:
            r.run("AGT-RES-001", RES.complete(case), case, "Complete renewal", "legitimate")
        else:
            break
        last = r.steps[-1] if r.steps else None
        after = r.case(case_id)
        if last is not None and not last.executed:
            break  # denied or held for approval: stop and let the officer act
        if (after.state, tuple(after.completed_prerequisites), len(r.steps)) == before:
            break
    return r.finish("safe_recovery", case_id)
