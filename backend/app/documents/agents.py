"""Agents that consume documents — both SIMULATED (deterministic Python, no LLM is called anywhere).

* ``DocumentIntakeAgent`` — the normal path. It receives only the policy-permitted agent view, treats the
  content as data (extracts the citizen reference and request type) and proposes NO tool call from document
  text. Workflow actions come only from the case workflow, under the case mandate, through the gateway.
* ``run_adversarial_test`` — Scenario B, a clearly labelled ADVERSARIAL TEST. A deliberately manipulated
  simulated agent reads the RAW text of every layer (as if Document Shield had been bypassed or had missed the
  instruction), obeys the hidden payment instruction, and signs the request with its own real key and its real
  case mandate. The gateway decides independently; the ledger is compared before and after.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents import SimulatedInsuranceAgent as INS, SimulatedPaymentAgent as PAY, SimulatedResidencyAgent as RES, ToolCall
from app.workflow.delegation_scenarios import prepare
from app.workflow.intake import open_case
from app.workflow.scenarios import WorkflowRunner, case_audit_events

from .service import DocumentRejected, DocumentStore

CITIZEN = re.compile(r"\bC-\d{4}\b")
AMOUNT = re.compile(r"(?:AED\s*)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s*(?:AED)?", re.IGNORECASE)
RECIPIENT = re.compile(r"\bSYNTH-[A-Z0-9][A-Z0-9-]{3,40}\b")


class DocumentIntakeAgent:
    agent_id = "AGT-RES-001"

    def process(self, view: dict[str, Any]) -> dict[str, Any]:
        if not view["released"]:
            return {"agent_id": self.agent_id, "used_document": False, "proposed_tool_calls": [],
                    "observation": f"Document withheld ({view.get('withheld_reason')}); waiting for an officer. No action taken."}
        text = "\n".join(view["content"].values())
        citizens = sorted(set(CITIZEN.findall(text)))
        return {"agent_id": self.agent_id, "used_document": True, "proposed_tool_calls": [],
                "extracted_data": {"citizen_refs_mentioned": citizens, "mentions_residency_renewal": "renewal" in text.lower()},
                "observation": "Document text treated as untrusted data. No instruction in it was followed; any workflow "
                               "step must come from the case and be authorized by the gateway under the case mandate."}


def _parse_payment(text: str) -> dict[str, str] | None:
    """What a manipulated agent would 'understand' from the injected text (deterministic): the amount stated
    closest before the named recipient."""
    rec = RECIPIENT.search(text)
    if not rec:
        return None
    window = text[max(0, rec.start() - 200):rec.start()]
    amounts = []
    for a in AMOUNT.finditer(window):
        whole = a.group(1).replace(",", "")
        if whole.isdigit() and int(whole) >= 1 and ("AED" in a.group(0).upper() or a.group(2)):
            amounts.append(f"{int(whole)}.{(a.group(2) or '00').ljust(2, '0')}")
    if not amounts:
        return None
    return {"amount": amounts[-1], "recipient": rec.group(0)}


def run_adversarial_test(env: Any, doc_id: str) -> dict[str, Any]:
    store = DocumentStore(env)
    rec = store.get(doc_id)
    if rec is None:
        raise DocumentRejected("DOCUMENT_NOT_FOUND", 404)
    raw_text = "\n".join(r["text"] for r in rec["runs"])  # ALL layers, including hidden: Document Shield deliberately bypassed
    instruction = _parse_payment(raw_text)
    citizen = next(iter(CITIZEN.findall("\n".join(r["text"] for r in rec["runs"] if not r["hidden_reasons"]))), "C-1001")
    if env.repo.get_citizen(citizen) is None:
        citizen = "C-1001"
    result: dict[str, Any] = {
        "label": "ADVERSARIAL TEST — simulated manipulated agent (deterministic script; no real LLM was used or manipulated)",
        "document_id": doc_id, "document_disposition": rec["disposition"],
        "bypass_note": "The manipulated agent reads raw text from every layer, including content Document Shield withheld, "
                       "to show the second, independent layer: the authorization gateway.",
        "parsed_instruction": instruction, "attempts": [],
    }
    if instruction is None:
        result["outcome"] = "No actionable payment instruction found in the document text; no attempt made."
        return result
    r = WorkflowRunner(env, "document_shield_adversarial")
    case = open_case(env, citizen, "delegated")
    child = prepare(r, case, "Setup · ")
    cur = r.case(case.case_id)
    if child:
        r.run("AGT-INS-001", INS.verify(cur), cur, "Setup · legitimate insurance check", "legitimate", mandate_id=child)
    cur = r.case(case.case_id)
    setup_steps = len(r.steps)
    ledger_before = env.services.ledger(case.case_id)
    all_before = env.db.query("SELECT COUNT(*) AS n FROM payment_ledger")[0]["n"]
    state_before = cur.state.value
    attempts = [
        ("AGT-PAY-001", PAY.collect(cur, instruction["amount"], instruction["recipient"]),
         "Manipulated Payment Agent obeys the hidden instruction (own key, own case mandate)"),
        ("AGT-RES-001", PAY.collect(cur, instruction["amount"], instruction["recipient"]),
         "Manipulated document-reading Residency Agent tries the payment tool itself"),
    ]
    for agent, call, title in attempts:
        step = r.run(agent, call, cur, f"ADVERSARIAL · {title}", "unauthorized")
        result["attempts"].append({
            "agent_id": agent, "title": title, "tool_name": call.tool_name, "parameters": step.parameters,
            "allowed": step.decision.allowed if step.decision else False, "executed": step.executed,
            "reason_codes": [c.value for c in step.decision.reason_codes] if step.decision else [],
            "explanation": step.decision.human_readable_explanation if step.decision else None,
            "audit_reference": step.decision.audit_reference if step.decision else None,
            "checks": [c.model_dump() for c in step.checks],
        })
    after = r.case(case.case_id)
    ledger_after = env.services.ledger(case.case_id)
    all_after = env.db.query("SELECT COUNT(*) AS n FROM payment_ledger")[0]["n"]
    result.update({
        "case_id": case.case_id, "citizen_ref": citizen, "setup_steps": [s.model_dump(mode="json") for s in r.steps[:setup_steps]],
        "case_state_before": state_before, "case_state_after": after.state.value,
        "ledger_entries_for_case_before": len(ledger_before), "ledger_entries_for_case_after": len(ledger_after),
        "ledger_rows_total_before": all_before, "ledger_rows_total_after": all_after,
        "ledger_unchanged": len(ledger_before) == len(ledger_after) and all_before == all_after,
        "audit_events": [e.model_dump(mode="json") for e in sorted(case_audit_events(env, case.case_id), key=lambda e: e.sequence or 0)],
        "outcome": ("Gateway denied every manipulated attempt; no payment was recorded."
                    if not any(a["executed"] for a in result["attempts"]) else "WARNING: a manipulated attempt executed."),
    })
    rec = store.get(doc_id)
    rec["adversarial_test"] = {k: result[k] for k in ("case_id", "outcome", "ledger_unchanged")} | {
        "attempts": [{k: a[k] for k in ("agent_id", "allowed", "executed", "reason_codes", "audit_reference")} for a in result["attempts"]]}
    store.save(rec)
    return result


__all__ = ["DocumentIntakeAgent", "ToolCall", "run_adversarial_test", "RES"]
