"""Hash chain over audit events.

event_hash = SHA-256( canonical JSON of the event without ``event_hash`` )

Because each event includes ``previous_event_hash`` and its ``sequence``,
editing, reordering or deleting an event in the middle of the log breaks
verification from that point on.

What this does NOT prevent: someone who controls the storage can truncate the
tail or rewrite the whole chain consistently. Production needs the head hash
anchored externally (e.g. periodic checkpoints to a separate, write-once
system or a transparency log).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.crypto import canonical_json, sha256_hex
from app.schemas import AuditEvent

GENESIS_HASH = "0" * 64


def compute_event_hash(event: AuditEvent) -> str:
    return sha256_hex(canonical_json(event.model_dump(mode="json", exclude={"event_hash"})))


@dataclass(frozen=True)
class IntegrityReport:
    valid: bool
    event_count: int
    head_hash: str
    first_broken_sequence: int | None
    detail: str


def verify_chain(rows: list[tuple[int, str, str]]) -> IntegrityReport:
    """``rows`` = (sequence column, event_hash column, payload JSON), ordered by sequence."""
    prev = GENESIS_HASH
    expected_seq = 1
    for seq, stored_hash, payload in rows:
        try:
            event = AuditEvent.model_validate_json(payload)
        except ValueError:
            return IntegrityReport(False, len(rows), prev, seq, "event payload is not a valid AuditEvent")
        if seq != expected_seq or event.sequence != seq:
            return IntegrityReport(False, len(rows), prev, seq, "sequence gap or mismatch")
        if event.previous_event_hash != prev:
            return IntegrityReport(False, len(rows), prev, seq, "previous_event_hash does not match predecessor")
        recomputed = compute_event_hash(event)
        if recomputed != stored_hash or event.event_hash != stored_hash:
            return IntegrityReport(False, len(rows), prev, seq, "event content does not match its hash")
        prev = stored_hash
        expected_seq += 1
    return IntegrityReport(True, len(rows), prev, None, "chain verified")
