"""Trusted mandate issuers and the limits of their authority.

An issuer can only grant what its registered authority covers: specific
services, specific agents, specific tools, a maximum amount, specific
recipients and a maximum mandate lifetime. A mandate exceeding any of these
is rejected even if its signature is valid.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .common import AgentId, IssuerId, KeyId, Money, ServiceId, ShortText, StrictModel, SyntheticAccountRef, ToolName


class IssuerAuthority(StrictModel):
    services: list[ServiceId] = Field(min_length=1)
    agents: list[AgentId] = Field(min_length=1)
    tools: list[ToolName] = Field(min_length=1)
    # None = this issuer cannot grant any monetary authority.
    max_amount: Money | None = None
    recipients: list[SyntheticAccountRef] = Field(default_factory=list)
    max_lifetime_hours: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def _money_consistency(self) -> "IssuerAuthority":
        if (self.max_amount is None) != (not self.recipients):
            raise ValueError("max_amount and recipients must be defined together")
        return self


class TrustedIssuer(StrictModel):
    issuer_id: IssuerId
    name: ShortText
    status: Literal["active", "revoked"]
    key_id: KeyId
    authority: IssuerAuthority
    synthetic: Literal[True] = True
