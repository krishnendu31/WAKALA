"""Policy Drafting API. Drafting: dev mode + local client. Approval: authenticated officer with policies.approve of the
entity that owns the receiving service. Approved policies are signed but NOT enforced in this prototype."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import Field

from app.api.dev import require_dev_access
from app.api.officer import Officer
from app.api.routes import Env
from app.api.workflow import require_local_client
from app.policy_drafting import service as D
from app.schemas.common import StrictModel

router = APIRouter(prefix="/api/policies", tags=["policy drafting (draft-only)"], dependencies=[Depends(require_local_client)])
PolPath = Annotated[str, Path(pattern=r"^POL-[A-Z0-9]{8}$")]


def _err(e: D.PolicyError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "message": "Policy request refused."})


class DraftBody(StrictModel):
    text: str = Field(min_length=1, max_length=400)


class DecideBody(StrictModel):
    approve: bool
    note: str = Field(default="", max_length=300)


@router.get("")
def list_all(env: Env) -> list[dict[str, Any]]:
    return D.list_policies(env)


@router.post("/drafts", dependencies=[Depends(require_dev_access)], status_code=201)
def draft(body: DraftBody, env: Env) -> dict[str, Any]:
    try:
        return D.create_draft(env, body.text)
    except D.PolicyError as e:
        raise _err(e) from None


@router.post("/{policy_id}/decision")
def decide(policy_id: PolPath, body: DecideBody, env: Env, p: Officer) -> dict[str, Any]:
    try:
        return D.decide(env, policy_id, p, body.approve, body.note)
    except D.PolicyError as e:
        raise _err(e) from None


@router.get("/{policy_id}/verify")
def verify(policy_id: PolPath, env: Env) -> dict[str, Any]:
    return D.verify_policy(env, policy_id)
