"""Trusted catalogue of delegable business tasks.

A *task* is what one agent may commission from another ("verify insurance
eligibility for this case"). It maps — in server-side code, never from
request data — to the exact receiving-service operations a child mandate may
contain, the agents allowed to receive it, the receiving entity whose own
authority must also cover those operations, and the resource template.

Commission authority (``DigitalMandate.commissionable_tasks``) is separate
from execution authority (``allowed_tools``): the Residency Agent may
commission an insurance check without being allowed to read insurance
records itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType
from typing import Literal

COMMISSION_TOOL = "delegation.commission_task"
GLOBAL_MAX_DELEGATION_DEPTH = 3


@dataclass(frozen=True)
class ResourceTemplate:
    resource_type: str
    access: str
    # Which case attribute supplies the single permitted identifier.
    identifier: Literal["citizen_ref", "case_id"]


@dataclass(frozen=True)
class DelegableTask:
    task_id: str
    title: str
    operations: frozenset[str]
    receivers: frozenset[str]
    receiving_issuer: str
    resources: tuple[ResourceTemplate, ...]
    max_lifetime: timedelta
    monetary: bool = False


TASK_CATALOG = MappingProxyType({
    "insurance_eligibility_check": DelegableTask(
        task_id="insurance_eligibility_check",
        title="Verify insurance eligibility for the case citizen",
        operations=frozenset({"insurance.verify_case_eligibility"}),
        receivers=frozenset({"AGT-INS-001"}),
        receiving_issuer="ISS-INSURANCE-REG",
        resources=(ResourceTemplate("insurance_record", "read", "citizen_ref"),),
        max_lifetime=timedelta(minutes=30),
    ),
    "renewal_fee_collection": DelegableTask(
        task_id="renewal_fee_collection",
        title="Collect the renewal fee for the case",
        operations=frozenset({"payment.collect_renewal_fee"}),
        receivers=frozenset({"AGT-PAY-001"}),
        receiving_issuer="ISS-PAYMENTS-OFFICE",
        resources=(ResourceTemplate("payment", "execute", "case_id"),),
        max_lifetime=timedelta(minutes=30),
        monetary=True,
    ),
})
