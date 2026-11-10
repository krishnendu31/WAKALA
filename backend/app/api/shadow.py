"""Shadow Mode API — developer/demo mode and local clients only. Synthetic events; never executes anything."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dev import require_dev_access
from app.api.workflow import require_local_client
from app.shadow.service import EVENTS, run_demo

router = APIRouter(prefix="/api/shadow", tags=["shadow mode (synthetic)"],
                   dependencies=[Depends(require_local_client), Depends(require_dev_access)])


@router.get("/events")
def events() -> list[dict[str, Any]]:
    return [{"key": e.key, "description": e.description, "agent_id": e.agent, "source_decision": e.source_decision,
             "synthetic_intent": e.intent} for e in EVENTS]


@router.post("/demo")
def demo() -> dict[str, Any]:
    """Step 1: watch-only shadow evaluation of copied events. Step 2: active enforcement in a separate fresh environment."""
    return run_demo()
