"""My AI Activity — the citizen's transparency receipt for one case (synthetic, local/dev-only portal).

Accuracy rules
* An action is "completed" only if the gateway ALLOWED it AND the protected service recorded an execution outcome
  ``executed`` for that decision. Authorized-but-not-executed actions are listed as such.
* A blocked action is described as blocked before it ran; nothing is claimed to have been accessed.
* The summary sentence is generated from the counted events and is only shown when they support it.

Privacy filtering: no other citizen's reference or name, no rule IDs or thresholds, no incident intelligence,
no officer identities, no keys, signatures, mandate internals or raw audit metadata. Event IDs are exposed only as
opaque receipt references so a citizen can quote them to an officer.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.workflow.scenarios import case_audit_events

from .explain import ACTION_NAMES, AGENT_NAMES

PURPOSE = {
    "residency.register_renewal_case": "Register your renewal application",
    "residency.check_eligibility": "Check your residency renewal eligibility",
    "residency.complete_renewal": "Complete your residency renewal",
    "insurance.verify_case_eligibility": "Confirm your health insurance is valid",
    "payment.collect_renewal_fee": "Collect the AED 500 renewal fee",
    "delegation.commission_task": "Hand the insurance check to the Insurance Agent",
}
OFFICER_ACTIONS = {"officer.case_resume": "A government officer reviewed your case and allowed it to continue.",
                   "officer.task_reassign": "A government officer assigned a replacement AI agent to one task.",
                   "officer.approval_approve": "A government officer approved a held step after it was re-checked.",
                   "officer.incident_status": "A government officer reviewed the security check on your case."}


def _ref(event_id: str) -> str:
    return "R-" + hashlib.sha256(event_id.encode()).hexdigest()[:10].upper()


def build_receipt(env: Any, case_id: str) -> dict[str, Any] | None:
    case = env.cases.get(case_id)
    if case is None:
        return None
    citizen = env.repo.get_citizen(case.citizen_ref)
    events = sorted(case_audit_events(env, case_id), key=lambda e: e.sequence or 0)
    executions = {e.evidence_metadata.get("decision_event"): e for e in events if str(e.action).endswith(":execution")}
    rows, blocked, held = [], [], []
    for e in events:
        if e.decision not in ("allowed", "denied", "escalated"):
            continue
        agent = AGENT_NAMES.get(e.actor, "A government AI agent")
        delegated = bool(e.related_mandate and str(e.related_mandate).startswith("MND-DLG"))
        base = {"agent": agent, "purpose": PURPOSE.get(e.action, ACTION_NAMES.get(e.action, "A service step")),
                "at": e.timestamp.isoformat(), "delegated": delegated, "reference": _ref(e.event_id)}
        if e.decision == "allowed":
            ex = executions.get(e.event_id)
            done = ex is not None and ex.evidence_metadata.get("execution_status") == "executed"
            rows.append({**base, "authorized": True, "completed": done,
                         "status": "Completed — authorized for your case" if done else "Authorized, but the service did not complete it"})
        elif e.decision == "escalated":
            held.append({**base, "status": "Held for a government officer's approval before it could run"})
        else:
            target = e.evidence_metadata.get("target_resource")
            outside = isinstance(target, str) and target.startswith("C-") and target != case.citizen_ref
            blocked.append({**base, "status": "Blocked before it ran — nothing was executed and no data was returned",
                            "why": ("It asked for a record outside your case." if outside else
                                    "It was outside what the agent was authorized to do for your case.")})
    officer = []
    for e in events:
        if str(e.actor).startswith("OFF-") and e.action in OFFICER_ACTIONS:
            officer.append({"at": e.timestamp.isoformat(), "what": OFFICER_ACTIONS[e.action], "reference": _ref(e.event_id)})
    incidents = [i for i in env.assurance.incidents.list(limit=500) if i.case_id == case_id] if env.assurance else []
    completed = [r for r in rows if r["completed"]]
    agents = sorted({r["agent"] for r in completed})
    lines = []
    if completed:
        lines.append(f"{len(agents)} government AI agent{'s' if len(agents) != 1 else ''} completed actions on your residency "
                     "application. Every completed action was authorized for your case.")
    if any(r["delegated"] for r in completed):
        lines.append("One task was delegated: the Residency Agent handed the insurance check to an Insurance Agent "
                     "under narrower, case-specific authority.")
    if blocked:
        lines.append(f"{len(blocked)} action{' was' if len(blocked) == 1 else 's were'} blocked before running. "
                     "Nothing was executed and no data was returned by the blocked request.")
    if incidents:
        lines.append("A security check paused your service for review.")
    if officer:
        lines.append("A government officer reviewed your case." + (" Your service then continued." if case.state.value == "COMPLETED" else ""))
    final = {"COMPLETED": "Completed", "PAUSED_FOR_REVIEW": "Paused for security review", "FAILED": "Not completed"}.get(
        case.state.value, "In progress")
    return {
        "receipt_id": "RCPT-" + hashlib.sha256(f"{case_id}|{len(events)}".encode()).hexdigest()[:10].upper(),
        "synthetic": True, "label": "SYNTHETIC RECEIPT — fictional service, synthetic citizen; not an official document",
        "case_id": case_id, "citizen": {"name": citizen.full_name if citizen else None, "ref": case.citizen_ref},
        "service": "Residency permit renewal (fictional)", "final_status": final,
        "recovered_after_review": case.recovery_status == "recovered",
        "summary": lines, "agents_with_completed_actions": agents, "actions": rows, "held": held, "blocked": blocked,
        "interrupted_by_security_check": bool(incidents), "officer_review": officer,
        "officer_review_completed": bool(officer) and not (env.assurance and env.assurance.incidents.case_has_active(case_id)),
        "privacy_note": "This receipt shows only your own case. Other people's information, internal security rules and "
                        "officer identities are never included.",
    }
