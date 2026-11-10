from __future__ import annotations

from typing import Protocol

from app.schemas import AuditEvent


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> None:
        """Append-only. Implementations must never mutate existing events."""
        ...

    def count(self) -> int: ...
