"""Interface for FUTURE LLM tool-use adapters (not implemented in Phase 2).

An LLM adapter would receive tool definitions exported from the gateway's
trusted registry, let a model choose a ``ToolCall``, and submit it through a
``SigningAgentAdapter`` exactly like the simulated agents. The model never
holds keys or decides authorization; the gateway enforces the same checks.
No external model is called anywhere in this codebase.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.execution import ToolRegistry
from app.schemas.case import RenewalCase

from .interface import ToolCall


def export_tool_definitions(registry: ToolRegistry, *, case_bound_only: bool = True) -> list[dict[str, Any]]:
    """JSON-schema tool definitions suitable for common tool-use APIs."""
    out = []
    for spec in registry.specs.values():
        if case_bound_only and spec.case_states is None:
            continue
        out.append({
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.params_model.model_json_schema(),
            "wakala": {"service_id": spec.service_id, "resource_type": spec.resource_type, "access": spec.access,
                       "target": spec.target, "case_states": sorted(spec.case_states or []), "monetary": spec.monetary},
        })
    return out


class ToolUsePlanner(Protocol):
    """A model-backed planner would implement this. Phase 3+."""

    def next_call(self, case: RenewalCase, tools: list[dict[str, Any]], observations: list[dict[str, Any]]) -> ToolCall | None: ...


class LLMToolUseAdapter:
    def __init__(self, planner: ToolUsePlanner | None = None) -> None:
        self._planner = planner

    def next_call(self, case: RenewalCase, tools: list[dict[str, Any]], observations: list[dict[str, Any]]) -> ToolCall | None:
        if self._planner is None:
            raise NotImplementedError("LLM tool-use adapters are planned; Phase 2 uses deterministic simulated agents.")
        return self._planner.next_call(case, tools, observations)
