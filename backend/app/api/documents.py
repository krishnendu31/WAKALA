"""Document Shield API (development prototype; synthetic PDFs only).

Upload and adversarial tests require developer mode and a local client; reads require a local client;
releasing a REVIEW document requires an authenticated officer with ``documents.review``.
Uploads are raw ``application/pdf`` bodies, streamed with a hard size cap (no multipart parser, no
client-supplied paths: the filename is display text only).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import FileResponse
from pydantic import Field

from app.api.dev import require_dev_access
from app.api.officer import Officer
from app.api.routes import Env, ErrorResponse
from app.api.workflow import require_local_client
from app.documents.agents import DocumentIntakeAgent, run_adversarial_test
from app.documents.samples import SAMPLES
from app.documents.service import MAX_BYTES, DocumentRejected, DocumentStore
from app.schemas.common import StrictModel

router = APIRouter(prefix="/api/documents", tags=["document shield"], dependencies=[Depends(require_local_client)],
                   responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
                              413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}})
DocPath = Annotated[str, Path(pattern=r"^DOC-[A-Z0-9]{6,16}$")]
SUMMARY_KEYS = ("document_id", "display_name", "source", "created_at", "sha256", "size_bytes", "status", "disposition",
                "released_to_agents", "page_count")


def _err(e: DocumentRejected) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": "Document refused."})


def _summary(rec: dict[str, Any]) -> dict[str, Any]:
    return {**{k: rec.get(k) for k in SUMMARY_KEYS}, "findings": len(rec.get("findings", [])),
            "high_findings": sum(1 for f in rec.get("findings", []) if f["severity"] == "high"),
            "hidden_runs": len(rec.get("hidden_run_indexes", []))}


@router.get("")
def list_documents(env: Env) -> list[dict[str, Any]]:
    return [_summary(r) for r in DocumentStore(env).list()]


@router.get("/samples")
def list_samples() -> list[dict[str, str]]:
    return [{"key": k, "description": d} for k, (d, _) in SAMPLES.items()]


@router.post("", dependencies=[Depends(require_dev_access)], status_code=201)
async def upload(request: Request, env: Env, content_type: Annotated[str | None, Header()] = None,
                 x_filename: Annotated[str | None, Header(max_length=200)] = None,
                 content_length: Annotated[int | None, Header()] = None) -> dict[str, Any]:
    if (content_type or "").split(";")[0].strip().lower() != "application/pdf":
        raise HTTPException(status_code=415, detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Send the PDF as application/pdf."})
    if content_length is not None and content_length > MAX_BYTES:
        raise HTTPException(status_code=413, detail={"code": "PDF_TOO_LARGE", "message": f"Limit is {MAX_BYTES} bytes."})
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_BYTES:
            raise HTTPException(status_code=413, detail={"code": "PDF_TOO_LARGE", "message": f"Limit is {MAX_BYTES} bytes."})
    try:
        return DocumentStore(env).ingest(bytes(buf), x_filename, "upload")
    except DocumentRejected as e:
        raise _err(e) from None


@router.post("/samples/{key}", dependencies=[Depends(require_dev_access)], status_code=201)
def ingest_sample(key: Annotated[str, Path(pattern=r"^[a-z_]{3,40}$")], env: Env) -> dict[str, Any]:
    if key not in SAMPLES:
        raise HTTPException(status_code=404, detail={"code": "SAMPLE_NOT_FOUND", "message": "Unknown sample."})
    return DocumentStore(env).ingest(SAMPLES[key][1](), f"{key}.pdf", "synthetic_sample")


@router.get("/{doc_id}")
def get_document(doc_id: DocPath, env: Env) -> dict[str, Any]:
    rec = DocumentStore(env).get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_FOUND", "message": "Unknown document."})
    return rec


@router.get("/{doc_id}/pages/{page}")
def page_preview(doc_id: DocPath, page: Annotated[int, Path(ge=1, le=20)], env: Env) -> FileResponse:
    store = DocumentStore(env)
    if store.get(doc_id) is None:
        raise HTTPException(status_code=404, detail={"code": "DOCUMENT_NOT_FOUND", "message": "Unknown document."})
    try:
        p = store.path(doc_id, f"page-{page}.png")
    except DocumentRejected as e:
        raise _err(e) from None
    if not p.is_file():
        raise HTTPException(status_code=404, detail={"code": "PREVIEW_NOT_AVAILABLE", "message": "No preview for this page."})
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{doc_id}/agent-view")
def agent_view(doc_id: DocPath, env: Env) -> dict[str, Any]:
    try:
        view = DocumentStore(env).agent_view(doc_id)
    except DocumentRejected as e:
        raise _err(e) from None
    return {"view": view, "agent_result": DocumentIntakeAgent().process(view)}


@router.post("/{doc_id}/adversarial-test", dependencies=[Depends(require_dev_access)])
def adversarial_test(doc_id: DocPath, env: Env) -> dict[str, Any]:
    try:
        return run_adversarial_test(env, doc_id)
    except DocumentRejected as e:
        raise _err(e) from None


class ReviewBody(StrictModel):
    decision: Literal["release", "quarantine"]
    note: str = Field(default="", max_length=300)


@router.post("/{doc_id}/review")
def review(doc_id: DocPath, body: ReviewBody, env: Env, p: Officer) -> dict[str, Any]:
    try:
        return _summary(DocumentStore(env).review(doc_id, p, body.decision, body.note))
    except DocumentRejected as e:
        raise _err(e) from None
