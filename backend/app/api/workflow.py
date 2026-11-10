"""Government Workflow API.

* Running a scenario (which opens a case and has issuers sign case mandates
  with development keys) requires dev mode, a loopback client and a
  same-site origin — the same protection as /api/dev/*.
* Read endpoints are restricted to local console clients. The prototype has
  no operator login yet (see SECURITY_MODEL.md).
* There is no endpoint that calls a protected service directly: every
  service operation is a signed agent request through Gateway.execute().
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from pydantic import Field

from app.agents import export_tool_definitions
from app.api.dev import require_dev_access
from app.api.routes import Env, ErrorResponse
from app.core.audit import AuditUnavailableError
from app.schemas.common import CitizenRef, StrictModel
from app.schemas.workflow import CaseDetail, WorkflowRun, WorkflowScenarioInfo
from app.workflow.intake import IntakeRefused
from app.workflow.scenarios import SCENARIO_KEYS, WORKFLOW_SCENARIOS, case_audit_events, run_workflow


def require_local_client(request: Request) -> None:
    env = request.app.state.env
    client = request.client.host if request.client else ""
    if client not in env.settings.console_allowed_hosts:
        raise HTTPException(status_code=403, detail={"code": "LOCAL_CONSOLE_ONLY", "message": "Console endpoints accept local clients only."})


router = APIRouter(prefix="/api/workflow", tags=["government workflow"], dependencies=[Depends(require_local_client)],
                   responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})

CaseIdPath = Annotated[str, Path(pattern=r"^CASE-[A-Z0-9]{6,12}$")]


class RunRequest(StrictModel):
    citizen_ref: CitizenRef = Field(default="C-1001")


@router.get("/scenarios", response_model=list[WorkflowScenarioInfo])
def list_workflow_scenarios() -> list[WorkflowScenarioInfo]:
    return [WorkflowScenarioInfo(key=s.key, title=s.title, description=s.description, citizen_selectable=s.citizen_selectable)
            for s in WORKFLOW_SCENARIOS]


@router.post("/scenarios/{key}/run", response_model=WorkflowRun, dependencies=[Depends(require_dev_access)])
def run_workflow_scenario(key: Annotated[str, Path(pattern=r"^[a-z_]{3,40}$")], env: Env,
                          body: Annotated[RunRequest | None, Body()] = None) -> WorkflowRun:
    if key not in SCENARIO_KEYS:
        raise HTTPException(status_code=404, detail={"code": "SCENARIO_NOT_FOUND", "message": f"Unknown scenario {key!r}."})
    try:
        return run_workflow(env, key, (body or RunRequest()).citizen_ref)
    except IntakeRefused:
        raise HTTPException(status_code=404, detail={"code": "CITIZEN_NOT_FOUND", "message": "Unknown citizen."}) from None
    except AuditUnavailableError:
        raise HTTPException(status_code=503, detail={"code": "AUDIT_UNAVAILABLE", "message": "Audit unavailable; workflow stopped."}) from None


@router.get("/cases", response_model=list[dict[str, Any]])
def list_cases(env: Env) -> list[dict[str, Any]]:
    return [{"case_id": c.case_id, "citizen_ref": c.citizen_ref, "state": c.state.value, "created_at": c.created_at.isoformat(),
             "expires_at": c.expires_at.isoformat(), "completed_prerequisites": c.completed_prerequisites,
             "recovery_status": c.recovery_status} for c in env.cases.list()]


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: CaseIdPath, env: Env) -> CaseDetail:
    case = env.cases.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "No such case."})
    return CaseDetail(case=case, ledger=env.services.ledger(case_id), renewals=env.services.renewals(case_id),
                      audit_events=case_audit_events(env, case_id))


@router.get("/ledger", response_model=list[dict[str, str]])
def synthetic_ledger(env: Env) -> list[dict[str, str]]:
    return env.services.ledger()


@router.get("/tools", response_model=list[dict[str, Any]])
def tool_definitions(env: Env) -> list[dict[str, Any]]:
    """Case-bound tool definitions as exported for agent frameworks (no authority conferred)."""
    return export_tool_definitions(env.tools)
