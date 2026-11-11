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
    from app.core import public_demo
    if public_demo.enabled():  # hosted judge demo: mutations stay behind officer auth or require_dev_access
        return
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
    except AuditUnavailableError as exc:
        from app.api.gateway import audit_failure
        raise audit_failure(exc) from None


@router.get("/cases", response_model=list[dict[str, Any]])
def list_cases(env: Env) -> list[dict[str, Any]]:
    return [{"case_id": c.case_id, "citizen_ref": c.citizen_ref, "state": c.state.value, "created_at": c.created_at.isoformat(),
             "expires_at": c.expires_at.isoformat(), "completed_prerequisites": c.completed_prerequisites,
             "recovery_status": c.recovery_status, "authority_model": c.authority_model,
             "authority_revoked": c.authority_revoked} for c in env.cases.list()]


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: CaseIdPath, env: Env) -> CaseDetail:
    case = env.cases.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "No such case."})
    return CaseDetail(case=case, ledger=env.services.ledger(case_id), renewals=env.services.renewals(case_id),
                      audit_events=case_audit_events(env, case_id))


@router.get("/cases/{case_id}/authority-graph", response_model=dict[str, Any])
def authority_graph(case_id: CaseIdPath, env: Env) -> dict[str, Any]:
    """Live authority chain for a case: issuers, root and child mandates (verified now),
    agents and denied delegation attempts — derived only from stored records."""
    from app.workflow.authority_graph import build_authority_graph
    graph = build_authority_graph(env, case_id)
    if graph is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "No such case."})
    return graph


@router.get("/cases/{case_id}/case-view", response_model=dict[str, Any])
def case_view(case_id: CaseIdPath, env: Env) -> dict[str, Any]:
    """Compact Case View: citizen request → Residency Agent → delegated agent → protected services."""
    from app.workflow.case_view import build_case_view
    v = build_case_view(env, case_id)
    if v is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "No such case."})
    return v


@router.get("/delegations", response_model=list[dict[str, Any]])
def list_delegations(env: Env) -> list[dict[str, Any]]:
    return [{k: str(v) for k, v in d.items()} for d in env.mandates.delegations()]


@router.post("/recovery/{case_id}/continue", response_model=WorkflowRun, dependencies=[Depends(require_dev_access)])
def continue_recovery(case_id: CaseIdPath, env: Env) -> WorkflowRun:
    """Advance a case with the next legitimate SIGNED agent requests through the gateway.
    Never changes state directly; stops at any denial or pending approval."""
    from app.workflow.recovery import continue_case
    if env.cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "No such case."})
    try:
        return continue_case(env, case_id)
    except AuditUnavailableError as exc:
        from app.api.gateway import audit_failure
        raise audit_failure(exc) from None


class OversightBody(StrictModel):
    clean_cases: int = Field(default=4, ge=1, le=20)
    violating_cases: int = Field(default=1, ge=0, le=10)
    minutes_per_review: float = Field(default=2.0, gt=0, le=120)


@router.post("/oversight-comparison", response_model=dict[str, Any], dependencies=[Depends(require_dev_access)])
def oversight_comparison(body: Annotated[OversightBody | None, Body()] = None) -> dict[str, Any]:
    """Runs on an ISOLATED in-memory environment; never touches the live database."""
    from app.workflow.oversight import run_oversight_comparison
    b = body or OversightBody()
    return run_oversight_comparison(b.clean_cases, b.violating_cases, b.minutes_per_review)


@router.get("/ledger", response_model=list[dict[str, str]])
def synthetic_ledger(env: Env) -> list[dict[str, str]]:
    return env.services.ledger()


@router.get("/tools", response_model=list[dict[str, Any]])
def tool_definitions(env: Env) -> list[dict[str, Any]]:
    """Case-bound tool definitions as exported for agent frameworks (no authority conferred)."""
    return export_tool_definitions(env.tools)
