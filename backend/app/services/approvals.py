"""Pending human approvals.

A request held for approval is stored with its full signed form and digest.
NOTHING executes while it is pending. On approval, the stored request is
re-authorized with CURRENT state — identity key, agent status, mandate
signature, revocation, suspension, expiry, chain, case state, constraints —
before any dispatch. Only transport freshness and the nonce (checked when the
request first arrived) are exempt, and only for that exact digest, once.
Approval can never override revoked, suspended or expired authority.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from app.models.database import Database
from app.schemas import SignedActionRequest
from app.schemas.assurance import PendingApproval

APPROVAL_TTL = timedelta(minutes=30)


class ApprovalStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, signed: SignedActionRequest, digest: str, reason: str, incident_id: str | None,
               escalation_event: str, now: datetime) -> PendingApproval:
        req = signed.request
        approval = PendingApproval(
            approval_id=f"APR-{secrets.token_hex(4).upper()}", status="pending", created_at=now, expires_at=now + APPROVAL_TTL,
            case_id=req.case_id, agent_id=req.agent_id, tool_name=req.tool_name, mandate_id=req.mandate_id,
            request_digest=digest, reason=reason, incident_id=incident_id, escalation_event=escalation_event)
        with self._db.transaction() as conn:
            conn.execute("INSERT INTO pending_approvals (approval_id, status, case_id, payload, signed_request) VALUES (?, ?, ?, ?, ?)",
                         (approval.approval_id, approval.status, approval.case_id, approval.model_dump_json(), signed.model_dump_json()))
        return approval

    def get(self, approval_id: str) -> tuple[PendingApproval, SignedActionRequest] | None:
        rows = self._db.query("SELECT payload, signed_request FROM pending_approvals WHERE approval_id = ?", (approval_id,))
        if not rows:
            return None
        return PendingApproval.model_validate_json(rows[0]["payload"]), SignedActionRequest.model_validate_json(rows[0]["signed_request"])

    def list(self, status: str | None = None) -> list[PendingApproval]:
        sql, args = "SELECT payload FROM pending_approvals", ()
        if status:
            sql, args = sql + " WHERE status = ?", (status,)
        return [PendingApproval.model_validate_json(r["payload"]) for r in self._db.query(sql + " ORDER BY rowid DESC", args)]

    def transition(self, approval_id: str, expected: str, update: dict[str, Any]) -> PendingApproval | None:
        """Compare-and-swap on status: an approval can be claimed for execution exactly once."""
        with self._db.transaction() as conn:
            row = conn.execute("SELECT payload FROM pending_approvals WHERE approval_id = ? AND status = ?",
                               (approval_id, expected)).fetchone()
            if row is None:
                return None
            current = PendingApproval.model_validate_json(row["payload"])
            updated = PendingApproval.model_validate({**current.model_dump(), **update})
            conn.execute("UPDATE pending_approvals SET status = ?, payload = ? WHERE approval_id = ? AND status = ?",
                         (updated.status, updated.model_dump_json(), approval_id, expected))
            return updated

    def expire_due(self, now: datetime) -> int:
        n = 0
        for a in self.list("pending"):
            if now >= a.expires_at and self.transition(a.approval_id, "pending", {"status": "expired"}):
                n += 1
        return n
