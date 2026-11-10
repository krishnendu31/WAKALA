"""Response models for the Government Workflow API (public, synthetic data only)."""

from __future__ import annotations

from typing import Any, Literal

from .authorization import AuditEvent, AuthorizationDecision, ParamKey, ParamValue
from .case import RenewalCase
from .common import StrictModel
from .views import CheckTraceView


class WorkflowStep(StrictModel):
    index: int
    title: str
    intent: Literal["legitimate", "out_of_scope", "unauthorized", "prerequisite_check", "safety_control"]
    agent_id: str
    tool_name: str
    parameters: dict[ParamKey, ParamValue]
    target_resource: str
    case_id: str
    mandate_id: str
    request_digest: str | None = None
    decision: AuthorizationDecision | None = None
    checks: list[CheckTraceView] = []
    executed: bool
    execution_status: str
    result: dict[ParamKey, ParamValue] | None = None
    case_state_before: str
    case_state_after: str
    execution_audit_reference: str | None = None
    note: str | None = None


class BaselineComparison(StrictModel):
    label: Literal["INTENTIONALLY WEAK TEST-ONLY BASELINE"] = "INTENTIONALLY WEAK TEST-ONLY BASELINE"
    description: str
    request: dict[str, Any]
    baseline_allowed: bool
    baseline_checks_performed: list[str]
    baseline_returned_data: dict[str, Any] | None
    wakala_allowed: bool
    wakala_reason_codes: list[str]
    wakala_returned_data: dict[str, Any] | None
    wakala_audit_reference: str


class WorkflowRun(StrictModel):
    scenario: str
    title: str
    description: str
    simulated_agents: Literal[True] = True
    case: RenewalCase
    steps: list[WorkflowStep]
    ledger: list[dict[str, str]]
    renewals: list[dict[str, str]]
    audit_events: list[AuditEvent]
    baseline: BaselineComparison | None = None
    related_cases: list[RenewalCase] = []
    delegations: list[dict[str, str]] = []


class WorkflowScenarioInfo(StrictModel):
    key: str
    title: str
    description: str
    citizen_selectable: bool


class CaseDetail(StrictModel):
    case: RenewalCase
    ledger: list[dict[str, str]]
    renewals: list[dict[str, str]]
    audit_events: list[AuditEvent]
