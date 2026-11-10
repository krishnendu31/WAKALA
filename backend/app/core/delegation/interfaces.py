from __future__ import annotations

from typing import Protocol

from app.schemas import DigitalMandate, ReasonCode


class DelegationValidator(Protocol):
    def validate(self, parent: DigitalMandate, child: DigitalMandate) -> list[ReasonCode]:
        """Return an empty list only if ``child`` is a narrowing of ``parent``."""
        ...
