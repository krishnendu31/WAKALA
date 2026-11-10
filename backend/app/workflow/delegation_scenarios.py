"""Phase 3 delegation scenarios, executed through the REAL gateway.

Every agent step is a signed request through ``Gateway.execute()``; child
mandates are issued only by the ``delegation.commission_task`` handler after
the gateway authorized the commission. Forged / expired chains are presented
through the gateway's ``mandate_source`` hook (simulating compromised or stale
storage) — the verifier, not the scenario, decides the outcome.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES, ToolCall
from app.devtools.issuance import sign_mandate
from app.schemas import DigitalMandate
from app.schemas.case import CaseState, RenewalCase
from app.schemas.workflow import WorkflowRun, WorkflowStep
from app.services.bootstrap import WakalaEnvironment
from app.services.revocation import revoke_case_authority, revoke_mandate

from .intake import _case_mandate, open_case
from .scenarios import WorkflowRunner

INSURANCE_TASK = "insurance_eligibility_check"


def commission_call(case: RenewalCase, task: str = INSURANCE_TASK, receiver: str = "AGT-INS-001",
                    operations: str = "insurance.verify_case_eligibility") -> ToolCall:
    return ToolCall("delegation.commission_task",
                    {"case_id": case.case_id, "citizen_ref": case.citizen_ref, "task": task,
                     "receiving_agent_id": receiver, "requested_operations": operations},
                    case.case_id, f"Commission {task} from {receiver}")


def _control_step(r: WorkflowRunner, title: str, case: RenewalCase, tool: str, note: str, audit_ref: str | None,
                  before: str) -> None:
    r.steps.append(WorkflowStep(
        index=len(r.steps) + 1, title=title, intent="safety_control", agent_id="OFF-0101", tool_name=tool,
        parameters={"case_id": case.case_id}, target_resource=case.case_id, case_id=case.case_id, mandate_id="—",
        executed=True, execution_status="executed", case_state_before=before,
        case_state_after=r.case(case.case_id).state.value, execution_audit_reference=audit_ref, note=note))


def _last_audit(env: WakalaEnvironment, action: str) -> str | None:
    rows = env.db.query("SELECT json_extract(payload, '$.event_id') AS id FROM audit_events "
                        "WHERE json_extract(payload, '$.action') = ? ORDER BY seq DESC LIMIT 1", (action,))
    return rows[0]["id"] if rows else None


def prepare(r: WorkflowRunner, case: RenewalCase, label: str = "") -> str | None:
    """Register, check eligibility and commission the insurance check. Returns the child mandate ID."""
    r.run("AGT-RES-001", RES.register(case), case, f"{label}Register renewal case", "legitimate")
    r.run("AGT-RES-001", RES.check_eligibility(case), case, f"{label}Check residency eligibility", "legitimate")
    if r.case(case.case_id).state is not CaseState.VERIFYING:
        return None
    step = r.run("AGT-RES-001", commission_call(case), case, f"{label}Residency Agent commissions insurance check",
                 "legitimate", note="Commission authority (not execution authority): WAKALA verifies the parent grant "
                                    "and issues a narrowed, signed child mandate to the Insurance Agent.")
    return str(step.result["child_mandate_id"]) if step.executed and step.result else None


def run_delegation_scenario(env: WakalaEnvironment, key: str, citizen_ref: str = "C-1001") -> WorkflowRun:
    r = WorkflowRunner(env, key)

    if key == "delegated_renewal":
        case = open_case(env, citizen_ref, "delegated")
        child = prepare(r, case)
        if child:
            r.run("AGT-INS-001", INS.verify(case), case, "Insurance Agent verifies insurance with its child mandate",
                  "legitimate", mandate_id=child,
                  note="The gateway resolves child → parent → root from server-side records and verifies every link.")
        if r.case(case.case_id).state is CaseState.AWAITING_PAYMENT:
            r.run("AGT-PAY-001", PAY.collect(case), case, "Collect AED 500 renewal fee", "legitimate")
        ready = r.case(case.case_id).state is CaseState.READY_TO_COMPLETE
        r.run("AGT-RES-001", RES.complete(case), case, "Complete renewal", "legitimate" if ready else "prerequisite_check")
        return r.finish(key, case.case_id)

    if key == "selective_revocation":
        c1, c2 = open_case(env, "C-1001", "delegated"), open_case(env, "C-1001", "delegated")
        k1, k2 = prepare(r, c1, "Case 1 · "), prepare(r, c2, "Case 2 · ")
        before = r.case(c1.case_id).state.value
        revoked = revoke_case_authority(env, c1.case_id, "officer withdrew authority for case 1")
        _control_step(r, "Officer revokes case 1 authority (cascades to its delegation)", c1, "case.revoke_authority",
                      f"Revoked {len(revoked)} mandates: case 1 roots and every child delegated from them.",
                      _last_audit(env, "case.revoke_authority"), before)
        if k1:
            r.run("AGT-INS-001", INS.verify(c1), c1, "Case 1 · Insurance check with revoked child", "unauthorized", mandate_id=k1)
        if k2:
            r.run("AGT-INS-001", INS.verify(c2), c2, "Case 2 · Insurance check continues", "legitimate", mandate_id=k2,
                  note="Independent case: its own root and child mandates are untouched.")
        return r.finish(key, c1.case_id, related=[c2.case_id])

    # delegation_attacks ------------------------------------------------------------------
    c1, c2, c3 = (open_case(env, "C-1001", "delegated") for _ in range(3))
    k1 = prepare(r, c1, "Setup · ")
    k2 = prepare(r, c2, "Setup case 2 · ")
    k3 = prepare(r, c3, "Setup case 3 · ")
    if not (k1 and k2 and k3):
        return r.finish(key, c1.case_id, related=[c2.case_id, c3.case_id])

    r.run("AGT-INS-001", INS.verify(c1, "C-1003"), c1, "B · Child mandate reads another citizen", "out_of_scope", mandate_id=k1)
    r.run("AGT-INS-001", PAY.collect(c1), c1, "C · Insurance Agent attempts to collect a payment", "unauthorized", mandate_id=k1)
    r.run("AGT-INS-001", commission_call(c1, "renewal_fee_collection", "AGT-PAY-001", "payment.collect_renewal_fee"), c1,
          "D · Insurance Agent tries to create a broader child mandate", "unauthorized", mandate_id=k1)

    child1 = env.mandates.get(k1)
    forged = child1.model_copy(update={"allowed_tools": ["insurance.verify_case_eligibility", "payment.collect_renewal_fee"]})
    r.run("AGT-INS-001", INS.verify(c1), c1, "E · Forged delegation (scope widened after signing)", "unauthorized",
          mandate_id=k1, mandate_source=lambda mid: forged if mid == k1 else env.mandates.get(mid),
          note="The stored child is replaced in transit by a copy with an extra tool; the delegation signature no longer matches.")
    attacker = Ed25519PrivateKey.generate()
    impostor = sign_mandate(child1.model_copy(update={"mandate_id": "MND-DLG-FORGED01", "signature_metadata": None}),
                            attacker, "KEY-ISS-WAKALA-DELEGATION", child1.issued_at)
    r.run("AGT-INS-001", INS.verify(c1), c1, "E · Child mandate signed with an attacker key", "unauthorized",
          mandate_id=impostor.mandate_id, mandate_source=lambda mid: impostor if mid == impostor.mandate_id else env.mandates.get(mid))

    now = env.clock()
    issuers = {i.issuer_id: i for i in env.repo.list_issuers()}
    root_body = _case_mandate("AGT-RES-001", c1.case_id, c1.citizen_ref, c1.request_id, now - timedelta(hours=3),
                              now - timedelta(hours=2), "delegated")
    root_body["mandate_id"] = f"MND-RES-EXP{secrets.token_hex(2).upper()}"
    iss = issuers["ISS-RESIDENCY-AUTH"]
    old_root = sign_mandate(DigitalMandate.model_validate(root_body), env.keystore.private_key(iss.key_id), iss.key_id,
                            now - timedelta(hours=3))
    assert env.delegation is not None
    old_child = env.delegation._sign(env.delegation.build_child(old_root, INSURANCE_TASK, "AGT-INS-001",
                                                                {"insurance.verify_case_eligibility"}, c1.case_id,
                                                                now - timedelta(hours=3)))
    stale: dict[str, Any] = {old_root.mandate_id: old_root, old_child.mandate_id: old_child}
    r.run("AGT-INS-001", INS.verify(c1), c1, "F · Child of an expired parent mandate", "unauthorized",
          mandate_id=old_child.mandate_id, mandate_source=lambda mid: stale.get(mid) or env.mandates.get(mid),
          note="Both mandates carry valid signatures; the parent's validity window has ended.")

    r.run("AGT-INS-001", INS.verify(c2), c2, "H · Child mandate for case 1 reused on case 2", "out_of_scope", mandate_id=k1)
    r.run("AGT-INS-001", commission_call(c1, INSURANCE_TASK, "AGT-RES-001"), c1,
          "I · Re-delegation back to the Residency Agent (cycle / depth)", "unauthorized", mandate_id=k1)
    r.run("AGT-INS-001", INS.verify(c1), c1, "A · Valid delegated insurance check for Mariam", "legitimate", mandate_id=k1)

    before = r.case(c3.case_id).state.value
    revoked = revoke_mandate(env, c3.mandate_refs["AGT-RES-001"], "parent mandate withdrawn (case 3)")
    _control_step(r, "Officer revokes case 3's Residency mandate", c3, "mandate.revoke",
                  f"Cascade revoked {len(revoked)} mandates (parent + delegated child).", _last_audit(env, "mandate.revoke"), before)
    r.run("AGT-INS-001", INS.verify(c3), c3, "G · Child of a revoked parent", "unauthorized", mandate_id=k3)

    before = r.case(c1.case_id).state.value
    revoked = revoke_case_authority(env, c1.case_id, "case 1 authority withdrawn")
    _control_step(r, "Officer revokes case 1 authority", c1, "case.revoke_authority",
                  f"Revoked {len(revoked)} mandates rooted in case 1.", _last_audit(env, "case.revoke_authority"), before)
    r.run("AGT-PAY-001", PAY.collect(c1), c1, "J · Case 1 operation after revocation", "unauthorized")
    r.run("AGT-INS-001", INS.verify(c2), c2, "J · Independent case 2 continues", "legitimate", mandate_id=k2,
          note="Selective revocation: case 2's authority is untouched; agents were not revoked by any denial above.")
    return r.finish(key, c1.case_id, related=[c2.case_id, c3.case_id])
