"""Security metrics from ground-truth labels. Every rate carries its numerator and denominator.

Authorization PREVENTION (the request was not executed) and monitoring DETECTION (a behavioural rule fired on
the audited decision) are reported separately: a request stopped by case-bound authorization is a prevention,
and counts as a detection only if a monitoring rule also fired on it.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .dataset import CATEGORIES


def rate(num: int, den: int) -> dict[str, Any]:
    return {"numerator": num, "denominator": den, "rate": round(num / den, 6) if den else None}


def _scored(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("applicable") and "harness_error" not in r]


def summarize(config: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _scored(records)
    legit = [r for r in scored if r["label"] == "legitimate"]
    unauth = [r for r in scored if r["label"] == "unauthorized"]
    not_applicable = [r for r in records if not r.get("applicable")]
    errors = [r for r in records if "harness_error" in r]

    def group(keys: set[str]) -> list[dict[str, Any]]:
        return [r for r in unauth if r["category"] in keys]

    escalation = group({"delegation_privilege_escalation", "forged_child_mandate"})
    revocation = group({"revoked_mandate", "revoked_ancestor_mandate"})
    by_cat = []
    for c in CATEGORIES:
        rs = [r for r in scored if r["category"] == c.key]
        na = sum(1 for r in not_applicable if r["category"] == c.key)
        if c.label == "legitimate":
            row = {"outcome": rate(sum(r["executed"] for r in rs), len(rs)), "outcome_name": "legitimate operations completed"}
        else:
            row = {"outcome": rate(sum(not r["executed"] for r in rs), len(rs)), "outcome_name": "unauthorized operations prevented"}
        row.update({
            "category": c.key, "label": c.label, "not_applicable": na,
            "detection_specific": rate(sum(r["detected_specific"] for r in rs), len(rs)),
            "detection_any_rule": rate(sum(r["detected_any"] for r in rs), len(rs)),
            "escalated_to_officer_queue": rate(sum(r.get("escalated", False) for r in rs), len(rs)),
            "reason_codes": dict(Counter(code for r in rs for code in r["reason_codes"]).most_common(4)),
        })
        by_cat.append(row)
    false_denials = [r for r in legit if not r["executed"]]
    return {
        "config": config,
        "requests_in_dataset": len(records),
        "requests_evaluated": len(scored),
        "not_applicable": len(not_applicable),
        "harness_errors": [{"item_id": r["item_id"], "error": r["harness_error"]} for r in errors],
        "legitimate_total": len(legit),
        "unauthorized_total": len(unauth),
        # the five headline counts (ground truth x outcome)
        "unauthorized_operations_executed": rate(sum(r["executed"] for r in unauth), len(unauth)),
        "unauthorized_operations_prevented": rate(sum(not r["executed"] for r in unauth), len(unauth)),
        "unauthorized_incorrectly_permitted": rate(sum(r["allowed"] for r in unauth), len(unauth)),
        "legitimate_operations_allowed": rate(sum(r["executed"] for r in legit), len(legit)),
        "legitimate_incorrectly_denied": rate(len(false_denials), len(legit)),
        "legitimate_held_for_approval": rate(sum(r["held"] for r in legit), len(legit)),
        "false_denial_reasons": dict(Counter(f"{r['category']}: {','.join(r['reason_codes'])}" for r in false_denials)),
        "delegation_escalation_prevention": rate(sum(not r["executed"] for r in escalation), len(escalation)),
        "revocation_effectiveness": rate(sum(not r["executed"] for r in revocation), len(revocation)),
        "unauthorized_state_mutations": rate(sum(r["state_mutated"] for r in unauth), len(unauth)),
        "protective_case_pauses": sum(r["protective_pause"] for r in unauth),
        "monitoring": {
            "unauthorized_detected_specific_rule": rate(sum(r["detected_specific"] for r in unauth), len(unauth)),
            "unauthorized_detected_any_rule": rate(sum(r["detected_any"] for r in unauth), len(unauth)),
            "unauthorized_escalated_to_officer_queue": rate(sum(r.get("escalated", False) for r in unauth), len(unauth)),
            "legitimate_with_specific_rule_alert": rate(sum(r["detected_specific"] for r in legit), len(legit)),
            "legitimate_with_any_rule_alert": rate(sum(r["detected_any"] for r in legit), len(legit)),
            "rule_hits": dict(Counter(rule for r in scored for rule in r["rules"])),
            "note": "Detection counts a deterministic monitoring rule firing on the audited decision; it is separate from "
                    "prevention. REQUEST_RATE fires on machine-speed benchmark traffic, so 'specific' excludes it.",
        },
        "audit_evidence_complete": rate(sum(r["audit_complete"] for r in scored), len(scored)),
        "by_category": by_cat,
    }
