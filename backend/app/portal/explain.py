"""Plain-English explanations of real gateway decisions, for the citizen portal and the officer console.

Generated from the decision's reason codes and the case — never invented. The technical codes are always shown
alongside, in a details panel.
"""

from __future__ import annotations

from typing import Any

AGENT_NAMES = {"AGT-RES-001": "Residency Agent", "AGT-INS-001": "Insurance Agent", "AGT-INS-002": "Insurance Agent (standby)",
               "AGT-PAY-001": "Payment Agent"}
ACTION_NAMES = {
    "residency.register_renewal_case": "register the renewal application",
    "residency.check_eligibility": "check residency eligibility",
    "residency.complete_renewal": "complete the renewal",
    "insurance.verify_case_eligibility": "check insurance",
    "payment.collect_renewal_fee": "collect the renewal fee",
    "delegation.commission_task": "delegate the insurance check",
}


def _who(agent_id: str) -> str:
    return AGENT_NAMES.get(agent_id, agent_id)


def explain(decision: dict[str, Any], *, agent_id: str, tool_name: str, parameters: dict[str, Any] | None = None,
            case_citizen: str | None = None, citizen_name: str | None = None) -> str:
    codes = set(decision.get("reason_codes", []))
    p = parameters or {}
    action = ACTION_NAMES.get(tool_name, tool_name)
    who = _who(agent_id)
    owner = citizen_name or case_citizen or "this applicant"
    if decision.get("allowed"):
        return f"Allowed: the {who} was authorized to {action} for {owner}'s case."
    if "ESCALATE_HUMAN_REVIEW" in codes:
        return f"Held for an officer: the {who} asked to {action} while this case is under security review. Nothing ran yet."
    if {"DENY_REQUEST_SIGNATURE_INVALID", "DENY_UNKNOWN_AGENT", "DENY_IDENTITY_UNVERIFIED"} & codes:
        return f"Blocked: the request could not be proven to come from the {who} — its signature did not verify."
    if "DENY_REPLAYED_REQUEST" in codes:
        return "Blocked: this exact request had already been used once and cannot be replayed."
    target = p.get("citizen_ref")
    if ({"DENY_CASE_SCOPE_VIOLATION", "DENY_SCOPE_VIOLATION"} & codes) and target and case_citizen and target != case_citizen:
        return (f"Blocked: this AI agent was authorized to {action} for {owner}, not another citizen's record ({target}).")
    if "DENY_AMOUNT_EXCEEDS_LIMIT" in codes or "DENY_RECIPIENT_NOT_ALLOWLISTED" in codes:
        parts = []
        if "DENY_AMOUNT_EXCEEDS_LIMIT" in codes:
            parts.append(f"AED {p.get('amount', '?')} is above the AED 500 fee it was authorized to collect")
        if "DENY_RECIPIENT_NOT_ALLOWLISTED" in codes:
            parts.append(f"{p.get('recipient', 'that account')} is not the official treasury account")
        return "Blocked: " + " and ".join(parts) + ". No money moved."
    if {"DENY_TOOL_EXPLICITLY_DENIED", "DENY_TOOL_NOT_PERMITTED"} & codes:
        return f"Blocked: the {who} is not authorized to {action} — that belongs to a different agent's mandate."
    if {"DENY_CASE_AGENT_NOT_ASSIGNED", "DENY_DELEGATION_CASE_MISMATCH"} & codes:
        return f"Blocked: the {who} presented authority that was issued for a different case."
    if {"DENY_MANDATE_REVOKED", "DENY_PARENT_MANDATE_REVOKED", "DENY_MANDATE_SUSPENDED", "DENY_PARENT_MANDATE_SUSPENDED",
        "DENY_CASE_AUTHORITY_REVOKED"} & codes:
        return f"Blocked: the {who}'s authority for this case was suspended or revoked by an officer or a security rule."
    if {"DENY_MANDATE_EXPIRED", "DENY_PARENT_MANDATE_EXPIRED", "DENY_CASE_EXPIRED"} & codes:
        return f"Blocked: the {who}'s authority for this case has expired."
    if any(c.startswith("DENY_DELEGATION") for c in codes):
        return f"Blocked: the {who} tried to hand on more authority than it was given."
    if {"DENY_CASE_STATE_INVALID"} & codes:
        return f"Not yet: the case is not at the step where the {who} may {action}."
    return f"Blocked: the {who} was not authorized to {action} here."
