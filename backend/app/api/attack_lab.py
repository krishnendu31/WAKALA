"""Attack Lab API — developer/demo mode and local clients only. Every run uses fresh isolated synthetic environments."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import Field

from app.api.dev import require_dev_access
from app.api.routes import Env, ErrorResponse
from app.api.workflow import require_local_client
from app.attack_lab import service as L
from app.schemas.common import StrictModel

router = APIRouter(prefix="/api/attack-lab", tags=["attack lab (synthetic)"],
                   dependencies=[Depends(require_local_client), Depends(require_dev_access)],
                   responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})


class RunBody(StrictModel):
    scenarios: list[Literal[tuple(L.BY_KEY)]] | Literal["all"] = "all"  # type: ignore[valid-type]
    seed: int = Field(default=2026, ge=0, le=2**31)


@router.get("/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return [{"key": s.key, "letter": s.letter, "title": s.title, "story": s.story, "actor": s.actor, "operation": s.operation,
             "target": s.target, "original_authority": s.authority, "baseline_note": s.baseline_note} for s in L.SCENARIOS]


@router.post("/run")
def run(body: RunBody, env: Env) -> dict[str, Any]:
    keys = list(L.BY_KEY) if body.scenarios == "all" else list(dict.fromkeys(body.scenarios))
    return L.save_run(env, [L.run_scenario(k, body.seed) for k in keys], body.seed)


@router.get("/runs")
def runs(env: Env) -> dict[str, Any]:
    return {"session_id": L.lab_session(env), "runs": L.list_runs(env)}


@router.get("/runs/{run_id}")
def get_run(run_id: Annotated[str, Path(pattern=r"^LAB-[A-Z0-9]{8}$")], env: Env) -> dict[str, Any]:
    r = L.get_run(env, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": "Unknown run."})
    return r


@router.post("/reset")
def reset(env: Env) -> dict[str, str]:
    return L.reset(env)
