"""Synthetic protected government services: Residency, Insurance, Payment.

These are server-side adapters. They are reachable ONLY as handlers in the
gateway's trusted tool registry, so each call has already passed request
authentication, mandate verification, case binding and policy checks.
They nevertheless re-validate their own preconditions inside one database
transaction (defence in depth and protection against state changing between
authorization and execution). On any refusal the transaction is rolled back:
no record, case or ledger row changes.

Nothing here contacts a real bank, payment provider or government system.
"""

from __future__ import annotations


import secrets
import sqlite3
from datetime import timedelta
from decimal import Decimal

from app.core.execution.tools import (
    CaseOperationParams,
    ExecutionContext,
    FeeCollectionParams,
    Scalar,
    ServiceRefusal,
    ToolSpec,
)
from app.models.database import Database
from app.schemas import Citizen, GovernmentService
from app.schemas.case import CaseEvent, CaseState, RenewalCase
from app.services.cases import CaseStore, InvalidTransition, next_case, with_event, with_prerequisite

S = CaseState
SERVICE_ID = "residency_renewal"


class ProtectedServices:
    def __init__(self, db: Database, service: GovernmentService) -> None:
        self._db = db
        self._fee = service.fee
        self._treasury = service.official_payment_destination

    # --- shared guards -----------------------------------------------------
    def _case(self, conn: sqlite3.Connection, params: CaseOperationParams, ctx: ExecutionContext,
              states: set[CaseState]) -> RenewalCase:
        case = CaseStore.load_in(conn, params.case_id)
        if case is None or ctx.case_id != case.case_id:
            raise ServiceRefusal("CASE_NOT_FOUND")
        if case.citizen_ref != params.citizen_ref or ctx.agent_id not in case.assigned_agents:
            raise ServiceRefusal("CASE_SCOPE_MISMATCH")
        if case.state not in states:
            raise ServiceRefusal("CASE_STATE_CHANGED")
        return case

    @staticmethod
    def _citizen(conn: sqlite3.Connection, citizen_ref: str) -> Citizen:
        row = conn.execute("SELECT payload FROM citizens WHERE citizen_ref = ?", (citizen_ref,)).fetchone()
        if row is None:
            raise ServiceRefusal("CITIZEN_NOT_FOUND")
        return Citizen.model_validate_json(row["payload"])

    @staticmethod
    def _op_event(ctx: ExecutionContext, detail: str) -> CaseEvent:
        return CaseEvent(at=ctx.now, actor=ctx.agent_id, kind="operation_executed", detail=detail,
                         audit_reference=ctx.audit_reference)

    def _move(self, case: RenewalCase, to: CaseState, ctx: ExecutionContext, detail: str) -> RenewalCase:
        try:
            return next_case(case, to, actor=ctx.agent_id, at=ctx.now, detail=detail, audit_reference=ctx.audit_reference)
        except InvalidTransition:
            raise ServiceRefusal("INVALID_TRANSITION") from None

    # --- Residency service ----------------------------------------------------
    def register_case(self, params: CaseOperationParams, ctx: ExecutionContext) -> dict[str, Scalar]:
        with self._db.transaction() as conn:
            before = self._case(conn, params, ctx, {S.CREATED})
            after = with_event(before, self._op_event(ctx, "Renewal application registered with the residency service"))
            after = self._move(after, S.VERIFYING, ctx, "Verification started")
            CaseStore.save_in(conn, before, after)
        return {"case_id": after.case_id, "case_state": after.state.value}

    def check_eligibility(self, params: CaseOperationParams, ctx: ExecutionContext) -> dict[str, Scalar]:
        with self._db.transaction() as conn:
            before = self._case(conn, params, ctx, {S.VERIFYING})
            citizen = self._citizen(conn, before.citizen_ref)
            eligible = citizen.service_attributes.renewal_eligible and citizen.residency.status != "expired"
            after = with_event(before, self._op_event(ctx, "Residency eligibility checked"))
            if eligible:
                after = with_prerequisite(after, "residency_eligibility", actor=ctx.agent_id, at=ctx.now,
                                          detail="Residency eligibility confirmed", audit_reference=ctx.audit_reference)
                after = self._maybe_await_payment(after, ctx)
            else:
                after = with_event(after, CaseEvent(at=ctx.now, actor=ctx.agent_id, kind="prerequisite_failed",
                                                    detail="Applicant is not eligible for renewal", audit_reference=ctx.audit_reference))
                after = self._move(after, S.FAILED, ctx, "Residency eligibility not met; officer review required")
            CaseStore.save_in(conn, before, after)
        # Minimal disclosure: eligibility facts only, never the full record.
        return {"citizen_ref": citizen.citizen_ref, "eligible": eligible, "permit_status": citizen.residency.status,
                "permit_expiry": citizen.residency.expiry_date.isoformat(), "case_state": after.state.value}

    def complete_renewal(self, params: CaseOperationParams, ctx: ExecutionContext) -> dict[str, Scalar]:
        with self._db.transaction() as conn:
            before = self._case(conn, params, ctx, {S.READY_TO_COMPLETE})
            citizen = self._citizen(conn, before.citizen_ref)
            renewed = citizen.residency.expiry_date + timedelta(days=365)
            after = with_event(before, self._op_event(ctx, f"Renewal prepared; synthetic permit extended to {renewed.isoformat()}"))
            after = self._move(after, S.COMPLETED, ctx, "Renewal completed")
            conn.execute(
                "INSERT INTO residency_renewals (case_id, citizen_ref, previous_expiry, renewed_expiry, completed_at, decision_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (after.case_id, after.citizen_ref, citizen.residency.expiry_date.isoformat(), renewed.isoformat(),
                 ctx.now.isoformat(), ctx.decision_id),
            )
            CaseStore.save_in(conn, before, after)
        return {"case_id": after.case_id, "renewed_permit_expiry": renewed.isoformat(), "case_state": after.state.value}

    # --- Insurance service ------------------------------------------------------
    def verify_insurance(self, params: CaseOperationParams, ctx: ExecutionContext) -> dict[str, Scalar]:
        with self._db.transaction() as conn:
            before = self._case(conn, params, ctx, {S.VERIFYING})
            citizen = self._citizen(conn, before.citizen_ref)
            ins = citizen.insurance
            valid = ins.status == "valid" and ins.valid_until is not None and ins.valid_until > ctx.now.date()
            after = with_event(before, self._op_event(ctx, "Insurance eligibility verified"))
            if valid:
                after = with_prerequisite(after, "insurance_verified", actor=ctx.agent_id, at=ctx.now,
                                          detail="Valid insurance cover confirmed", audit_reference=ctx.audit_reference)
                after = self._maybe_await_payment(after, ctx)
            else:
                after = with_event(after, CaseEvent(at=ctx.now, actor=ctx.agent_id, kind="prerequisite_failed",
                                                    detail="No valid insurance cover", audit_reference=ctx.audit_reference))
                after = self._move(after, S.FAILED, ctx, "Insurance prerequisite not met; officer review required")
            CaseStore.save_in(conn, before, after)
        # Only what the case needs: valid yes/no and until when. No policy number or provider.
        return {"citizen_ref": citizen.citizen_ref, "insurance_valid": valid,
                "valid_until": ins.valid_until.isoformat() if ins.valid_until else None, "case_state": after.state.value}

    def _maybe_await_payment(self, case: RenewalCase, ctx: ExecutionContext) -> RenewalCase:
        if {"residency_eligibility", "insurance_verified"} <= set(case.completed_prerequisites):
            return self._move(case, S.AWAITING_PAYMENT, ctx, "All verifications complete; fee due")
        return case

    # --- Payment service --------------------------------------------------------
    def collect_fee(self, params: FeeCollectionParams, ctx: ExecutionContext) -> dict[str, Scalar]:
        if params.recipient != self._treasury:
            raise ServiceRefusal("DESTINATION_NOT_OFFICIAL")
        if params.currency != self._fee.currency or params.amount != self._fee.amount:
            raise ServiceRefusal("AMOUNT_NOT_OFFICIAL_FEE")
        with self._db.transaction() as conn:
            existing = conn.execute("SELECT * FROM payment_ledger WHERE case_id = ?", (params.case_id,)).fetchone()
            if existing is not None:
                same = (existing["idempotency_key"] == params.idempotency_key and Decimal(existing["amount"]) == params.amount
                        and existing["recipient"] == params.recipient)
                if not same:
                    raise ServiceRefusal("FEE_ALREADY_COLLECTED")
                case = self._case(conn, params, ctx, {S.READY_TO_COMPLETE, S.AWAITING_PAYMENT})
                return {"transaction_id": existing["transaction_id"], "amount": existing["amount"], "currency": existing["currency"],
                        "recipient": existing["recipient"], "status": "settled_synthetic", "idempotent_replay": True,
                        "case_state": case.state.value}
            before = self._case(conn, params, ctx, {S.AWAITING_PAYMENT})
            txn = f"TXN-SYNTH-{secrets.token_hex(5).upper()}"
            conn.execute(
                "INSERT INTO payment_ledger (transaction_id, case_id, idempotency_key, citizen_ref, amount, currency, recipient, created_at, decision_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (txn, params.case_id, params.idempotency_key, params.citizen_ref, f"{params.amount:.2f}", params.currency,
                 params.recipient, ctx.now.isoformat(), ctx.decision_id),
            )
            after = with_event(before, self._op_event(ctx, f"Synthetic fee {params.currency} {params.amount:.2f} collected ({txn})"))
            after = with_prerequisite(after, "fee_paid", actor=ctx.agent_id, at=ctx.now, detail="Renewal fee paid",
                                      audit_reference=ctx.audit_reference)
            after = self._move(after, S.READY_TO_COMPLETE, ctx, "Fee received; ready to complete")
            CaseStore.save_in(conn, before, after)
        return {"transaction_id": txn, "amount": f"{params.amount:.2f}", "currency": params.currency, "recipient": params.recipient,
                "status": "settled_synthetic", "idempotent_replay": False, "case_state": after.state.value}

    # --- read models -------------------------------------------------------------
    def ledger(self, case_id: str | None = None) -> list[dict[str, str]]:
        sql, args = "SELECT * FROM payment_ledger", ()
        if case_id:
            sql, args = sql + " WHERE case_id = ?", (case_id,)
        return [{k: str(r[k]) for k in r.keys()} for r in self._db.query(sql + " ORDER BY created_at DESC", args)]

    def renewals(self, case_id: str) -> list[dict[str, str]]:
        return [{k: str(r[k]) for k in r.keys()}
                for r in self._db.query("SELECT * FROM residency_renewals WHERE case_id = ?", (case_id,))]

    def tool_specs(self) -> list[ToolSpec]:
        common = {"service_id": SERVICE_ID, "needs_context": True, "audit_execution": True}
        return [
            ToolSpec("residency.register_renewal_case", resource_type="renewal_case", access="write", target="case_id",
                     params_model=CaseOperationParams, monetary=False, handler=self.register_case,
                     description="Register the renewal application and start verification.",
                     case_states=frozenset({S.CREATED.value}), **common),
            ToolSpec("residency.check_eligibility", resource_type="citizen_record", access="read", target="citizen_ref",
                     params_model=CaseOperationParams, monetary=False, handler=self.check_eligibility,
                     description="Check the case applicant's residency renewal eligibility.",
                     case_states=frozenset({S.VERIFYING.value}), **common),
            ToolSpec("insurance.verify_case_eligibility", resource_type="insurance_record", access="read", target="citizen_ref",
                     params_model=CaseOperationParams, monetary=False, handler=self.verify_insurance,
                     description="Verify insurance eligibility for the case's citizen only.",
                     case_states=frozenset({S.VERIFYING.value}), **common),
            ToolSpec("payment.collect_renewal_fee", resource_type="payment", access="execute", target="case_id",
                     params_model=FeeCollectionParams, monetary=True, handler=self.collect_fee,
                     description="Collect the synthetic AED 500 fee to the official treasury destination (idempotent).",
                     case_states=frozenset({S.AWAITING_PAYMENT.value, S.READY_TO_COMPLETE.value}), **common),
            ToolSpec("residency.complete_renewal", resource_type="renewal_case", access="write", target="case_id",
                     params_model=CaseOperationParams, monetary=False, handler=self.complete_renewal,
                     description="Complete the renewal once all prerequisites are satisfied.",
                     case_states=frozenset({S.READY_TO_COMPLETE.value}), **common),
        ]


__all__ = ["ProtectedServices", "SERVICE_ID"]
