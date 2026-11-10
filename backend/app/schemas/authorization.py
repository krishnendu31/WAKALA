"""ActionRequest, SignedActionRequest, AuthorizationDecision and AuditEvent.

Traffic through the enforcement gateway:

    agent ──SignedActionRequest──▶ gateway ──AuthorizationDecision──▶ agent
                                      └──AuditEvent──▶ hash-chained log

``agent_id`` inside an ActionRequest is a *claim*. It is authenticated only
by the Ed25519 signature in ``SignedActionRequest.signature``, verified
against the public key registered for that agent.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from .common import (
    ActionId,
    CaseId,
    AgentId,
    DecisionId,
    EventId,
    KeyId,
    MandateId,
    NonEmptyText,
    Nonce,
    RequestId,
    Sha256Hex,
    ShortText,
    SignatureValue,
    StrictModel,
    ToolName,
)

# Parameters are restricted to flat JSON scalars so that nested, ambiguous or
# executable payloads cannot be smuggled into a tool call.
ParamKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
ParamValue = Union[Annotated[str, StringConstraints(max_length=2000)], int, float, bool, None]


class DelegationLink(StrictModel):
    """One hop: ``from_agent_id`` delegated to ``to_agent_id`` under ``mandate_id``."""

    from_agent_id: AgentId
    to_agent_id: AgentId
    mandate_id: MandateId

    @model_validator(mode="after")
    def _no_self_delegation(self) -> "DelegationLink":
        if self.from_agent_id == self.to_agent_id:
            raise ValueError("an agent cannot delegate to itself")
        return self


class ActionRequest(StrictModel):
    action_id: ActionId
    request_id: RequestId
    agent_id: AgentId
    # The mandate the agent invokes. The gateway loads it from its own store;
    # agents never submit mandate bodies.
    mandate_id: MandateId
    tool_name: ToolName
    parameters: dict[ParamKey, ParamValue] = Field(default_factory=dict, max_length=32)
    target_resource: ShortText
    purpose: NonEmptyText
    delegation_chain: list[DelegationLink] = Field(default_factory=list, max_length=8)
    timestamp: AwareDatetime
    # Single-use value; a second request with the same (agent_id, nonce) is a replay.
    nonce: Nonce
    # Phase 2: the renewal case this action belongs to. Signed like every
    # other field; required for case-bound tools.
    case_id: CaseId | None = None

    @model_validator(mode="after")
    def _chain_is_contiguous(self) -> "ActionRequest":
        chain = self.delegation_chain
        for prev, nxt in zip(chain, chain[1:]):
            if prev.to_agent_id != nxt.from_agent_id:
                raise ValueError("delegation_chain is not contiguous")
        if chain and chain[-1].to_agent_id != self.agent_id:
            raise ValueError("delegation_chain must end at the requesting agent")
        return self


class RequestSignature(StrictModel):
    algorithm: Literal["Ed25519"] = "Ed25519"
    key_id: KeyId
    # Ed25519 over b"WAKALA-ACTION-REQUEST-v1\n" + canonical JSON of ``request``.
    value: SignatureValue


class SignedActionRequest(StrictModel):
    request: ActionRequest
    signature: RequestSignature


class ReasonCode(str, Enum):
    ALLOW_WITHIN_MANDATE = "ALLOW_WITHIN_MANDATE"
    DENY_DEFAULT = "DENY_DEFAULT"
    DENY_ENGINE_NOT_CONNECTED = "DENY_ENGINE_NOT_CONNECTED"
    DENY_POLICY_EVALUATION_ERROR = "DENY_POLICY_EVALUATION_ERROR"
    # 1 — identity
    DENY_UNKNOWN_AGENT = "DENY_UNKNOWN_AGENT"
    DENY_IDENTITY_UNVERIFIED = "DENY_IDENTITY_UNVERIFIED"
    DENY_REQUEST_SIGNATURE_INVALID = "DENY_REQUEST_SIGNATURE_INVALID"
    DENY_IDENTITY_MISMATCH = "DENY_IDENTITY_MISMATCH"
    # 2 — agent status
    DENY_AGENT_NOT_ACTIVE = "DENY_AGENT_NOT_ACTIVE"
    # 3 — mandate integrity and issuer trust
    DENY_MANDATE_MISSING = "DENY_MANDATE_MISSING"
    DENY_MANDATE_MALFORMED = "DENY_MANDATE_MALFORMED"
    DENY_MANDATE_UNSIGNED = "DENY_MANDATE_UNSIGNED"
    DENY_SIGNATURE_INVALID = "DENY_SIGNATURE_INVALID"
    DENY_ISSUER_UNTRUSTED = "DENY_ISSUER_UNTRUSTED"
    DENY_ISSUER_AUTHORITY_EXCEEDED = "DENY_ISSUER_AUTHORITY_EXCEEDED"
    DENY_MANDATE_AGENT_MISMATCH = "DENY_MANDATE_AGENT_MISMATCH"
    # 4 — mandate lifecycle
    DENY_MANDATE_EXPIRED = "DENY_MANDATE_EXPIRED"
    DENY_MANDATE_NOT_YET_VALID = "DENY_MANDATE_NOT_YET_VALID"
    DENY_MANDATE_REVOKED = "DENY_MANDATE_REVOKED"
    # 5 — tool permission
    DENY_UNKNOWN_TOOL = "DENY_UNKNOWN_TOOL"
    DENY_TOOL_NOT_PERMITTED = "DENY_TOOL_NOT_PERMITTED"
    DENY_TOOL_EXPLICITLY_DENIED = "DENY_TOOL_EXPLICITLY_DENIED"
    DENY_SERVICE_SCOPE_VIOLATION = "DENY_SERVICE_SCOPE_VIOLATION"
    # 6 — resource scope and case binding
    DENY_SCOPE_VIOLATION = "DENY_SCOPE_VIOLATION"
    DENY_CASE_REQUIRED = "DENY_CASE_REQUIRED"
    DENY_CASE_NOT_FOUND = "DENY_CASE_NOT_FOUND"
    DENY_CASE_SCOPE_VIOLATION = "DENY_CASE_SCOPE_VIOLATION"
    DENY_CASE_AGENT_NOT_ASSIGNED = "DENY_CASE_AGENT_NOT_ASSIGNED"
    DENY_CASE_OPERATION_NOT_AUTHORIZED = "DENY_CASE_OPERATION_NOT_AUTHORIZED"
    DENY_CASE_PURPOSE_MISMATCH = "DENY_CASE_PURPOSE_MISMATCH"
    DENY_CASE_STATE_INVALID = "DENY_CASE_STATE_INVALID"
    DENY_CASE_EXPIRED = "DENY_CASE_EXPIRED"
    # 7 — action constraints
    DENY_INVALID_PARAMETERS = "DENY_INVALID_PARAMETERS"
    DENY_CONSTRAINT_MISSING = "DENY_CONSTRAINT_MISSING"
    DENY_AMOUNT_EXCEEDS_LIMIT = "DENY_AMOUNT_EXCEEDS_LIMIT"
    DENY_RECIPIENT_NOT_ALLOWLISTED = "DENY_RECIPIENT_NOT_ALLOWLISTED"
    # 8 — request context
    DENY_REQUEST_STALE = "DENY_REQUEST_STALE"
    DENY_REPLAYED_REQUEST = "DENY_REPLAYED_REQUEST"
    DENY_DELEGATION_EXPANDS_AUTHORITY = "DENY_DELEGATION_EXPANDS_AUTHORITY"
    DENY_DELEGATION_CHAIN_INVALID = "DENY_DELEGATION_CHAIN_INVALID"
    # Phase 3 — mandate chains and delegation
    DENY_DELEGATION_NOT_PERMITTED = "DENY_DELEGATION_NOT_PERMITTED"
    DENY_DELEGATION_DEPTH_EXCEEDED = "DENY_DELEGATION_DEPTH_EXCEEDED"
    DENY_DELEGATION_CYCLE = "DENY_DELEGATION_CYCLE"
    DENY_DELEGATION_CASE_MISMATCH = "DENY_DELEGATION_CASE_MISMATCH"
    DENY_PARENT_MANDATE_INVALID = "DENY_PARENT_MANDATE_INVALID"
    DENY_PARENT_MANDATE_EXPIRED = "DENY_PARENT_MANDATE_EXPIRED"
    DENY_PARENT_MANDATE_REVOKED = "DENY_PARENT_MANDATE_REVOKED"
    DENY_CASE_AUTHORITY_REVOKED = "DENY_CASE_AUTHORITY_REVOKED"
    # Phase 4 — interventions
    DENY_MANDATE_SUSPENDED = "DENY_MANDATE_SUSPENDED"
    DENY_PARENT_MANDATE_SUSPENDED = "DENY_PARENT_MANDATE_SUSPENDED"
    ESCALATE_HUMAN_REVIEW = "ESCALATE_HUMAN_REVIEW"


class AuthorizationDecision(StrictModel):
    decision_id: DecisionId
    allowed: bool
    reason_codes: list[ReasonCode] = Field(min_length=1)
    human_readable_explanation: NonEmptyText
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    decision_latency_ms: float = Field(ge=0, le=60_000)
    audit_reference: EventId
    mandate_id: MandateId | None = None
    # SHA-256 of the exact signed request bytes this decision applies to.
    request_digest: Sha256Hex | None = None
    # Phase 4: set when the request was held for human approval (nothing executed).
    pending_approval_id: str | None = Field(default=None, pattern=r"^APR-[A-Z0-9]{6,16}$")

    @model_validator(mode="after")
    def _codes_match_outcome(self) -> "AuthorizationDecision":
        allow_codes = [c for c in self.reason_codes if c is ReasonCode.ALLOW_WITHIN_MANDATE]
        if self.allowed and (len(allow_codes) != len(self.reason_codes)):
            raise ValueError("an allowed decision may only carry ALLOW_* reason codes")
        if not self.allowed and allow_codes:
            raise ValueError("a denied decision cannot carry ALLOW_* reason codes")
        return self


AUDIT_ACTORS_SPECIAL = {"WAKALA-GATEWAY", "UNAUTHENTICATED"}


class AuditEvent(StrictModel):
    event_id: EventId
    timestamp: AwareDatetime
    # Verified agent identity, or UNAUTHENTICATED when the signature failed.
    actor: ShortText
    action: ShortText
    decision: Literal["allowed", "denied", "escalated", "informational"]
    request_id: RequestId | None = None
    related_mandate: MandateId | None = None
    evidence_metadata: dict[ParamKey, ParamValue] = Field(default_factory=dict, max_length=64)
    # --- Phase 1 decision fields (optional so informational events stay valid)
    sequence: int | None = Field(default=None, ge=1)
    authenticated: bool = False
    claimed_agent_id: AgentId | None = None
    mandate_version: int | None = Field(default=None, ge=1)
    decision_id: DecisionId | None = None
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    policy_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    decision_latency_ms: float | None = Field(default=None, ge=0)
    # Hash chain: each event commits to its predecessor's hash.
    previous_event_hash: Sha256Hex | None = None
    event_hash: Sha256Hex | None = None

    @field_validator("actor")
    @classmethod
    def _actor_format(cls, actor: str) -> str:
        if not (actor.startswith("AGT-") or actor.startswith("OFF-") or actor in AUDIT_ACTORS_SPECIAL):
            raise ValueError("actor must be an agent id, an officer id, WAKALA-GATEWAY or UNAUTHENTICATED")
        return actor


ExecutionStatus = Literal["executed", "denied", "no_handler_registered", "execution_failed", "refused_by_service",
                          "pending_approval"]


class ExecutionResponse(StrictModel):
    decision: AuthorizationDecision
    executed: bool
    execution_status: ExecutionStatus
    result: dict[ParamKey, ParamValue] | None = None
