"""Phase 1: protected execution boundary."""

from __future__ import annotations

import pytest

from app.core.audit import AuditUnavailableError
from app.core.authorization import PolicyEvaluation
from app.core.execution import ToolRegistry, ToolSpec
from app.core.execution.gateway import AuthorizationBindingError, ExecutionGrant, ToolDispatcher
from app.core.execution.tools import CitizenLookupParams, build_default_tool_registry
from app.core.identity import request_digest
from app.schemas import ReasonCode as R, SignedActionRequest
from tests.conftest import make_harness


@pytest.fixture()
def spy():
    """Harness whose read tool records every invocation."""
    calls: list[str] = []

    def handler(params: CitizenLookupParams) -> dict:
        calls.append(params.citizen_ref)
        return {"citizen_ref": params.citizen_ref, "ok": True}

    tools = ToolRegistry([
        ToolSpec("residency.read_status", "residency_renewal", "citizen_record", "read", "citizen_ref",
                 CitizenLookupParams, False, "spy", handler),
        *[s for n, s in build_default_tool_registry(lambda _: None, lambda _: None).specs.items() if n != "residency.read_status"],
    ])
    harness = make_harness(tools=tools)
    harness.calls = calls
    yield harness
    harness.env.close()


def test_allowed_action_invokes_registered_tool(spy):
    out = spy.env.gateway.execute(spy.residency_read())
    assert out.decision.allowed and out.executed and out.status == "executed"
    assert spy.calls == ["C-1001"]
    assert out.result == {"citizen_ref": "C-1001", "ok": True}


@pytest.mark.parametrize("make", [
    lambda h: h.residency_read("C-1003"),                         # out of scope
    lambda h: h.residency_read(private_key=h.keys.private_key("KEY-AGT-INS-001")),  # bad signature
    lambda h: h.residency_read(mandate_id="MND-DOES-NOT-EXIST"),  # no mandate
    lambda h: h.signed("AGT-RES-001", tool_name="residency.read_status",
                       parameters={"citizen_ref": "C-1001", "extra": 1}, target_resource="C-1001"),
])
def test_denied_action_never_invokes_tool(spy, make):
    out = spy.env.gateway.execute(make(spy))
    assert not out.decision.allowed and not out.executed and out.status == "denied"
    assert spy.calls == []


def test_replayed_execution_runs_tool_once(spy):
    signed = spy.residency_read()
    assert spy.env.gateway.execute(signed).executed
    assert not spy.env.gateway.execute(signed).executed
    assert spy.calls == ["C-1001"]


def test_authorize_endpoint_never_executes(spy):
    assert spy.env.gateway.authorize(spy.residency_read()).decision.allowed
    assert spy.calls == []


def test_authorized_request_cannot_then_be_executed(spy):
    """A decision is not a reusable token: the nonce is consumed by /authorize."""
    signed = spy.residency_read()
    assert spy.env.gateway.authorize(signed).decision.allowed
    out = spy.env.gateway.execute(signed)
    assert out.decision.reason_codes == [R.DENY_REPLAYED_REQUEST] and spy.calls == []


def test_unknown_tool_cannot_be_dispatched(spy):
    signed = spy.signed("AGT-RES-001", tool_name="os.system", parameters={"citizen_ref": "C-1001"}, target_resource="C-1001")
    out = spy.env.gateway.execute(signed)
    assert R.DENY_UNKNOWN_TOOL in out.decision.reason_codes and not out.executed
    dispatcher = ToolDispatcher(spy.env.tools)
    with pytest.raises(AuthorizationBindingError):
        dispatcher.dispatch(ExecutionGrant("DEC-X", request_digest(signed.request), "os.system"), signed.request)


def test_grant_cannot_be_reused_with_modified_parameters(spy):
    signed = spy.residency_read()
    grant = ExecutionGrant("DEC-TEST", request_digest(signed.request), signed.request.tool_name)
    modified = signed.request.model_copy(update={"parameters": {"citizen_ref": "C-1003"}, "target_resource": "C-1003"})
    with pytest.raises(AuthorizationBindingError):
        ToolDispatcher(spy.env.tools).dispatch(grant, modified)
    assert spy.calls == []


def test_modified_parameters_after_signing_denied_end_to_end(spy):
    signed = spy.residency_read()
    modified = signed.request.model_copy(update={"parameters": {"citizen_ref": "C-1003"}, "target_resource": "C-1003"})
    out = spy.env.gateway.execute(SignedActionRequest(request=modified, signature=signed.signature))
    assert out.decision.reason_codes == [R.DENY_REQUEST_SIGNATURE_INVALID] and spy.calls == []


def test_policy_failure_does_not_execute(spy, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("engine crashed")
    monkeypatch.setattr(spy.env.gateway, "_policy", broken)
    out = spy.env.gateway.execute(spy.residency_read())
    assert out.decision.reason_codes == [R.DENY_POLICY_EVALUATION_ERROR]
    assert not out.executed and spy.calls == []


def test_check_exception_inside_engine_denies(spy, monkeypatch):
    import app.core.authorization.engine as eng
    monkeypatch.setattr(eng, "check_action_constraints", lambda *a: 1 / 0)
    out = spy.env.gateway.execute(spy.residency_read())
    assert out.decision.reason_codes == [R.DENY_POLICY_EVALUATION_ERROR] and spy.calls == []


def test_policy_returning_inconsistent_allow_is_not_trusted(spy, monkeypatch):
    monkeypatch.setattr(spy.env.gateway, "_policy", lambda *a: PolicyEvaluation(True, (R.DENY_DEFAULT,), ()))
    out = spy.env.gateway.execute(spy.residency_read())
    assert not out.decision.allowed and spy.calls == []


def test_audit_failure_blocks_execution(spy, monkeypatch):
    def fail(event):
        raise AuditUnavailableError("disk full")
    monkeypatch.setattr(spy.env.audit, "append", fail)
    with pytest.raises(AuditUnavailableError):
        spy.env.gateway.execute(spy.residency_read())
    assert spy.calls == []


def test_tool_without_handler_is_authorized_but_not_executed(h):
    out = h.env.gateway.execute(h.payment())
    assert out.decision.allowed and not out.executed and out.status == "no_handler_registered"


def test_default_read_tool_returns_minimal_fields(h):
    out = h.env.gateway.execute(h.residency_read())
    assert out.executed
    assert set(out.result) == {"citizen_ref", "residency_status", "permit_expiry", "renewal_eligible", "synthetic"}
    assert "account_ref" not in out.result and "full_name" not in out.result
