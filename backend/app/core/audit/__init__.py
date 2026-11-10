"""Audit trail: one hash-chained AuditEvent per authorization decision.

Events are appended, never updated or deleted through the API. The chain
detects modification, reordering and mid-log deletion; it cannot detect tail
truncation or a consistent rewrite by whoever controls the storage (see
``chain.py`` and docs/SECURITY_MODEL.md).
"""

from .chain import GENESIS_HASH, IntegrityReport, compute_event_hash, verify_chain
from .interfaces import AuditSink
from .sink import AuditUnavailableError, SqliteAuditSink

__all__ = [
    "GENESIS_HASH",
    "AuditSink",
    "AuditUnavailableError",
    "IntegrityReport",
    "SqliteAuditSink",
    "compute_event_hash",
    "verify_chain",
]
