"""Read-model response schemas for the console API (public information only)."""

from __future__ import annotations

from typing import Literal

from .authorization import AuditEvent, AuthorizationDecision, ParamKey, ParamValue, ReasonCode
from .common import StrictModel
from .issuer import TrustedIssuer
from .mandate import DigitalMandate


class MandateVerificationView(StrictModel):
    valid: bool
    effective_status: Literal["active", "revoked", "expired", "not_yet_valid", "invalid"]
    signature_valid: bool
    issuer_trusted: bool
    within_issuer_authority: bool
    reason_codes: list[ReasonCode]
    checked_at: str


class MandateView(StrictModel):
    mandate: DigitalMandate
    verification: MandateVerificationView
    revoked: bool
    revoked_at: str | None = None
    revocation_reason: str | None = None


class IssuerView(StrictModel):
    issuer: TrustedIssuer
    key_fingerprint: str | None
    key_registered: bool


class PublicKeyView(StrictModel):
    key_id: str
    owner_type: Literal["agent", "issuer"]
    owner_id: str
    algorithm: Literal["Ed25519"] = "Ed25519"
    fingerprint: str
    status: Literal["active", "revoked"]
    registered_at: str


class AuditIntegrityView(StrictModel):
    valid: bool
    event_count: int
    head_hash: str
    first_broken_sequence: int | None
    detail: str
    scope_note: str = (
        "Detects modification, reordering and mid-log deletion. Does not detect tail truncation or a consistent "
        "rewrite by whoever controls storage; production requires external checkpointing."
    )


class AuditEventListView(StrictModel):
    items: list[AuditEvent]
    count: int
    allowed_count: int
    denied_count: int
    synthetic_data: Literal[True] = True
    enforcement_engine_connected: bool


class CheckTraceView(StrictModel):
    name: str
    status: Literal["passed", "failed", "not_evaluated"]
    reason_codes: list[ReasonCode]


class DevScenarioInfo(StrictModel):
    key: str
    title: str
    description: str
    designed_to_test: str


class DevRequestSummary(StrictModel):
    agent_id: str
    tool_name: str
    mandate_id: str
    target_resource: str
    parameters: dict[ParamKey, ParamValue]
    nonce: str
    request_digest: str


class DevScenarioResult(StrictModel):
    scenario: DevScenarioInfo
    request: DevRequestSummary
    decision: AuthorizationDecision
    executed: bool
    execution_status: str
    result: dict[ParamKey, ParamValue] | None
    checks: list[CheckTraceView]
    note: str | None = None
    development_only: Literal[True] = True
