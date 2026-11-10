"""Continuous assurance service: observes audited gateway decisions, evaluates the
deterministic rules, opens/updates incidents and applies graduated responses.

Runs AFTER the gateway has decided and audited a request. It can never turn a
denial into an allow; detection errors are logged and swallowed so they cannot
change the outcome returned to the agent. Agents never see incident or rule
details — only their own decision.
"""

from __future__ import annotations

import logging
import threading
import secrets
from datetime import datetime, timedelta
from typing import Any

from app.core.assurance import DEFAULT_RULES, INTERPRETATION, EventFacts, Finding, evaluate_rules, plan_response
from app.models.database import Database
from app.schemas import ActionRequest, AuditEvent
from app.schemas.assurance import (
    ACTIVE_INCIDENT_STATUSES,
    SEVERITY_ORDER,
    Incident,
    InterventionReason,
    ResponseAction,
    ResponseRecord,
)
from app.schemas.case import CaseEvent, CaseState
from app.services.cases import CaseStore, InvalidTransition, next_case, with_event

logger = logging.getLogger("wakala.assurance")
LOOKBACK = max(r.window for r in DEFAULT_RULES)
RECENT_EVENT_CAP = 120  # 2x the largest rule threshold (see _recent_for)
assert RECENT_EVENT_CAP >= 2 * max(max(r.threshold, r.escalate_at or 0) for r in DEFAULT_RULES)
# Operations that require officer approval while the case has an active incident.
SENSITIVE_OPERATIONS = frozenset({"payment.collect_renewal_fee", "residency.complete_renewal", "delegation.commission_task"})


class SuspensionStore:
    """Reversible suspension, separate from (irreversible) revocation."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def suspend(self, mandate_id: str, reason: str, actor: str, now: datetime, incident_id: str | None = None) -> bool:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT active FROM mandate_suspensions WHERE mandate_id = ?", (mandate_id,)).fetchone()
            if row is not None and row["active"]:
                return False
            conn.execute(
                "INSERT INTO mandate_suspensions (mandate_id, active, suspended_at, reason, incident_id, actor) VALUES (?, 1, ?, ?, ?, ?) "
                "ON CONFLICT(mandate_id) DO UPDATE SET active=1, suspended_at=excluded.suspended_at, reason=excluded.reason, "
                "incident_id=excluded.incident_id, actor=excluded.actor, lifted_at=NULL, lifted_by=NULL",
                (mandate_id, now.isoformat(), reason[:200], incident_id, actor))
        return True

    def lift(self, mandate_id: str, actor: str, now: datetime) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute("UPDATE mandate_suspensions SET active = 0, lifted_at = ?, lifted_by = ? WHERE mandate_id = ? AND active = 1",
                               (now.isoformat(), actor, mandate_id))
            return cur.rowcount == 1

    def active_ids(self) -> frozenset[str]:
        return frozenset(r["mandate_id"] for r in self._db.query("SELECT mandate_id FROM mandate_suspensions WHERE active = 1"))

    def list(self) -> list[dict[str, Any]]:
        return [{k: r[k] for k in r.keys()} for r in self._db.query("SELECT * FROM mandate_suspensions ORDER BY suspended_at DESC")]


class IncidentConflict(RuntimeError):
    pass


class IncidentStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, incident_id: str) -> Incident | None:
        rows = self._db.query("SELECT payload FROM incidents WHERE incident_id = ?", (incident_id,))
        return Incident.model_validate_json(rows[0]["payload"]) if rows else None

    def list(self, status: str | None = None, limit: int = 200) -> list[Incident]:
        sql, args = "SELECT payload FROM incidents", ()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        rows = self._db.query(sql + " ORDER BY last_seen DESC LIMIT ?", (*args, limit))
        return [Incident.model_validate_json(r["payload"]) for r in rows]

    def active_for(self, dedupe_key: str) -> Incident | None:
        marks = ",".join("?" for _ in ACTIVE_INCIDENT_STATUSES)
        rows = self._db.query(f"SELECT payload FROM incidents WHERE dedupe_key = ? AND status IN ({marks}) "
                              "ORDER BY last_seen DESC LIMIT 1", (dedupe_key, *ACTIVE_INCIDENT_STATUSES))
        return Incident.model_validate_json(rows[0]["payload"]) if rows else None

    def case_has_active(self, case_id: str) -> Incident | None:
        marks = ",".join("?" for _ in ACTIVE_INCIDENT_STATUSES)
        rows = self._db.query(f"SELECT payload FROM incidents WHERE case_id = ? AND status IN ({marks}) "
                              "ORDER BY last_seen DESC LIMIT 1", (case_id, *ACTIVE_INCIDENT_STATUSES))
        return Incident.model_validate_json(rows[0]["payload"]) if rows else None

    def insert(self, incident: Incident, dedupe_key: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("INSERT INTO incidents (incident_id, dedupe_key, status, severity, case_id, last_seen, version, payload) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (incident.incident_id, dedupe_key, incident.status, incident.severity, incident.case_id,
                          incident.last_seen.isoformat(), incident.version, incident.model_dump_json()))

    def save(self, before: Incident, after: Incident) -> None:
        after = Incident.model_validate({**after.model_dump(), "version": before.version + 1})
        with self._db.transaction() as conn:
            cur = conn.execute("UPDATE incidents SET status = ?, severity = ?, last_seen = ?, version = ?, payload = ? "
                               "WHERE incident_id = ? AND version = ?",
                               (after.status, after.severity, after.last_seen.isoformat(), after.version, after.model_dump_json(),
                                before.incident_id, before.version))
            if cur.rowcount != 1:
                raise IncidentConflict("incident changed concurrently")


class AssuranceService:
    def __init__(self, env: Any) -> None:
        self.env = env
        self.incidents = IncidentStore(env.db)
        self.suspensions = SuspensionStore(env.db)
        self._record_lock = threading.Lock()

    # --- facts ----------------------------------------------------------------
    def _facts(self, events: list[AuditEvent]) -> list[EventFacts]:
        out = []
        case_cache: dict[str, str | None] = {}
        for e in events:
            tags: set[str] = set()
            cid = e.evidence_metadata.get("case_id")
            if isinstance(cid, str):
                if cid not in case_cache:
                    c = self.env.cases.get(cid)
                    case_cache[cid] = c.citizen_ref if c else None
                citizen = case_cache[cid]
                target = e.evidence_metadata.get("target_resource")
                if citizen and isinstance(target, str) and target.startswith("C-") and target != citizen:
                    tags.add("cross_citizen")
            out.append(EventFacts(e, case_cache.get(cid) if isinstance(cid, str) else None, frozenset(tags)))
        return out

    def _recent_for(self, subject: str, now: datetime) -> list[AuditEvent]:
        since = (now - LOOKBACK).isoformat()
        # Phase 5 bottleneck fix (found by the stress benchmark): before, every event of the subject in the lookback
        # was parsed on every decision, so cost grew linearly with the agent's recent history. Now two bounded
        # queries are merged: the most recent RECENT_EVENT_CAP decisions of any kind (REQUEST_RATE) and the most
        # recent RECENT_EVENT_CAP denials (all denial rules). Rule firing is exact while a subject has at most
        # RECENT_EVENT_CAP denials in the lookback; beyond that counts saturate at the cap (still above every
        # threshold), and a category-specific escalation could be missed if > cap other denials are interleaved.
        # Each (column, decision set) branch walks a composite (subject, seq) index backwards and stops at the cap.
        rows: dict[int, str] = {}
        for column in ("$.actor", "$.claimed_agent_id"):
            for decisions in ("'allowed','denied','escalated'", "'denied'"):
                sql = (f"SELECT seq, payload FROM audit_events WHERE json_extract(payload, '{column}') = ? "
                       f"AND json_extract(payload, '$.decision') IN ({decisions}) AND timestamp >= ? ORDER BY seq DESC LIMIT ?")
                rows.update({r["seq"]: r["payload"] for r in self.env.db.query(sql, (subject, since, RECENT_EVENT_CAP))})
        return [AuditEvent.model_validate_json(rows[s]) for s in sorted(rows)]

    # --- observer hook (called by the gateway after each audited decision) ------------
    def observe(self, event: AuditEvent, request: ActionRequest) -> list[Incident]:
        try:
            if event.decision not in ("allowed", "denied", "escalated"):
                return []
            subject = event.actor if event.authenticated else (event.claimed_agent_id or "UNAUTHENTICATED")
            now = event.timestamp
            facts = self._facts(self._recent_for(subject, now))
            latest = next((f for f in reversed(facts) if f.event.event_id == event.event_id), None)
            if latest is None:
                return []
            return [self._record(f, now) for f in evaluate_rules(subject, facts, now, latest=latest)]
        except Exception:  # noqa: BLE001 — detection must never affect the decision already returned
            logger.exception("assurance evaluation failed")
            return []

    def _record(self, finding: Finding, now: datetime) -> Incident:
        # Phase 5 (found by the concurrency stress test): concurrent decisions for the same subject raced on the
        # incident's compare-and-swap and the losing update was dropped. Re-read and re-apply, bounded.
        for attempt in range(5):
            try:
                with self._record_lock:  # serialises read-modify-write within this process; CAS still guards others
                    return self._record_once(finding, now)
            except IncidentConflict:
                if attempt == 4:
                    raise
        raise AssertionError("unreachable")

    def _record_once(self, finding: Finding, now: datetime) -> Incident:
        key = f"{finding.rule.rule_id}|{finding.subject}|{finding.case_id or '-'}"
        existing = self.incidents.active_for(key)
        if existing is not None:
            evidence = list(dict.fromkeys([*existing.evidence_event_ids, *finding.evidence_event_ids]))[-200:]
            escalated = SEVERITY_ORDER[finding.severity] > SEVERITY_ORDER[existing.severity]
            updated = existing.model_copy(update={
                "last_seen": now, "occurrences": max(existing.occurrences, finding.count), "evidence_event_ids": evidence,
                "severity": finding.severity if escalated else existing.severity, "summary": finding.summary,
                "mandate_id": finding.mandate_id or existing.mandate_id,
            })
            if escalated:
                updated = self._apply(updated, finding, now)  # graduated response only on escalation
            self.incidents.save(existing, updated)
            return updated
        incident = Incident(
            incident_id=f"INC-{secrets.token_hex(4).upper()}", rule_id=finding.rule.rule_id, title=finding.rule.title,
            severity=finding.severity, classification=finding.rule.classification, status="open",  # type: ignore[arg-type]
            agent_id=finding.subject, case_id=finding.case_id, mandate_id=finding.mandate_id, first_seen=now, last_seen=now,
            occurrences=finding.count, evidence_event_ids=list(finding.evidence_event_ids), summary=finding.summary,
            interpretation=INTERPRETATION[finding.rule.classification],
        )
        incident = self._apply(incident, finding, now)
        self.incidents.insert(incident, key)
        return incident

    # --- graduated response -------------------------------------------------------------
    def _contain_allowed(self, finding: Finding) -> bool:
        if not finding.case_id:
            return False
        case = self.env.cases.get(finding.case_id)
        return case is not None and case.incident_policy == "contain"

    def _apply(self, incident: Incident, finding: Finding, now: datetime) -> Incident:
        records = list(incident.responses)
        contain = self._contain_allowed(finding)
        containment = {ResponseAction.SUSPEND_MANDATE, ResponseAction.REVOKE_MANDATE, ResponseAction.REQUIRE_HUMAN_APPROVAL}
        for step in plan_response(finding):
            applied, detail = False, ""
            if step.action in containment and not contain:
                applied, detail = False, ("Not applied automatically: the case incident policy is 'monitor'. "
                                          "An authorized officer may apply it.")
            elif step.action is ResponseAction.SUSPEND_MANDATE and step.target:
                applied = self.suspensions.suspend(step.target, f"incident {incident.incident_id}: {finding.rule.rule_id}",
                                                   "WAKALA-GATEWAY", now, incident.incident_id)
                detail = f"Mandate {step.target} suspended (reversible); other mandates of the agent untouched."
            elif step.action is ResponseAction.REVOKE_MANDATE and step.target:
                from app.services.revocation import revoke_mandate
                revoked = revoke_mandate(self.env, step.target, f"incident {incident.incident_id}: {finding.rule.rule_id}",
                                         actor="WAKALA-GATEWAY")
                applied, detail = bool(revoked), f"Revoked {len(revoked)} mandate(s) (the affected mandate and its delegations)."
            elif step.reason is InterventionReason.RESP_PAUSE_CASE_FOR_REVIEW and step.target:
                applied, detail = self._pause_case(step.target, incident, now)
            elif step.reason is InterventionReason.RESP_REQUIRE_APPROVAL_FOR_SENSITIVE_OPS:
                applied, detail = True, "Sensitive operations on this case require officer approval while the incident is active."
            elif step.action is ResponseAction.ESCALATE_INCIDENT:
                applied, detail = True, ("Escalated to the officer queue." if step.reason is InterventionReason.RESP_ESCALATE_FOR_REVIEW
                                         else "Rotate the claimed agent's identity key if the failures are not explained.")
            elif step.reason is InterventionReason.RESP_NO_AGENT_WIDE_ACTION:
                applied, detail = True, "No agent-wide action taken automatically; agent-wide suspension is an officer decision."
            elif step.reason is InterventionReason.RESP_NO_MANDATE_TO_CONTAIN:
                applied, detail = True, "No authenticated mandate is associated with these requests."
            else:
                applied, detail = True, "Request denied before any protected operation executed."
            ev = self.env.audit.append(AuditEvent(
                event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=now, actor="WAKALA-GATEWAY",
                action=f"assurance.{step.action.value.lower()}", decision="informational",
                related_mandate=step.target if step.target and step.target.startswith("MND-") else None,
                evidence_metadata={"incident_id": incident.incident_id, "rule_id": finding.rule.rule_id,
                                   "severity": finding.severity, "reason": step.reason.value, "applied": applied,
                                   "case_id": finding.case_id, "origin": "assurance"}))
            records.append(ResponseRecord(at=now, action=step.action, reason=step.reason, target=step.target, applied=applied,
                                          detail=detail, audit_reference=ev.event_id))
        return incident.model_copy(update={"responses": records})

    def _pause_case(self, case_id: str, incident: Incident, now: datetime) -> tuple[bool, str]:
        with self.env.db.transaction() as conn:
            before = CaseStore.load_in(conn, case_id)
            if before is None or before.state in (CaseState.COMPLETED, CaseState.FAILED, CaseState.PAUSED_FOR_REVIEW):
                return False, "Case not paused (already terminal or paused)."
            try:
                after = next_case(before, CaseState.PAUSED_FOR_REVIEW, actor="WAKALA-GATEWAY", at=now,
                                  detail=f"Paused for review: incident {incident.incident_id}")
            except InvalidTransition:
                return False, "Case could not be paused."
            after = with_event(after, CaseEvent(at=now, actor="WAKALA-GATEWAY", kind="incident_opened",
                                                detail=f"{incident.title} ({incident.severity})"))
            CaseStore.save_in(conn, before, after)
        return True, f"Case {case_id} paused for human review; resumption requires an authorized officer."

    # --- approval gate (consulted by the gateway for otherwise-allowed requests) --------
    def approval_required(self, request: ActionRequest, now: datetime) -> str | None:
        if request.tool_name not in SENSITIVE_OPERATIONS or request.case_id is None:
            return None
        case = self.env.cases.get(request.case_id)
        if case is None or case.incident_policy != "contain":
            return None
        inc = self.incidents.case_has_active(request.case_id)
        return inc.incident_id if inc else None

    # --- officer-side updates -----------------------------------------------------------------
    def set_status(self, incident_id: str, status: str, officer_id: str, note: str, now: datetime) -> Incident:
        inc = self.incidents.get(incident_id)
        if inc is None:
            raise KeyError(incident_id)
        allowed = {"open": {"under_review", "contained", "resolved", "dismissed"},
                   "under_review": {"contained", "resolved", "dismissed"},
                   "contained": {"resolved", "under_review"}, "resolved": set(), "dismissed": set()}
        if status not in allowed[inc.status]:
            raise ValueError(f"cannot move incident from {inc.status} to {status}")
        updated = inc.model_copy(update={"status": status, "last_seen": now,
                                         "notes": [*inc.notes, {"at": now.isoformat(), "officer": officer_id, "status": status,
                                                                "note": note[:500]}]})
        self.incidents.save(inc, updated)
        return updated


def expired_cutoff(now: datetime, minutes: int) -> datetime:
    return now - timedelta(minutes=minutes)
