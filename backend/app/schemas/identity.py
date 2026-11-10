"""AgentPassport — the registered, accountable identity of a government AI agent.

A passport is *registry data*, not a credential. Possessing or quoting an
``agent_id`` proves nothing: from Phase 1 every request must be accompanied by
a signature produced with the private key referenced by
``identity_key_reference``, and verified by the gateway.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .common import AgentId, AgentStatus, KeyId, NonEmptyText, RiskLevel, ShortText, StrictModel, ToolName


class AccountableOfficer(StrictModel):
    """The named human accountable for the agent's conduct (synthetic)."""

    name: ShortText
    title: ShortText
    officer_id: str = Field(pattern=r"^OFF-\d{4}$")


class IdentityKeyReference(StrictModel):
    """Pointer to the agent's public signing key. Private keys never live here."""

    key_id: KeyId
    algorithm: Literal["Ed25519"] = "Ed25519"
    # Phase 0: no key material is provisioned. Phase 1 generates Ed25519
    # key pairs and records the public key fingerprint.
    provisioning_status: Literal["not_provisioned", "provisioned", "rotated", "revoked"]
    public_key_fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


class AgentPassport(StrictModel):
    agent_id: AgentId
    name: ShortText
    name_ar: ShortText
    description: NonEmptyText
    owner_entity: ShortText
    accountable_officer: AccountableOfficer
    platform: ShortText
    risk_level: RiskLevel
    status: AgentStatus
    identity_key_reference: IdentityKeyReference
    # Tools the agent is *technically able* to request. Being listed here
    # grants nothing: each call still requires a valid mandate.
    declared_tools: list[ToolName] = Field(min_length=1)
    restrictions: list[NonEmptyText] = Field(default_factory=list)
    synthetic: Literal[True] = True

    @field_validator("declared_tools")
    @classmethod
    def _unique_tools(cls, tools: list[str]) -> list[str]:
        if len(set(tools)) != len(tools):
            raise ValueError("declared_tools contains duplicates")
        return tools

    @field_validator("identity_key_reference")
    @classmethod
    def _fingerprint_matches_status(cls, ref: IdentityKeyReference) -> IdentityKeyReference:
        if ref.provisioning_status == "not_provisioned" and ref.public_key_fingerprint is not None:
            raise ValueError("a key that is not provisioned cannot have a fingerprint")
        if ref.provisioning_status == "provisioned" and ref.public_key_fingerprint is None:
            raise ValueError("a provisioned key requires a public_key_fingerprint")
        return ref
