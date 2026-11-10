"""Graduated response policy (pure).

severity  → actions (the triggering request has ALREADY been denied)
  low      DENY · monitor
  medium   DENY · ESCALATE_INCIDENT
  high     DENY · SUSPEND_MANDATE (only the mandate used) · REQUIRE_HUMAN_APPROVAL (case paused; sensitive
           operations on the case need officer approval) · ESCALATE_INCIDENT
  critical DENY · REVOKE_MANDATE (only the mandate used, cascading to its delegations) · ESCALATE_INCIDENT

Never agent-wide: suspending or revoking an agent is an explicit officer decision.
Credential findings have no trustworthy mandate to contain (the request was not
authenticated); they escalate and recommend key rotation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.assurance import InterventionReason as IR, ResponseAction as RA

from .rules import Finding


@dataclass(frozen=True)
class PlannedResponse:
    action: RA
    reason: IR
    target: str | None


def plan_response(finding: Finding) -> list[PlannedResponse]:
    sev = finding.severity
    credential = finding.rule.classification == "possible_credential_misuse"
    plan: list[PlannedResponse] = [PlannedResponse(RA.DENY, IR.RESP_MONITOR_ONLY, None)]
    if sev == "low":
        return plan + [PlannedResponse(RA.DENY, IR.RESP_NO_AGENT_WIDE_ACTION, finding.subject)]
    plan.append(PlannedResponse(RA.ESCALATE_INCIDENT, IR.RESP_ESCALATE_FOR_REVIEW, finding.case_id))
    if credential:
        plan.append(PlannedResponse(RA.ESCALATE_INCIDENT, IR.RESP_RECOMMEND_KEY_ROTATION, finding.subject))
        plan.append(PlannedResponse(RA.DENY, IR.RESP_NO_MANDATE_TO_CONTAIN, None))
    elif sev == "high":
        if finding.mandate_id:
            plan.append(PlannedResponse(RA.SUSPEND_MANDATE, IR.RESP_SUSPEND_AFFECTED_MANDATE, finding.mandate_id))
        else:
            plan.append(PlannedResponse(RA.DENY, IR.RESP_NO_MANDATE_TO_CONTAIN, None))
        if finding.case_id:
            plan.append(PlannedResponse(RA.REQUIRE_HUMAN_APPROVAL, IR.RESP_PAUSE_CASE_FOR_REVIEW, finding.case_id))
            plan.append(PlannedResponse(RA.REQUIRE_HUMAN_APPROVAL, IR.RESP_REQUIRE_APPROVAL_FOR_SENSITIVE_OPS, finding.case_id))
    elif sev == "critical":
        if finding.mandate_id:
            plan.append(PlannedResponse(RA.REVOKE_MANDATE, IR.RESP_REVOKE_AFFECTED_MANDATE, finding.mandate_id))
        if finding.case_id:
            plan.append(PlannedResponse(RA.REQUIRE_HUMAN_APPROVAL, IR.RESP_PAUSE_CASE_FOR_REVIEW, finding.case_id))
    plan.append(PlannedResponse(RA.DENY, IR.RESP_NO_AGENT_WIDE_ACTION, finding.subject))
    return plan
