"""Policy Drafting — DRAFT-ONLY DEMONSTRATION with a full approval-and-signing safety lifecycle.

1. A deterministic, restricted template parser turns one sentence into a structured draft. Anything it does not
   recognise is reported as unrecognised; nothing is guessed. No language model is used.
2. Schema validation and conflict checks (against the agent's registered service, the case-bound authority model,
   the case-mandate lifetime, the operation's risk and existing approved policies).
3. A human-readable summary for the reviewer.
4. Explicit approval by an authenticated officer of the entity that owns the receiving service (``policies.approve``).
5. Ed25519 signature by that entity's issuer key, verifiable afterwards.
6. Status after approval: ``approved_signed_not_enforced``. Approved policies are NOT wired into ``Gateway.execute()``
   in this prototype and never replace existing authorization policy. Enforcing them would require mapping each
   field onto mandate issuance and the policy engine, with its own tests — not implemented.
"""

from __future__ import annotations

import json
import re
import secrets
from typing import Any

from app.core.crypto import canonical_json, sign, verify
from app.schemas import AuditEvent

TAG = b"WAKALA-POLICY-DRAFT-V1"
CASE_MANDATE_LIFETIME_MIN = 120
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ROLES = {"insurance": ("Insurance Agent", "insurance", "ISS-INSURANCE-REG"),
         "residency": ("Residency Agent", "residency", "ISS-RESIDENCY-AUTH"),
         "payment": ("Payment Agent", "payment", "ISS-PAYMENTS-OFFICE")}
ACTIONS = [  # (pattern, tool, risk)
    (r"verify (?:insurance )?coverage|verify (?:the )?insurance|check (?:the )?insurance", "insurance.verify_case_eligibility", "low"),
    (r"check (?:residency )?eligibility", "residency.check_eligibility", "low"),
    (r"complete (?:the )?renewal", "residency.complete_renewal", "medium"),
    (r"collect (?:the )?(?:renewal )?fee|take (?:the )?payment", "payment.collect_renewal_fee", "high"),
]
SCHEMA_FIELDS = ("agent_role", "permitted_action", "citizen_scope", "case_scope", "action_limit", "expiration_minutes",
                 "receiving_service", "required_approval_level")


class PolicyError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code, self.status = code, status


def parse(text: str) -> dict[str, Any]:
    t = " " + re.sub(r"\s+", " ", text.lower().strip()) + " "
    consumed: list[tuple[int, int]] = []

    def take(pattern: str) -> re.Match[str] | None:
        m = re.search(pattern, t)
        if m:
            consumed.append(m.span())
        return m

    draft: dict[str, Any] = dict.fromkeys(SCHEMA_FIELDS)
    if m := take(r"\b(?:the )?(insurance|residency|payment) agent\b"):
        draft["agent_role"] = m.group(1)
    for pat, tool, risk in ACTIONS:
        if m := take(rf"\bmay (?:only )?(?:{pat})\b"):
            draft["permitted_action"], draft["_risk"] = tool, risk
            draft["receiving_service"] = tool.split(".")[0]
            break
    if take(r"\bonly for the citizen in the current case\b|\bonly for the (?:case )?applicant\b"):
        draft["citizen_scope"], draft["case_scope"] = "current_case_citizen", "current_case_only"
    elif take(r"\bfor any citizen\b|\bfor all citizens\b"):
        draft["citizen_scope"], draft["case_scope"] = "any_citizen", "none"
    if m := take(r"\bno more than (\w+) times?\b|\bat most (\w+) times?\b"):
        w = m.group(1) or m.group(2)
        draft["action_limit"] = int(w) if w.isdigit() else NUM.get(w)
    if m := take(r"\b(?:for|within|expires? after) (\d+) (minutes?|hours?)\b"):
        n = int(m.group(1))
        draft["expiration_minutes"] = n * (60 if m.group(2).startswith("hour") else 1)
    if m := take(r"\bwith (supervisor|officer) approval\b|\bwithout approval\b"):
        draft["required_approval_level"] = m.group(1) or "none"
    # anything substantive left over is reported, never guessed
    rest = list(t)
    for a, b in consumed:
        rest[a:b] = " " * (b - a)
    leftover = re.sub(r"\b(and|the|a|an|,|\.|;)\b", " ", "".join(rest))
    words = [w for w in re.findall(r"[a-z0-9]+", leftover)]
    draft["unrecognised_text"] = " ".join(words) if words else ""
    return draft


def validate(env: Any, d: dict[str, Any]) -> dict[str, list[str]]:
    errors, conflicts, warnings = [], [], []
    for f in ("agent_role", "permitted_action", "citizen_scope", "action_limit"):
        if d.get(f) in (None, ""):
            errors.append(f"Missing {f.replace('_', ' ')} — the parser accepts only the documented sentence patterns.")
    if d.get("unrecognised_text"):
        errors.append(f"Unrecognised wording: “{d['unrecognised_text']}”. Rephrase with a supported pattern.")
    if d.get("action_limit") is not None and not 1 <= d["action_limit"] <= 20:
        errors.append("Action limit must be between 1 and 20.")
    role, tool = d.get("agent_role"), d.get("permitted_action")
    if role and tool and tool.split(".")[0] != ROLES[role][1]:
        conflicts.append(f"{ROLES[role][0]} is registered for the {ROLES[role][1]} service only; {tool} belongs to another service.")
    if d.get("citizen_scope") == "any_citizen":
        conflicts.append("WAKALA authority is case-bound: a policy for any citizen would bypass case scope. Not allowed.")
    if d.get("expiration_minutes") and d["expiration_minutes"] > CASE_MANDATE_LIFETIME_MIN:
        conflicts.append(f"Expiry of {d['expiration_minutes']} min exceeds the {CASE_MANDATE_LIFETIME_MIN}-min case-mandate lifetime.")
    if d.get("_risk") == "high" and d.get("required_approval_level") in (None, "none"):
        conflicts.append("Payment operations require officer or supervisor approval in the policy.")
    if d.get("required_approval_level") is None:
        warnings.append("No approval level stated; defaults to none for low-risk operations.")
    if d.get("expiration_minutes") is None:
        warnings.append(f"No expiry stated; the case-mandate lifetime ({CASE_MANDATE_LIFETIME_MIN} min) applies.")
    for p in list_policies(env):
        if p["status"] == "approved_signed_not_enforced" and p["draft"].get("agent_role") == role and p["draft"].get("permitted_action") == tool:
            conflicts.append(f"An approved policy ({p['policy_id']}) already covers this agent and action; drafts never silently replace it.")
    return {"errors": errors, "conflicts": conflicts, "warnings": warnings}


def human_summary(d: dict[str, Any]) -> str:
    if not d.get("agent_role") or not d.get("permitted_action"):
        return "Incomplete draft."
    scope = {"current_case_citizen": "only for the citizen of the current case", "any_citizen": "for ANY citizen"}.get(
        d.get("citizen_scope") or "", "with no citizen scope stated")
    lim = f", at most {d['action_limit']} time{'s' if d['action_limit'] != 1 else ''}" if d.get("action_limit") else ""
    exp = f", within {d['expiration_minutes']} minutes" if d.get("expiration_minutes") else ""
    appr = {"none": "No approval needed", "officer": "An officer must approve", "supervisor": "A supervisor must approve"}.get(
        d.get("required_approval_level") or "none", "No approval needed")
    return f"The {ROLES[d['agent_role']][0]} may use {d['permitted_action']} {scope}{lim}{exp}. {appr}."


def _audit(env: Any, actor: str, action: str, ev: dict[str, Any]) -> str:
    return env.audit.append(AuditEvent(event_id=f"EVT-{secrets.token_hex(8).upper()}", timestamp=env.clock(), actor=actor,
                                       action=action, decision="informational",
                                       evidence_metadata={k: v for k, v in ev.items() if isinstance(v, (str, int, bool)) or v is None})).event_id


def create_draft(env: Any, text: str, author: str = "service-owner-ui") -> dict[str, Any]:
    if not text.strip() or len(text) > 400:
        raise PolicyError("INVALID_TEXT")
    d = parse(text)
    v = validate(env, d)
    rec = {"policy_id": f"POL-{secrets.token_hex(4).upper()}", "created_at": env.clock().isoformat(), "source_text": text.strip(),
           "draft": {k: d.get(k) for k in (*SCHEMA_FIELDS, "unrecognised_text")}, "risk": d.get("_risk"), "validation": v,
           "valid": not v["errors"] and not v["conflicts"], "human_summary": human_summary(d),
           "status": "draft" if not v["errors"] and not v["conflicts"] else "draft_invalid",
           "drafted_by": "deterministic template parser (no AI model)", "author": author, "approval": None, "signature": None,
           "enforcement": "NOT ENFORCED — prototype demonstration of the approval lifecycle only"}
    rec["audit_event"] = _audit(env, "WAKALA-GATEWAY", "policy.draft_created", {"policy_id": rec["policy_id"], "valid": rec["valid"]})
    with env.db.transaction() as conn:
        conn.execute("INSERT INTO policy_drafts (policy_id, created_at, status, payload) VALUES (?, ?, ?, ?)",
                     (rec["policy_id"], rec["created_at"], rec["status"], json.dumps(rec)))
    return rec


def list_policies(env: Any) -> list[dict[str, Any]]:
    return [json.loads(r["payload"]) for r in env.db.query("SELECT payload FROM policy_drafts ORDER BY created_at DESC LIMIT 100")]


def get_policy(env: Any, pid: str) -> dict[str, Any] | None:
    rows = env.db.query("SELECT payload FROM policy_drafts WHERE policy_id = ?", (pid,))
    return json.loads(rows[0]["payload"]) if rows else None


def _save(env: Any, rec: dict[str, Any]) -> None:
    with env.db.transaction() as conn:
        conn.execute("UPDATE policy_drafts SET status = ?, payload = ? WHERE policy_id = ?", (rec["status"], json.dumps(rec), rec["policy_id"]))


def decide(env: Any, pid: str, officer: Any, approve: bool, note: str) -> dict[str, Any]:
    rec = get_policy(env, pid)
    if rec is None:
        raise PolicyError("POLICY_NOT_FOUND", 404)
    if not officer.can("policies.approve"):
        _audit(env, officer.officer_id, "officer.action_refused", {"attempted": "policy_approval", "code": "PERMISSION_DENIED", "target": pid})
        raise PolicyError("PERMISSION_DENIED", 403)
    if rec["status"] != "draft":
        raise PolicyError("NOT_AN_APPROVABLE_DRAFT", 409)
    issuer_id = ROLES[rec["draft"]["agent_role"]][2]
    issuer = next((i for i in env.repo.list_issuers() if i.issuer_id == issuer_id), None)
    if issuer is None or not issuer.name.startswith(officer.officer.entity):
        _audit(env, officer.officer_id, "officer.action_refused", {"attempted": "policy_approval", "code": "OUT_OF_ENTITY_SCOPE", "target": pid})
        raise PolicyError("OUT_OF_ENTITY_SCOPE", 403)
    v = validate(env, {**rec["draft"], "_risk": rec["risk"]})  # re-validate at approval time
    if v["errors"] or v["conflicts"]:
        rec["validation"], rec["status"] = v, "draft_invalid"
        _save(env, rec)
        raise PolicyError("VALIDATION_FAILED_AT_APPROVAL", 409)
    now = env.clock().isoformat()
    if approve:
        body = {"policy_id": pid, "draft": rec["draft"], "human_summary": rec["human_summary"], "approved_by": officer.officer_id,
                "approved_at": now, "issuer_id": issuer_id}
        sig = sign(env.keystore.private_key(issuer.key_id), TAG, canonical_json(body))
        rec["signature"] = {"algorithm": "Ed25519", "issuer_id": issuer_id, "key_id": issuer.key_id, "value": sig, "signed_body": body}
        rec["status"] = "approved_signed_not_enforced"
    else:
        rec["status"] = "rejected"
    rec["approval"] = {"officer_id": officer.officer_id, "decision": "approved" if approve else "rejected", "note": note[:300], "at": now}
    rec["approval"]["audit_event"] = _audit(env, officer.officer_id, "officer.policy_decision",
                                            {"policy_id": pid, "decision": rec["approval"]["decision"], "issuer_id": issuer_id})
    _save(env, rec)
    return rec


def verify_policy(env: Any, pid: str) -> dict[str, Any]:
    rec = get_policy(env, pid)
    if rec is None or not rec.get("signature"):
        return {"policy_id": pid, "signed": False, "valid": False}
    s = rec["signature"]
    key = env.repo.get_key(s["key_id"])
    ok = key is not None and key.owner_type == "issuer" and key.owner_id == s["issuer_id"] and key.status == "active"         and verify(key.public_key, TAG, canonical_json(s["signed_body"]), s["value"])
    body_matches = s["signed_body"]["draft"] == rec["draft"]
    return {"policy_id": pid, "signed": True, "valid": ok and body_matches, "signature_valid": ok, "body_matches_stored_draft": body_matches,
            "issuer_id": s["issuer_id"], "key_id": s["key_id"]}
