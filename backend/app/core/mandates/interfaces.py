from __future__ import annotations

from typing import Protocol

from app.schemas import DigitalMandate


class MandateSigner(Protocol):
    def sign(self, mandate: DigitalMandate) -> DigitalMandate:
        """Return a copy of the mandate with populated signature_metadata."""
        ...


class MandateVerifier(Protocol):
    def verify(self, mandate: DigitalMandate) -> bool:
        """True only if signature_metadata verifies over the canonical bytes."""
        ...
