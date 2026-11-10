"""Phase 3: transactional outcome audit, failure injection and reconciliation."""

from __future__ import annotations

import pytest

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.audit import AuditUnavailableError, OutcomeAuditUnavailable
from app.services.reconciliation import reconcile_outcomes
from app.workflow.intake import open_case
from app.workflow.scenarios import WorkflowRunner


class Flow:
    def __init__(self, h):
        self.h, self.env = h, h.env
        self.case = open_case(h.env, "C-1001")
        self.r = WorkflowRunner(h.env, "test")

    def exe(self, agent, call):
        return self.env.gateway.execute(self.r.agents[agent].sign(call, self.case), origin="test")

    def to_payment(self):
        for a, c in (("AGT-RES-001", RES.register(self.case)), ("AGT-RES-001", RES.check_eligibility(self.case)),
                     ("AGT-INS-001", INS.verify(self.case))):
            assert self.exe(a, c).executed


def snap(env):
    return {t: [tuple(r) for r in env.db.query(f"SELECT * FROM {t} ORDER BY 1")]
            for t in ("renewal_cases", "payment_ledger", "residency_renewals", "delegations")}


def test_outcome_event_committed_atomically(h):
    f = Flow(h)
    f.to_payment()
    out = f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert out.executed and out.execution_event is not None
    assert out.execution_event.evidence_metadata["outcome_recorded_atomically"] is True
    assert out.execution_event.evidence_metadata["decision_event"] == out.decision.audit_reference
    assert h.env.audit.verify().valid


def test_failed_outcome_record_rolls_back_service_change(h, monkeypatch):
    f = Flow(h)
    f.to_payment()
    before = snap(h.env)
    monkeypatch.setattr(h.env.audit, "append_in", lambda *a: (_ for _ in ()).throw(AuditUnavailableError("disk full")))
    with pytest.raises(OutcomeAuditUnavailable) as exc:
        f.exe("AGT-PAY-001", PAY.collect(f.case))
    assert exc.value.committed is False  # truthfully: nothing committed
    assert snap(h.env) == before and h.env.services.ledger() == []
    monkeypatch.undo()
    # Decision event (authorized) exists, plus a "rolled back" outcome — the distinction is preserved.
    events = h.env.audit.list(10)
    assert events[1].decision == "allowed" and events[1].action == "payment.collect_renewal_fee"
    assert events[0].evidence_metadata["execution_status"] == "rolled_back_outcome_not_recorded"
    assert h.env.audit.verify().valid


def test_both_outcome_writes_fail_then_reconciliation_records_it(h, monkeypatch):
    f = Flow(h)
    f.to_payment()
    real_append = h.env.audit.append
    calls = {"n": 0}

    def append_only_decision(draft):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_append(draft)  # decision event succeeds
        raise AuditUnavailableError("disk full")

    monkeypatch.setattr(h.env.audit, "append", append_only_decision)
    monkeypatch.setattr(h.env.audit, "append_in", lambda *a: (_ for _ in ()).throw(AuditUnavailableError("disk full")))
    with pytest.raises(OutcomeAuditUnavailable):
        f.exe("AGT-PAY-001", PAY.collect(f.case))
    monkeypatch.undo()
    assert h.env.services.ledger() == []
    first = reconcile_outcomes(h.env)
    assert [r["status"] for r in first.recorded] == ["authorized_not_executed"]
    assert reconcile_outcomes(h.env).recorded == []  # idempotent
    assert h.env.audit.verify().valid


def test_reconciliation_detects_committed_effect_without_outcome(h):
    """Simulate a non-transactional writer: effect committed, outcome missing → reconstructed, never 'rolled back'."""
    f = Flow(h)
    f.to_payment()
    out = f.exe("AGT-PAY-001", PAY.collect(f.case))
    with h.env.db.transaction() as conn:  # remove the outcome event to model the gap (test-only)
        conn.execute("DELETE FROM audit_events WHERE event_id = ?", (out.execution_event.event_id,))
    recorded = reconcile_outcomes(h.env).recorded
    assert recorded == [{"decision_event": out.decision.audit_reference, "status": "committed_outcome_reconstructed"}]


def test_refused_operation_outcome_recorded_without_mutation(h):
    f = Flow(h)
    f.to_payment()
    before = snap(h.env)
    out = f.exe("AGT-PAY-001", PAY.collect(f.case, "499.00"))
    assert out.status == "refused_by_service" and snap(h.env) == before
    assert out.execution_event.evidence_metadata["execution_status"] == "refused_by_service"
    assert out.execution_event.evidence_metadata["outcome_recorded_atomically"] is False


def test_api_reports_rollback_truthfully(harness_client, monkeypatch):
    c, h = harness_client
    f = Flow(h)
    f.to_payment()
    monkeypatch.setattr(h.env.audit, "append_in", lambda *a: (_ for _ in ()).throw(AuditUnavailableError("x")))
    signed = f.r.agents["AGT-PAY-001"].sign(PAY.collect(f.case), f.case)
    r = c.post("/api/gateway/execute", json=signed.model_dump(mode="json"))
    assert r.status_code == 503 and r.json()["error"]["code"] == "OUTCOME_NOT_RECORDED_ROLLED_BACK"
    assert h.env.services.ledger() == []


def test_api_reports_committed_but_unrecorded_truthfully():
    from app.api.gateway import audit_failure
    e = audit_failure(OutcomeAuditUnavailable("x", committed=True))
    assert e.status_code == 503 and e.detail["code"] == "OUTCOME_NOT_RECORDED"
    assert "committed" in e.detail["message"] and "rolled back" not in e.detail["message"]


def test_delegation_issuance_is_atomic_with_its_audit(h, monkeypatch):
    from app.workflow.delegation_scenarios import commission_call
    case = open_case(h.env, "C-1001", "delegated")
    r = WorkflowRunner(h.env, "t")
    for c in (RES.register(case), RES.check_eligibility(case)):
        assert h.env.gateway.execute(r.agents["AGT-RES-001"].sign(c, case)).executed
    before = snap(h.env)
    mandates_before = h.env.db.query("SELECT COUNT(*) AS n FROM mandates")[0]["n"]
    monkeypatch.setattr(h.env.audit, "append_in", lambda *a: (_ for _ in ()).throw(AuditUnavailableError("x")))
    with pytest.raises(OutcomeAuditUnavailable):
        h.env.gateway.execute(r.agents["AGT-RES-001"].sign(commission_call(case), case))
    assert snap(h.env) == before
    assert h.env.db.query("SELECT COUNT(*) AS n FROM mandates")[0]["n"] == mandates_before  # no orphan child mandate


def test_startup_reconciliation_runs(tmp_path):
    from tests.conftest import DeterministicKeystore, FrozenClock
    from app.core.config import Settings
    from app.services.bootstrap import bootstrap
    db = str(tmp_path / "w.db")
    env = bootstrap(Settings(db_path=db), keystore=DeterministicKeystore(), clock=FrozenClock())
    case = open_case(env, "C-1001")
    r = WorkflowRunner(env, "t")
    signed = r.agents["AGT-RES-001"].sign(RES.register(case), case)
    env.gateway.authorize(signed)  # an authorized decision for an audited tool with no execution
    env.close()
    env2 = bootstrap(Settings(db_path=db), keystore=DeterministicKeystore(), clock=FrozenClock())
    rows = env2.db.query("SELECT payload FROM audit_events WHERE json_extract(payload, '$.action') LIKE '%:reconciliation'")
    assert len(rows) == 1 and "authorized_not_executed" in rows[0]["payload"]
    env2.close()
