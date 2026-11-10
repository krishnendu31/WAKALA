"""Shared, strictly validated primitive types for WAKALA contracts.

Every identifier has a fixed, recognisable format so that a malformed or
smuggled reference is rejected at the schema boundary, long before any
policy logic runs. All timestamps must be timezone-aware (naive datetimes are
ambiguous and therefore rejected). Money is always an explicit
(amount, currency) pair using Decimal — never a float.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictModel(BaseModel):
    """Base model: unknown fields are rejected and instances are immutable."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


# --- Identifiers -----------------------------------------------------------
# Agent IDs encode a role code and serial, e.g. AGT-RES-001.
AgentId = Annotated[str, StringConstraints(pattern=r"^AGT-[A-Z]{3,8}-\d{3}$")]
# Synthetic citizen reference, e.g. C-1001.
CitizenRef = Annotated[str, StringConstraints(pattern=r"^C-\d{4}$")]
MandateId = Annotated[str, StringConstraints(pattern=r"^MND-[A-Z0-9-]{4,40}$")]
IssuerId = Annotated[str, StringConstraints(pattern=r"^ISS-[A-Z0-9-]{3,40}$")]
CaseId = Annotated[str, StringConstraints(pattern=r"^CASE-[A-Z0-9]{6,12}$")]
RequestId = Annotated[str, StringConstraints(pattern=r"^REQ-[A-Z0-9-]{4,40}$")]
ActionId = Annotated[str, StringConstraints(pattern=r"^ACT-[A-Z0-9-]{4,40}$")]
DecisionId = Annotated[str, StringConstraints(pattern=r"^DEC-[A-Z0-9-]{4,40}$")]
EventId = Annotated[str, StringConstraints(pattern=r"^EVT-[A-Z0-9-]{4,40}$")]
ScenarioId = Annotated[str, StringConstraints(pattern=r"^SCN-\d{3}$")]
DocumentId = Annotated[str, StringConstraints(pattern=r"^DOC-[A-Z0-9-]{4,40}$")]
ServiceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{2,63}$")]
# Tool names are dotted, lower-case verbs, e.g. "residency.read_status".
ToolName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$")]
KeyId = Annotated[str, StringConstraints(pattern=r"^KEY-[A-Z0-9-]{4,40}$")]
# Single-use request nonce (e.g. secrets.token_urlsafe(16)).
Nonce = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,64}$")]
# Raw 64-byte Ed25519 signature, base64url without padding.
SignatureValue = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{86}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

# Every financial reference in the prototype MUST be an obviously fictional
# test identifier. Anything resembling a real IBAN / account number is
# rejected by construction.
SyntheticAccountRef = Annotated[str, StringConstraints(pattern=r"^SYNTH-[A-Z]{2,10}-[A-Z0-9-]{3,32}$")]

NonEmptyText = Annotated[str, StringConstraints(min_length=1, max_length=500)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=120)]

# --- Money -----------------------------------------------------------------
Currency = Literal["AED"]


class Money(StrictModel):
    """A monetary amount. Decimal with at most 2 fractional digits, AED only."""

    amount: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1000000"), max_digits=12, decimal_places=2)]
    currency: Currency = "AED"


# --- Enumerations ----------------------------------------------------------
RiskLevel = Literal["low", "medium", "high", "critical"]
AgentStatus = Literal["active", "suspended", "revoked", "pending_review"]
MandateStatus = Literal["active", "revoked", "suspended"]
RevocationStatus = MandateStatus  # Phase 0 alias
