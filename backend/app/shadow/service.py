"""Shadow Mode — a WATCH-ONLY evaluator for a government entity's adoption path.

What it is
* ``ShadowEvaluator`` applies the SAME authentication (``app.core.identity.authenticate``) and the SAME policy
  function (``app.core.authorization.authorize``) the gateway uses, to copies of requests a source system already
  processed, and records what WAKALA *would* have decided.
* It is not a mode of ``Gateway.execute()``: it holds no tool registry dispatcher, writes no audit events, records
  no nonces in the shared replay store (it keeps its own in-memory set to detect replays among the copied events),
  triggers no monitoring, approvals or containment, and never calls a protected service. The source system's
  decision is reported next to WAKALA's; it is never changed.
* "Would have blocked" is a COUNTERFACTUAL policy result on copied events, not a prevented attack.

Demo: an isolated synthetic "mirror" environment is provisioned (cases and mandates reach the needed stage through
real signed requests — that is provisioning, done before observation starts). The copied event stream is evaluated
in shadow. Then, in an ENTIRELY SEPARATE fresh environment, the same event specifications are run with active
enforcement through ``Gateway.execute()`` and compared with the shadow prediction.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES
from app.core.authorization import PolicyContext, authorize
from app.core.identity import authenticate
from app.evaluation.environment import isolated_env
from app.evaluation.harness import WakalaHarness
from app.portal.explain import explain
from app.schemas import ReasonCode, SignedActionRequest

SECURITY_CODES = {"DENY_SCOPE_VIOLATION", "DENY_CASE_SCOPE_VIOLATION", "DENY_AMOUNT_EXCEEDS_LIMIT", "DENY_RECIPIENT_NOT_ALLOWLISTED",
                  "DENY_TOOL_EXPLICITLY_DENIED", "DENY_TOOL_NOT_PERMITTED", "DENY_REQUEST_SIGNATURE_INVALID", "DENY_REPLAYED_REQUEST",
                  "DENY_IDENTITY_UNVERIFIED", "DENY_DELEGATION_EXPANDS_AUTHORITY", "DENY_DELEGATION_NOT_PERMITTED"}
OPERATIONAL_CODES = {"DENY_MANDATE_EXPIRED", "DENY_PARENT_MANDATE_EXPIRED", "DENY_CASE_EXPIRED", "DENY_CASE_STATE_INVALID",
                     "DENY_REQUEST_STALE"}


class ShadowEvaluator:
    """Read-only policy evaluation. Inputs: the environment's stored mandates, cases, keys and revocation/suspension
    lists (read), and the copied signed request. Output: the decision WAKALA would make. No side effects."""

    def __init__(self, env: Any) -> None:
        self._repo, self._mandates, self._cases = env.repo, env.mandates, env.cases
        self._tools = env.tools.specs
        self._snapshot = env.gateway.policy_snapshot          # read-only lists
        self._ancestors = env.gateway.resolve_ancestors       # read-only chain lookup
        self._skew = getattr(env.gateway, "_skew", timedelta(minutes=5))
        self._seen_nonces: set[tuple[str, str]] = set()      # the shadow's OWN replay memory

    def evaluate(self, signed: SignedActionRequest, now: datetime) -> dict[str, Any]:
        req = signed.request
        auth = authenticate(signed, self._repo.get_agent_key)
        principal = auth.principal
        replayed = False
        if principal is not None:
            key = (principal.agent_id, req.nonce)
            replayed = key in self._seen_nonces
            self._seen_nonces.add(key)
        mandate = self._mandates.get(req.mandate_id) if principal is not None else None
        case = self._cases.get(req.case_id) if principal is not None and req.case_id else None
        ancestors, chain_error = self._ancestors(mandate, None) if mandate is not None else ((), None)
        ctx = PolicyContext(case=case, mandate_ancestors=ancestors, chain_resolution_error=chain_error, now=now,
                            passport=self._repo.get_agent(req.agent_id) if principal is not None else None, tools=self._tools,
                            max_request_skew=self._skew, replay_detected=replayed, authentication_failure=auth.failure,
                            mandate_malformed=False, approved_reauthorization=False, **self._snapshot(now))
        ev = authorize(req, principal, mandate, ctx)
        allowed = ev.allowed is True and ev.reason_codes == (ReasonCode.ALLOW_WITHIN_MANDATE,)
        codes = [c.value for c in ev.reason_codes if c is not ReasonCode.ALLOW_WITHIN_MANDATE] or ([] if allowed else ["DENY_DEFAULT"])
        return {"would_allow": allowed, "reason_codes": codes or ["ALLOW_WITHIN_MANDATE"]}


@dataclass(frozen=True)
class EventSpec:
    key: str
    description: str
    agent: str
    stage: str
    intent: str              # synthetic ground truth: "legitimate" | "unauthorized"
    source_decision: str     # what the source (legacy role-based) system decided: "allowed" | "denied"
    shift: timedelta = timedelta(0)


EVENTS: tuple[EventSpec, ...] = (
    EventSpec("eligibility", "Residency Agent checks eligibility for the applicant", "AGT-RES-001", "REGISTERED", "legitimate", "allowed"),
    EventSpec("commission", "Residency Agent delegates the insurance check", "AGT-RES-001", "ELIGIBLE", "legitimate", "allowed"),
    EventSpec("insurance_own", "Insurance Agent checks the applicant's insurance", "AGT-INS-001", "DELEGATED", "legitimate", "allowed"),
    EventSpec("fee_500", "Payment Agent collects AED 500 to the treasury", "AGT-PAY-001", "AWAITING_PAYMENT", "legitimate", "allowed"),
    EventSpec("complete", "Residency Agent completes the renewal", "AGT-RES-001", "READY", "legitimate", "allowed"),
    EventSpec("complete_late", "Residency Agent completes a renewal 3 h after the case opened (batch backlog)", "AGT-RES-001", "READY",
              "legitimate", "allowed", timedelta(hours=3)),
    EventSpec("insurance_other", "Insurance Agent checks ANOTHER citizen's insurance", "AGT-INS-001", "DELEGATED", "unauthorized", "allowed"),
    EventSpec("fee_50000", "Payment Agent sends AED 50,000 to an external account", "AGT-PAY-001", "AWAITING_PAYMENT", "unauthorized", "allowed"),
    EventSpec("fee_replay", "The same AED 500 payment request submitted twice", "AGT-PAY-001", "AWAITING_PAYMENT", "unauthorized", "allowed"),
    EventSpec("residency_pays", "Residency Agent calls the payment tool", "AGT-RES-001", "AWAITING_PAYMENT", "unauthorized", "denied"),
)


def _build(h: WakalaHarness, spec: EventSpec, citizen: str) -> list[SignedActionRequest]:
    from app.workflow.delegation_scenarios import commission_call
    case, child = h.stage(citizen, spec.stage)
    ins_m = h._ins_mandate(case, child)
    s = h._sign
    if spec.key == "eligibility":
        return [s("AGT-RES-001", RES.check_eligibility(case), case)]
    if spec.key == "commission":
        return [s("AGT-RES-001", commission_call(case), case)]
    if spec.key == "insurance_own":
        return [s("AGT-INS-001", INS.verify(case), case, mandate_id=ins_m)]
    if spec.key == "insurance_other":
        return [s("AGT-INS-001", INS.verify(case, "C-1003"), case, mandate_id=ins_m)]
    if spec.key == "fee_500":
        return [s("AGT-PAY-001", PAY.collect(case), case)]
    if spec.key == "fee_50000":
        return [s("AGT-PAY-001", PAY.collect(case, "50000.00", "SYNTH-EXT-UNVERIFIED-9999"), case)]
    if spec.key == "fee_replay":
        one = s("AGT-PAY-001", PAY.collect(case), case)
        return [one, one]
    if spec.key == "residency_pays":
        return [s("AGT-RES-001", PAY.collect(case), case)]
    return [s("AGT-RES-001", RES.complete(case), case)]   # complete / complete_late


def _classify(spec: EventSpec, would_allow: bool, codes: list[str]) -> str:
    src_allowed = spec.source_decision == "allowed"
    if would_allow == src_allowed:
        return "agreement"
    if src_allowed and not would_allow:
        if spec.intent == "legitimate" or set(codes) & OPERATIONAL_CODES and not set(codes) & SECURITY_CODES:
            return "false_denial_candidate"
        return "would_block"
    return "would_allow_where_source_denied"


def run_shadow(citizen: str = "C-1001") -> dict[str, Any]:
    t0 = time.perf_counter()
    with isolated_env("memory") as (env, clock, keys):
        h = WakalaHarness(env, clock, keys, "C")
        copied: list[tuple[EventSpec, SignedActionRequest, datetime]] = []
        for spec in EVENTS:  # provisioning (stage setup) happens here, BEFORE observation
            reqs = _build(h, spec, citizen)
            at = clock() + spec.shift
            copied += [(spec, r, at) for r in reqs]
        before = {t: env.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
                  for t in ("audit_events", "payment_ledger", "residency_renewals", "request_nonces", "incidents", "pending_approvals")}
        cases_before = {c.case_id: (c.state.value, tuple(c.completed_prerequisites)) for c in env.cases.list()}
        shadow = ShadowEvaluator(env)
        rows = []
        for i, (spec, signed, at) in enumerate(copied, 1):
            r = shadow.evaluate(signed, at)
            req = signed.request
            rows.append({
                "n": i, "event": spec.key, "description": spec.description, "agent_id": req.agent_id, "tool_name": req.tool_name,
                "observed_at": at.isoformat(), "source_decision": spec.source_decision, "synthetic_intent": spec.intent,
                "wakala_would": "allow" if r["would_allow"] else "deny", "reason_codes": r["reason_codes"],
                "classification": _classify(spec, r["would_allow"], r["reason_codes"]),
                "plain_english": explain({"allowed": r["would_allow"], "reason_codes": r["reason_codes"]}, agent_id=req.agent_id,
                                         tool_name=req.tool_name, parameters=dict(req.parameters), case_citizen=citizen,
                                         citizen_name="Mariam").replace("Blocked:", "Would block:").replace("Allowed:", "Would allow:"),
                "request_digest": hashlib.sha256(json.dumps(req.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()[:16],
            })
        after = {t: env.db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in before}
        cases_after = {c.case_id: (c.state.value, tuple(c.completed_prerequisites)) for c in env.cases.list()}
    untouched = before == after and cases_before == cases_after
    report = _report(rows)
    return {"shadow_run_id": f"SHD-{secrets.token_hex(4).upper()}", "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "WATCH-ONLY (counterfactual)", "events": rows, "report": report,
            "isolation_check": {"source_state_unchanged_during_observation": untouched, "counts_before": before, "counts_after": after},
            "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            "note": "'Would block' is a counterfactual policy result on copied events — nothing was prevented, because nothing "
                    "was executed by WAKALA in shadow mode. The source system's own decisions are shown unchanged."}


def _report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by = lambda c: [r for r in rows if r["classification"] == c]  # noqa: E731
    fd = by("false_denial_candidate")
    conflicts = []
    for r in fd:
        if set(r["reason_codes"]) & {"DENY_MANDATE_EXPIRED", "DENY_PARENT_MANDATE_EXPIRED"}:
            conflicts.append({"event": r["event"], "conflict": "Case mandate lifetime (2 h) is shorter than the source workflow's "
                                                              "observed completion time.", "codes": r["reason_codes"]})
        elif "DENY_CASE_STATE_INVALID" in r["reason_codes"]:
            conflicts.append({"event": r["event"], "conflict": "Step order in the source system differs from the case workflow.",
                              "codes": r["reason_codes"]})
    steps = ["Review every false-denial candidate with the service owner before enforcing."]
    if any("lifetime" in c["conflict"] for c in conflicts):
        steps.append("Decide whether to lengthen the case-mandate lifetime for batch backlogs or require re-issuance; do not "
                     "simply disable expiry.")
    if by("would_block"):
        steps.append("Investigate the would-block events in the source system: they were executed there.")
    steps.append("Re-run shadow mode on fresh copied traffic after tuning, then enforce in a separate test environment first.")
    return {"events_observed": len(rows), "would_allow": sum(1 for r in rows if r["wakala_would"] == "allow"),
            "would_deny": sum(1 for r in rows if r["wakala_would"] == "deny"), "agreements": len(by("agreement")),
            "differences": len(rows) - len(by("agreement")), "would_block_source_allowed": len(by("would_block")),
            "false_denial_candidates": [r["event"] for r in fd], "would_allow_where_source_denied": [r["event"] for r in by("would_allow_where_source_denied")],
            "policy_conflicts": conflicts, "next_steps": steps}


def run_enforcement(citizen: str = "C-1001") -> dict[str, Any]:
    """Phase 2 of the demo: the same event specifications with ACTIVE enforcement, in a separate fresh environment."""
    rows = []
    with isolated_env("memory") as (env, clock, keys):
        h = WakalaHarness(env, clock, keys, "C")
        for spec in EVENTS:
            reqs = _build(h, spec, citizen)
            for signed in reqs:
                with clock.shifted(spec.shift):
                    out = env.gateway.execute(signed, origin="shadow-demo:enforce")
                rows.append({"event": spec.key, "allowed": out.decision.allowed, "executed": out.executed, "status": out.status,
                             "reason_codes": [c.value for c in out.decision.reason_codes]})
        ledger = env.db.query("SELECT COUNT(*) AS n FROM payment_ledger")[0]["n"]
        chain = env.audit.verify().valid
    return {"environment": "separate fresh synthetic test environment (not the shadow mirror, not the live app)",
            "events": rows, "ledger_rows": ledger, "audit_chain_valid": chain}


def run_demo() -> dict[str, Any]:
    shadow = run_shadow()
    enforce = run_enforcement()
    pairs = list(zip(shadow["events"], enforce["events"], strict=True))
    agree = [s["event"] for s, e in pairs if (s["wakala_would"] == "allow") == e["allowed"]]
    return {"shadow": shadow, "enforcement": enforce,
            "prediction_agreement": {"matched": len(agree), "total": len(pairs),
                                     "mismatches": [{"event": s["event"], "shadow": s["wakala_would"], "enforced_allowed": e["allowed"],
                                                     "enforced_status": e["status"]} for s, e in pairs
                                                    if (s["wakala_would"] == "allow") != e["allowed"]]}}
