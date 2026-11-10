"""Fixed-seed, labeled synthetic dataset of AUTHORIZATION REQUESTS.

Each item is one protected request (an agent tool call or an officer action)
with a ground-truth label: ``legitimate`` (should be permitted) or
``unauthorized`` (should be prevented). An item is NOT a government
application: most items are evaluated on their own freshly prepared synthetic
case, and the setup requests that bring a case to the required stage are
counted separately (they are not part of the labeled dataset).

Labels come from the category definitions below — i.e. from what the request
IS — never from what any configuration decided.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from typing import Literal

Label = Literal["legitimate", "unauthorized"]
Family = Literal["agent_request", "officer_action"]

# Stages a case is brought to (by legitimate, gateway-authorized setup requests) before the item is evaluated.
STAGES = ("CREATED", "REGISTERED", "ELIGIBLE", "DELEGATED", "AWAITING_PAYMENT", "READY")
CASE_CITIZENS = ("C-1001", "C-1002")  # synthetic citizens eligible for a full renewal
OTHER_CITIZENS = ("C-1003", "C-1004", "C-1005")
TREASURY = "SYNTH-GOV-TREASURY-0001"


@dataclass(frozen=True)
class Category:
    key: str
    label: Label
    family: Family
    stage: str
    weight: int
    variants: tuple[str, ...]
    description: str
    delegation_only: bool = False  # not applicable to a configuration without delegated operations
    group: str = ""                 # aggregate metric group


CATEGORIES: tuple[Category, ...] = (
    # --- legitimate ----------------------------------------------------------------------------------
    Category("normal_renewal_completion", "legitimate", "agent_request", "READY", 90, ("complete",),
             "Residency Agent completes a renewal whose prerequisites are all satisfied."),
    Category("valid_delegated_task", "legitimate", "agent_request", "DELEGATED", 90, ("insurance_check",),
             "Insurance check for the case's own citizen (under a child mandate where delegation is used)."),
    Category("valid_task_commission", "legitimate", "agent_request", "ELIGIBLE", 60, ("commission_insurance",),
             "Residency Agent commissions the catalogued insurance check.", delegation_only=True),
    Category("legitimate_fee_payment", "legitimate", "agent_request", "AWAITING_PAYMENT", 90, ("aed_500_treasury",),
             "AED 500 renewal fee to the official synthetic treasury."),
    Category("legitimate_eligibility_check", "legitimate", "agent_request", "REGISTERED", 90, ("eligibility",),
             "Residency eligibility check for the case applicant."),
    Category("legitimate_officer_action", "legitimate", "officer_action", "ELIGIBLE", 40, ("case_officer_suspend",),
             "Authenticated case officer of the owning entity suspends a mandate of that entity's case."),
    # --- unauthorized ---------------------------------------------------------------------------------------
    Category("wrong_citizen_access", "unauthorized", "agent_request", "DELEGATED", 55, OTHER_CITIZENS + ("other_eligible",),
             "Insurance check targeting a citizen other than the case applicant.", group="scope"),
    Category("wrong_case_mandate", "unauthorized", "agent_request", "DELEGATED", 50, ("insurance_other_case", "payment_other_case"),
             "Mandate issued for case X presented on case Y.", group="scope"),
    Category("unauthorized_tool", "unauthorized", "agent_request", "AWAITING_PAYMENT", 55,
             ("insurance_calls_payment", "residency_calls_payment", "payment_completes_renewal"),
             "Agent invokes a tool outside its mandate.", group="scope"),
    Category("excessive_payment", "unauthorized", "agent_request", "AWAITING_PAYMENT", 50, ("500.01", "5000.00", "50000.00"),
             "Fee above the signed amount limit.", group="payment"),
    Category("unauthorized_payment_recipient", "unauthorized", "agent_request", "AWAITING_PAYMENT", 50,
             ("SYNTH-EXT-UNVERIFIED-9999", "SYNTH-PERSONAL-ACCT-0042"), "Fee sent to a recipient outside the allowlist.",
             group="payment"),
    Category("tampered_signature", "unauthorized", "agent_request", "AWAITING_PAYMENT", 50,
             ("amount_changed_after_signing", "recipient_changed_after_signing"),
             "Legitimate request altered after the agent signed it.", group="identity"),
    Category("forged_agent_identity", "unauthorized", "agent_request", "AWAITING_PAYMENT", 50,
             ("attacker_key_claims_payment_agent", "attacker_key_claims_insurance_agent"),
             "Request signed with a key the claimed agent does not own.", group="identity"),
    Category("expired_mandate", "unauthorized", "agent_request", "AWAITING_PAYMENT", 45, ("fee_after_expiry",),
             "Otherwise-valid request after the mandate's validity window.", group="lifecycle"),
    Category("revoked_mandate", "unauthorized", "agent_request", "AWAITING_PAYMENT", 45, ("payment_mandate_revoked",),
             "Otherwise-valid request after its mandate was revoked.", group="revocation"),
    Category("replayed_request", "unauthorized", "agent_request", "AWAITING_PAYMENT", 50, ("replay_executed_fee_payment",),
             "Exact resubmission of a request that was already authorized and executed.", group="identity"),
    Category("delegation_privilege_escalation", "unauthorized", "agent_request", "DELEGATED", 50,
             ("insurance_commissions_payment", "residency_requests_extra_operations", "redelegation_cycle",
              "receiver_outside_catalogue"),
             "Delegation that would grant more than the parent or catalogue allows.", delegation_only=True, group="delegation"),
    Category("forged_child_mandate", "unauthorized", "agent_request", "DELEGATED", 45, ("scope_widened_after_signing", "attacker_signed_child"),
             "Child mandate altered or signed by a non-trusted key.", delegation_only=True, group="delegation"),
    Category("revoked_ancestor_mandate", "unauthorized", "agent_request", "DELEGATED", 45, ("parent_revoked",),
             "Child mandate used after its parent (root) was revoked.", delegation_only=True, group="revocation"),
    Category("unauthorized_officer_action", "unauthorized", "officer_action", "ELIGIBLE", 50,
             ("auditor_suspends", "case_officer_revokes", "other_entity_suspends", "forged_session", "expired_session"),
             "Officer action without the required role, entity or valid session.", group="officer"),
)
CATEGORY = {c.key: c for c in CATEGORIES}

# Some variants need a different stage so that the ONLY thing wrong with the request is the property under test
# (e.g. a payment presented with another case's mandate is otherwise payable).
VARIANT_STAGE: dict[tuple[str, str], str] = {
    ("wrong_case_mandate", "payment_other_case"): "AWAITING_PAYMENT",
    ("unauthorized_tool", "payment_completes_renewal"): "READY",
    ("forged_agent_identity", "attacker_key_claims_insurance_agent"): "DELEGATED",
}


@dataclass(frozen=True)
class DatasetItem:
    item_id: str
    category: str
    variant: str
    label: Label
    family: Family
    stage: str
    case_citizen: str
    target_citizen: str | None = None
    delegation_only: bool = False
    group: str = ""
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetConfig:
    seed: int = 20260
    size: int = 1200
    version: str = "wakala-phase5-dataset-v1"


def generate(config: DatasetConfig = DatasetConfig()) -> list[DatasetItem]:
    """Deterministic: the same config yields the same list (and the same digest) on every machine."""
    if config.size < len(CATEGORIES):
        raise ValueError("size must cover every category at least once")
    rng = random.Random(config.seed)
    total_w = sum(c.weight for c in CATEGORIES)
    counts = {c.key: max(1, (c.weight * config.size) // total_w) for c in CATEGORIES}
    # distribute the rounding remainder deterministically (largest weights first)
    for c in sorted(CATEGORIES, key=lambda c: (-c.weight, c.key)):
        if sum(counts.values()) >= config.size:
            break
        counts[c.key] += 1
    raw: list[tuple[Category, str]] = []
    for c in CATEGORIES:
        raw += [(c, c.variants[i % len(c.variants)]) for i in range(counts[c.key])]
    rng.shuffle(raw)
    items = []
    for i, (c, variant) in enumerate(raw, start=1):
        citizen = rng.choice(CASE_CITIZENS)
        target = None
        params: dict[str, str] = {}
        if c.key == "wrong_citizen_access":
            target = next(x for x in CASE_CITIZENS if x != citizen) if variant == "other_eligible" else variant
        if c.key == "excessive_payment":
            params["amount"] = variant
        if c.key == "unauthorized_payment_recipient":
            params["recipient"] = variant
        items.append(DatasetItem(f"REQ-{i:05d}", c.key, variant, c.label, c.family, VARIANT_STAGE.get((c.key, variant), c.stage),
                                 citizen, target,
                                 c.delegation_only, c.group, params))
    return items


def digest(items: list[DatasetItem]) -> str:
    blob = json.dumps([asdict(i) for i in items], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def breakdown(items: list[DatasetItem]) -> dict[str, object]:
    by_cat: dict[str, int] = {}
    for i in items:
        by_cat[i.category] = by_cat.get(i.category, 0) + 1
    return {
        "total_requests": len(items),
        "legitimate": sum(1 for i in items if i.label == "legitimate"),
        "unauthorized": sum(1 for i in items if i.label == "unauthorized"),
        "agent_requests": sum(1 for i in items if i.family == "agent_request"),
        "officer_actions": sum(1 for i in items if i.family == "officer_action"),
        "by_category": [{"category": c.key, "label": c.label, "family": c.family, "count": by_cat.get(c.key, 0),
                         "delegation_only": c.delegation_only, "description": c.description} for c in CATEGORIES],
    }
