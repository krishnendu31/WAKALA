"""Transparent efficiency model. Inputs are ASSUMPTIONS the user sets; nothing here is an observed statistic,
except the clearly separated "observed_in_synthetic_benchmark" reference values read from the result files.

Primary users: government cybersecurity and AI-operations teams. Potential customers: government entities
deploying autonomous AI services. WAKALA does not decide visa eligibility or change approval rates, and the
model never removes human review that law or policy requires (``legally_required_review_pct`` is a floor
applied to both scenarios).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import StrictModel


class BusinessAssumptions(StrictModel):
    annual_agent_operations: int = Field(default=100_000, ge=1, le=10_000_000_000)
    manual_review_pct: float = Field(default=20.0, ge=0, le=100)
    manual_review_minutes: float = Field(default=6.0, gt=0, le=600)
    staff_cost_per_fte_year: float = Field(default=300_000.0, ge=0, le=100_000_000)
    productive_hours_per_fte_year: float = Field(default=1_700.0, gt=0, le=8_760)
    wakala_exception_review_pct: float = Field(default=2.0, ge=0, le=100)
    exception_review_minutes: float = Field(default=6.0, gt=0, le=600)
    legally_required_review_pct: float = Field(default=0.0, ge=0, le=100)
    annual_platform_and_integration_cost: float = Field(default=250_000.0, ge=0, le=10_000_000_000)
    currency: str = Field(default="AED", pattern=r"^[A-Z]{3}$")


ASSUMPTION_NOTES = {
    "annual_agent_operations": "ASSUMPTION — protected AI-agent operations per year for one entity.",
    "manual_review_pct": "ASSUMPTION — share of operations a manual-review-heavy process routes to an officer.",
    "manual_review_minutes": "ASSUMPTION — average officer time per routine manual review.",
    "staff_cost_per_fte_year": "ASSUMPTION — fully loaded annual cost of one reviewer (salary, benefits, overhead).",
    "productive_hours_per_fte_year": "ASSUMPTION — productive review hours per FTE per year.",
    "wakala_exception_review_pct": "ASSUMPTION — share of operations escalated to officers with WAKALA (incidents + holds).",
    "exception_review_minutes": "ASSUMPTION — average officer time per WAKALA exception review.",
    "legally_required_review_pct": "ASSUMPTION — share of operations that must be human-reviewed by law/policy in BOTH scenarios.",
    "annual_platform_and_integration_cost": "ASSUMPTION — annual WAKALA platform, integration and operations cost.",
}


def _scenario(a: BusinessAssumptions, review_pct: float, minutes: float, extra_cost: float) -> dict[str, float]:
    pct = max(review_pct, a.legally_required_review_pct)
    reviews = a.annual_agent_operations * pct / 100
    hours = reviews * minutes / 60
    hourly = a.staff_cost_per_fte_year / a.productive_hours_per_fte_year
    return {"review_pct_applied": pct, "reviews": round(reviews, 1), "review_hours": round(hours, 1),
            "review_fte": round(hours / a.productive_hours_per_fte_year, 2), "review_cost": round(hours * hourly, 2),
            "platform_cost": extra_cost, "total_cost": round(hours * hourly + extra_cost, 2)}


def calculate(a: BusinessAssumptions, observed: dict[str, Any] | None = None) -> dict[str, Any]:
    manual = _scenario(a, a.manual_review_pct, a.manual_review_minutes, 0.0)
    wakala = _scenario(a, a.wakala_exception_review_pct, a.exception_review_minutes, a.annual_platform_and_integration_cost)
    hourly = a.staff_cost_per_fte_year / a.productive_hours_per_fte_year
    diff = round(manual["total_cost"] - wakala["total_cost"], 2)
    saved_per_op = (manual["review_cost"] - wakala["review_cost"]) / a.annual_agent_operations
    break_even_ops = (a.annual_platform_and_integration_cost / saved_per_op) if saved_per_op > 0 else None
    # break-even manual-review share: manual review cost == wakala total cost
    per_pct_cost = a.annual_agent_operations / 100 * a.manual_review_minutes / 60 * hourly
    break_even_manual_pct = (wakala["total_cost"] / per_pct_cost) if per_pct_cost > 0 else None
    sensitivity = []
    for m in (5.0, 10.0, 20.0, 40.0):
        for e in (0.5, 2.0, 5.0, 10.0):
            alt = a.model_copy(update={"manual_review_pct": m, "wakala_exception_review_pct": e})
            mm = _scenario(alt, m, a.manual_review_minutes, 0.0)
            ww = _scenario(alt, e, a.exception_review_minutes, a.annual_platform_and_integration_cost)
            sensitivity.append({"manual_review_pct": m, "wakala_exception_review_pct": e,
                                "annual_cost_difference": round(mm["total_cost"] - ww["total_cost"], 2)})
    return {
        "label": "HYPOTHETICAL MODEL — every input is an assumption, not an observed government statistic.",
        "assumptions": a.model_dump(), "assumption_notes": ASSUMPTION_NOTES,
        "manual_review_scenario": manual, "wakala_exception_scenario": wakala,
        "routine_manual_reviews_avoided": round(manual["reviews"] - wakala["reviews"], 1),
        "review_hours_avoided": round(manual["review_hours"] - wakala["review_hours"], 1),
        "operational_workload_reduction": {"numerator_hours": round(manual["review_hours"] - wakala["review_hours"], 1),
                                           "denominator_hours": manual["review_hours"],
                                           "rate": round(1 - wakala["review_hours"] / manual["review_hours"], 4) if manual["review_hours"] else None},
        "hypothetical_annual_cost_difference": diff,
        "break_even": {"annual_operations": round(break_even_ops, 0) if break_even_ops else None,
                       "manual_review_pct": round(break_even_manual_pct, 3) if break_even_manual_pct is not None else None,
                       "note": "Operations per year (or manual-review share) at which review savings equal the platform cost."},
        "sensitivity": sensitivity,
        "observed_in_synthetic_benchmark": observed or {},
        "limits": ["WAKALA does not decide visa eligibility and does not change approval rates.",
                   "Human review required by law or policy is kept in both scenarios (legally_required_review_pct).",
                   "Exception rates observed in the synthetic benchmark depend on its attack mix and are not a forecast."],
    }
