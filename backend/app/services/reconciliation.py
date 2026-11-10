"""Idempotent audit reconciliation (startup recovery + dev CLI).

Authorization (decision event) and execution (outcome event) are separate
records. For local SQLite services the outcome is written in the same
transaction as the service change, so they cannot diverge. A gap remains
possible in two cases:

1. the process stops, or the outcome write fails, after the decision was
   recorded but before/while the service transaction runs (→ rolled back);
2. a future non-transactional handler commits and then cannot record.

``reconcile_outcomes`` finds allowed decisions for audited tools that have no
outcome event, inspects the service-side records that carry the decision ID,
and appends exactly one informational reconciliation event per decision:

* ``authorized_not_executed``      — no service effect exists
* ``committed_outcome_reconstructed`` — a service effect exists (case 2)

Running it again appends nothing new.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.schemas import AuditEvent
from app.services.bootstrap import WakalaEnvironment


@dataclass(frozen=True)
class ReconciliationResult:
    examined: int
    recorded: list[dict[str, str]]


def _effects_for(env: WakalaEnvironment, decision_id: str, decision_event_id: str) -> list[str]:
    effects = []
    if env.db.query("SELECT 1 FROM payment_ledger WHERE decision_id = ?", (decision_id,)):
        effects.append("payment_ledger")
    if env.db.query("SELECT 1 FROM residency_renewals WHERE decision_id = ?", (decision_id,)):
        effects.append("residency_renewals")
    if env.db.query("SELECT 1 FROM delegations WHERE decision_id = ?", (decision_id,)):
        effects.append("delegations")
    rows = env.db.query("SELECT payload FROM renewal_cases WHERE payload LIKE ?", (f"%{decision_event_id}%",))
    if rows:
        effects.append("renewal_cases")
    return effects


def reconcile_outcomes(env: WakalaEnvironment) -> ReconciliationResult:
    audited = [name for name, spec in env.tools.specs.items() if spec.audit_execution]
    if not audited:
        return ReconciliationResult(0, [])
    marks = ",".join("?" for _ in audited)
    decisions = env.db.query(
        f"SELECT payload FROM audit_events WHERE json_extract(payload, '$.decision') = 'allowed' "
        f"AND json_extract(payload, '$.action') IN ({marks}) ORDER BY seq", tuple(audited))
    covered = {
        r["ref"] for r in env.db.query(
            "SELECT json_extract(payload, '$.evidence_metadata.decision_event') AS ref FROM audit_events "
            "WHERE json_extract(payload, '$.decision') = 'informational' "
            "AND json_extract(payload, '$.evidence_metadata.decision_event') IS NOT NULL")
    }
    recorded = []
    for row in decisions:
        decision = AuditEvent.model_validate_json(row["payload"])
        if decision.event_id in covered or decision.decision_id is None:
            continue
        effects = _effects_for(env, decision.decision_id, decision.event_id)
        status = "committed_outcome_reconstructed" if effects else "authorized_not_executed"
        env.audit.append(AuditEvent(
            event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor="WAKALA-GATEWAY",
            action=f"{decision.action}:reconciliation"[:120], decision="informational", request_id=decision.request_id,
            related_mandate=decision.related_mandate, decision_id=decision.decision_id,
            evidence_metadata={"decision_event": decision.event_id, "execution_status": status,
                               "observed_effects": ",".join(effects) or None,
                               "case_id": decision.evidence_metadata.get("case_id"), "origin": "reconciliation"},
        ))
        recorded.append({"decision_event": decision.event_id, "status": status})
    return ReconciliationResult(len(decisions), recorded)
