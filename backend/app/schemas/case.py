"""Renewal case: the unit of case-specific authority.

Every protected Phase 2 operation carries a signed ``case_id``. The gateway
checks that the case exists, belongs to the mandated citizen and request,
lists the agent and its mandate, authorizes the operation, is in a state
that permits it, and has not expired. An agent that is authenticated and
holds general access to a service still cannot act outside its case.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, Field

from .common import AgentId, CitizenRef, MandateId, NonEmptyText, RequestId, ServiceId, ShortText, StrictModel, ToolName


class CaseState(str, Enum):
    CREATED = "CREATED"
    VERIFYING = "VERIFYING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    READY_TO_COMPLETE = "READY_TO_COMPLETE"
    COMPLETED = "COMPLETED"
    PAUSED_FOR_REVIEW = "PAUSED_FOR_REVIEW"
    FAILED = "FAILED"


Prerequisite = Literal["residency_eligibility", "insurance_verified", "fee_paid"]
RecoveryStatus = Literal["none", "paused_for_review", "manual_review_required", "recovered"]


class CaseEvent(StrictModel):
    at: AwareDatetime
    actor: ShortText
    kind: Literal["case_opened", "mandates_issued", "operation_executed", "state_transition", "prerequisite_completed",
                  "prerequisite_failed", "paused_for_review", "resumed", "delegation_issued", "authority_revoked",
                  "task_reassigned", "incident_opened", "officer_action"]
    detail: NonEmptyText
    audit_reference: str | None = None
    from_state: CaseState | None = None
    to_state: CaseState | None = None


class RenewalCase(StrictModel):
    case_id: str = Field(pattern=r"^CASE-[A-Z0-9]{6,12}$")
    citizen_ref: CitizenRef
    service_id: ServiceId
    service_owner: ShortText
    authorized_purpose: NonEmptyText
    request_id: RequestId
    state: CaseState
    paused_from: CaseState | None = None
    assigned_agents: list[AgentId] = Field(min_length=1)
    mandate_refs: dict[AgentId, MandateId]
    authorized_operations: list[ToolName] = Field(min_length=1)
    completed_prerequisites: list[Prerequisite] = Field(default_factory=list)
    created_at: AwareDatetime
    expires_at: AwareDatetime
    recovery_status: RecoveryStatus = "none"
    # Phase 3: case-level revocation (persistent). Revokes the case's mandates and
    # every mandate delegated from them; other cases are unaffected.
    authority_revoked: bool = False
    # How agents obtain authority: "direct" (one issuer mandate each, Phase 2) or
    # "delegated" (some agents only receive WAKALA-issued child mandates).
    authority_model: Literal["direct", "delegated"] = "direct"
    # Phase 4: officer reassignment of a delegable task to a specific receiving agent
    # (e.g. a standby agent). Overrides the catalogue's default receiver for THIS case only.
    task_assignments: dict[str, AgentId] = Field(default_factory=dict)
    # Phase 4 incident policy: "monitor" records and escalates incidents only; "contain"
    # also applies automatic graduated containment (suspend mandate, pause case,
    # require officer approval for sensitive operations).
    incident_policy: Literal["monitor", "contain"] = "monitor"
    version: int = Field(default=1, ge=1)
    history: list[CaseEvent] = Field(default_factory=list)
    synthetic: Literal[True] = True
