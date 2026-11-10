"""Compact, projector-friendly Case View of one case's authority story.

Citizen request → Residency Agent (root case mandate) → delegated agent(s) (child mandates) → protected services.
Built only from the verified authority graph (stored signed mandates, verified now) and the case's audit decisions.
Each step carries a short explanation and a technical-details block (mandate IDs, verification codes, reason codes).
"""

from __future__ import annotations

from typing import Any

from app.portal.explain import AGENT_NAMES, ACTION_NAMES, explain
from app.workflow.authority_graph import build_authority_graph
from app.workflow.scenarios import case_audit_events

SERVICE_OF = {"residency": "Residency service", "insurance": "Insurance service", "payment": "Payment service (synthetic treasury)",
              "delegation": "WAKALA delegation service"}


def _state(status: str) -> str:
    return {"active": "authorized", "verified": "authorized", "suspended": "suspended", "revoked": "revoked",
            "expired": "revoked", "invalid": "denied"}.get(status, status)


def build_case_view(env: Any, case_id: str) -> dict[str, Any] | None:
    g = build_authority_graph(env, case_id)
    case = env.cases.get(case_id)
    if g is None or case is None:
        return None
    citizen = env.repo.get_citizen(case.citizen_ref)
    first = citizen.full_name.split()[0] if citizen else case.citizen_ref
    mandates = {n["label"]: n for n in g["nodes"] if n["kind"] in ("mandate", "child_mandate")}
    pending_tools = {(a.agent_id, a.tool_name) for a in env.approvals.list() if a.case_id == case_id and a.status == "pending"}
    events = [e for e in sorted(case_audit_events(env, case_id), key=lambda e: e.sequence or 0)
              if e.decision in ("allowed", "denied", "escalated")]

    def agent_lane(mid: str, node: dict[str, Any], delegated_from: str | None) -> dict[str, Any]:
        m = node["data"].get("mandate", {})
        agent = m.get("agent_id")
        ver = node["data"].get("verification", {})
        actions = []
        for e in events:
            if e.actor != agent or (e.related_mandate and e.related_mandate != mid) or e.action == "delegation.commission_task":
                continue
            codes = [c.value for c in e.reason_codes]
            target = e.evidence_metadata.get("target_resource")
            st = "authorized" if e.decision == "allowed" else "pending_approval" if e.decision == "escalated" else "denied"
            actions.append({
                "service": SERVICE_OF.get(str(e.action).split(".")[0], e.action), "tool_name": e.action,
                "action": ACTION_NAMES.get(e.action, e.action), "state": st, "at": e.timestamp.isoformat(),
                "explanation": explain({"allowed": e.decision == "allowed", "reason_codes": codes}, agent_id=agent, tool_name=e.action,
                                       parameters={"citizen_ref": target} if str(target).startswith("C-") else {},
                                       case_citizen=case.citizen_ref, citizen_name=first),
                "technical": {"event_id": e.event_id, "sequence": e.sequence, "reason_codes": codes, "mandate_id": e.related_mandate,
                              "target": target},
            })
        recovered = bool(delegated_from) and case.recovery_status == "recovered" and agent in case.task_assignments.values() \
            and any(a["state"] == "authorized" for a in actions)
        state = _state(node["status"])
        if (agent, "delegation.commission_task") in pending_tools and not delegated_from:
            state = "pending_approval"
        return {
            "agent_id": agent, "agent_name": AGENT_NAMES.get(agent, agent), "mandate_id": mid, "delegated_from": delegated_from,
            "task": m.get("delegated_task"), "state": "recovered" if recovered and state == "authorized" else state,
            "explanation": (f"{AGENT_NAMES.get(agent, agent)} acts for {first}'s case only"
                            + (f", with authority delegated by the Residency Agent for {m.get('delegated_task')}." if delegated_from else ".")
                            + ({"suspended": " Its authority is suspended pending review.", "revoked": " Its authority has been revoked."}
                               .get(state, ""))),
            "allowed_tools": m.get("allowed_tools", []),
            "technical": {"verification_valid": ver.get("valid"), "verification_codes": ver.get("reason_codes", []),
                          "chain_length": ver.get("chain_length"), "issuer": m.get("issuer_id"), "expires_at": m.get("expires_at"),
                          "parent_mandate_id": m.get("parent_mandate_id"), "signature": (m.get("signature_metadata") or {}).get("algorithm")},
            "actions": actions,
        }

    lanes = []
    for agent, mid in case.mandate_refs.items():
        if mid in mandates and agent == "AGT-RES-001":
            lanes.append(agent_lane(mid, mandates[mid], None))
    for d in g["delegations"]:
        cid = d.get("child_mandate_id")
        if cid in mandates:
            lanes.append(agent_lane(cid, mandates[cid], d.get("parent_mandate_id")))
    for agent, mid in case.mandate_refs.items():
        if mid in mandates and agent not in ("AGT-RES-001",) and all(l["mandate_id"] != mid for l in lanes):
            lanes.append(agent_lane(mid, mandates[mid], None))
    denied_delegations = [{"explanation": "Blocked: an agent tried to hand on more authority than it was given.",
                           "technical": {"event_id": n["data"]["audit_event"]["event_id"],
                                         "reason_codes": n["data"]["audit_event"]["reason_codes"], "actor": n["sublabel"]}}
                          for n in g["nodes"] if n["kind"] == "denied_attempt"]
    inc = env.assurance.incidents.case_has_active(case_id) if env.assurance else None
    return {
        "case_id": case_id, "citizen": {"ref": case.citizen_ref, "first_name": first}, "state": case.state.value,
        "recovery_status": case.recovery_status,
        "request": {"text": "Renew my residency permit", "service": "Residency permit renewal (synthetic)"},
        "lanes": lanes, "denied_delegations": denied_delegations,
        "incident": {"incident_id": inc.incident_id, "title": inc.title, "severity": inc.severity} if inc else None,
        "legend": ["authorized", "denied", "suspended", "revoked", "pending_approval", "recovered"],
        "source": "verified stored signed mandate chain + hash-chained audit decisions", "generated_at": g["generated_at"],
    }
