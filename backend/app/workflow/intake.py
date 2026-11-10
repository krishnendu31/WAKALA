"""Case intake (DEVELOPMENT simulation of the service front office).

Opening a case is not an agent action: it represents the citizen's
application being accepted by the residency service. Intake creates the case
and has each issuing authority sign a mandate scoped to exactly that case's
citizen, request and resources. In the prototype the issuers' signatures use
the local development keystore.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from app.devtools.issuance import TREASURY, sign_mandate
from app.schemas import DigitalMandate
from app.schemas.case import CaseEvent, CaseState, RenewalCase
from app.services.bootstrap import WakalaEnvironment

CASE_LIFETIME = timedelta(hours=2)  # bounded by the strictest issuer (payments: 2 h)
SERVICE_OWNER = "Fictional Residency Services Authority (demo)"

AGENT_OPERATIONS: dict[str, tuple[str, list[str], list[str]]] = {
    # agent -> (issuer, allowed tools, denied tools)
    "AGT-RES-001": ("ISS-RESIDENCY-AUTH",
                    ["residency.register_renewal_case", "residency.check_eligibility", "residency.complete_renewal"],
                    ["payment.collect_renewal_fee", "insurance.verify_case_eligibility"]),
    "AGT-INS-001": ("ISS-INSURANCE-REG", ["insurance.verify_case_eligibility"],
                    ["payment.collect_renewal_fee", "residency.complete_renewal"]),
    "AGT-PAY-001": ("ISS-PAYMENTS-OFFICE", ["payment.collect_renewal_fee"],
                    ["residency.complete_renewal", "insurance.verify_case_eligibility"]),
}


class IntakeRefused(ValueError):
    pass


def _case_mandate(agent_id: str, case_id: str, citizen: str, request_id: str, now: datetime, expires: datetime) -> dict[str, Any]:
    issuer, allowed, denied = AGENT_OPERATIONS[agent_id]
    resources = {
        "AGT-RES-001": [{"resource_type": "renewal_case", "access": "write", "identifiers": [case_id]},
                        {"resource_type": "citizen_record", "access": "read", "identifiers": [citizen]}],
        "AGT-INS-001": [{"resource_type": "insurance_record", "access": "read", "identifiers": [citizen]}],
        "AGT-PAY-001": [{"resource_type": "payment", "access": "execute", "identifiers": [case_id]}],
    }[agent_id]
    body: dict[str, Any] = {
        "mandate_id": f"MND-{agent_id[4:7]}-{case_id[5:]}",
        "version": 1,
        "agent_id": agent_id,
        "issuer_id": issuer,
        "service_id": "residency_renewal",
        "purpose": f"Residency renewal case {case_id} for citizen {citizen} only.",
        "citizen_or_request_scope": {"citizen_ref": citizen, "request_id": request_id},
        "allowed_tools": allowed,
        "denied_tools": denied,
        "resource_constraints": resources,
        "issued_at": now,
        "expires_at": expires,
        "status": "active",
    }
    if agent_id == "AGT-PAY-001":
        body["amount_limit"] = {"amount": "500.00", "currency": "AED"}
        body["recipient_allowlist"] = [TREASURY]
    return body


def open_case(env: WakalaEnvironment, citizen_ref: str) -> RenewalCase:
    if env.repo.get_citizen(citizen_ref) is None:
        raise IntakeRefused("unknown citizen")
    now = env.clock()
    expires = now + CASE_LIFETIME
    case_id = f"CASE-{secrets.token_hex(4).upper()}"
    request_id = f"REQ-{case_id}"
    issuers = {i.issuer_id: i for i in env.repo.list_issuers()}
    refs: dict[str, str] = {}
    for agent_id, (issuer_id, _, _) in AGENT_OPERATIONS.items():
        unsigned = DigitalMandate.model_validate(_case_mandate(agent_id, case_id, citizen_ref, request_id, now, expires))
        issuer = issuers[issuer_id]
        env.mandates.put(sign_mandate(unsigned, env.keystore.private_key(issuer.key_id), issuer.key_id, now))
        refs[agent_id] = unsigned.mandate_id
    operations = [t for _, allowed, _ in AGENT_OPERATIONS.values() for t in allowed]
    case = RenewalCase(
        case_id=case_id, citizen_ref=citizen_ref, service_id="residency_renewal", service_owner=SERVICE_OWNER,
        authorized_purpose="Renew the applicant's synthetic residency permit", request_id=request_id,
        state=CaseState.CREATED, assigned_agents=list(AGENT_OPERATIONS), mandate_refs=refs,
        authorized_operations=operations, created_at=now, expires_at=expires,
        history=[
            CaseEvent(at=now, actor="OFF-0101", kind="case_opened", detail=f"Renewal application accepted for {citizen_ref}"),
            CaseEvent(at=now, actor="OFF-0101", kind="mandates_issued",
                      detail="Case-scoped mandates signed by " + ", ".join(sorted({v[0] for v in AGENT_OPERATIONS.values()}))),
        ],
    )
    env.cases.create(case)
    return case
