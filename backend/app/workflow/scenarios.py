"""Government workflow scenarios A–D, executed through the REAL gateway.

Every agent step is a signed request submitted via ``Gateway.execute()``.
No outcome is set here: each step records whatever the gateway and the
protected service actually returned. Agents are deterministic simulations.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.agents import (
    AgentIdentity,
    InProcessGatewayTransport,
    SigningAgentAdapter,
    SimulatedInsuranceAgent,
    SimulatedPaymentAgent,
    SimulatedResidencyAgent,
    ToolCall,
)
from typing import Any

from app.schemas import AuditEvent, ExecutionResponse
from app.schemas.case import CaseState, RenewalCase
from app.schemas.views import CheckTraceView
from app.schemas.workflow import BaselineComparison, WorkflowRun, WorkflowStep
from app.services.bootstrap import WakalaEnvironment
from app.services.cases import next_case

from .baseline import WeakRoleBaseline
from .intake import open_case


@dataclass(frozen=True)
class ScenarioDef:
    key: str
    title: str
    description: str
    citizen_selectable: bool = False


WORKFLOW_SCENARIOS: tuple[ScenarioDef, ...] = (
    ScenarioDef("legitimate_renewal", "A · Legitimate renewal",
                "Open a case and let the three simulated agents check residency, verify insurance, pay the synthetic "
                "AED 500 fee and complete the renewal — each step independently authorized and audited.", True),
    ScenarioDef("wrong_citizen", "B · Wrong-citizen access",
                "While handling Mariam's case, the authenticated Insurance Agent requests another citizen's insurance "
                "record. The service supports insurance reads in general; this request exceeds the case."),
    ScenarioDef("unauthorized_payment", "C · Unauthorized financial action",
                "With Mariam's case awaiting payment, the Payment Agent attempts AED 50,000 to an unverified "
                "destination. A safety control then pauses the case for human review."),
    ScenarioDef("baseline_comparison", "D · Weak baseline vs WAKALA",
                "The same wrong-citizen request sent to an isolated, intentionally weak role-based baseline and to WAKALA."),
    ScenarioDef("delegated_renewal", "E · Delegated renewal (mandate chain)",
                "The Residency Agent commissions the insurance check; WAKALA issues a narrowed, signed child mandate to the "
                "Insurance Agent, which uses it through the gateway. The renewal then completes.", True),
    ScenarioDef("delegation_attacks", "F · Delegation attack suite",
                "Ten delegation checks (valid use, wrong citizen, payment, broader child, forged signature, expired parent, "
                "revoked parent, cross-case reuse, cycle/depth, selective revocation), each against the real gateway."),
    ScenarioDef("safe_recovery", "H · Incident, human review and safe recovery",
                "Mariam's delegated case: the Insurance Agent requests another citizen's record, WAKALA denies it and opens "
                "an incident, suspends only that child mandate and pauses the case. An authenticated officer reviews and "
                "recovers it in the Security Operations console; Omar's case continues meanwhile."),
    ScenarioDef("selective_revocation", "G · Selective revocation",
                "Two independent delegated cases. Revoking one case's authority cascades to its child mandate only; the "
                "other case continues."),
)
SCENARIO_KEYS = {s.key: s for s in WORKFLOW_SCENARIOS}
OUT_OF_SCOPE_CITIZEN = "C-1003"


class WorkflowRunner:
    def __init__(self, env: WakalaEnvironment, scenario: str) -> None:
        self.env = env
        self.origin = f"workflow:{scenario}"
        self.transport = InProcessGatewayTransport(env.gateway)
        self.agents: dict[str, SigningAgentAdapter] = {}
        standby = [a.agent_id for a in env.repo.list_standby_agents()] if hasattr(env.repo, "list_standby_agents") else []
        for agent_id in ("AGT-RES-001", "AGT-INS-001", "AGT-PAY-001", *standby):
            passport = env.repo.get_agent(agent_id)
            if passport is None:
                raise RuntimeError(f"agent {agent_id} not registered")
            key_id = passport.identity_key_reference.key_id
            self.agents[agent_id] = SigningAgentAdapter(AgentIdentity(agent_id, key_id), env.keystore.private_key(key_id),
                                                        self.transport, env.clock)
        self.steps: list[WorkflowStep] = []

    def case(self, case_id: str) -> RenewalCase:
        c = self.env.cases.get(case_id)
        if c is None:
            raise RuntimeError(f"case {case_id} not found")
        return c

    def run(self, agent_id: str, call: ToolCall, case: RenewalCase, title: str, intent: str, note: str | None = None,
            *, mandate_id: str | None = None, mandate_source: Any = None, **sign_overrides: Any) -> WorkflowStep:
        before = self.case(case.case_id).state.value
        if mandate_id is not None:
            sign_overrides["mandate_id"] = mandate_id
        if sign_overrides or mandate_source is not None:
            signed = self.agents[agent_id].sign(call, case, **sign_overrides)
            out = self.env.gateway.execute(signed, origin=self.origin, mandate_source=mandate_source)
            resp = ExecutionResponse(decision=out.decision, executed=out.executed, execution_status=out.status, result=out.result)
        else:
            signed, resp = self.agents[agent_id].submit(call, case, origin=self.origin)
            out = self.transport.last_outcome
        step = WorkflowStep(
            index=len(self.steps) + 1, title=title, intent=intent,  # type: ignore[arg-type]
            agent_id=agent_id, tool_name=call.tool_name, parameters=signed.request.parameters,
            target_resource=call.target_resource, case_id=case.case_id, mandate_id=signed.request.mandate_id,
            request_digest=resp.decision.request_digest, decision=resp.decision,
            checks=[CheckTraceView(name=c.name, status=c.status, reason_codes=list(c.reason_codes)) for c in out.evaluation.checks],
            executed=resp.executed, execution_status=resp.execution_status, result=resp.result,
            case_state_before=before, case_state_after=self.case(case.case_id).state.value,
            execution_audit_reference=out.execution_event.event_id if out.execution_event else None, note=note,
        )
        self.steps.append(step)
        return step

    def finish(self, key: str, case_id: str, baseline: BaselineComparison | None = None,
               related: list[str] | None = None) -> WorkflowRun:
        d = SCENARIO_KEYS[key]
        related = [c for c in (related or []) if c != case_id]
        events = case_audit_events(self.env, case_id)
        for rc in related:
            events += case_audit_events(self.env, rc)
        return WorkflowRun(scenario=key, title=d.title, description=d.description, case=self.case(case_id), steps=self.steps,
                           ledger=self.env.services.ledger(case_id), renewals=self.env.services.renewals(case_id),
                           audit_events=sorted(events, key=lambda e: e.sequence or 0), baseline=baseline,
                           related_cases=[self.case(c) for c in related],
                           delegations=[{k: str(v) for k, v in d.items()} for cid in [case_id, *related]
                                        for d in self.env.mandates.delegations(cid)])


def case_audit_events(env: WakalaEnvironment, case_id: str) -> list[AuditEvent]:
    rows = env.db.query(
        "SELECT payload FROM audit_events WHERE json_extract(payload, '$.evidence_metadata.case_id') = ? ORDER BY seq", (case_id,))
    return [AuditEvent.model_validate_json(r["payload"]) for r in rows]


def pause_for_review(env: WakalaEnvironment, case_id: str, reason: str, related_decision: str | None) -> tuple[RenewalCase, AuditEvent]:
    """Safety control (prototype policy): pause a case after a denied high-risk action. Recorded and audited."""
    from app.services.cases import CaseStore

    now = env.clock()
    current = env.cases.get(case_id)
    if current is None:
        raise RuntimeError("case not found")
    next_case(current, CaseState.PAUSED_FOR_REVIEW, actor="WAKALA-GATEWAY", at=now, detail=reason)  # validate first
    event = env.audit.append(AuditEvent(
        event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=now, actor="WAKALA-GATEWAY", action="case.pause_for_review",
        decision="informational", evidence_metadata={"case_id": case_id, "reason": reason[:200],
                                                     "related_decision": related_decision, "origin": "safety_control"},
    ))
    with env.db.transaction() as conn:
        before = CaseStore.load_in(conn, case_id)
        if before is None:
            raise RuntimeError("case not found")
        after = next_case(before, CaseState.PAUSED_FOR_REVIEW, actor="WAKALA-GATEWAY", at=now, detail=reason,
                          audit_reference=event.event_id)
        CaseStore.save_in(conn, before, after)
    return after, event


def _verify_prereqs(r: WorkflowRunner, case: RenewalCase) -> RenewalCase:
    res, ins = SimulatedResidencyAgent, SimulatedInsuranceAgent
    r.run("AGT-RES-001", res.register(case), case, "Register renewal case", "legitimate")
    r.run("AGT-RES-001", res.check_eligibility(case), case, "Check residency eligibility", "legitimate")
    if r.case(case.case_id).state is CaseState.VERIFYING:
        r.run("AGT-INS-001", ins.verify(case), case, "Verify insurance eligibility", "legitimate")
    return r.case(case.case_id)


def run_workflow(env: WakalaEnvironment, key: str, citizen_ref: str = "C-1001") -> WorkflowRun:
    if key not in SCENARIO_KEYS:
        raise KeyError(key)
    if key == "safe_recovery":
        from .recovery import setup_recovery
        return setup_recovery(env)
    if key in {"delegated_renewal", "delegation_attacks", "selective_revocation"}:
        from .delegation_scenarios import run_delegation_scenario
        return run_delegation_scenario(env, key, citizen_ref if SCENARIO_KEYS[key].citizen_selectable else "C-1001")
    if not SCENARIO_KEYS[key].citizen_selectable:
        citizen_ref = "C-1001"
    r = WorkflowRunner(env, key)
    case = open_case(env, citizen_ref)
    res, ins, pay = SimulatedResidencyAgent, SimulatedInsuranceAgent, SimulatedPaymentAgent

    if key == "legitimate_renewal":
        current = _verify_prereqs(r, case)
        if current.state is CaseState.AWAITING_PAYMENT:
            r.run("AGT-PAY-001", pay.collect(case), case, "Collect AED 500 renewal fee", "legitimate")
        # Always attempt completion: if prerequisites failed, the gateway must refuse it.
        r.run("AGT-RES-001", res.complete(case), case, "Complete renewal",
              "legitimate" if r.case(case.case_id).state is CaseState.READY_TO_COMPLETE else "prerequisite_check",
              note=None if r.case(case.case_id).state is CaseState.READY_TO_COMPLETE else
              "Attempted although prerequisites are not satisfied — completion must be refused.")
        return r.finish(key, case.case_id)

    if key == "wrong_citizen":
        r.run("AGT-RES-001", res.register(case), case, "Register renewal case", "legitimate")
        r.run("AGT-RES-001", res.check_eligibility(case), case, "Check residency eligibility", "legitimate")
        r.run("AGT-INS-001", ins.verify(case, OUT_OF_SCOPE_CITIZEN), case, f"Insurance lookup for {OUT_OF_SCOPE_CITIZEN} (wrong citizen)",
              "out_of_scope", note="Same agent, same service, valid identity and mandate — but a citizen outside this case.")
        r.run("AGT-INS-001", ins.verify(case), case, "Insurance lookup for the case citizen", "legitimate",
              note="The identical operation within the case scope is authorized.")
        return r.finish(key, case.case_id)

    if key == "unauthorized_payment":
        _verify_prereqs(r, case)
        bad = r.run("AGT-PAY-001", pay.collect(case, "50000.00", "SYNTH-EXT-UNVERIFIED-9999"), case,
                    "Transfer AED 50,000 to SYNTH-EXT-UNVERIFIED-9999", "unauthorized")
        if bad.decision is not None and not bad.decision.allowed:
            before = r.case(case.case_id).state.value
            paused, ev = pause_for_review(env, case.case_id, "Denied high-risk financial request; human review required",
                                          bad.decision.decision_id)
            r.steps.append(WorkflowStep(
                index=len(r.steps) + 1, title="Safety control: pause case for human review", intent="safety_control",
                agent_id="WAKALA-GATEWAY", tool_name="case.pause_for_review", parameters={"case_id": case.case_id},
                target_resource=case.case_id, case_id=case.case_id, mandate_id="—", executed=True,
                execution_status="executed", case_state_before=before, case_state_after=paused.state.value,
                execution_audit_reference=ev.event_id,
                note="Not an agent action: a server-side control. The denied transfer itself changed nothing.",
            ))
        return r.finish(key, case.case_id)

    # baseline_comparison
    r.run("AGT-RES-001", res.register(case), case, "Register renewal case", "legitimate")
    r.run("AGT-RES-001", res.check_eligibility(case), case, "Check residency eligibility", "legitimate")
    wak = r.run("AGT-INS-001", ins.verify(case, OUT_OF_SCOPE_CITIZEN), case,
                f"WAKALA: insurance lookup for {OUT_OF_SCOPE_CITIZEN}", "out_of_scope")
    base = WeakRoleBaseline().read_insurance("AGT-INS-001", OUT_OF_SCOPE_CITIZEN, env.clock())
    if wak.decision is None:
        raise RuntimeError("gateway returned no decision")
    comparison = BaselineComparison(
        description=("Role-only check ('insurance agents may read insurance records'), no signature, no mandate, no case "
                     "binding. Isolated in-memory copy of the synthetic fixtures; not connected to WAKALA's services."),
        request={"agent_id": "AGT-INS-001", "operation": "read insurance record", "citizen_ref": OUT_OF_SCOPE_CITIZEN,
                 "active_case": case.case_id, "case_citizen": case.citizen_ref},
        baseline_allowed=base["allowed"], baseline_checks_performed=base["checks_performed"],
        baseline_returned_data=base["returned_data"],
        wakala_allowed=wak.decision.allowed, wakala_reason_codes=[c.value for c in wak.decision.reason_codes],
        wakala_returned_data=wak.result if wak.executed else None, wakala_audit_reference=wak.decision.audit_reference,
    )
    return r.finish(key, case.case_id, comparison)

