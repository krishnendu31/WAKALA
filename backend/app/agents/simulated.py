"""Deterministic SIMULATED agents for the residency renewal workflow.

These are scripted Python policies, not model-driven autonomous AI. They
exist so the protected workflow can be exercised reproducibly. Each one
only proposes ``ToolCall``s; authority is decided by the gateway.
"""

from __future__ import annotations

from app.schemas.case import RenewalCase

from .interface import ToolCall

TREASURY = "SYNTH-GOV-TREASURY-0001"


class SimulatedResidencyAgent:
    agent_id = "AGT-RES-001"

    @staticmethod
    def register(case: RenewalCase) -> ToolCall:
        return ToolCall("residency.register_renewal_case", {"case_id": case.case_id, "citizen_ref": case.citizen_ref},
                        case.case_id, "Register the residency renewal application")

    @staticmethod
    def check_eligibility(case: RenewalCase) -> ToolCall:
        return ToolCall("residency.check_eligibility", {"case_id": case.case_id, "citizen_ref": case.citizen_ref},
                        case.citizen_ref, "Check renewal eligibility for the case applicant")

    @staticmethod
    def complete(case: RenewalCase) -> ToolCall:
        return ToolCall("residency.complete_renewal", {"case_id": case.case_id, "citizen_ref": case.citizen_ref},
                        case.case_id, "Complete the residency renewal")


class SimulatedInsuranceAgent:
    agent_id = "AGT-INS-001"

    @staticmethod
    def verify(case: RenewalCase, citizen_ref: str | None = None) -> ToolCall:
        """``citizen_ref`` lets a scenario model a mistaken request for someone else."""
        who = citizen_ref or case.citizen_ref
        return ToolCall("insurance.verify_case_eligibility", {"case_id": case.case_id, "citizen_ref": who},
                        who, "Verify insurance eligibility for the renewal")


class SimulatedPaymentAgent:
    agent_id = "AGT-PAY-001"

    @staticmethod
    def collect(case: RenewalCase, amount: str = "500.00", recipient: str = TREASURY) -> ToolCall:
        return ToolCall(
            "payment.collect_renewal_fee",
            {"case_id": case.case_id, "citizen_ref": case.citizen_ref, "amount": amount, "currency": "AED",
             "recipient": recipient, "idempotency_key": f"IDEM-{case.case_id}"},
            case.case_id, "Collect the residency renewal fee",
        )
