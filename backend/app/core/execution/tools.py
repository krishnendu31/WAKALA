"""Trusted server-side tool registry.

The registry is a fixed mapping from tool name to a ``ToolSpec`` defined in
code. Nothing here resolves functions, modules, paths or URLs from request
data: an unknown name simply has no entry. Each spec declares the service it
belongs to, the resource type and access mode it touches, which request
field identifies its target, a strict parameter model and, optionally, a
handler. Handlers receive only the validated parameter object (and, for
case-bound Phase 2 tools, a server-built ``ExecutionContext``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import Field

from datetime import datetime

from app.schemas.common import CaseId, CitizenRef, StrictModel, SyntheticAccountRef
from app.schemas.mandate import AccessMode, ResourceType

Scalar = str | int | float | bool | None
ToolHandler = Callable[[Any], dict[str, Scalar]]


class CitizenLookupParams(StrictModel):
    citizen_ref: CitizenRef


class FeePaymentParams(StrictModel):
    citizen_ref: CitizenRef
    amount: Annotated[Decimal, Field(gt=Decimal("0"), le=Decimal("1000000"), max_digits=12, decimal_places=2)]
    currency: Literal["AED"]
    recipient: SyntheticAccountRef


@dataclass(frozen=True)
class ToolSpec:
    name: str
    service_id: str
    resource_type: ResourceType
    access: AccessMode
    # Which value must equal ``ActionRequest.target_resource``.
    target: Literal["citizen_ref", "request_id", "case_id"]
    params_model: type[StrictModel]
    monetary: bool
    description: str
    handler: ToolHandler | None = None
    # Phase 2: case-bound tools. ``case_states`` lists the case states in
    # which the operation may be authorized; None = not case-bound.
    case_states: frozenset[str] | None = None
    # Handler is called as handler(params, ExecutionContext).
    needs_context: bool = False
    # Record a second, informational audit event with the execution result.
    audit_execution: bool = False


class CaseOperationParams(StrictModel):
    case_id: CaseId
    citizen_ref: CitizenRef


class FeeCollectionParams(FeePaymentParams):
    case_id: CaseId
    idempotency_key: Annotated[str, Field(pattern=r"^IDEM-[A-Z0-9-]{6,40}$")]


@dataclass(frozen=True)
class ExecutionContext:
    """Built by the gateway from the authorized request — never from the agent."""

    agent_id: str
    request_id: str
    case_id: str | None
    decision_id: str
    audit_reference: str
    now: datetime


class ServiceRefusal(RuntimeError):
    """A protected service declined an authorized call (business rule). Safe code only."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        names = [s.name for s in specs]
        if len(set(names)) != len(names):
            raise ValueError("duplicate tool names in registry")
        self._specs: Mapping[str, ToolSpec] = MappingProxyType({s.name: s for s in specs})

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    @property
    def specs(self) -> Mapping[str, ToolSpec]:
        return self._specs


def build_default_tool_registry(
    residency_lookup: Callable[[str], dict[str, Scalar] | None],
    insurance_lookup: Callable[[str], dict[str, Scalar] | None],
) -> ToolRegistry:
    """Phase 1 catalogue. Two harmless read-only tools are executable; the
    write and payment tools are authorization-only until Phase 2 mock services."""

    def read_status(params: CitizenLookupParams) -> dict[str, Scalar]:
        record = residency_lookup(params.citizen_ref)
        if record is None:
            raise LookupError("citizen not found")
        return record

    def verify_eligibility(params: CitizenLookupParams) -> dict[str, Scalar]:
        record = insurance_lookup(params.citizen_ref)
        if record is None:
            raise LookupError("citizen not found")
        return record

    return ToolRegistry([
        ToolSpec("residency.read_status", "residency_renewal", "citizen_record", "read", "citizen_ref",
                 CitizenLookupParams, False, "Read a citizen's residency permit status (minimal fields).", read_status),
        ToolSpec("residency.prepare_renewal", "residency_renewal", "application", "write", "request_id",
                 CitizenLookupParams, False, "Prepare a renewal application (Phase 2 mock service)."),
        ToolSpec("insurance.verify_eligibility", "residency_renewal", "insurance_record", "read", "citizen_ref",
                 CitizenLookupParams, False, "Check whether a citizen holds valid insurance cover.", verify_eligibility),
        ToolSpec("payment.request_fee_payment", "residency_renewal", "payment", "execute", "request_id",
                 FeePaymentParams, True, "Request payment of the synthetic renewal fee (Phase 2 mock service)."),
    ])
