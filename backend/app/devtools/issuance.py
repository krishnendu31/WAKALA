"""DEVELOPMENT-ONLY mandate issuance for the three synthetic agents.

Simulates each issuing authority signing a task-limited mandate for Mariam
Al Hashimi's (synthetic) residency renewal request.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.crypto import sign
from app.core.mandates import mandate_signing_message, verify_mandate
from app.schemas import DigitalMandate, SignatureMetadata, TrustedIssuer

DEV_CITIZEN_REF = "C-1001"
DEV_REQUEST_ID = "REQ-2026-C1001-RENEWAL"
TREASURY = "SYNTH-GOV-TREASURY-0001"

# agent_id -> (issuer_id, mandate prefix, body template)
DEV_MANDATE_TEMPLATES: dict[str, tuple[str, str, dict[str, Any]]] = {
    "AGT-RES-001": ("ISS-RESIDENCY-AUTH", "MND-RES", {
        "purpose": "Read residency status and prepare the renewal application for request REQ-2026-C1001-RENEWAL.",
        "allowed_tools": ["residency.read_status", "residency.prepare_renewal"],
        "denied_tools": ["payment.request_fee_payment"],
        "resource_constraints": [
            {"resource_type": "citizen_record", "access": "read", "identifiers": [DEV_CITIZEN_REF]},
            {"resource_type": "application", "access": "write", "identifiers": [DEV_REQUEST_ID]},
        ],
    }),
    "AGT-INS-001": ("ISS-INSURANCE-REG", "MND-INS", {
        "purpose": "Verify insurance eligibility for the residency renewal request REQ-2026-C1001-RENEWAL.",
        "allowed_tools": ["insurance.verify_eligibility"],
        "denied_tools": ["payment.request_fee_payment", "residency.prepare_renewal"],
        "resource_constraints": [
            {"resource_type": "insurance_record", "access": "read", "identifiers": [DEV_CITIZEN_REF]},
        ],
    }),
    "AGT-PAY-001": ("ISS-PAYMENTS-OFFICE", "MND-PAY", {
        "purpose": "Request the synthetic AED 500 renewal fee for request REQ-2026-C1001-RENEWAL.",
        "allowed_tools": ["payment.request_fee_payment"],
        "denied_tools": ["residency.read_status", "insurance.verify_eligibility"],
        "resource_constraints": [
            {"resource_type": "payment", "access": "execute", "identifiers": [DEV_REQUEST_ID]},
        ],
        "amount_limit": {"amount": "500.00", "currency": "AED"},
        "recipient_allowlist": [TREASURY],
    }),
}


def sign_mandate(unsigned: DigitalMandate, private_key: Ed25519PrivateKey, key_id: str, signed_at: datetime) -> DigitalMandate:
    tag, payload = mandate_signing_message(unsigned)
    meta = SignatureMetadata(key_id=key_id, signature=sign(private_key, tag, payload), signed_at=signed_at)
    return unsigned.model_copy(update={"signature_metadata": meta})


def build_dev_mandate(
    agent_id: str, issued_at: datetime, lifetime: timedelta, *, overrides: dict[str, Any] | None = None, suffix: str | None = None
) -> DigitalMandate:
    issuer_id, prefix, body = DEV_MANDATE_TEMPLATES[agent_id]
    data: dict[str, Any] = {
        "mandate_id": f"{prefix}-{suffix or secrets.token_hex(3).upper()}",
        "version": 1,
        "agent_id": agent_id,
        "issuer_id": issuer_id,
        "service_id": "residency_renewal",
        "citizen_or_request_scope": {"citizen_ref": DEV_CITIZEN_REF, "request_id": DEV_REQUEST_ID},
        "issued_at": issued_at,
        "expires_at": issued_at + lifetime,
        "status": "active",
        **body,
        **(overrides or {}),
    }
    return DigitalMandate.model_validate(data)


def issue_dev_mandate(
    agent_id: str,
    issuers: dict[str, TrustedIssuer],
    keystore: Any,
    issued_at: datetime,
    lifetime: timedelta,
    **kwargs: Any,
) -> DigitalMandate:
    unsigned = build_dev_mandate(agent_id, issued_at, lifetime, **kwargs)
    issuer = issuers[unsigned.issuer_id]
    return sign_mandate(unsigned, keystore.private_key(issuer.key_id), issuer.key_id, issued_at)


def ensure_dev_mandates(gateway: Any, store: Any, keystore: Any, issuers: dict[str, TrustedIssuer], now: datetime, lifetime: timedelta, *, force: bool = False) -> list[DigitalMandate]:
    """Issue a fresh mandate for any agent without a currently valid one."""
    snapshot = gateway.policy_snapshot(now)
    issued = []
    for agent_id in DEV_MANDATE_TEMPLATES:
        has_valid = any(
            verify_mandate(s.mandate, snapshot["issuers"], snapshot["issuer_public_keys"], now, snapshot["revoked_mandate_ids"]).valid
            for s in store.list(agent_id)
            if s.mandate.citizen_or_request_scope.request_id == DEV_REQUEST_ID
        )
        if force or not has_valid:
            mandate = issue_dev_mandate(agent_id, issuers, keystore, now, lifetime)
            store.put(mandate)
            issued.append(mandate)
    return issued
