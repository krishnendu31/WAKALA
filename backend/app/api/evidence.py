"""Phase 5 evidence API: serves the GENERATED benchmark files exactly as written, plus the assumption calculator.

Read-only. Nothing here computes or alters benchmark outcomes; if the files are missing the API says so
(``EVIDENCE_NOT_GENERATED``) instead of showing placeholders. Loopback clients only, like the console.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.api.workflow import require_local_client
from app.evaluation.business import BusinessAssumptions, calculate

router = APIRouter(prefix="/api/evidence", tags=["evidence"], dependencies=[Depends(require_local_client)])
SERVED = ("summary.json", "config.json", "environment.json", "manifest.json", "REPORT.md")


def _dir(request: Request) -> Path:
    return Path(request.app.state.env.settings.evidence_dir)


def _read(request: Request, name: str) -> bytes:
    path = _dir(request) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "EVIDENCE_NOT_GENERATED",
                                                     "message": "No benchmark evidence found. Run: python -m app.evaluation.run"})
    return path.read_bytes()


def _integrity(request: Request) -> dict[str, Any]:
    try:
        manifest = json.loads(_read(request, "manifest.json"))
    except HTTPException:
        return {"manifest_present": False, "files_verified": 0, "mismatched": []}
    bad = []
    for name, sha in manifest.get("files", {}).items():
        p = _dir(request) / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            bad.append(name)
    return {"manifest_present": True, "files_verified": len(manifest.get("files", {})) - len(bad), "mismatched": bad,
            "generated_at": manifest.get("generated_at")}


@router.get("/summary")
def summary(request: Request) -> dict[str, Any]:
    data = json.loads(_read(request, "summary.json"))
    return {**data, "integrity": _integrity(request)}


@router.get("/report", response_class=PlainTextResponse)
def report(request: Request) -> str:
    return _read(request, "REPORT.md").decode("utf-8")


@router.get("/files")
def files(request: Request) -> dict[str, Any]:
    return {"directory_name": _dir(request).name, "served": [n for n in SERVED if (_dir(request) / n).is_file()],
            "integrity": _integrity(request)}


@router.post("/business-model")
def business_model(body: BusinessAssumptions, request: Request) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    try:
        s = json.loads(_read(request, "summary.json"))
        observed = s["business_model_defaults"].get("observed_in_synthetic_benchmark", {})
    except (HTTPException, KeyError, ValueError):
        observed = {}
    return calculate(body, observed)
