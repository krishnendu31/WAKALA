"""Fictional Government AI Services Portal API (development prototype; synthetic citizens only).

There is no citizen authentication in this prototype, so every state-changing portal call requires developer
mode and a local client, exactly like the other demo endpoints. Reads require a local client.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from pydantic import Field

from app.api.dev import require_dev_access
from app.api.routes import Env, ErrorResponse
from app.api.workflow import require_local_client
from app.core.audit import AuditUnavailableError
from app.documents.samples import SAMPLES
from app.documents.service import MAX_BYTES
from app.portal import service as P
from app.portal.agent import model_config
from app.schemas.common import CitizenRef, StrictModel

router = APIRouter(prefix="/api/portal", tags=["government AI portal (fictional)"], dependencies=[Depends(require_local_client)],
                   responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
CasePath = Annotated[str, Path(pattern=r"^CASE-[A-Z0-9]{6,12}$")]
DocPath = Annotated[str, Path(pattern=r"^DOC-[A-Z0-9]{6,16}$")]


def _err(e: P.PortalError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": "Portal request refused."})


def _guard(fn, *a: Any, **kw: Any) -> Any:  # type: ignore[no-untyped-def]
    try:
        return fn(*a, **kw)
    except P.PortalError as e:
        raise _err(e) from None
    except AuditUnavailableError as exc:
        from app.api.gateway import audit_failure
        raise audit_failure(exc) from None


class RequestBody(StrictModel):
    citizen_ref: CitizenRef = Field(default="C-1001")
    message: str = Field(default=P.DEFAULT_REQUEST, min_length=1, max_length=500)
    use_model: bool = True


class ContinueBody(StrictModel):
    use_model: bool = False


@router.get("/config")
def config() -> dict[str, Any]:
    cfg = model_config()
    return {"model_provider": cfg["provider"], "model": cfg["model"] if cfg["configured"] else None, "model_configured": cfg["configured"],
            "agent_mode": f"model-driven ({cfg['model']})" if cfg["configured"] else "deterministic offline planner (no AI model)",
            "fictional_service": "Fictional Residency Services Authority (demo) — not a real government website"}


@router.get("/demo")
def demo(env: Env) -> dict[str, Any]:
    return P.demo_overview(env)


@router.post("/demo/reset", dependencies=[Depends(require_dev_access)])
def demo_reset(env: Env) -> dict[str, Any]:
    return P.reset_demo(env)


@router.post("/requests", dependencies=[Depends(require_dev_access)], status_code=201)
def new_request(body: RequestBody, env: Env) -> dict[str, Any]:
    return _guard(P.start_request, env, body.citizen_ref, body.message, prefer_model=body.use_model)


@router.post("/scenes/incident", dependencies=[Depends(require_dev_access)], status_code=201)
def scene_incident(env: Env) -> dict[str, Any]:
    return _guard(P.start_incident_scene, env)


@router.get("/cases/{case_id}")
def case(case_id: CasePath, env: Env) -> dict[str, Any]:
    return _guard(P.case_view, env, case_id)


@router.get("/cases/{case_id}/receipt")
def receipt(case_id: CasePath, env: Env) -> dict[str, Any]:
    """My AI Activity: citizen-safe transparency receipt (synthetic; the portal has no citizen login — local/dev only)."""
    from app.portal.receipt import build_receipt
    r = build_receipt(env, case_id)
    if r is None:
        raise HTTPException(status_code=404, detail={"code": "CASE_NOT_FOUND", "message": "Unknown case."})
    return r


@router.post("/cases/{case_id}/continue", dependencies=[Depends(require_dev_access)])
def cont(case_id: CasePath, env: Env, body: ContinueBody | None = None) -> dict[str, Any]:
    return _guard(P.continue_request, env, case_id, prefer_model=(body or ContinueBody()).use_model)


@router.post("/cases/{case_id}/documents", dependencies=[Depends(require_dev_access)], status_code=201)
async def upload(case_id: CasePath, request: Request, env: Env, content_type: Annotated[str | None, Header()] = None,
                 x_filename: Annotated[str | None, Header(max_length=200)] = None) -> dict[str, Any]:
    if (content_type or "").split(";")[0].strip().lower() != "application/pdf":
        raise HTTPException(status_code=415, detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Send the PDF as application/pdf."})
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_BYTES:
            raise HTTPException(status_code=413, detail={"code": "PDF_TOO_LARGE", "message": f"Limit is {MAX_BYTES} bytes."})
    return _guard(P.attach_document, env, case_id, bytes(buf), x_filename, "portal_upload")


@router.post("/cases/{case_id}/documents/samples/{key}", dependencies=[Depends(require_dev_access)], status_code=201)
def attach_sample(case_id: CasePath, key: Annotated[str, Path(pattern=r"^[a-z_]{3,40}$")], env: Env) -> dict[str, Any]:
    if key not in SAMPLES:
        raise HTTPException(status_code=404, detail={"code": "SAMPLE_NOT_FOUND", "message": "Unknown sample."})
    return _guard(P.attach_document, env, case_id, SAMPLES[key][1](), f"{key}.pdf", "portal_synthetic_sample")


@router.post("/cases/{case_id}/documents/{doc_id}/injection-test", dependencies=[Depends(require_dev_access)])
def injection_test(case_id: CasePath, doc_id: DocPath, env: Env) -> dict[str, Any]:
    return _guard(P.run_injection_test, env, case_id, doc_id)
