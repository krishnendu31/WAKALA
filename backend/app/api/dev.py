"""Developer demonstration endpoints — disabled unless WAKALA_DEV_MODE=1.

Even when enabled they (a) only answer loopback clients, (b) reject
cross-site browser origins, and (c) expose fixed, server-side scenarios.
There is no endpoint to choose an agent, sign arbitrary payloads, generate
keys, issue or revoke mandates; those are CLI-only (app.devtools.cli).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.api.routes import Env, ErrorResponse
from app.core.audit import AuditUnavailableError
from app.core.identity import request_digest
from app.devtools.scenarios import DEV_SCENARIOS, SCENARIOS_BY_KEY, ScenarioUnavailable, run_scenario
from app.schemas.views import CheckTraceView, DevRequestSummary, DevScenarioInfo, DevScenarioResult


def require_dev_access(request: Request) -> None:
    env = request.app.state.env
    if not env.settings.dev_mode:
        raise HTTPException(status_code=404, detail={"code": "DEV_MODE_DISABLED", "message": "Developer endpoints are disabled."})
    client = request.client.host if request.client else ""
    if client not in env.settings.dev_allowed_hosts:
        raise HTTPException(status_code=403, detail={"code": "DEV_LOOPBACK_ONLY", "message": "Developer endpoints accept local clients only."})
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in env.settings.cors_origins:
        raise HTTPException(status_code=403, detail={"code": "DEV_ORIGIN_REJECTED", "message": "Cross-site origin rejected."})


router = APIRouter(prefix="/api/dev", tags=["developer (dev mode only)"], dependencies=[Depends(require_dev_access)],
                   responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})

ScenarioKey = Annotated[str, Path(pattern=r"^[a-z_]{3,40}$")]


def _info(key: str) -> DevScenarioInfo:
    s = SCENARIOS_BY_KEY[key]
    return DevScenarioInfo(key=s.key, title=s.title, description=s.description, designed_to_test=s.designed_to_test)


@router.get("/scenarios", response_model=list[DevScenarioInfo])
def list_dev_scenarios() -> list[DevScenarioInfo]:
    return [_info(s.key) for s in DEV_SCENARIOS]


@router.post("/scenarios/{key}/run", response_model=DevScenarioResult)
def run_dev_scenario(key: ScenarioKey, env: Env) -> DevScenarioResult:
    if key not in SCENARIOS_BY_KEY:
        raise HTTPException(status_code=404, detail={"code": "SCENARIO_NOT_FOUND", "message": f"Unknown scenario {key!r}."})
    try:
        outcome, signed, note = run_scenario(env, key)
    except ScenarioUnavailable as exc:
        raise HTTPException(status_code=409, detail={"code": "SCENARIO_UNAVAILABLE", "message": str(exc)}) from None
    except AuditUnavailableError:
        raise HTTPException(status_code=503, detail={"code": "AUDIT_UNAVAILABLE", "message": "Audit unavailable; nothing executed."}) from None
    req = signed.request
    return DevScenarioResult(
        scenario=_info(key),
        request=DevRequestSummary(agent_id=req.agent_id, tool_name=req.tool_name, mandate_id=req.mandate_id,
                                  target_resource=req.target_resource, parameters=dict(req.parameters),
                                  nonce=req.nonce, request_digest=request_digest(req)),
        decision=outcome.decision,
        executed=outcome.executed,
        execution_status=outcome.status,
        result=outcome.result,
        checks=[CheckTraceView(name=c.name, status=c.status, reason_codes=list(c.reason_codes)) for c in outcome.evaluation.checks],
        note=note,
    )
