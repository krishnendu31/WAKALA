"""Agent adapter interface: how any agent framework calls WAKALA.

An adapter turns an agent's intent (a ``ToolCall``) into a signed
``SignedActionRequest`` with the agent's own key and submits it through a
``GatewayTransport``. The gateway — not the adapter — decides. Adapters never
call protected services directly; there is no API for that.

Transports:
* ``InProcessGatewayTransport`` — calls ``Gateway.execute()`` in-process
  (used by the simulated agents and tests).
* ``HttpGatewayTransport`` — POSTs to ``/api/gateway/execute`` so an external
  runtime (any language/framework) gets identical enforcement.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.devtools.agent_client import build_request, sign_request
from app.schemas import ExecutionResponse, SignedActionRequest
from app.schemas.case import RenewalCase


@dataclass(frozen=True)
class ToolCall:
    """What an agent wants to do. Carries no authority."""

    tool_name: str
    parameters: dict[str, Any]
    target_resource: str
    purpose: str


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    key_id: str


class GatewayTransport(Protocol):
    def execute(self, signed: SignedActionRequest, *, origin: str) -> ExecutionResponse: ...


class InProcessGatewayTransport:
    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway
        self.last_outcome: Any = None  # full outcome (incl. check trace) for the console timeline

    def execute(self, signed: SignedActionRequest, *, origin: str) -> ExecutionResponse:
        out = self._gateway.execute(signed, origin=origin)
        self.last_outcome = out
        return ExecutionResponse(decision=out.decision, executed=out.executed, execution_status=out.status, result=out.result)


class HttpGatewayTransport:
    """Framework-neutral transport. ``post(url, json_body) -> (status, json)`` is injectable."""

    def __init__(self, base_url: str, post: Callable[[str, dict[str, Any]], tuple[int, dict[str, Any]]] | None = None) -> None:
        self._url = base_url.rstrip("/") + "/api/gateway/execute"
        self._post = post or _urllib_post

    def execute(self, signed: SignedActionRequest, *, origin: str = "http") -> ExecutionResponse:
        status, body = self._post(self._url, signed.model_dump(mode="json"))
        if status not in (200, 403):
            raise RuntimeError(f"gateway returned HTTP {status}")
        return ExecutionResponse.model_validate(body)


def _urllib_post(url: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 — loopback dev gateway
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


class AgentAdapter(Protocol):
    """Implemented by simulated agents now and by LLM tool-use adapters later."""

    identity: AgentIdentity

    def submit(self, call: ToolCall, case: RenewalCase, *, origin: str) -> tuple[SignedActionRequest, ExecutionResponse]: ...


@dataclass
class SigningAgentAdapter:
    """Signs a ToolCall in the context of a case and submits it. Holds the agent's own key."""

    identity: AgentIdentity
    private_key: Ed25519PrivateKey
    transport: GatewayTransport
    clock: Callable[[], datetime]
    submitted: list[str] = field(default_factory=list)

    def sign(self, call: ToolCall, case: RenewalCase, **overrides: Any) -> SignedActionRequest:
        """Overrides (e.g. ``mandate_id``, ``case_id``, ``nonce``) exist for tests and scenarios."""
        fields: dict[str, Any] = {
            "agent_id": self.identity.agent_id,
            "mandate_id": case.mandate_refs.get(self.identity.agent_id, "MND-NOT-ASSIGNED"),
            "tool_name": call.tool_name,
            "parameters": call.parameters,
            "target_resource": call.target_resource,
            "request_id": case.request_id,
            "timestamp": self.clock(),
            "purpose": call.purpose,
        }
        case_id = overrides.pop("case_id", case.case_id)
        fields.update(overrides)
        request = build_request(**fields)
        request = type(request).model_validate({**request.model_dump(), "case_id": case_id})  # re-validate before signing
        return sign_request(request, self.private_key, self.identity.key_id)

    def submit(self, call: ToolCall, case: RenewalCase, *, origin: str) -> tuple[SignedActionRequest, ExecutionResponse]:
        signed = self.sign(call, case)
        self.submitted.append(signed.request.action_id)
        return signed, self.transport.execute(signed, origin=origin)
