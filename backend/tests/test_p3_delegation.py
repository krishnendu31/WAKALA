"""Phase 3: signed, non-expanding mandate chains through the real gateway."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.delegation import TASK_CATALOG, check_non_expansion, verify_chain
from app.core.mandates import canonical_mandate_bytes
from app.devtools.agent_client import sign_request
from app.devtools.issuance import sign_mandate
from app.schemas import ActionRequest, DigitalMandate, ReasonCode as R
from app.schemas.case import CaseState
from app.services.revocation import revoke_agent, revoke_case_authority, revoke_mandate
from app.workflow.delegation_scenarios import commission_call, prepare
from app.workflow.intake import _case_mandate, open_case
from app.workflow.scenarios import WorkflowRunner, run_workflow

S = CaseState


class DFlow:
    def __init__(self, h, citizen="C-1001"):
        self.h, self.env = h, h.env
        self.case = open_case(h.env, citizen, "delegated")
        self.r = WorkflowRunner(h.env, "test")

    def sign(self, agent, call, **kw):
        return self.r.agents[agent].sign(call, self.case, **kw)

    def exe(self, agent, call, *, case=None, mandate_source=None, **kw):
        c = case or self.case
        signed = self.r.agents[agent].sign(call, c, **kw)
        return self.env.gateway.execute(signed, origin="test", mandate_source=mandate_source)

    def setup(self):
        assert self.exe("AGT-RES-001", RES.register(self.case)).executed
        assert self.exe("AGT-RES-001", RES.check_eligibility(self.case)).executed
        out = self.exe("AGT-RES-001", commission_call(self.case))
        assert out.decision.allowed and out.executed, out.decision.reason_codes
        self.child = str(out.result["child_mandate_id"])
        return self.child

    @property
    def root(self):
        return self.case.mandate_refs["AGT-RES-001"]

    def state(self):
        return self.env.cases.get(self.case.case_id).state

    def snapshot(self):
        tables = ("renewal_cases", "payment_ledger", "residency_renewals", "mandates", "delegations")
        return {t: [tuple(r) for r in self.env.db.query(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}


@pytest.fixture()
def f(h):
    return DFlow(h)


# --- valid delegation ---------------------------------------------------------------

def test_delegated_case_model(f):
    assert f.case.authority_model == "delegated"
    assert "AGT-INS-001" not in f.case.mandate_refs and "AGT-INS-001" not in f.case.assigned_agents
    root = f.env.mandates.get(f.root)
    assert root.commissionable_tasks == ["insurance_eligibility_check"] and root.case_id == f.case.case_id
    assert "insurance.verify_case_eligibility" in root.denied_tools  # may commission, may NOT execute


def test_residency_agent_cannot_execute_what_it_may_commission(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    out = f.exe("AGT-RES-001", INS.verify(f.case))
    assert R.DENY_TOOL_EXPLICITLY_DENIED in out.decision.reason_codes and not out.executed


def test_insurance_agent_without_delegation_is_denied(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=f.root)  # tries the parent's mandate
    assert R.DENY_MANDATE_AGENT_MISMATCH in out.decision.reason_codes


def test_valid_delegated_authorization(f):
    child_id = f.setup()
    child = f.env.mandates.get(child_id)
    assert child.parent_mandate_id == f.root and child.root_mandate_id == f.root
    assert child.issuer_id == "ISS-WAKALA-DELEGATION" and child.delegated_by_agent == "AGT-RES-001"
    assert child.allowed_tools == ["insurance.verify_case_eligibility"]
    assert child.case_id == f.case.case_id and child.delegation_depth == 1
    assert child.expires_at <= f.env.mandates.get(f.root).expires_at
    assert child.commissionable_tasks == []
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child_id)
    assert out.decision.allowed and out.executed and out.result["insurance_valid"] is True
    assert [c.status for c in out.evaluation.checks] == ["passed"] * 8
    assert f.state() is S.AWAITING_PAYMENT


def test_delegated_renewal_completes(h):
    run = run_workflow(h.env, "delegated_renewal")
    assert run.case.state is S.COMPLETED and len(run.delegations) == 1
    assert all(s.decision.allowed and s.executed for s in run.steps)
    assert [s.tool_name for s in run.steps][2:4] == ["delegation.commission_task", "insurance.verify_case_eligibility"]
    assert h.env.audit.verify().valid


def test_delegation_events_are_audited(f):
    child = f.setup()
    events = f.env.audit.list(50)
    commission = [e for e in events if e.action == "delegation.commission_task" and e.decision == "allowed"]
    outcome = [e for e in events if e.action == "delegation.commission_task:execution"]
    assert len(commission) == 1 and len(outcome) == 1
    assert outcome[0].evidence_metadata["outcome_recorded_atomically"] is True
    record = f.env.mandates.delegations(f.case.case_id)[0]
    assert record["child_mandate_id"] == child and record["decision_event"] == commission[0].event_id
    assert any(ev.kind == "delegation_issued" for ev in f.env.cases.get(f.case.case_id).history)


# --- adversarial ---------------------------------------------------------------------

def test_b_child_cannot_read_another_citizen(f):
    child = f.setup()
    before = f.snapshot()
    out = f.exe("AGT-INS-001", INS.verify(f.case, "C-1003"), mandate_id=child)
    assert {R.DENY_SCOPE_VIOLATION, R.DENY_CASE_SCOPE_VIOLATION} <= set(out.decision.reason_codes) and out.result is None
    assert f.snapshot() == before


def test_c_child_cannot_collect_payment(f):
    child = f.setup()
    out = f.exe("AGT-INS-001", PAY.collect(f.case), mandate_id=child)
    assert R.DENY_TOOL_EXPLICITLY_DENIED in out.decision.reason_codes or R.DENY_TOOL_NOT_PERMITTED in out.decision.reason_codes
    assert f.env.services.ledger() == []


def test_d_child_cannot_create_broader_child(f):
    child = f.setup()
    before = f.snapshot()
    for call in (commission_call(f.case, "renewal_fee_collection", "AGT-PAY-001", "payment.collect_renewal_fee"),
                 commission_call(f.case, "insurance_eligibility_check", "AGT-PAY-001")):
        out = f.exe("AGT-INS-001", call, mandate_id=child)
        assert R.DENY_DELEGATION_NOT_PERMITTED in out.decision.reason_codes and not out.executed
    assert f.snapshot() == before and len(f.env.mandates.delegations()) == 1


def test_parent_cannot_request_operations_beyond_the_task(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    out = f.exe("AGT-RES-001", commission_call(f.case, operations="insurance.verify_case_eligibility,payment.collect_renewal_fee"))
    assert R.DENY_DELEGATION_EXPANDS_AUTHORITY in out.decision.reason_codes and f.env.mandates.delegations() == []


def test_parent_cannot_commission_ungranted_task(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    out = f.exe("AGT-RES-001", commission_call(f.case, "renewal_fee_collection", "AGT-PAY-001", "payment.collect_renewal_fee"))
    assert R.DENY_DELEGATION_NOT_PERMITTED in out.decision.reason_codes


def test_parent_cannot_delegate_to_unlisted_receiver(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    out = f.exe("AGT-RES-001", commission_call(f.case, receiver="AGT-PAY-001"))
    assert R.DENY_DELEGATION_NOT_PERMITTED in out.decision.reason_codes


@pytest.mark.parametrize("change", [
    {"allowed_tools": ["insurance.verify_case_eligibility", "payment.collect_renewal_fee"]},
    {"expires_at_delta": timedelta(hours=5)},
    {"citizen": "C-1003"},
    {"case_id": "CASE-00000000"},
    {"agent_id": "AGT-PAY-001"},
])
def test_e_forged_or_modified_delegation_rejected(f, change):
    child_id = f.setup()
    child = f.env.mandates.get(child_id)
    upd = dict(change)
    if "expires_at_delta" in upd:
        upd = {"expires_at": child.expires_at + upd.pop("expires_at_delta")}
    if "citizen" in upd:
        upd = {"citizen_or_request_scope": child.citizen_or_request_scope.model_copy(update={"citizen_ref": upd.pop("citizen")})}
    forged = child.model_copy(update=upd)
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child_id,
                mandate_source=lambda mid: forged if mid == child_id else f.env.mandates.get(mid))
    assert not out.decision.allowed and R.DENY_SIGNATURE_INVALID in out.decision.reason_codes


def test_e_child_signed_by_attacker_key_rejected(f):
    child = f.env.mandates.get(f.setup())
    fake = sign_mandate(child.model_copy(update={"mandate_id": "MND-DLG-FAKE0001", "signature_metadata": None}),
                        Ed25519PrivateKey.generate(), "KEY-ISS-WAKALA-DELEGATION", child.issued_at)
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=fake.mandate_id,
                mandate_source=lambda mid: fake if mid == fake.mandate_id else f.env.mandates.get(mid))
    assert out.decision.reason_codes == [R.DENY_SIGNATURE_INVALID]


def test_e_correctly_signed_but_expanding_child_rejected(f):
    """Even a child validly signed by the delegation authority is rejected if it expands the parent."""
    child = f.env.mandates.get(f.setup())
    wide = DigitalMandate.model_validate({**child.model_dump(), "mandate_id": "MND-DLG-WIDE0001", "signature_metadata": None,
                                          "resource_constraints": [{"resource_type": "insurance_record", "access": "read",
                                                                    "identifiers": ["C-1001", "C-1003"]}]})
    wide = f.env.delegation._sign(wide)
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=wide.mandate_id,
                mandate_source=lambda mid: wide if mid == wide.mandate_id else f.env.mandates.get(mid))
    assert out.decision.reason_codes == [R.DENY_DELEGATION_EXPANDS_AUTHORITY]


def test_root_signed_by_delegation_authority_rejected(f):
    """The delegation authority can never mint a chain root."""
    f.exe("AGT-RES-001", RES.register(f.case))
    root = f.env.mandates.get(f.root)
    fake_root = f.env.delegation._sign(DigitalMandate.model_validate(
        {**root.model_dump(), "mandate_id": "MND-RES-FAKEROOT", "issuer_id": "ISS-WAKALA-DELEGATION", "signature_metadata": None}))
    out = f.exe("AGT-RES-001", RES.check_eligibility(f.case), mandate_id=fake_root.mandate_id,
                mandate_source=lambda mid: fake_root if mid == fake_root.mandate_id else f.env.mandates.get(mid))
    assert R.DENY_ISSUER_AUTHORITY_EXCEEDED in out.decision.reason_codes


def test_f_expired_parent_rejected(f):
    child = f.setup()
    f.h.clock.advance(hours=2, seconds=1)  # root mandate (2 h) has expired
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child)
    assert not out.decision.allowed
    assert {R.DENY_PARENT_MANDATE_EXPIRED} & set(out.decision.reason_codes) or R.DENY_MANDATE_EXPIRED in out.decision.reason_codes


def test_f_expired_parent_with_unexpired_child_rejected(f, h):
    """Chain verification catches an ancestor that expired even if the child itself still looks valid."""
    now = h.clock()
    body = _case_mandate("AGT-RES-001", f.case.case_id, "C-1001", f.case.request_id, now - timedelta(hours=1, minutes=50),
                         now - timedelta(minutes=10), "delegated")
    body["mandate_id"] = "MND-RES-OLDROOT1"
    iss = {i.issuer_id: i for i in h.env.repo.list_issuers()}["ISS-RESIDENCY-AUTH"]
    root = sign_mandate(DigitalMandate.model_validate(body), h.keys.private_key(iss.key_id), iss.key_id, body["issued_at"])
    child = h.env.delegation.build_child(root, "insurance_eligibility_check", "AGT-INS-001",
                                         {"insurance.verify_case_eligibility"}, f.case.case_id, now - timedelta(minutes=40))
    child = h.env.delegation._sign(child.model_copy(update={"expires_at": now + timedelta(minutes=20)}))
    store = {root.mandate_id: root, child.mandate_id: child}
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child.mandate_id, mandate_source=lambda m: store.get(m))
    assert out.decision.reason_codes == [R.DENY_PARENT_MANDATE_EXPIRED]


def test_g_revoked_parent_denies_dependent_authority(f):
    child = f.setup()
    revoked = revoke_mandate(f.env, f.root, "test")
    assert set(revoked) == {f.root, child}  # cascade recorded
    before = f.snapshot()
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child)
    assert out.decision.reason_codes == [R.DENY_PARENT_MANDATE_REVOKED] and not out.executed
    assert f.snapshot() == before


def test_g_ancestor_check_independent_of_cascade(f):
    """Even without the cascade record, the chain verifier rejects a child whose parent is revoked."""
    child = f.setup()
    revoke_mandate(f.env, f.root, "no cascade", cascade=False)
    assert not f.env.mandates.is_revoked(child)
    assert f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child).decision.reason_codes == [R.DENY_PARENT_MANDATE_REVOKED]


def test_h_child_cannot_be_reused_for_another_case(h):
    a, b = DFlow(h), DFlow(h)
    child_a = a.setup()
    b.setup()
    out = a.exe("AGT-INS-001", INS.verify(b.case), case=b.case, mandate_id=child_a)
    assert {R.DENY_DELEGATION_CASE_MISMATCH, R.DENY_CASE_AGENT_NOT_ASSIGNED} <= set(out.decision.reason_codes)
    assert b.state() is S.VERIFYING


def test_i_cycle_and_depth_denied(f):
    child = f.setup()
    out = f.exe("AGT-INS-001", commission_call(f.case, receiver="AGT-RES-001"), mandate_id=child)
    assert {R.DENY_DELEGATION_CYCLE, R.DENY_DELEGATION_DEPTH_EXCEEDED} <= set(out.decision.reason_codes)


def test_i_chain_cycle_in_storage_detected(f):
    child_id = f.setup()
    child = f.env.mandates.get(child_id)
    looped_root = f.env.mandates.get(f.root).model_copy(update={"parent_mandate_id": child_id})
    out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child_id,
                mandate_source=lambda m: looped_root if m == f.root else (child if m == child_id else None))
    assert R.DENY_DELEGATION_CYCLE in out.decision.reason_codes


def test_client_supplied_delegation_chain_never_trusted(f):
    child = f.setup()
    signed = f.sign("AGT-INS-001", INS.verify(f.case), mandate_id=child)
    req = ActionRequest.model_validate({**signed.request.model_dump(), "delegation_chain": [
        {"from_agent_id": "AGT-RES-001", "to_agent_id": "AGT-INS-001", "mandate_id": f.root}]})
    out = f.env.gateway.execute(sign_request(req, f.h.keys.private_key("KEY-AGT-INS-001"), "KEY-AGT-INS-001"))
    assert R.DENY_DELEGATION_CHAIN_INVALID in out.decision.reason_codes


def test_replayed_delegated_request_denied(f):
    child = f.setup()
    signed = f.sign("AGT-INS-001", INS.verify(f.case), mandate_id=child)
    assert f.env.gateway.execute(signed).executed
    again = f.env.gateway.execute(signed)
    assert R.DENY_REPLAYED_REQUEST in again.decision.reason_codes and not again.executed


def test_replayed_commission_does_not_issue_twice(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    signed = f.sign("AGT-RES-001", commission_call(f.case))
    assert f.env.gateway.execute(signed).executed
    assert f.env.gateway.execute(signed).decision.reason_codes == [R.DENY_REPLAYED_REQUEST]
    assert len(f.env.mandates.delegations()) == 1


# --- revocation and continuity ------------------------------------------------------------

def test_j_case_revocation_is_selective(h):
    a, b = DFlow(h), DFlow(h)
    ka, kb = a.setup(), b.setup()
    revoked = revoke_case_authority(h.env, a.case.case_id, "test")
    assert set(revoked) == {*a.case.mandate_refs.values(), ka}
    assert h.env.cases.get(a.case.case_id).authority_revoked
    denied = a.exe("AGT-INS-001", INS.verify(a.case), mandate_id=ka)
    assert not denied.decision.allowed
    ok = b.exe("AGT-INS-001", INS.verify(b.case), mandate_id=kb)
    assert ok.decision.allowed and ok.executed
    assert h.env.repo.get_agent("AGT-INS-001").status == "active"


def test_routine_denial_never_revokes_agent(f):
    child = f.setup()
    for _ in range(3):
        f.exe("AGT-INS-001", INS.verify(f.case, "C-1003"), mandate_id=child)
    assert f.env.repo.get_agent("AGT-INS-001").status == "active"
    assert not f.env.mandates.is_revoked(child)
    assert f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=child).executed


def test_agent_wide_revocation_is_separate(h):
    a = DFlow(h)
    child = a.setup()
    revoke_agent(h.env, "AGT-INS-001", "compromised key suspected")
    assert a.exe("AGT-INS-001", INS.verify(a.case), mandate_id=child).decision.reason_codes == [R.DENY_AGENT_NOT_ACTIVE]
    assert not h.env.mandates.is_revoked(child)  # mandates untouched; the agent is what was revoked
    assert a.exe("AGT-PAY-001", PAY.collect(a.case)).decision.reason_codes  # other agents keep working (state-dependent)


def test_revocation_persists_after_restart(tmp_path):
    from tests.conftest import DeterministicKeystore, FrozenClock
    from app.core.config import Settings
    from app.services.bootstrap import bootstrap
    db = str(tmp_path / "wakala.db")
    keys, clock = DeterministicKeystore(), FrozenClock()
    env = bootstrap(Settings(db_path=db), keystore=keys, clock=clock)

    class H:  # minimal harness
        pass
    h = H(); h.env, h.keys, h.clock = env, keys, clock
    a, b = DFlow(h), DFlow(h)
    ka, kb = a.setup(), b.setup()
    revoke_mandate(env, a.root, "persist test")
    revoke_agent(env, "AGT-PAY-001", "persist test")
    case_ids = (a.case.case_id, b.case.case_id)
    env.close()

    env2 = bootstrap(Settings(db_path=db), keystore=keys, clock=clock)  # restart: registry reseeded
    h.env = env2
    a.env = b.env = env2
    a.r = b.r = WorkflowRunner(env2, "after-restart")
    a.case, b.case = env2.cases.get(case_ids[0]), env2.cases.get(case_ids[1])
    assert env2.mandates.is_revoked(a.root) and env2.mandates.is_revoked(ka)
    assert env2.repo.get_agent("AGT-PAY-001").status == "revoked"
    assert a.exe("AGT-INS-001", INS.verify(a.case), mandate_id=ka).decision.reason_codes == [R.DENY_PARENT_MANDATE_REVOKED]
    assert b.exe("AGT-INS-001", INS.verify(b.case), mandate_id=kb).executed
    env2.close()


# --- pure function properties ---------------------------------------------------------------

def test_non_expansion_pure_checks(f):
    child = f.env.mandates.get(f.setup())
    parent = f.env.mandates.get(f.root)
    issuers = {i.issuer_id: i for i in f.env.repo.list_issuers()}
    assert check_non_expansion(child, parent, issuers) == []
    for upd, code in [
        ({"delegated_task": "renewal_fee_collection"}, R.DENY_DELEGATION_NOT_PERMITTED),
        ({"delegation_depth": 2}, R.DENY_DELEGATION_CHAIN_INVALID),
        ({"delegated_by_agent": "AGT-PAY-001"}, R.DENY_DELEGATION_CHAIN_INVALID),
        ({"case_id": "CASE-00000000"}, R.DENY_DELEGATION_CASE_MISMATCH),
        ({"commissionable_tasks": ["insurance_eligibility_check", "renewal_fee_collection"]}, R.DENY_DELEGATION_EXPANDS_AUTHORITY),
        ({"amount_limit": {"amount": "1.00", "currency": "AED"}, "recipient_allowlist": ["SYNTH-GOV-TREASURY-0001"]},
         R.DENY_DELEGATION_EXPANDS_AUTHORITY),
    ]:
        bad = DigitalMandate.model_validate({**child.model_dump(), **upd}) if "amount_limit" in upd else child.model_copy(update=upd)
        assert code in check_non_expansion(bad, parent, issuers), upd


def test_receiving_entity_policy_enforced(f):
    """If the receiving entity's own authority no longer covers the operation, the child is not usable."""
    child = f.env.mandates.get(f.setup())
    parent = f.env.mandates.get(f.root)
    issuers = {i.issuer_id: i for i in f.env.repo.list_issuers()}
    ins = issuers["ISS-INSURANCE-REG"]
    issuers["ISS-INSURANCE-REG"] = ins.model_copy(update={"authority": ins.authority.model_copy(update={"tools": ["insurance.verify_eligibility"]})})
    assert R.DENY_DELEGATION_NOT_PERMITTED in check_non_expansion(child, parent, issuers)


def test_task_catalog_is_immutable():
    with pytest.raises(TypeError):
        TASK_CATALOG["anything"] = None  # type: ignore[index]


def test_phase1_signatures_unchanged_by_phase3_fields(h):
    """Pre-Phase-3 mandates (no chain fields) must keep byte-identical canonical bodies."""
    m = h.env.mandates.get(h.mandate("AGT-PAY-001"))
    assert b"delegation_depth" not in canonical_mandate_bytes(m) and b"case_id" not in canonical_mandate_bytes(m)


def test_delegation_issuance_records_measured_latency(f):
    f.exe("AGT-RES-001", RES.register(f.case))
    f.exe("AGT-RES-001", RES.check_eligibility(f.case))
    out = f.exe("AGT-RES-001", commission_call(f.case))
    assert out.decision.decision_latency_ms > 0
    child_out = f.exe("AGT-INS-001", INS.verify(f.case), mandate_id=str(out.result["child_mandate_id"]))
    assert child_out.decision.decision_latency_ms > 0  # measured by perf_counter, not asserted against a target


def test_verify_chain_direct_mandate_is_empty(f):
    root = f.env.mandates.get(f.root)
    snap = f.env.gateway.policy_snapshot(f.h.clock())
    assert verify_chain(root, (), snap["issuers"], snap["issuer_public_keys"], f.h.clock(), frozenset()) == []
