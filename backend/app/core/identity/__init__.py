"""Agent identity: Ed25519 proof of possession, verified by the gateway.

* Each agent has a key pair. Only the public key and its SHA-256 fingerprint
  live in the server's key registry; private keys stay with the agent runtime
  (in the prototype: a git-ignored development keystore, see app.devtools).
* Every ActionRequest is signed over ``ACTION_REQUEST_TAG + canonical JSON``.
  The signed bytes bind agent, mandate, tool, parameters, target, request ID,
  timestamp and nonce.
* A plain-text ``agent_id`` is a claim, never proof.
"""

from .authentication import (
    AuthenticatedPrincipal,
    AuthenticationOutcome,
    RegisteredKey,
    authenticate,
    canonical_request_bytes,
    request_digest,
)
from .interfaces import IdentityVerifier, VerifiedIdentity

__all__ = [
    "AuthenticatedPrincipal",
    "AuthenticationOutcome",
    "IdentityVerifier",
    "RegisteredKey",
    "VerifiedIdentity",
    "authenticate",
    "canonical_request_bytes",
    "request_digest",
]
