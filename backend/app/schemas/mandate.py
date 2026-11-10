"""DigitalMandate — a signed, task-limited grant of authority to one agent.

Conceptually similar to a narrowly scoped power of attorney: *who* may do
*what*, *for whom*, *for how long* and *within which limits*. This is a
technical authorization artefact only; it is not a legally recognised
government power of attorney.

A mandate is trusted **only** because it carries a valid Ed25519 signature
from a registered issuer whose authority covers it (see
``app.core.mandates.verification``). No field in the body — ``issuer_id``
included — confers trust by itself.

Structural invariants enforced here (independent of signatures):

* timestamps are timezone-aware and ``expires_at > issued_at``
* a mandate lives at most ``MAX_MANDATE_LIFETIME`` (task-limited, not standing)
* a tool cannot be both allowed and denied
* monetary limits and recipient allow-lists must appear together
* resource identifiers are explicit (no wildcards)
* a mandate cannot name itself as its own parent
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .common import (
    AgentId,
    CitizenRef,
    IssuerId,
    KeyId,
    MandateId,
    MandateStatus,
    Money,
    NonEmptyText,
    RequestId,
    ServiceId,
    SignatureValue,
    StrictModel,
    SyntheticAccountRef,
    ToolName,
)

MAX_MANDATE_LIFETIME = timedelta(hours=24)

ResourceType = Literal["citizen_record", "insurance_record", "payment", "document", "application", "renewal_case"]
AccessMode = Literal["read", "write", "execute"]


class MandateScope(StrictModel):
    """The single citizen and request this mandate is bound to."""

    citizen_ref: CitizenRef
    request_id: RequestId


class ResourceConstraint(StrictModel):
    resource_type: ResourceType
    access: AccessMode
    # Explicit identifiers only — wildcards are not representable.
    identifiers: list[str] = Field(min_length=1, max_length=20)

    @field_validator("identifiers")
    @classmethod
    def _no_wildcards(cls, ids: list[str]) -> list[str]:
        for item in ids:
            if not item or len(item) > 64 or any(ch in item for ch in "*?%"):
                raise ValueError("resource identifiers must be explicit; wildcards are not allowed")
        return ids


class SignatureMetadata(StrictModel):
    algorithm: Literal["Ed25519"] = "Ed25519"
    key_id: KeyId
    # Base64url Ed25519 signature over b"WAKALA-MANDATE-v1\n" + canonical body
    # (see app.core.mandates.canonical). ``signed_at`` is informational and
    # is not covered by the signature.
    signature: SignatureValue
    signed_at: AwareDatetime


class DigitalMandate(StrictModel):
    mandate_id: MandateId
    version: int = Field(default=1, ge=1, le=10_000)
    agent_id: AgentId
    issuer_id: IssuerId
    service_id: ServiceId
    purpose: NonEmptyText
    citizen_or_request_scope: MandateScope
    allowed_tools: list[ToolName] = Field(min_length=1, max_length=32)
    denied_tools: list[ToolName] = Field(default_factory=list, max_length=32)
    resource_constraints: list[ResourceConstraint] = Field(default_factory=list, max_length=16)
    amount_limit: Money | None = None
    recipient_allowlist: list[SyntheticAccountRef] = Field(default_factory=list, max_length=16)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    # Status as signed at issuance. Revocation after issue is recorded in the
    # server-side mandate store and checked by the gateway.
    status: MandateStatus = "active"
    parent_mandate_id: MandateId | None = None
    # ``None`` means unsigned. The gateway rejects unsigned mandates.
    signature_metadata: SignatureMetadata | None = None

    @field_validator("allowed_tools", "denied_tools", "recipient_allowlist")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("list contains duplicate entries")
        return values

    @model_validator(mode="after")
    def _structural_invariants(self) -> "DigitalMandate":
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        if self.expires_at - self.issued_at > MAX_MANDATE_LIFETIME:
            raise ValueError(f"mandate lifetime exceeds maximum of {MAX_MANDATE_LIFETIME}")
        overlap = set(self.allowed_tools) & set(self.denied_tools)
        if overlap:
            raise ValueError(f"tools cannot be both allowed and denied: {sorted(overlap)}")
        if self.amount_limit is not None and not self.recipient_allowlist:
            raise ValueError("a monetary amount_limit requires a non-empty recipient_allowlist")
        if self.recipient_allowlist and self.amount_limit is None:
            raise ValueError("a recipient_allowlist requires an explicit amount_limit")
        if self.parent_mandate_id is not None and self.parent_mandate_id == self.mandate_id:
            raise ValueError("a mandate cannot be its own parent")
        return self

    def is_expired_at(self, moment: datetime) -> bool:
        return moment >= self.expires_at
