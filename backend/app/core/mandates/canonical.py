"""Deterministic byte encoding of a mandate, used as the signature payload.

Sorted keys, no insignificant whitespace, UTF-8, and ``signature_metadata``
excluded (a signature cannot sign itself). Two semantically identical
mandates always produce identical bytes; any change to any signed field
produces different bytes.
"""

from __future__ import annotations

from app.core.crypto import MANDATE_TAG, canonical_json
from app.schemas import DigitalMandate


# Phase 3 fields are omitted from the signed body when they hold their default
# value, so every mandate signed before Phase 3 keeps exactly the same bytes and
# its signature stays valid. When set, they are signed like every other field.
PHASE3_DEFAULTS: dict[str, object] = {
    "case_id": None,
    "root_mandate_id": None,
    "delegation_depth": 0,
    "delegated_by_agent": None,
    "delegated_task": None,
    "commissionable_tasks": [],
    "max_delegation_depth": 0,
}


def canonical_mandate_bytes(mandate: DigitalMandate) -> bytes:
    body = mandate.model_dump(mode="json", exclude={"signature_metadata"})
    for key, default in PHASE3_DEFAULTS.items():
        if body.get(key) == default:
            body.pop(key, None)
    return canonical_json(body)


def mandate_signing_message(mandate: DigitalMandate) -> tuple[bytes, bytes]:
    """(domain tag, payload) pair to pass to ``app.core.crypto.sign/verify``."""
    return MANDATE_TAG, canonical_mandate_bytes(mandate)
