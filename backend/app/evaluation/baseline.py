"""Configuration A — INTENTIONALLY WEAK role-only authorization (benchmark comparison only).

Model: "the claimed caller holds a role that includes this operation". It trusts
the claimed agent/officer identity, and has no signatures, mandates, case or
citizen binding, amount or recipient limits, expiry, revocation, replay
protection, delegation verification, entity scope or tamper-evident audit.

It is deliberately weak, as a lower bound, and does NOT represent all real IAM
implementations (many production systems add attribute checks, sessions,
signed tokens, etc.). Isolation: it holds only its own in-memory state; it never
touches WAKALA's database, gateway, services, mandates, keys or audit trail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .dataset import CATEGORY, DatasetItem

AGENT_ROLES: dict[str, frozenset[str]] = {
    "AGT-RES-001": frozenset({"residency.register_renewal_case", "residency.check_eligibility", "residency.complete_renewal",
                              "delegation.commission_task"}),
    "AGT-INS-001": frozenset({"insurance.verify_case_eligibility"}),
    "AGT-INS-002": frozenset({"insurance.verify_case_eligibility"}),
    "AGT-PAY-001": frozenset({"payment.collect_renewal_fee"}),
}
OFFICER_ROLES: dict[str, str] = {"OFF-0101": "case_officer", "OFF-0202": "case_officer", "OFF-0900": "security_supervisor",
                                 "OFF-0950": "auditor"}
WRITE_ROLES = frozenset({"case_officer", "security_supervisor"})  # coarse: any write role may do any officer write


def abstract_call(item: DatasetItem) -> tuple[str, str]:
    """(claimed caller, operation) — the only facts a role-only check uses. Same request semantics as B/C."""
    c, v = item.category, item.variant
    if item.family == "officer_action":
        claimed = {"case_officer_suspend": "OFF-0101", "auditor_suspends": "OFF-0950", "case_officer_revokes": "OFF-0101",
                   "other_entity_suspends": "OFF-0202", "forged_session": "OFF-0900", "expired_session": "OFF-0101"}[v]
        return claimed, "officer.revoke_mandate" if v == "case_officer_revokes" else "officer.suspend_mandate"
    if c == "normal_renewal_completion":
        return "AGT-RES-001", "residency.complete_renewal"
    if c in ("valid_delegated_task", "wrong_citizen_access", "forged_child_mandate", "revoked_ancestor_mandate"):
        return "AGT-INS-001", "insurance.verify_case_eligibility"
    if c == "valid_task_commission":
        return "AGT-RES-001", "delegation.commission_task"
    if c == "legitimate_eligibility_check":
        return "AGT-RES-001", "residency.check_eligibility"
    if c == "wrong_case_mandate":
        return ("AGT-INS-001", "insurance.verify_case_eligibility") if v == "insurance_other_case" else \
            ("AGT-PAY-001", "payment.collect_renewal_fee")
    if c == "unauthorized_tool":
        return {"insurance_calls_payment": ("AGT-INS-001", "payment.collect_renewal_fee"),
                "residency_calls_payment": ("AGT-RES-001", "payment.collect_renewal_fee"),
                "payment_completes_renewal": ("AGT-PAY-001", "residency.complete_renewal")}[v]
    if c == "forged_agent_identity":
        return ("AGT-PAY-001", "payment.collect_renewal_fee") if "payment" in v else ("AGT-INS-001", "insurance.verify_case_eligibility")
    if c == "delegation_privilege_escalation":
        return ("AGT-INS-001" if v in ("insurance_commissions_payment", "redelegation_cycle") else "AGT-RES-001",
                "delegation.commission_task")
    # fee-style requests: excessive amount, wrong recipient, tampered, expired, revoked, replayed, legitimate fee
    return "AGT-PAY-001", "payment.collect_renewal_fee"


@dataclass
class RoleOnlyBaseline:
    log: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, int] = field(default_factory=lambda: {"payments_recorded": 0, "records_read": 0, "renewals_completed": 0,
                                                            "officer_writes": 0, "delegations_recorded": 0})

    def evaluate(self, item: DatasetItem) -> dict[str, Any]:
        t = time.perf_counter()
        claimed, op = abstract_call(item)
        if op.startswith("officer."):
            allowed = OFFICER_ROLES.get(claimed) in WRITE_ROLES
        else:
            allowed = op in AGENT_ROLES.get(claimed, frozenset())
        ms = (time.perf_counter() - t) * 1000
        if allowed:  # "execute" against the baseline's own in-memory state only
            key = {"payment.collect_renewal_fee": "payments_recorded", "insurance.verify_case_eligibility": "records_read",
                   "residency.complete_renewal": "renewals_completed", "delegation.commission_task": "delegations_recorded"}
            self.state[key.get(op, "officer_writes" if op.startswith("officer.") else "records_read")] += 1
            if item.category == "replayed_request":
                self.state["payments_recorded"] += 1  # the original submission was also executed
        self.log.append({"item_id": item.item_id, "claimed": claimed, "operation": op, "allowed": allowed})
        return {"applicable": True, "allowed": allowed, "executed": allowed, "held": False,
                "reason_codes": ["BASELINE_ROLE_ALLOWS" if allowed else "BASELINE_ROLE_DENIES"],
                "decision_ms": round(ms, 5), "wall_ms": round(ms, 5), "state_mutated": allowed and CATEGORY[item.category].label == "unauthorized",
                "protective_pause": False, "audit_complete": False, "audit_note": "plain in-memory log; not tamper-evident",
                "detected_any": False, "detected_specific": False, "rules": []}
