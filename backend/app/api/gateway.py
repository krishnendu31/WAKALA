"""Gateway endpoints. The caller is authenticated by the Ed25519 signature in
the request body — there is no other way to act as an agent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.routes import Env, ErrorResponse
from app.core.audit import AuditUnavailableError, OutcomeAuditUnavailable
from app.schemas import AuthorizationDecision, ExecutionResponse, SignedActionRequest

router = APIRouter(prefix="/api/gateway", tags=["gateway"], responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})

_AUDIT_DOWN = {"code": "AUDIT_UNAVAILABLE", "message": "The decision could not be audited, so no action was taken."}


def audit_failure(exc: AuditUnavailableError) -> HTTPException:
    """Truthful 503: distinguishes 'never ran', 'rolled back' and 'committed, outcome pending'."""
    if isinstance(exc, OutcomeAuditUnavailable):
        if exc.committed:
            return HTTPException(status_code=503, detail={
                "code": "OUTCOME_NOT_RECORDED",
                "message": "The operation committed but its outcome record could not be written; reconciliation will record it."})
        return HTTPException(status_code=503, detail={
            "code": "OUTCOME_NOT_RECORDED_ROLLED_BACK",
            "message": "The outcome could not be recorded, so the operation was rolled back. Nothing changed."})
    return HTTPException(status_code=503, detail=_AUDIT_DOWN)


@router.post("/authorize", response_model=AuthorizationDecision)
def authorize_action(body: SignedActionRequest, env: Env) -> AuthorizationDecision:
    """Policy query: returns ALLOW or DENY for a signed request. Never executes a tool.
    Consumes the request nonce, so the same signed request cannot later be executed."""
    try:
        return env.gateway.authorize(body).decision
    except AuditUnavailableError:
        raise HTTPException(status_code=503, detail=_AUDIT_DOWN) from None


@router.post("/execute", response_model=ExecutionResponse, responses={403: {"model": ExecutionResponse}})
def execute_action(body: SignedActionRequest, env: Env):  # type: ignore[no-untyped-def]
    """Authorize and, only if allowed, dispatch through the trusted tool registry.
    Denied requests return 403 and the tool is never invoked."""
    try:
        outcome = env.gateway.execute(body)
    except AuditUnavailableError as exc:
        raise audit_failure(exc) from None
    resp = ExecutionResponse(decision=outcome.decision, executed=outcome.executed,
                             execution_status=outcome.status, result=outcome.result)
    if not outcome.decision.allowed:
        return JSONResponse(status_code=403, content=resp.model_dump(mode="json"))
    return resp
