"""Digital mandates: canonical encoding, signature and authority verification.

An issuing authority signs ``MANDATE_TAG + canonical_mandate_bytes(m)`` with
its Ed25519 key. The gateway verifies that signature against the issuer's
*registered* public key before evaluating any field of the mandate, then
checks that the mandate stays within the issuer's registered authority.
A mandate whose bytes change after signing fails verification.
"""

from .canonical import canonical_mandate_bytes, mandate_signing_message
from .interfaces import MandateSigner, MandateVerifier
from .verification import (
    MandateVerification,
    check_issuer_authority,
    check_mandate_lifecycle,
    verify_mandate,
    verify_mandate_integrity,
)

__all__ = [
    "MandateSigner",
    "MandateVerification",
    "MandateVerifier",
    "canonical_mandate_bytes",
    "check_issuer_authority",
    "check_mandate_lifecycle",
    "mandate_signing_message",
    "verify_mandate",
    "verify_mandate_integrity",
]
