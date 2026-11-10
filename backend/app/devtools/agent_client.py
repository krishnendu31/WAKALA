"""DEVELOPMENT-ONLY agent-side request signer.

Represents what an agent runtime does: build an ActionRequest and sign it
with the agent's own private key. Used by tests, the CLI and the predefined
developer scenarios. Never exposed to the browser.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.crypto import ACTION_REQUEST_TAG, sign
from app.core.identity import canonical_request_bytes
from app.schemas import ActionRequest, RequestSignature, SignedActionRequest


def build_request(
    *,
    agent_id: str,
    mandate_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    target_resource: str,
    request_id: str,
    timestamp: datetime,
    purpose: str = "Synthetic residency renewal task",
    nonce: str | None = None,
    action_id: str | None = None,
) -> ActionRequest:
    return ActionRequest.model_validate({
        "action_id": action_id or f"ACT-{secrets.token_hex(6).upper()}",
        "request_id": request_id,
        "agent_id": agent_id,
        "mandate_id": mandate_id,
        "tool_name": tool_name,
        "parameters": parameters,
        "target_resource": target_resource,
        "purpose": purpose,
        "timestamp": timestamp,
        "nonce": nonce or secrets.token_urlsafe(16),
    })


def sign_request(request: ActionRequest, private_key: Ed25519PrivateKey, key_id: str) -> SignedActionRequest:
    value = sign(private_key, ACTION_REQUEST_TAG, canonical_request_bytes(request))
    return SignedActionRequest(request=request, signature=RequestSignature(key_id=key_id, value=value))
