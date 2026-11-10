"""Read-only registry, environment, mandate and audit endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Generic, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel

from app import __version__
from app.core.mandates import verify_mandate
from app.schemas import (
    SECURITY_CONTRACTS,
    AgentPassport,
    Citizen,
    GovernmentService,
    ReasonCode,
    ScenarioWithDocument,
    SystemCapabilities,
)
from app.schemas.views import (
    AuditEventListView,
    AuditIntegrityView,
    IssuerView,
    MandateVerificationView,
    MandateView,
    PublicKeyView,
)
from app.services.bootstrap import WakalaEnvironment
from app.services.capabilities import get_capabilities
from app.services.mandate_store import StoredMandate
from app.services.repository import Repository

T = TypeVar("T")
R = ReasonCode


class ListResponse(BaseModel, Generic[T]):
    items: list[T]
    count: int
    synthetic_data: Literal[True] = True


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["wakala-backend"]
    version: str
    synthetic_data_only: Literal[True] = True


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def get_env(request: Request) -> WakalaEnvironment:
    return request.app.state.env


def get_repository(request: Request) -> Repository:
    return request.app.state.env.repo


Env = Annotated[WakalaEnvironment, Depends(get_env)]
Repo = Annotated[Repository, Depends(get_repository)]
AgentIdPath = Annotated[str, Path(pattern=r"^AGT-[A-Z]{3,8}-\d{3}$", description="Agent identifier, e.g. AGT-RES-001")]
MandateIdPath = Annotated[str, Path(pattern=r"^MND-[A-Z0-9-]{4,40}$")]

router = APIRouter()
api = APIRouter(prefix="/api", responses={422: {"model": ErrorResponse}})


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="wakala-backend", version=__version__)


@api.get("/agents", response_model=ListResponse[AgentPassport], tags=["registry"])
def list_agents(repo: Repo) -> ListResponse[AgentPassport]:
    agents = repo.list_agents()
    return ListResponse[AgentPassport](items=agents, count=len(agents))


@api.get("/agents/{agent_id}", response_model=AgentPassport, tags=["registry"], responses={404: {"model": ErrorResponse}})
def get_agent(agent_id: AgentIdPath, repo: Repo) -> AgentPassport:
    agent = repo.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "AGENT_NOT_FOUND", "message": f"No registered agent with id {agent_id}."})
    return agent


@api.get("/citizens", response_model=ListResponse[Citizen], tags=["synthetic environment"])
def list_citizens(repo: Repo) -> ListResponse[Citizen]:
    citizens = repo.list_citizens()
    return ListResponse[Citizen](items=citizens, count=len(citizens))


@api.get("/services", response_model=ListResponse[GovernmentService], tags=["synthetic environment"])
def list_services(repo: Repo) -> ListResponse[GovernmentService]:
    services = repo.list_services()
    return ListResponse[GovernmentService](items=services, count=len(services))


@api.get("/scenarios", response_model=ListResponse[ScenarioWithDocument], tags=["synthetic environment"])
def list_scenarios(repo: Repo) -> ListResponse[ScenarioWithDocument]:
    scenarios = repo.list_scenarios()
    return ListResponse[ScenarioWithDocument](items=scenarios, count=len(scenarios))


# --- identity & mandates --------------------------------------------------------

@api.get("/identity/keys", response_model=ListResponse[PublicKeyView], tags=["identity"])
def list_public_keys(repo: Repo) -> ListResponse[PublicKeyView]:
    keys = [PublicKeyView.model_validate(k) for k in repo.list_keys()]
    return ListResponse[PublicKeyView](items=keys, count=len(keys))


@api.get("/issuers", response_model=ListResponse[IssuerView], tags=["mandates"])
def list_issuers(repo: Repo) -> ListResponse[IssuerView]:
    items = []
    for issuer in repo.list_issuers():
        key = repo.get_key(issuer.key_id)
        ok = key is not None and key.owner_type == "issuer" and key.owner_id == issuer.issuer_id
        items.append(IssuerView(issuer=issuer, key_fingerprint=key.fingerprint if ok and key else None, key_registered=ok))
    return ListResponse[IssuerView](items=items, count=len(items))


def _mandate_view(env: WakalaEnvironment, stored: StoredMandate) -> MandateView:
    now = env.clock()
    snap = env.gateway.policy_snapshot(now)
    v = verify_mandate(stored.mandate, snap["issuers"], snap["issuer_public_keys"], now, snap["revoked_mandate_ids"])
    codes = set(v.integrity_codes)
    return MandateView(
        mandate=stored.mandate,
        verification=MandateVerificationView(
            valid=v.valid,
            effective_status=v.effective_status,  # type: ignore[arg-type]
            signature_valid=not (codes & {R.DENY_MANDATE_UNSIGNED, R.DENY_SIGNATURE_INVALID, R.DENY_ISSUER_UNTRUSTED}),
            issuer_trusted=R.DENY_ISSUER_UNTRUSTED not in codes,
            within_issuer_authority=not codes,
            reason_codes=list(v.integrity_codes + v.lifecycle_codes),
            checked_at=now.isoformat(),
        ),
        revoked=stored.revoked,
        revoked_at=stored.revoked_at,
        revocation_reason=stored.revocation_reason,
    )


@api.get("/mandates", response_model=ListResponse[MandateView], tags=["mandates"])
def list_mandates(env: Env, agent_id: Annotated[str | None, Query(pattern=r"^AGT-[A-Z]{3,8}-\d{3}$")] = None) -> ListResponse[MandateView]:
    items = [_mandate_view(env, s) for s in env.mandates.list(agent_id)]
    return ListResponse[MandateView](items=items, count=len(items))


@api.get("/mandates/{mandate_id}", response_model=MandateView, tags=["mandates"], responses={404: {"model": ErrorResponse}})
def get_mandate(mandate_id: MandateIdPath, env: Env) -> MandateView:
    for stored in env.mandates.list():
        if stored.mandate.mandate_id == mandate_id:
            return _mandate_view(env, stored)
    raise HTTPException(status_code=404, detail={"code": "MANDATE_NOT_FOUND", "message": f"No mandate {mandate_id}."})


# --- audit ----------------------------------------------------------------------------

@api.get("/audit/events", response_model=AuditEventListView, tags=["audit"])
def list_audit_events(env: Env, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> AuditEventListView:
    counts = env.audit.decision_counts()
    return AuditEventListView(
        items=env.audit.list(limit),
        count=env.audit.count(),
        allowed_count=counts.get("allowed", 0),
        denied_count=counts.get("denied", 0),
        enforcement_engine_connected=True,
    )


@api.get("/audit/integrity", response_model=AuditIntegrityView, tags=["audit"])
def audit_integrity(env: Env) -> AuditIntegrityView:
    r = env.audit.verify()
    return AuditIntegrityView(valid=r.valid, event_count=r.event_count, head_hash=r.head_hash,
                              first_broken_sequence=r.first_broken_sequence, detail=r.detail)


# --- system ---------------------------------------------------------------------------

@api.get("/system/capabilities", response_model=SystemCapabilities, tags=["system"])
def capabilities(env: Env) -> SystemCapabilities:
    return get_capabilities(developer_demo_enabled=env.settings.dev_mode)


@api.get("/schemas", tags=["contracts"])
def list_contracts() -> dict[str, list[str]]:
    return {"contracts": list(SECURITY_CONTRACTS)}


@api.get("/schemas/{name}", tags=["contracts"], responses={404: {"model": ErrorResponse}})
def get_contract(name: str) -> dict[str, Any]:
    model = SECURITY_CONTRACTS.get(name)
    if model is None:
        raise HTTPException(status_code=404, detail={"code": "CONTRACT_NOT_FOUND", "message": f"Unknown contract {name!r}."})
    return model.model_json_schema()
