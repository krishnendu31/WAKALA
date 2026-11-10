"""Phase 4 contracts: incidents, graduated responses, pending approvals, officers.

Detection here is DETERMINISTIC rule evaluation over signed gateway and
delegation events — not machine-learning anomaly detection. An incident is
evidence that requests attributed to an agent violated policy (or that its
credential may be misused); it is not, by itself, proof the agent is malicious.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, Field

from .common import AgentId, CaseId, MandateId, NonEmptyText, ShortText, StrictModel

Severity = Literal["low", "medium", "high", "critical"]
SEVERITY_ORDER: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}

IncidentStatus = Literal["open", "under_review", "contained", "resolved", "dismissed"]
ACTIVE_INCIDENT_STATUSES = ("open", "under_review")

Classification = Literal["policy_violation", "operational_anomaly", "possible_credential_misuse"]


class ResponseAction(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"
    SUSPEND_MANDATE = "SUSPEND_MANDATE"
    REVOKE_MANDATE = "REVOKE_MANDATE"
    ESCALATE_INCIDENT = "ESCALATE_INCIDENT"


class InterventionReason(str, Enum):
    RESP_MONITOR_ONLY = "RESP_MONITOR_ONLY"
    RESP_ESCALATE_FOR_REVIEW = "RESP_ESCALATE_FOR_REVIEW"
    RESP_SUSPEND_AFFECTED_MANDATE = "RESP_SUSPEND_AFFECTED_MANDATE"
    RESP_PAUSE_CASE_FOR_REVIEW = "RESP_PAUSE_CASE_FOR_REVIEW"
    RESP_REQUIRE_APPROVAL_FOR_SENSITIVE_OPS = "RESP_REQUIRE_APPROVAL_FOR_SENSITIVE_OPS"
    RESP_REVOKE_AFFECTED_MANDATE = "RESP_REVOKE_AFFECTED_MANDATE"
    RESP_NO_MANDATE_TO_CONTAIN = "RESP_NO_MANDATE_TO_CONTAIN"
    RESP_NO_AGENT_WIDE_ACTION = "RESP_NO_AGENT_WIDE_ACTION"
    RESP_RECOMMEND_KEY_ROTATION = "RESP_RECOMMEND_KEY_ROTATION"


class ResponseRecord(StrictModel):
    at: AwareDatetime
    action: ResponseAction
    reason: InterventionReason
    target: str | None = None
    applied: bool
    detail: NonEmptyText
    audit_reference: str | None = None


class Incident(StrictModel):
    incident_id: str = Field(pattern=r"^INC-[A-Z0-9]{6,16}$")
    rule_id: str = Field(pattern=r"^[A-Z_]{3,40}$")
    title: ShortText
    severity: Severity
    classification: Classification
    status: IncidentStatus
    agent_id: str | None = None  # authenticated agent, or claimed identity for credential findings
    case_id: CaseId | None = None
    mandate_id: MandateId | None = None
    first_seen: AwareDatetime
    last_seen: AwareDatetime
    occurrences: int = Field(ge=1)
    evidence_event_ids: list[str] = Field(default_factory=list, max_length=200)
    summary: NonEmptyText
    interpretation: NonEmptyText
    responses: list[ResponseRecord] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    # Behaviour Watch 2.0 (absent on incidents recorded before Phase 6; treated as the severity's legacy level)
    intervention_level: str | None = None
    observed: str | None = None
    expected: str | None = None
    concern: str | None = None
    policy: str | None = None
    synthetic: Literal[True] = True


ApprovalStatus = Literal["pending", "executing", "approved_executed", "approved_denied", "rejected", "expired"]


class PendingApproval(StrictModel):
    approval_id: str = Field(pattern=r"^APR-[A-Z0-9]{6,16}$")
    status: ApprovalStatus
    created_at: AwareDatetime
    expires_at: AwareDatetime
    case_id: CaseId | None
    agent_id: AgentId
    tool_name: ShortText
    mandate_id: MandateId
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: NonEmptyText
    incident_id: str | None = None
    escalation_event: str
    decided_by: str | None = None
    decided_at: AwareDatetime | None = None
    decision_note: str | None = None
    reauthorization_decision_id: str | None = None
    reauthorization_codes: list[str] = Field(default_factory=list)
    execution_status: str | None = None


OfficerRole = Literal["auditor", "case_officer", "security_supervisor"]


class Officer(StrictModel):
    officer_id: str = Field(pattern=r"^OFF-\d{4}$")
    name: ShortText
    title: ShortText
    entity: ShortText
    role: OfficerRole
    status: Literal["active", "suspended"]
    synthetic: Literal[True] = True
