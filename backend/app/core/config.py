"""Centralised runtime configuration, read from environment variables.

The prototype is deliberately local-only: CORS origins must be loopback
addresses, servers bind to 127.0.0.1, development endpoints are OFF unless
``WAKALA_DEV_MODE=1`` and, even then, answer only loopback clients. The
development keystore refuses to run when ``WAKALA_ENV=production``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parents[2]
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)
DEFAULT_DB_PATH = str(BACKEND_DIR / "var" / "wakala.db")
DEFAULT_DEV_KEYS_DIR = str(BACKEND_DIR / ".dev_keys")
# Phase 5 generated benchmark evidence (committed JSON + Markdown; read-only for the API).
DEFAULT_EVIDENCE_DIR = str(BACKEND_DIR.parent / "evidence" / "phase5")
# Document Shield: originals and labelled extractions of uploaded (synthetic) PDFs. Git-ignored (backend/var/).
DEFAULT_DOCUMENTS_DIR = str(BACKEND_DIR / "var" / "documents")


class ConfigurationError(RuntimeError):
    pass


def parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_CORS_ORIGINS
    origins = tuple(o.strip().rstrip("/") for o in raw.split(",") if o.strip())
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK_HOSTS:
            raise ConfigurationError(
                f"Refusing non-local CORS origin {origin!r}: the WAKALA prototype is local-only."
            )
    return origins


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    db_path: str = ":memory:"
    cors_origins: tuple[str, ...] = field(default=DEFAULT_CORS_ORIGINS)
    # Developer demonstration endpoints (/api/dev/*). Off by default.
    dev_mode: bool = False
    dev_keys_dir: str = DEFAULT_DEV_KEYS_DIR
    # Client hosts allowed to call /api/dev/* when dev_mode is on.
    dev_allowed_hosts: tuple[str, ...] = ("127.0.0.1", "::1", "localhost")
    # Client hosts allowed to read console-only endpoints (/api/workflow/*).
    console_allowed_hosts: tuple[str, ...] = ("127.0.0.1", "::1", "localhost")
    # Signed requests must be within this many seconds of server time.
    max_request_skew_seconds: int = 60
    # Lifetime of development mandates issued at startup.
    dev_mandate_lifetime_minutes: int = 120
    # Where the Phase 5 evidence API reads generated benchmark files from.
    evidence_dir: str = DEFAULT_EVIDENCE_DIR
    # Document Shield storage (originals are written once, read-only; extractions are separate files).
    documents_dir: str = DEFAULT_DOCUMENTS_DIR

    def __post_init__(self) -> None:
        if self.environment == "production":
            raise ConfigurationError(
                "WAKALA Phase 1 is a development prototype: it uses a local development keystore and must not "
                "run with WAKALA_ENV=production. See docs/SECURITY_MODEL.md for production key management."
            )
        if not 5 <= self.max_request_skew_seconds <= 600:
            raise ConfigurationError("max_request_skew_seconds must be between 5 and 600")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("WAKALA_ENV", "development"),
            db_path=os.getenv("WAKALA_DB_PATH", DEFAULT_DB_PATH),
            cors_origins=parse_cors_origins(os.getenv("WAKALA_CORS_ORIGINS")),
            dev_mode=_flag("WAKALA_DEV_MODE"),
            dev_keys_dir=os.getenv("WAKALA_DEV_KEYS_DIR", DEFAULT_DEV_KEYS_DIR),
            max_request_skew_seconds=int(os.getenv("WAKALA_MAX_REQUEST_SKEW_SECONDS", "60")),
            evidence_dir=os.getenv("WAKALA_EVIDENCE_DIR", DEFAULT_EVIDENCE_DIR),
            documents_dir=os.getenv("WAKALA_DOCUMENTS_DIR", DEFAULT_DOCUMENTS_DIR),
        )
