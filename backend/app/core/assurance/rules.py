"""Deterministic behavioural detection rules (pure functions).

Each rule inspects recent, already-audited gateway events for one subject and
returns a Finding when its explicit threshold is met inside its rolling window.
Thresholds, windows and severities are configuration, not learned values.
This is NOT machine-learning anomaly detection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.schemas import AuditEvent

CROSS_CITIZEN_CODES = {"DENY_SCOPE_VIOLATION", "DENY_CASE_SCOPE_VIOLATION"}
DELEGATION_CODES = {"DENY_DELEGATION_NOT_PERMITTED", "DENY_DELEGATION_EXPANDS_AUTHORITY", "DENY_DELEGATION_DEPTH_EXCEEDED",
                    "DENY_DELEGATION_CYCLE", "DENY_DELEGATION_CASE_MISMATCH", "DENY_DELEGATION_CHAIN_INVALID"}
REVOKED_CODES = {"DENY_MANDATE_REVOKED", "DENY_PARENT_MANDATE_REVOKED", "DENY_CASE_AUTHORITY_REVOKED",
                 "DENY_AGENT_NOT_ACTIVE", "DENY_MANDATE_SUSPENDED", "DENY_PARENT_MANDATE_SUSPENDED"}
CREDENTIAL_CODES = {"DENY_REQUEST_SIGNATURE_INVALID", "DENY_REPLAYED_REQUEST", "DENY_IDENTITY_UNVERIFIED"}


@dataclass(frozen=True)
class RuleConfig:
    rule_id: str
    title: str
    threshold: int
    window: timedelta
    severity: str
    escalate_at: int | None
    escalated_severity: str | None
    classification: str


DEFAULT_RULES: tuple[RuleConfig, ...] = (
    RuleConfig("REPEATED_DENIALS", "Repeated denied requests from one agent", 5, timedelta(minutes=10), "medium", 10, "high",
               "policy_violation"),
    RuleConfig("REQUEST_RATE", "Unusual request frequency", 30, timedelta(seconds=60), "medium", 60, "high",
               "operational_anomaly"),
    RuleConfig("CROSS_CITIZEN_ACCESS", "Attempt to access a citizen outside the case", 1, timedelta(minutes=30), "high", 3,
               "critical", "policy_violation"),
    RuleConfig("UNAUTHORIZED_DELEGATION", "Unauthorized delegation attempt", 1, timedelta(minutes=30), "medium", 3, "high",
               "policy_violation"),
    RuleConfig("ACTION_AFTER_REVOCATION", "Attempt to act after revocation or suspension", 1, timedelta(minutes=30), "medium", 3,
               "high", "policy_violation"),
    RuleConfig("CREDENTIAL_FAILURES", "Repeated invalid signatures or replays", 3, timedelta(minutes=10), "high", 6, "critical",
               "possible_credential_misuse"),
)
RULES_BY_ID = {r.rule_id: r for r in DEFAULT_RULES}

INTERPRETATION = {
    "policy_violation": ("Requests attributed to this agent violated policy and were denied before execution. "
                         "This is evidence of a policy violation, not by itself evidence that the agent is malicious."),
    "operational_anomaly": "Request volume exceeded the configured rate. This may indicate a fault or misuse; it is not proof of either.",
    "possible_credential_misuse": ("Requests claiming this identity failed signature or replay checks. This may indicate an impersonation "
                                   "attempt or a mis-configured client; it says nothing about the genuine agent's intent."),
}


@dataclass(frozen=True)
class Finding:
    rule: RuleConfig
    severity: str
    subject: str
    case_id: str | None
    mandate_id: str | None
    count: int
    evidence_event_ids: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class EventFacts:
    """What a rule may know about one audited decision (no parameter values)."""

    event: AuditEvent
    case_citizen: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)


def _within(events: Sequence[EventFacts], now: datetime, window: timedelta) -> list[EventFacts]:
    return [e for e in events if now - e.event.timestamp <= window]


def _finding(rule: RuleConfig, matched: list[EventFacts], subject: str, summary: str) -> Finding | None:
    if len(matched) < rule.threshold:
        return None
    severity = rule.escalated_severity if rule.escalate_at and len(matched) >= rule.escalate_at else rule.severity
    latest = matched[-1].event
    return Finding(rule, severity or rule.severity, subject, latest.evidence_metadata.get("case_id"),  # type: ignore[arg-type]
                   latest.related_mandate, len(matched), tuple(e.event.event_id for e in matched[-50:]), summary)


def _codes(f: EventFacts) -> set[str]:
    return {c.value for c in f.event.reason_codes}


def evaluate_rules(subject: str, recent: Sequence[EventFacts], now: datetime,
                   rules: Sequence[RuleConfig] = DEFAULT_RULES, latest: EventFacts | None = None) -> list[Finding]:
    """Evaluate every rule for one subject. Only rules the latest event contributes to can fire,
    so an unrelated allowed request never re-raises an old finding."""
    out: list[Finding] = []
    latest = latest or (recent[-1] if recent else None)
    if latest is None:
        return out
    lc = _codes(latest)
    denied_latest = latest.event.decision == "denied"
    for rule in rules:
        window = _within(recent, now, rule.window)
        if rule.rule_id == "REPEATED_DENIALS" and denied_latest:
            m = [e for e in window if e.event.decision == "denied"]
            f = _finding(rule, m, subject, f"{len(m)} denied requests within {int(rule.window.total_seconds() // 60)} min")
        elif rule.rule_id == "REQUEST_RATE":
            m = [e for e in window if e.event.decision in ("allowed", "denied", "escalated")]
            f = _finding(rule, m, subject, f"{len(m)} requests within {int(rule.window.total_seconds())} s")
        elif rule.rule_id == "CROSS_CITIZEN_ACCESS" and denied_latest and lc & CROSS_CITIZEN_CODES and "cross_citizen" in latest.tags:
            m = [e for e in window if e.event.decision == "denied" and "cross_citizen" in e.tags]
            f = _finding(rule, m, subject, f"{len(m)} request(s) targeting a citizen outside the active case")
        elif rule.rule_id == "UNAUTHORIZED_DELEGATION" and denied_latest and lc & DELEGATION_CODES:
            m = [e for e in window if e.event.decision == "denied" and _codes(e) & DELEGATION_CODES]
            f = _finding(rule, m, subject, f"{len(m)} denied delegation attempt(s)")
        elif rule.rule_id == "ACTION_AFTER_REVOCATION" and denied_latest and lc & REVOKED_CODES:
            m = [e for e in window if e.event.decision == "denied" and _codes(e) & REVOKED_CODES]
            f = _finding(rule, m, subject, f"{len(m)} attempt(s) to act with revoked or suspended authority")
        elif rule.rule_id == "CREDENTIAL_FAILURES" and denied_latest and lc & CREDENTIAL_CODES:
            m = [e for e in window if e.event.decision == "denied" and _codes(e) & CREDENTIAL_CODES]
            f = _finding(rule, m, subject, f"{len(m)} invalid-signature / replay / unverified-identity failure(s)")
        else:
            f = None
        if f is not None:
            out.append(f)
    return out
