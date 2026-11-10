"""Authority-chain graph built ONLY from stored records.

Nodes: the case, issuers that signed its mandates, every root and delegated
child mandate (with live verification of the whole chain), holding agents,
and denied delegation attempts found in the audit trail. Edges come from
mandate fields (issuer_id, agent_id, parent_mandate_id) and audit records —
nothing is hard-coded.
"""

from __future__ import annotations

from typing import Any

from app.core.delegation import verify_chain
from app.core.mandates import verify_mandate
from app.schemas import AuditEvent, DigitalMandate
from app.services.bootstrap import WakalaEnvironment


def _mandate_events(env: WakalaEnvironment, mandate_id: str, limit: int = 12) -> list[AuditEvent]:
    rows = env.db.query("SELECT payload FROM audit_events WHERE json_extract(payload, '$.related_mandate') = ? "
                        "ORDER BY seq DESC LIMIT ?", (mandate_id, limit))
    return [AuditEvent.model_validate_json(r["payload"]) for r in rows]


def _counts(env: WakalaEnvironment, mandate_id: str) -> dict[str, int]:
    rows = env.db.query("SELECT json_extract(payload, '$.decision') AS d, COUNT(*) AS n FROM audit_events "
                        "WHERE json_extract(payload, '$.related_mandate') = ? GROUP BY d", (mandate_id,))
    return {str(r["d"]): int(r["n"]) for r in rows}


def build_authority_graph(env: WakalaEnvironment, case_id: str) -> dict[str, Any] | None:
    case = env.cases.get(case_id)
    if case is None:
        return None
    now = env.clock()
    snap = env.gateway.policy_snapshot(now)
    issuers = snap["issuers"]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_issuers: set[str] = set()
    seen_agents: set[str] = set()

    nodes.append({"id": f"case:{case.case_id}", "kind": "case", "label": case.case_id,
                  "sublabel": f"{case.citizen_ref} · {case.state.value}",
                  "status": "revoked" if case.authority_revoked else "active",
                  "data": {"case": case.model_dump(mode="json", exclude={"history"}),
                           "service_owner": case.service_owner, "authority_model": case.authority_model}})

    mandate_ids = list(dict.fromkeys([*case.mandate_refs.values(), *(str(d["child_mandate_id"]) for d in env.mandates.delegations(case_id))]))
    delegation_rows = {str(d["child_mandate_id"]): d for d in env.mandates.delegations(case_id)}
    for mid in mandate_ids:
        try:
            m: DigitalMandate | None = env.mandates.get(mid)
        except Exception:  # malformed row: show it as invalid, never hide it
            m = None
        if m is None:
            nodes.append({"id": f"mandate:{mid}", "kind": "mandate", "label": mid, "sublabel": "unreadable",
                          "status": "invalid", "data": {}})
            continue
        v = verify_mandate(m, issuers, snap["issuer_public_keys"], now, snap["revoked_mandate_ids"])
        ancestors, chain_err = env.gateway.resolve_ancestors(m)
        chain_codes = verify_chain(m, ancestors, issuers, snap["issuer_public_keys"], now,
                                   snap["revoked_mandate_ids"], chain_err) if m.parent_mandate_id else []
        status = v.effective_status if not chain_codes else (
            "revoked" if any("REVOKED" in c.value for c in chain_codes) else "invalid")
        suspended = snap["suspended_mandate_ids"]
        if status == "active" and (mid in suspended or any(a.mandate_id in suspended for a in ancestors)):
            status = "suspended"  # reversible officer/assurance hold; the gateway denies while it lasts
        counts = _counts(env, mid)
        nodes.append({
            "id": f"mandate:{mid}", "kind": "child_mandate" if m.parent_mandate_id else "mandate", "label": mid,
            "sublabel": f"{m.agent_id} · depth {m.delegation_depth}", "status": status,
            "data": {
                "mandate": m.model_dump(mode="json"),
                "verification": {"valid": v.valid and not chain_codes, "effective_status": status,
                                 "reason_codes": [c.value for c in (*v.integrity_codes, *v.lifecycle_codes, *chain_codes)],
                                 "chain_length": len(ancestors) + 1, "checked_at": now.isoformat()},
                "effective_permissions": m.allowed_tools, "commissionable_tasks": m.commissionable_tasks,
                "scope": m.citizen_or_request_scope.model_dump(), "resources": [r.model_dump() for r in m.resource_constraints],
                "expires_at": m.expires_at.isoformat(), "decision_counts": counts,
                "delegation_record": {k: str(val) for k, val in delegation_rows[mid].items()} if mid in delegation_rows else None,
                "audit_events": [e.model_dump(mode="json") for e in _mandate_events(env, mid)],
            },
        })
        if m.issuer_id not in seen_issuers:
            seen_issuers.add(m.issuer_id)
            iss = issuers.get(m.issuer_id)
            key = env.repo.get_key(iss.key_id) if iss else None
            nodes.append({"id": f"issuer:{m.issuer_id}", "kind": "issuer", "label": m.issuer_id,
                          "sublabel": iss.name if iss else "untrusted", "status": "active" if iss and iss.status == "active" else "invalid",
                          "data": {"issuer": iss.model_dump(mode="json") if iss else None,
                                   "key_fingerprint": key.fingerprint if key else None}})
        edges.append({"id": f"sig:{m.issuer_id}:{mid}", "source": f"issuer:{m.issuer_id}", "target": f"mandate:{mid}",
                      "kind": "signed", "label": "signed", "status": "invalid" if v.integrity_codes else "verified"})
        if m.parent_mandate_id:
            d = delegation_rows.get(mid)
            edges.append({"id": f"dlg:{m.parent_mandate_id}:{mid}", "source": f"mandate:{m.parent_mandate_id}",
                          "target": f"mandate:{mid}", "kind": "delegated",
                          "label": f"delegated · {m.delegated_task}", "status": "verified" if not chain_codes else status,
                          "decision_event": str(d["decision_event"]) if d else None})
        else:
            edges.append({"id": f"bind:{case.case_id}:{mid}", "source": f"case:{case.case_id}", "target": f"mandate:{mid}",
                          "kind": "binds", "label": "case authority", "status": "revoked" if case.authority_revoked else "verified"})
        if m.agent_id not in seen_agents:
            seen_agents.add(m.agent_id)
            passport = env.repo.get_agent(m.agent_id)
            nodes.append({"id": f"agent:{m.agent_id}", "kind": "agent", "label": passport.name if passport else m.agent_id,
                          "sublabel": m.agent_id, "status": passport.status if passport else "invalid",
                          "data": {"agent": passport.model_dump(mode="json") if passport else None}})
        edges.append({"id": f"held:{mid}:{m.agent_id}", "source": f"mandate:{mid}", "target": f"agent:{m.agent_id}",
                      "kind": "held_by", "label": "held by", "status": status})

    # Denied attempts to commission authority (unauthorized expansions).
    rows = env.db.query(
        "SELECT payload FROM audit_events WHERE json_extract(payload, '$.action') = 'delegation.commission_task' "
        "AND json_extract(payload, '$.decision') = 'denied' AND json_extract(payload, '$.evidence_metadata.case_id') = ? "
        "ORDER BY seq", (case_id,))
    for r in rows:
        e = AuditEvent.model_validate_json(r["payload"])
        nid = f"attempt:{e.event_id}"
        nodes.append({"id": nid, "kind": "denied_attempt", "label": "Denied delegation", "sublabel": e.actor,
                      "status": "denied", "data": {"audit_event": e.model_dump(mode="json")}})
        if e.related_mandate and f"mandate:{e.related_mandate}" in {n["id"] for n in nodes}:
            edges.append({"id": f"try:{e.event_id}", "source": f"mandate:{e.related_mandate}", "target": nid,
                          "kind": "denied_delegation", "label": ", ".join(c.value for c in e.reason_codes)[:80],
                          "status": "denied"})
    return {"case_id": case.case_id, "generated_at": now.isoformat(), "nodes": nodes, "edges": edges,
            "delegations": [{k: str(v) for k, v in d.items()} for d in env.mandates.delegations(case_id)]}
