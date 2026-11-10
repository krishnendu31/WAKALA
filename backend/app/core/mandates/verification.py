"""Mandate verification: integrity, issuer trust, issuer authority, lifecycle.

Order matters. The signature is verified *before* any authority-bearing field
is trusted. ``issuer_id`` is only used to look up which key must have signed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.crypto import verify
from app.schemas import DigitalMandate, ReasonCode, TrustedIssuer

from .canonical import mandate_signing_message

R = ReasonCode


def verify_mandate_integrity(
    mandate: DigitalMandate,
    issuers: Mapping[str, TrustedIssuer],
    issuer_public_keys: Mapping[str, Ed25519PublicKey],
) -> list[ReasonCode]:
    """Signature + issuer trust + issuer authority. Empty list = trusted."""
    meta = mandate.signature_metadata
    if meta is None:
        return [R.DENY_MANDATE_UNSIGNED]
    issuer = issuers.get(mandate.issuer_id)
    if issuer is None or issuer.status != "active":
        return [R.DENY_ISSUER_UNTRUSTED]
    if meta.key_id != issuer.key_id:
        # Signed with a key that does not belong to the named issuer.
        return [R.DENY_ISSUER_UNTRUSTED]
    public_key = issuer_public_keys.get(issuer.key_id)
    if public_key is None:
        return [R.DENY_ISSUER_UNTRUSTED]
    tag, payload = mandate_signing_message(mandate)
    if not verify(public_key, tag, payload, meta.signature):
        return [R.DENY_SIGNATURE_INVALID]
    return check_issuer_authority(mandate, issuer)


def check_issuer_authority(mandate: DigitalMandate, issuer: TrustedIssuer) -> list[ReasonCode]:
    auth = issuer.authority
    exceeded = (
        mandate.service_id not in auth.services
        or mandate.agent_id not in auth.agents
        or not set(mandate.allowed_tools) <= set(auth.tools)
        or not set(mandate.recipient_allowlist) <= set(auth.recipients)
        or (mandate.expires_at - mandate.issued_at).total_seconds() > auth.max_lifetime_hours * 3600
    )
    if mandate.amount_limit is not None:
        exceeded = exceeded or auth.max_amount is None or (
            mandate.amount_limit.currency != auth.max_amount.currency
            or mandate.amount_limit.amount > auth.max_amount.amount
        )
    return [R.DENY_ISSUER_AUTHORITY_EXCEEDED] if exceeded else []


def check_mandate_lifecycle(mandate: DigitalMandate, now: datetime, revoked_ids: frozenset[str]) -> list[ReasonCode]:
    if mandate.status != "active" or mandate.mandate_id in revoked_ids:
        return [R.DENY_MANDATE_REVOKED]
    if now < mandate.issued_at:
        return [R.DENY_MANDATE_NOT_YET_VALID]
    if now >= mandate.expires_at:
        return [R.DENY_MANDATE_EXPIRED]
    return []


@dataclass(frozen=True)
class MandateVerification:
    valid: bool
    effective_status: str  # active | revoked | expired | not_yet_valid | invalid
    integrity_codes: tuple[ReasonCode, ...]
    lifecycle_codes: tuple[ReasonCode, ...]


def verify_mandate(
    mandate: DigitalMandate,
    issuers: Mapping[str, TrustedIssuer],
    issuer_public_keys: Mapping[str, Ed25519PublicKey],
    now: datetime,
    revoked_ids: frozenset[str],
) -> MandateVerification:
    integrity = tuple(verify_mandate_integrity(mandate, issuers, issuer_public_keys))
    lifecycle = tuple(check_mandate_lifecycle(mandate, now, revoked_ids))
    if integrity:
        status = "invalid"
    elif R.DENY_MANDATE_REVOKED in lifecycle:
        status = "revoked"
    elif R.DENY_MANDATE_EXPIRED in lifecycle:
        status = "expired"
    elif R.DENY_MANDATE_NOT_YET_VALID in lifecycle:
        status = "not_yet_valid"
    else:
        status = "active"
    return MandateVerification(not integrity and not lifecycle, status, integrity, lifecycle)
