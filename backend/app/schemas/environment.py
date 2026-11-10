"""Synthetic government environment records: citizens, services, scenarios."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field, computed_field

from .common import (
    CitizenRef,
    DocumentId,
    Money,
    NonEmptyText,
    ScenarioId,
    ServiceId,
    ShortText,
    StrictModel,
    SyntheticAccountRef,
    ToolName,
)


class ResidencyStatus(StrictModel):
    permit_ref: str = Field(pattern=r"^SYNTH-RP-\d{6}$")
    status: Literal["active", "expiring_soon", "expired"]
    expiry_date: dt.date
    emirate: Literal["Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"]


class InsuranceStatus(StrictModel):
    policy_ref: str = Field(pattern=r"^SYNTH-INS-\d{6}$")
    provider: ShortText
    status: Literal["valid", "expired", "none"]
    valid_until: dt.date | None


class ServiceAttributes(StrictModel):
    sponsor_type: Literal["employer", "family", "self", "investor"]
    renewal_eligible: bool
    outstanding_fines: Money
    preferred_language: Literal["ar", "en"]


class Citizen(StrictModel):
    citizen_ref: CitizenRef
    full_name: ShortText
    full_name_ar: ShortText
    residency: ResidencyStatus
    insurance: InsuranceStatus
    service_attributes: ServiceAttributes
    account_ref: SyntheticAccountRef
    synthetic: Literal[True] = True


class GovernmentService(StrictModel):
    service_id: ServiceId
    name: ShortText
    name_ar: ShortText
    operating_entity: ShortText
    fee: Money
    official_payment_destination: SyntheticAccountRef
    tools: list[ToolName] = Field(min_length=1)
    synthetic: Literal[True] = True


class DocumentFixture(StrictModel):
    document_id: DocumentId
    title: ShortText
    citizen_ref: CitizenRef
    filename: str = Field(pattern=r"^[a-z0-9_]+\.txt$")
    trust_classification: Literal["untrusted_input"] = "untrusted_input"
    contains_injected_instruction: bool
    content: str = Field(min_length=1, max_length=20_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    synthetic: Literal[True] = True


class Scenario(StrictModel):
    scenario_id: ScenarioId
    title: ShortText
    summary: NonEmptyText
    citizen_ref: CitizenRef
    service_id: ServiceId
    document_id: DocumentId
    category: Literal["baseline", "prompt_injection"]
    planned_expected_outcome: NonEmptyText
    target_phase: int = Field(ge=1, le=5)
    # Execution stays disabled until the enforcement engine exists.
    execution_enabled: Literal[False] = False
    synthetic: Literal[True] = True


class ScenarioWithDocument(StrictModel):
    scenario: Scenario
    document: DocumentFixture


class CapabilityStatus(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    name: ShortText
    status: Literal["implemented", "planned"]
    phase: int = Field(ge=0, le=5)
    description: NonEmptyText


class SystemCapabilities(StrictModel):
    product: Literal["WAKALA"] = "WAKALA"
    version: str
    current_phase: int
    enforcement_engine_connected: bool
    developer_demo_enabled: bool = False
    synthetic_data_only: Literal[True] = True
    external_llm_dependency: Literal[False] = False
    capabilities: list[CapabilityStatus]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def implemented_count(self) -> int:
        return sum(1 for c in self.capabilities if c.status == "implemented")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def planned_count(self) -> int:
        return sum(1 for c in self.capabilities if c.status == "planned")
