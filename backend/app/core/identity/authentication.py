"""Request authentication: proof of possession of an agent's private key.

The gateway resolves the *claimed* ``agent_id`` to the public key registered
for that agent and verifies the request signature over the canonical request
bytes. Only a successful verification produces an ``AuthenticatedPrincipal``.
Freshness and replay are evaluated afterwards (authorization check 8) using
the authenticated nonce and timestamp, which are inside the signed bytes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.crypto import ACTION_REQUEST_TAG, canonical_json, sha256_hex, verify
from app.schemas import ActionRequest, ReasonCode, SignedActionRequest


@dataclass(frozen=True)
class RegisteredKey:
    key_id: str
    owner_type: str  # "agent" | "issuer"
    owner_id: str
    public_key: Ed25519PublicKey
    fingerprint: str
    status: str  # "active" | "revoked"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Exists only after a request signature verified against a registered key."""

    agent_id: str
    key_id: str
    request_digest: str


@dataclass(frozen=True)
class AuthenticationOutcome:
    principal: AuthenticatedPrincipal | None
    failure: ReasonCode | None
    request_digest: str


def canonical_request_bytes(request: ActionRequest) -> bytes:
    return canonical_json(request.model_dump(mode="json"))


def request_digest(request: ActionRequest) -> str:
    return sha256_hex(ACTION_REQUEST_TAG + canonical_request_bytes(request))


AgentKeyLookup = Callable[[str], RegisteredKey | None]


def authenticate(signed: SignedActionRequest, agent_key_lookup: AgentKeyLookup) -> AuthenticationOutcome:
    request = signed.request
    digest = request_digest(request)
    key = agent_key_lookup(request.agent_id)
    if key is None or key.owner_type != "agent" or key.owner_id != request.agent_id:
        return AuthenticationOutcome(None, ReasonCode.DENY_UNKNOWN_AGENT, digest)
    if key.status != "active" or signed.signature.key_id != key.key_id:
        return AuthenticationOutcome(None, ReasonCode.DENY_IDENTITY_UNVERIFIED, digest)
    if not verify(key.public_key, ACTION_REQUEST_TAG, canonical_request_bytes(request), signed.signature.value):
        return AuthenticationOutcome(None, ReasonCode.DENY_REQUEST_SIGNATURE_INVALID, digest)
    return AuthenticationOutcome(AuthenticatedPrincipal(request.agent_id, key.key_id, digest), None, digest)
