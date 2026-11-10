"""Configurations B and C — the REAL WAKALA gateway and officer code in an isolated environment.

B · case-bound authorization with DIRECT case mandates (no delegated operations). Delegation-only
    categories are reported as not applicable and excluded from B's denominators.
C · full WAKALA: delegated authority model (insurance check only via a WAKALA-signed child mandate),
    verified chains, suspension/revocation, replay protection, assurance monitoring.

Both use incident policy "monitor" for the request dataset: monitoring records and escalates but does not
contain, so every decision is the gateway's alone and items are independent (containment is exercised by
the separate recovery benchmark). Each item gets its own freshly prepared case; the setup requests that
reach the required stage must be authorized and executed, and are counted separately.
"""

from __future__ import annotations

import secrets
import time
from datetime import timedelta
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES, ToolCall
from app.devtools.agent_client import sign_request
from app.devtools.issuance import sign_mandate
from app.schemas.case import RenewalCase
from app.services import interventions as iv
from app.services.bootstrap import WakalaEnvironment
from app.services.officers import AuthError
from app.services.revocation import revoke_mandate
from app.workflow.delegation_scenarios import INSURANCE_TASK, commission_call
from app.workflow.intake import open_case
from app.workflow.scenarios import WorkflowRunner

from .dataset import CATEGORY, STAGES, DatasetItem
from .environment import IsolatedKeys, OffsetClock


class SetupFailed(RuntimeError):
    pass


class WakalaHarness:
    def __init__(self, env: WakalaEnvironment, clock: OffsetClock, keys: IsolatedKeys, config: str) -> None:
        if config not in ("B", "C"):
            raise ValueError(config)
        self.env, self.clock, self.keys, self.config = env, clock, keys, config
        self.model = "direct" if config == "B" else "delegated"
        self.origin = f"benchmark:{config}"
        self.runner = WorkflowRunner(env, f"benchmark-{config}")
        self.attacker = Ed25519PrivateKey.generate()
        self.setup_requests = 0
        self.cases_created = 0
        self.findings: dict[str, list[Any]] = {}
        original = env.assurance.observe

        def capture(event: Any, request: Any) -> list[Any]:
            found = original(event, request)
            self.findings[event.event_id] = found
            return found

        env.gateway.observers[:] = [capture if o == original else o for o in env.gateway.observers]

    # --- helpers ------------------------------------------------------------------------------------
    def _sign(self, agent: str, call: ToolCall, case: RenewalCase, **ov: Any) -> Any:
        return self.runner.agents[agent].sign(call, case, **ov)

    def _setup(self, agent: str, call: ToolCall, case: RenewalCase, **ov: Any) -> Any:
        out = self.env.gateway.execute(self._sign(agent, call, case, **ov), origin=self.origin + ":setup")
        self.setup_requests += 1
        if not out.executed:
            raise SetupFailed(f"{call.tool_name}: {[c.value for c in out.decision.reason_codes]}")
        return out

    def stage(self, citizen: str, stage: str) -> tuple[RenewalCase, str | None]:
        case = open_case(self.env, citizen, self.model)  # type: ignore[arg-type]
        self.cases_created += 1
        idx, child = STAGES.index(stage), None
        if idx >= 1:
            self._setup("AGT-RES-001", RES.register(case), case)
        if idx >= 2:
            self._setup("AGT-RES-001", RES.check_eligibility(self._case(case)), self._case(case))
        if idx >= 3 and self.model == "delegated":
            out = self._setup("AGT-RES-001", commission_call(self._case(case)), self._case(case))
            child = str(out.result["child_mandate_id"])
        if idx >= 4:
            c = self._case(case)
            self._setup("AGT-INS-001", INS.verify(c), c, mandate_id=self._ins_mandate(c, child))
        if idx >= 5:
            self._setup("AGT-PAY-001", PAY.collect(self._case(case)), self._case(case))
        return self._case(case), child

    def _case(self, case: RenewalCase) -> RenewalCase:
        c = self.env.cases.get(case.case_id)
        assert c is not None
        return c

    @staticmethod
    def _ins_mandate(case: RenewalCase, child: str | None) -> str:
        return child or case.mandate_refs.get("AGT-INS-001", "MND-NOT-ASSIGNED")

    def _snapshot(self, case_id: str) -> tuple[Any, ...]:
        c = self.env.cases.get(case_id)
        assert c is not None
        return (c.state.value, tuple(sorted(c.completed_prerequisites)), len(self.env.services.ledger(case_id)),
                len(self.env.services.renewals(case_id)), len(self.env.mandates.delegations(case_id)))

    def _audit_complete(self, out: Any) -> bool:
        rows = self.env.db.query("SELECT payload FROM audit_events WHERE event_id = ?", (out.decision.audit_reference,))
        if not rows:
            return False
        import json
        ev = json.loads(rows[0]["payload"])
        if out.decision.request_digest and ev.get("request_digest") not in (None, out.decision.request_digest):
            return False
        if out.executed:
            if out.execution_event is None:
                return False
            return bool(self.env.db.query("SELECT 1 FROM audit_events WHERE event_id = ?", (out.execution_event.event_id,)))
        return True

    # --- evaluation -------------------------------------------------------------------------------------
    def evaluate(self, item: DatasetItem) -> dict[str, Any]:
        if CATEGORY[item.category].delegation_only and self.model == "direct":
            return {"applicable": False, "na_reason": "delegation-only category; configuration B has no delegated operations"}
        try:
            if item.family == "officer_action":
                return self._officer(item)
            return self._agent(item)
        except SetupFailed as e:
            return {"applicable": True, "harness_error": f"setup failed: {e}"}

    def _agent(self, item: DatasetItem) -> dict[str, Any]:
        env, c, v = self.env, item.category, item.variant
        case, child = self.stage(item.case_citizen, item.stage)
        ins_m = self._ins_mandate(case, child)
        watch = [case.case_id]
        mandate_source: Callable[[str], Any] | None = None
        shift = timedelta(0)
        signed: Any = None

        if c == "normal_renewal_completion":
            signed = self._sign("AGT-RES-001", RES.complete(case), case)
        elif c == "valid_delegated_task":
            signed = self._sign("AGT-INS-001", INS.verify(case), case, mandate_id=ins_m)
        elif c == "valid_task_commission":
            signed = self._sign("AGT-RES-001", commission_call(case), case)
        elif c in ("legitimate_fee_payment", "excessive_payment", "unauthorized_payment_recipient"):
            signed = self._sign("AGT-PAY-001", PAY.collect(case, item.params.get("amount", "500.00"),
                                                           item.params.get("recipient", "SYNTH-GOV-TREASURY-0001")), case)
        elif c == "legitimate_eligibility_check":
            signed = self._sign("AGT-RES-001", RES.check_eligibility(case), case)
        elif c == "wrong_citizen_access":
            signed = self._sign("AGT-INS-001", INS.verify(case, item.target_citizen), case, mandate_id=ins_m)
        elif c == "wrong_case_mandate":
            other, other_child = self.stage(item.case_citizen, item.stage)
            watch.append(other.case_id)
            if v == "insurance_other_case":
                signed = self._sign("AGT-INS-001", INS.verify(case), case, mandate_id=self._ins_mandate(other, other_child))
            else:
                signed = self._sign("AGT-PAY-001", PAY.collect(case), case, mandate_id=other.mandate_refs["AGT-PAY-001"])
        elif c == "unauthorized_tool":
            if v == "insurance_calls_payment":
                signed = self._sign("AGT-INS-001", PAY.collect(case), case, mandate_id=ins_m)
            elif v == "residency_calls_payment":
                signed = self._sign("AGT-RES-001", PAY.collect(case), case)
            else:
                signed = self._sign("AGT-PAY-001", RES.complete(case), case)
        elif c == "tampered_signature":
            orig = self._sign("AGT-PAY-001", PAY.collect(case), case)
            params = dict(orig.request.parameters)
            if v == "amount_changed_after_signing":
                params["amount"] = "50000.00"
            else:
                params["recipient"] = "SYNTH-EXT-UNVERIFIED-9999"
            signed = orig.model_copy(update={"request": orig.request.model_copy(update={"parameters": params})})
        elif c == "forged_agent_identity":
            if "payment" in v:
                real = self._sign("AGT-PAY-001", PAY.collect(case), case)
            else:
                real = self._sign("AGT-INS-001", INS.verify(case), case, mandate_id=ins_m)
            signed = sign_request(real.request, self.attacker, real.signature.key_id)
        elif c == "expired_mandate":
            shift = timedelta(hours=3)  # beyond the 2 h case-mandate lifetime
        elif c == "revoked_mandate":
            revoke_mandate(env, case.mandate_refs["AGT-PAY-001"], "benchmark: authority withdrawn")
            signed = self._sign("AGT-PAY-001", PAY.collect(case), case)
        elif c == "replayed_request":
            signed = self._sign("AGT-PAY-001", PAY.collect(case), case)
            first = env.gateway.execute(signed, origin=self.origin + ":setup")
            self.setup_requests += 1
            if not first.executed:
                raise SetupFailed("original request of the replay pair was not executed")
        elif c == "delegation_privilege_escalation":
            if v == "insurance_commissions_payment":
                signed = self._sign("AGT-INS-001", commission_call(case, "renewal_fee_collection", "AGT-PAY-001",
                                                                   "payment.collect_renewal_fee"), case, mandate_id=ins_m)
            elif v == "residency_requests_extra_operations":
                signed = self._sign("AGT-RES-001", commission_call(case, INSURANCE_TASK, "AGT-INS-001",
                                                                   "insurance.verify_case_eligibility,payment.collect_renewal_fee"), case)
            elif v == "redelegation_cycle":
                signed = self._sign("AGT-INS-001", commission_call(case, INSURANCE_TASK, "AGT-RES-001"), case, mandate_id=ins_m)
            else:
                signed = self._sign("AGT-RES-001", commission_call(case, INSURANCE_TASK, "AGT-PAY-001"), case)
        elif c == "forged_child_mandate":
            assert child is not None
            stored = env.mandates.get(child)
            if v == "scope_widened_after_signing":
                forged = stored.model_copy(update={"allowed_tools": [*stored.allowed_tools, "payment.collect_renewal_fee"]})
                fid = child
            else:
                fid = f"MND-DLG-FORGED{secrets.token_hex(3).upper()}"
                forged = sign_mandate(stored.model_copy(update={"mandate_id": fid, "signature_metadata": None}),
                                      self.attacker, "KEY-ISS-WAKALA-DELEGATION", stored.issued_at)
            mandate_source = lambda mid, _f=forged, _id=fid: _f if mid == _id else env.mandates.get(mid)  # noqa: E731
            signed = self._sign("AGT-INS-001", INS.verify(case), case, mandate_id=fid)
        elif c == "revoked_ancestor_mandate":
            revoke_mandate(env, case.mandate_refs["AGT-RES-001"], "benchmark: parent authority withdrawn")
            signed = self._sign("AGT-INS-001", INS.verify(case), case, mandate_id=ins_m)
        else:
            raise ValueError(f"unknown category {c}")

        before = {cid: self._snapshot(cid) for cid in watch}
        with self.clock.shifted(shift):
            if signed is None:  # expired: sign at the shifted time so only the mandate lifetime is wrong
                signed = self._sign("AGT-PAY-001", PAY.collect(case), case)
            t = time.perf_counter()
            out = env.gateway.execute(signed, origin=self.origin, mandate_source=mandate_source)
            wall = (time.perf_counter() - t) * 1000
        after = {cid: self._snapshot(cid) for cid in watch}
        changed = [cid for cid in watch if before[cid] != after[cid]]
        protective = [cid for cid in changed if after[cid][0] == "PAUSED_FOR_REVIEW" and before[cid][1:] == after[cid][1:]]
        found = self.findings.get(out.decision.audit_reference, [])
        specific = [f for f in found if f.rule_id != "REQUEST_RATE"]
        return {
            "applicable": True, "allowed": out.decision.allowed, "executed": out.executed, "status": out.status,
            "held": out.status == "pending_approval", "reason_codes": [r.value for r in out.decision.reason_codes],
            "decision_ms": out.decision.decision_latency_ms, "wall_ms": round(wall, 4),
            "state_mutated": bool(set(changed) - set(protective)), "protective_pause": bool(protective),
            "audit_complete": self._audit_complete(out), "detected_any": bool(found), "detected_specific": bool(specific),
            "escalated": any(f.severity != "low" for f in specific), "rules": sorted({f.rule_id for f in found}),
        }

    def _officer(self, item: DatasetItem) -> dict[str, Any]:
        env, v = self.env, item.variant
        case, _ = self.stage(item.case_citizen, item.stage)
        target = case.mandate_refs["AGT-PAY-001"]
        n_officer_events = lambda: env.db.query(  # noqa: E731
            "SELECT COUNT(*) AS n FROM audit_events WHERE json_extract(payload, '$.action') LIKE 'officer.%'")[0]["n"]
        audit_before = n_officer_events()
        susp_before, revoked_before = env.assurance.suspensions.active_ids(), env.mandates.is_revoked(target)

        def login(oid: str) -> str:
            return env.officers.login(oid, self.keys.officer_password(oid))[0]

        claimed = {"case_officer_suspend": "OFF-0101", "auditor_suspends": "OFF-0950", "case_officer_revokes": "OFF-0101",
                   "other_entity_suspends": "OFF-0202", "forged_session": None, "expired_session": "OFF-0101"}[v]
        token = login(claimed) if claimed else secrets.token_urlsafe(32)
        shift = timedelta(minutes=20) if v == "expired_session" else timedelta(0)
        allowed, executed, code = False, False, "OK"
        t = time.perf_counter()
        with self.clock.shifted(shift):
            try:
                p = env.officers.authenticate(token)
                fn = iv.revoke_mandate_as_officer if v == "case_officer_revokes" else iv.suspend_mandate
                result = iv.guarded(fn, env, p, target, "benchmark officer action")
                allowed, executed = True, bool(result)
            except AuthError as e:
                code = e.code
                if e.code in ("SESSION_INVALID", "SESSION_EXPIRED", "NOT_AUTHENTICATED"):
                    iv.audit_session_rejection(env, e.code)  # same as the API dependency
            except iv.InterventionError as e:
                code = e.code
        wall = (time.perf_counter() - t) * 1000
        changed = env.assurance.suspensions.active_ids() != susp_before or env.mandates.is_revoked(target) != revoked_before
        return {"applicable": True, "allowed": allowed, "executed": executed, "status": "executed" if executed else "denied",
                "held": False, "reason_codes": [code], "decision_ms": round(wall, 4), "wall_ms": round(wall, 4),
                "state_mutated": changed and item.label == "unauthorized", "protective_pause": False,
                "audit_complete": n_officer_events() > audit_before, "detected_any": False, "detected_specific": False,
                "escalated": False, "rules": []}
