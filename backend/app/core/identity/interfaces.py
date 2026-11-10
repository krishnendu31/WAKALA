from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas import ActionRequest


@dataclass(frozen=True)
class VerifiedIdentity:
    """Produced only after a cryptographic signature check succeeds."""

    agent_id: str
    key_id: str


class IdentityVerifier(Protocol):
    def verify(self, request: ActionRequest, signature: bytes) -> VerifiedIdentity | None:
        """Return a VerifiedIdentity, or None if the signature does not verify."""
        ...
