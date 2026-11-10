"""Behaviour Watch 2.0 — deterministic behavioural detection rules (pure functions).

Two policies are kept side by side so the Phase 5 recovery regression stays reproducible:
* ``watch-2.0`` (default): REQUEST_RATE counts requests of one agent *within one case* (a burst inside a case is
  suspicious; the same agent serving many independent citizens is not). Agent-wide volume is a separate
  AGENT_REQUEST_VOLUME signal that never contains a case. Four additional context signals are evaluated.
* ``phase5-original``: the Phase 5 rules exactly as benchmarked (agent-wide REQUEST_RATE, no extra signals).

Intervention ladder: NORMAL → OBSERVE → ALERT → REQUIRE_APPROVAL → SUSPEND_SPECIFIC_AUTHORITY → REVOKE.
OBSERVE is recorded, never an incident; ALERT is an incident for officer review with no automatic containment.
Monitoring never authorizes or denies anything — the gateway decides independently.

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
EXPIRED_CODES = {"DENY_MANDATE_EXPIRED", "DENY_PARENT_MANDATE_EXPIRED", "DENY_CASE_EXPIRED"}
DECISIONS = ("allowed", "denied", "escalated")

LEVELS = ("NORMAL", "OBSERVE", "ALERT", "REQUIRE_APPROVAL", "SUSPEND_SPECIFIC_AUTHORITY", "REVOKE")
LEVEL_ORDER = {name: i for i, name in enumerate(LEVELS)}
SEVERITY_LEVEL = {"low": "ALERT", "medium": "REQUIRE_APPROVAL", "high": "SUSPEND_SPECIFIC_AUTHORITY", "critical": "REVOKE"}
POLICIES = ("watch-2.0", "phase5-original")


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
    expected: str = ""


DEFAULT_RULES: tuple[RuleConfig, ...] = (
    RuleConfig("REPEATED_DENIALS", "Repeated denied requests from one agent", 5, timedelta(minutes=10), "medium", 10, "high",
               "policy_violation", "fewer than 5 denied requests per agent in 10 min"),
    RuleConfig("REQUEST_RATE", "Unusual request frequency within one case", 30, timedelta(seconds=60), "medium", 60, "high",
               "operational_anomaly", "fewer than 30 requests per agent per case in 60 s"),
    RuleConfig("CROSS_CITIZEN_ACCESS", "Attempt to access a citizen outside the case", 1, timedelta(minutes=30), "high", 3,
               "critical", "policy_violation", "no requests for citizens outside the active case"),
    RuleConfig("UNAUTHORIZED_DELEGATION", "Unauthorized delegation attempt", 1, timedelta(minutes=30), "medium", 3, "high",
               "policy_violation", "delegations only within the delegator's own authority"),
    RuleConfig("ACTION_AFTER_REVOCATION", "Attempt to act after revocation or suspension", 1, timedelta(minutes=30), "medium", 3,
               "high", "policy_violation", "no use of revoked or suspended authority"),
    RuleConfig("CREDENTIAL_FAILURES", "Repeated invalid signatures or replays", 3, timedelta(minutes=10), "high", 6, "critical",
               "possible_credential_misuse", "fewer than 3 signature/replay failures per identity in 10 min"),
)
# Behaviour Watch 2.0 context signals (not part of the Phase 5 policy).
WATCH_SIGNALS: tuple[RuleConfig, ...] = (
    RuleConfig("AGENT_REQUEST_VOLUME", "High request volume across cases", 60, timedelta(seconds=60), "low", None, None,
               "operational_anomaly", "fewer than 60 requests per agent in 60 s across all cases"),
    RuleConfig("UNEXPECTED_DATA_CATEGORY", "Request for a data category outside the agent's declared service", 1,
               timedelta(minutes=30), "low", 3, "medium", "policy_violation",
               "only tools in the agent's registered service categories"),
    RuleConfig("OFF_SCHEDULE", "Activity outside the configured operating schedule", 1, timedelta(minutes=30), "low", 3, "low",
               "operational_anomaly", "activity within the configured operating hours"),
    RuleConfig("EXPIRED_AUTHORITY_REUSE", "Repeated use of expired authority", 1, timedelta(minutes=30), "low", 3, "low",
               "policy_violation", "expired mandates are not presented again"),
)
ALL_RULES = DEFAULT_RULES + WATCH_SIGNALS
RULES_BY_ID = {r.rule_id: r for r in ALL_RULES}

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
    level: str = "ALERT"
    observed: str = ""
    expected: str = ""
    concern: str = ""


@dataclass(frozen=True)
class EventFacts:
    """What a rule may know about one audited decision (no parameter values)."""

    event: AuditEvent
    case_citizen: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)


def _within(events: Sequence[EventFacts], now: datetime, window: timedelta) -> list[EventFacts]:
    return [e for e in events if now - e.event.timestamp <= window]


CONCERN = {
    "REPEATED_DENIALS": "The agent keeps requesting actions its authority does not cover.",
    "REQUEST_RATE": "A burst of requests inside one case is not how a single citizen's service normally progresses.",
    "CROSS_CITIZEN_ACCESS": "The agent asked for a citizen who is not part of the case it was authorized for.",
    "UNAUTHORIZED_DELEGATION": "The agent tried to hand on authority it does not hold.",
    "ACTION_AFTER_REVOCATION": "The agent kept acting after its authority was withdrawn.",
    "CREDENTIAL_FAILURES": "Requests in this agent's name failed signature or replay checks — possible impersonation.",
    "AGENT_REQUEST_VOLUME": "Unusually high volume for one agent; worth a look even if each request was legitimate.",
    "UNEXPECTED_DATA_CATEGORY": "The agent reached for a kind of data its registered service does not use.",
    "OFF_SCHEDULE": "Activity outside the hours this service is configured to operate.",
    "EXPIRED_AUTHORITY_REUSE": "Expired authority presented repeatedly — a stale client or an attempt to reuse old mandates.",
}


def _finding(rule: RuleConfig, matched: list[EventFacts], subject: str, summary: str, *, level: str | None = None,
             agent_scope: bool = False, observed: str | None = None) -> Finding | None:
    if len(matched) < rule.threshold:
        return None
    severity = rule.escalated_severity if rule.escalate_at and len(matched) >= rule.escalate_at else rule.severity
    latest = matched[-1].event
    case_id = None if agent_scope else latest.evidence_metadata.get("case_id")
    return Finding(rule, severity or rule.severity, subject, case_id,  # type: ignore[arg-type]
                   None if agent_scope else latest.related_mandate, len(matched),
                   tuple(e.event.event_id for e in matched[-50:]), summary,
                   level=level or SEVERITY_LEVEL[severity or rule.severity], observed=observed or summary,
                   expected=rule.expected, concern=CONCERN.get(rule.rule_id, ""))


def _codes(f: EventFacts) -> set[str]:
    return {c.value for c in f.event.reason_codes}


def evaluate_rules(subject: str, recent: Sequence[EventFacts], now: datetime,
                   rules: Sequence[RuleConfig] = DEFAULT_RULES, latest: EventFacts | None = None,
                   policy: str = "watch-2.0") -> list[Finding]:
    """Evaluate every rule for one subject. Only rules the latest event contributes to can fire,
    so an unrelated allowed request never re-raises an old finding."""
    out: list[Finding] = []
    if policy == "watch-2.0" and rules is DEFAULT_RULES:
        rules = ALL_RULES
    latest = latest or (recent[-1] if recent else None)
    if latest is None:
        return out
    lc = _codes(latest)
    denied_latest = latest.event.decision == "denied"
    for rule in rules:
        window = _within(recent, now, rule.window)
        if rule.rule_id == "REPEATED_DENIALS" and denied_latest:
            m = [e for e in window if e.event.decision == "denied"]
            cases = {e.event.evidence_metadata.get("case_id") for e in m}
            spread = policy == "watch-2.0" and len(cases) > 1
            # watch-2.0: denials spread over several cases are an AGENT-level pattern (officer alert, no case containment);
            # they must not be pinned on whichever legitimate case happened to be the latest.
            f = _finding(rule, m, subject,
                         f"{len(m)} denied requests within {int(rule.window.total_seconds() // 60)} min"
                         + (f" across {len(cases)} cases" if spread else ""),
                         level="ALERT" if spread else None, agent_scope=spread)
        elif rule.rule_id == "REQUEST_RATE":
            m = [e for e in window if e.event.decision in DECISIONS]
            if policy == "watch-2.0":  # scoped counter: only this agent's requests in the SAME case (or same no-case path)
                cid = latest.event.evidence_metadata.get("case_id")
                m = [e for e in m if e.event.evidence_metadata.get("case_id") == cid]
                where = f"in case {cid}" if cid else "outside any case"
            else:
                where = "across all cases"
            f = _finding(rule, m, subject, f"{len(m)} requests {where} within {int(rule.window.total_seconds())} s")
        elif rule.rule_id == "AGENT_REQUEST_VOLUME":
            m = [e for e in window if e.event.decision in DECISIONS]
            if len(m) >= rule.threshold:
                cases = {e.event.evidence_metadata.get("case_id") for e in m} - {None}
                citizens = {e.case_citizen for e in m} - {None}
                denied = sum(1 for e in m if e.event.decision == "denied")
                batch = len(cases) >= 5 and denied <= len(m) * 0.1
                obs = (f"{len(m)} requests in {int(rule.window.total_seconds())} s across {len(cases)} cases / "
                       f"{len(citizens)} citizens; {denied} denied")
                f = _finding(rule, m, subject, obs + (" — consistent with a legitimate batch" if batch else ""),
                             level="OBSERVE" if batch else "ALERT", agent_scope=True)
            else:
                f = None
        elif rule.rule_id == "UNEXPECTED_DATA_CATEGORY" and "unexpected_category" in latest.tags:
            m = [e for e in window if "unexpected_category" in e.tags]
            f = _finding(rule, m, subject, f"{len(m)} request(s) for a data category outside the agent's declared service "
                                           f"(latest: {latest.event.action})",
                         level="ALERT" if len(m) < (rule.escalate_at or 99) else "REQUIRE_APPROVAL")
        elif rule.rule_id == "OFF_SCHEDULE" and "off_schedule" in latest.tags:
            m = [e for e in window if "off_schedule" in e.tags]
            denied = sum(1 for e in m if e.event.decision == "denied")
            # a single off-hours event is observed; repeated off-hours DENIALS are an alert, never auto-containment
            f = _finding(rule, m, subject, f"{len(m)} request(s) outside operating hours, {denied} denied",
                         level="ALERT" if denied >= (rule.escalate_at or 3) else "OBSERVE")
        elif rule.rule_id == "EXPIRED_AUTHORITY_REUSE" and denied_latest and lc & EXPIRED_CODES:
            m = [e for e in window if e.event.decision == "denied" and _codes(e) & EXPIRED_CODES]
            f = _finding(rule, m, subject, f"{len(m)} request(s) presenting expired authority",
                         level="ALERT" if len(m) >= (rule.escalate_at or 3) else "OBSERVE")
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
