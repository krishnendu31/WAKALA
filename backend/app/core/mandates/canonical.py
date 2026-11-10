"""Deterministic byte encoding of a mandate, used as the signature payload.

Sorted keys, no insignificant whitespace, UTF-8, and ``signature_metadata``
excluded (a signature cannot sign itself). Two semantically identical
mandates always produce identical bytes; any change to any signed field
produces different bytes.
"""

from __future__ import annotations

from app.core.crypto import MANDATE_TAG, canonical_json
from app.schemas import DigitalMandate


def canonical_mandate_bytes(mandate: DigitalMandate) -> bytes:
    return canonical_json(mandate.model_dump(mode="json", exclude={"signature_metadata"}))


def mandate_signing_message(mandate: DigitalMandate) -> tuple[bytes, bytes]:
    """(domain tag, payload) pair to pass to ``app.core.crypto.sign/verify``."""
    return MANDATE_TAG, canonical_mandate_bytes(mandate)
