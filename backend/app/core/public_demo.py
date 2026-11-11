"""Hosted public judge demo (deployment-only).

Enabled with ``WAKALA_PUBLIC_DEMO=1``. Off by default, so local development and the test suite behave exactly as
before. When enabled:

* read-only requests (GET/HEAD) to console endpoints are allowed for remote visitors;
* of the developer-only mutations, ONLY the guided judge-demo actions below are allowed, and only same-origin
  (they run predefined synthetic scenarios; every agent step still goes through the signed gateway);
* every other developer mutation (attack lab runs, document uploads, policy drafts, shadow runs, workflow
  scenarios, /api/dev/*) stays refused;
* officer actions keep requiring an authenticated officer session (unchanged);
* the officer password for the demo comes from the hosting secret ``WAKALA_DEMO_OFFICER_PASSWORD`` (stored hashed).
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from fastapi import HTTPException, Request

_ALLOWED_POSTS = [
    re.compile(r"^/api/portal/demo/reset$"),
    re.compile(r"^/api/portal/requests$"),
    re.compile(r"^/api/portal/scenes/incident$"),
    re.compile(r"^/api/portal/cases/CASE-[A-Z0-9]{6,12}/continue$"),
]
DEMO_OFFICER_ID = "OFF-0101"


def enabled() -> bool:
    return os.getenv("WAKALA_PUBLIC_DEMO", "").strip().lower() in {"1", "true", "yes", "on"}


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return urlparse(origin).netloc == request.headers.get("host", "")


def check_dev_access(request: Request) -> None:
    """Replaces the loopback-only developer guard when the public demo is enabled."""
    if request.method in ("GET", "HEAD"):
        return
    if request.method == "POST" and any(p.match(request.url.path) for p in _ALLOWED_POSTS):
        if not _same_origin(request):
            raise HTTPException(status_code=403, detail={"code": "DEMO_ORIGIN_REJECTED", "message": "Cross-site origin rejected."})
        return
    raise HTTPException(status_code=403, detail={"code": "PUBLIC_DEMO_READ_ONLY",
                                                 "message": "This action is not available in the public demo."})


def provision_officer(env) -> None:  # type: ignore[no-untyped-def]
    """Stores the hosting-secret demo officer password (hash only). Without the secret, officer sign-in is unavailable."""
    pw = os.getenv("WAKALA_DEMO_OFFICER_PASSWORD", "")
    if enabled() and len(pw) >= 12:
        env.officers._store_hash(DEMO_OFFICER_ID, pw)  # noqa: SLF001 — same hashing as the dev CLI
