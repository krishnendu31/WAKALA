"""Pydantic contracts shared by the API, the core security modules and tests."""

from .authorization import (
    ActionRequest,
    AuditEvent,
    AuthorizationDecision,
    DelegationLink,
    ExecutionResponse,
    ReasonCode,
    RequestSignature,
    SignedActionRequest,
)
from .environment import (
    CapabilityStatus,
    Citizen,
    DocumentFixture,
    GovernmentService,
    Scenario,
    ScenarioWithDocument,
    SystemCapabilities,
)
from .common import Money
from .identity import AgentPassport
from .issuer import IssuerAuthority, TrustedIssuer
from .mandate import MAX_MANDATE_LIFETIME, DigitalMandate, MandateScope, ResourceConstraint, SignatureMetadata

# Security contracts published at /api/schemas/{name}.
SECURITY_CONTRACTS = {
    "AgentPassport": AgentPassport,
    "DigitalMandate": DigitalMandate,
    "TrustedIssuer": TrustedIssuer,
    "ActionRequest": ActionRequest,
    "SignedActionRequest": SignedActionRequest,
    "AuthorizationDecision": AuthorizationDecision,
    "AuditEvent": AuditEvent,
}

__all__ = [
    "ActionRequest",
    "AgentPassport",
    "AuditEvent",
    "AuthorizationDecision",
    "CapabilityStatus",
    "Citizen",
    "DelegationLink",
    "DigitalMandate",
    "DocumentFixture",
    "ExecutionResponse",
    "IssuerAuthority",
    "MandateScope",
    "Money",
    "RequestSignature",
    "ResourceConstraint",
    "SignatureMetadata",
    "SignedActionRequest",
    "TrustedIssuer",
    "GovernmentService",
    "MAX_MANDATE_LIFETIME",
    "ReasonCode",
    "SECURITY_CONTRACTS",
    "Scenario",
    "ScenarioWithDocument",
    "SystemCapabilities",
]
