"""WAKALA backend entry point.

Run locally:  python run_dev.py            (dev mode: demo endpoints on)
              uvicorn app.main:app --host 127.0.0.1 --port 8000
API docs:     http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import attack_lab, dev, documents, evidence, gateway, officer, portal, workflow
from app.api.routes import api, router
from app.core.config import Settings
from app.services.bootstrap import WakalaEnvironment, bootstrap


def create_app(settings: Settings | None = None, *, env_factory: Callable[[Settings], WakalaEnvironment] | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        env = (env_factory or bootstrap)(settings)  # fails fast on invalid data or keys
        app.state.env = env
        try:
            yield
        finally:
            env.close()

    app = FastAPI(
        title="WAKALA | وكالة API",
        summary="Autonomous AI. Accountable Authority.",
        description=(
            "Phase 1 API for WAKALA, a verifiable identity and mandate-based authorization layer for government AI "
            "agents. **All data is synthetic. Development prototype — not production-ready.** Sensitive actions go "
            "through `POST /api/gateway/execute`, authenticated by an Ed25519 request signature and authorized by a "
            "deterministic default-deny policy against issuer-signed mandates."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = {"code": exc.detail["code"], "message": exc.detail.get("message", ""), "details": None}
        else:
            body = {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail), "details": None}
        return JSONResponse(status_code=exc.status_code, content={"error": body})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "VALIDATION_ERROR", "message": "Request failed validation.", "details": details}},
        )

    app.include_router(router)
    app.include_router(api)
    app.include_router(gateway.router)
    app.include_router(dev.router)
    app.include_router(workflow.router)
    app.include_router(officer.router)
    app.include_router(evidence.router)
    app.include_router(documents.router)
    app.include_router(portal.router)
    app.include_router(attack_lab.router)
    return app


app = create_app()
