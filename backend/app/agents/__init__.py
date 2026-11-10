"""Agent adapters. Phase 2 agents are deterministic simulations, not autonomous AI."""

from .interface import (
    AgentAdapter,
    AgentIdentity,
    GatewayTransport,
    HttpGatewayTransport,
    InProcessGatewayTransport,
    SigningAgentAdapter,
    ToolCall,
)
from .llm import LLMToolUseAdapter, export_tool_definitions
from .simulated import SimulatedInsuranceAgent, SimulatedPaymentAgent, SimulatedResidencyAgent

__all__ = [
    "AgentAdapter",
    "AgentIdentity",
    "GatewayTransport",
    "HttpGatewayTransport",
    "InProcessGatewayTransport",
    "LLMToolUseAdapter",
    "SigningAgentAdapter",
    "SimulatedInsuranceAgent",
    "SimulatedPaymentAgent",
    "SimulatedResidencyAgent",
    "ToolCall",
    "export_tool_definitions",
]
