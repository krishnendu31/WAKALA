"""Single source of truth for what WAKALA can and cannot do today.

The frontend renders this list verbatim. Update a capability's status here
only in the same change that implements and tests it.
"""

from __future__ import annotations

from app import __version__
from app.schemas import CapabilityStatus, SystemCapabilities

CURRENT_PHASE = 3
ENFORCEMENT_ENGINE_CONNECTED = True

_CAPABILITIES: tuple[CapabilityStatus, ...] = (
    CapabilityStatus(key="synthetic_environment", name="Synthetic government environment", status="implemented", phase=0,
                     description="Fictional agents, citizens, residency renewal service and document fixtures, validated at startup."),
    CapabilityStatus(key="agent_registry", name="Agent registry (read-only)", status="implemented", phase=0,
                     description="Agent passports with owner entity, accountable officer and risk level, served from SQLite."),
    CapabilityStatus(key="security_contracts", name="Security data contracts", status="implemented", phase=0,
                     description="Strict schemas for passports, mandates, action requests, decisions and audit events."),
    CapabilityStatus(key="agent_identity_keys", name="Cryptographic agent identity", status="implemented", phase=1,
                     description="Ed25519 key per agent; requests authenticated by signature over canonical bytes, never by agent_id."),
    CapabilityStatus(key="replay_protection", name="Freshness and replay protection", status="implemented", phase=1,
                     description="Signed timestamp within a skew window and single-use nonces per agent."),
    CapabilityStatus(key="signed_mandates", name="Signed digital mandates", status="implemented", phase=1,
                     description="Issuer-signed, task-limited mandates verified on every use; tampering breaks the signature."),
    CapabilityStatus(key="issuer_authority", name="Issuer trust and authority limits", status="implemented", phase=1,
                     description="Only registered issuers, and only within their declared services, agents, tools and limits."),
    CapabilityStatus(key="authorization_gateway", name="Default-deny authorization gateway", status="implemented", phase=1,
                     description="Deterministic eight-check policy engine; anything not positively authorized is denied."),
    CapabilityStatus(key="protected_execution", name="Protected tool execution boundary", status="implemented", phase=1,
                     description="Allowed actions dispatch only via a fixed server-side tool registry; denied actions never run."),
    CapabilityStatus(key="audit_trail", name="Hash-chained audit trail", status="implemented", phase=1,
                     description="One chained event per decision; integrity verifiable via GET /api/audit/integrity."),
    CapabilityStatus(key="mock_government_services", name="Protected synthetic government services", status="implemented", phase=2,
                     description="Residency, insurance and payment services reachable only through Gateway.execute(); synthetic ledger."),
    CapabilityStatus(key="case_bound_authority", name="Case-specific authority", status="implemented", phase=2,
                     description="Each operation must match its signed case: citizen, request, assigned agent, mandate, operation and state."),
    CapabilityStatus(key="case_state_machine", name="Renewal case lifecycle", status="implemented", phase=2,
                     description="Validated transitions with prerequisite guards, pause for review and failure states."),
    CapabilityStatus(key="agent_adapter_interface", name="Agent adapter interface (simulated agents)", status="implemented", phase=2,
                     description="Signing adapters with in-process and HTTP transports; agents are deterministic simulations, not LLMs."),
    CapabilityStatus(key="baseline_comparison", name="Isolated weak-baseline comparison", status="implemented", phase=2,
                     description="Test-only role-based baseline, fully separate from WAKALA, for the wrong-citizen scenario."),
    CapabilityStatus(key="safety_pause", name="Automatic pause after denied high-risk action", status="implemented", phase=2,
                     description="Prototype control pauses a case for review after a denied payment; resume via dev CLI only."),
    CapabilityStatus(key="non_expanding_delegation", name="Signed, non-expanding mandate chains", status="implemented", phase=3,
                     description="Gateway-authorized commission → WAKALA-signed child mandate; every link verified server-side and narrowed."),
    CapabilityStatus(key="commission_authority", name="Commission authority separate from execution", status="implemented", phase=3,
                     description="An agent may commission a catalogued task without being allowed to execute it itself."),
    CapabilityStatus(key="selective_revocation", name="Persistent, cascading, selective revocation", status="implemented", phase=3,
                     description="Mandate- and case-level revocation cascade to delegated children; agent-wide revocation is separate."),
    CapabilityStatus(key="transactional_outcome_audit", name="Transactional outcome audit + reconciliation", status="implemented", phase=3,
                     description="Service changes and their outcome event commit together; idempotent reconciliation on startup."),
    CapabilityStatus(key="authority_graph", name="Live authority-chain graph", status="implemented", phase=3,
                     description="Graph of issuers, root/child mandates, agents and denied delegation attempts from stored records."),
    CapabilityStatus(key="human_intervention", name="Officer console: approve, resume, revoke", status="planned", phase=4,
                     description="Authenticated accountable officers act from the console (today: dev CLI only)."),
    CapabilityStatus(key="llm_agent_adapters", name="LLM tool-use agent adapters", status="planned", phase=4,
                     description="Model-driven agents submitting through the same signing adapter; interface defined, not implemented."),
    CapabilityStatus(key="attack_simulation", name="Agent-driven attack simulation", status="planned", phase=4,
                     description="Prompt injection, forged identity, tampering and escalation scenarios run against the gateway."),
    CapabilityStatus(key="citizen_receipts", name="Citizen transparency receipts", status="planned", phase=4,
                     description="Plain-language record of which agents acted for a citizen, and under what mandate."),
    CapabilityStatus(key="measured_benchmarks", name="Measured security benchmarks", status="planned", phase=4,
                     description="Decision latency and scenario outcomes measured from real runs."),
)


def get_capabilities(developer_demo_enabled: bool = False) -> SystemCapabilities:
    return SystemCapabilities(
        version=__version__,
        current_phase=CURRENT_PHASE,
        enforcement_engine_connected=ENFORCEMENT_ENGINE_CONNECTED,
        developer_demo_enabled=developer_demo_enabled,
        capabilities=list(_CAPABILITIES),
    )
