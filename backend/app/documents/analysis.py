"""Visibility classification and transparent, rule-based prompt-injection detection.

Not machine learning and not complete: these are explicit patterns over the text the worker could extract.
Every finding carries evidence, location, a severity and a stated confidence limitation. A document with no
finding is "no indicator found", never "safe".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

TINY_PT = 3.0          # rendered text below this size is not readable at normal zoom
MIN_CHANGED_PIXELS = 3  # removing visible text must change at least this many pixels in its box
MIN_CHANGED_FRACTION = 0.01
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


def classify_run(r: dict[str, Any]) -> list[str]:
    """Reasons this run is hidden from a human reader (empty list = rendered visibly)."""
    reasons = []
    if r["on_page_fraction"] < 0.5:
        reasons.append("OFF_PAGE")
    if r["render_mode"] == 3:
        reasons.append("INVISIBLE_RENDER_MODE")
    if r["opacity"] <= 0.05:
        reasons.append("TRANSPARENT")
    if r["size"] < TINY_PT:
        reasons.append("TINY_TEXT")
    if r["visibility_analysed"] and "OFF_PAGE" not in reasons and r["render_sampled_pixels"] > 0:
        frac = r["render_changed_pixels"] / r["render_sampled_pixels"]
        if r["render_changed_pixels"] < MIN_CHANGED_PIXELS or frac < MIN_CHANGED_FRACTION:
            # no visible effect when the text is removed: same colour as the background, covered, or transparent
            if not ({"TRANSPARENT", "INVISIBLE_RENDER_MODE"} & set(reasons)):
                reasons.append("NO_RENDERED_EFFECT" if r["color"] not in ("#ffffff",) else "WHITE_ON_WHITE_OR_COVERED")
    return reasons


def overlaps(runs: list[dict[str, Any]]) -> set[int]:
    """Indexes of visible runs drawn substantially over other visible runs (possible obscuring)."""
    out: set[int] = set()
    by_page: dict[int, list[int]] = {}
    for i, r in enumerate(runs):
        if not r["hidden_reasons"]:
            by_page.setdefault(r["page"], []).append(i)
    for idx in by_page.values():
        for a_pos, i in enumerate(idx[:600]):
            ax0, ay0, ax1, ay1 = runs[i]["bbox"]
            area = max(1e-6, (ax1 - ax0) * (ay1 - ay0))
            for j in idx[a_pos + 1:600]:
                bx0, by0, bx1, by1 = runs[j]["bbox"]
                w, h = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
                if w > 0 and h > 0 and (w * h) / min(area, max(1e-6, (bx1 - bx0) * (by1 - by0))) > 0.6:
                    out.update((i, j))
    return out


# --- prompt-injection rules -------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str  # high | medium | low
    pattern: re.Pattern[str]
    description: str


def _r(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE | re.DOTALL)


RULES: tuple[Rule, ...] = (
    Rule("PI-OVERRIDE", "override_instructions", "high",
         _r(r"\b(ignore|disregard|forget|override|bypass)\b.{0,25}\b(all|any|the|your|previous|prior|above|earlier|system|original)\b.{0,25}"
            r"\b(instructions?|prompts?|rules|guidelines|directives|policies)\b|\bnew\s+instructions\s*:"),
         "Attempts to override the agent's instructions."),
    Rule("PI-ROLE", "impersonation", "high",
         _r(r"(^|\n|\[|<)\s*(system|developer|assistant|admin(istrator)?)\s*(message|prompt|note)?\s*[:\]>]|<\|im_start\|>|"
            r"\b(as|this is) (the|an|your) (system|administrator|admin|supervisor|security team)\b|\badmin(istrator)? override\b"),
         "Impersonates a system, developer or administrator message."),
    Rule("PI-TOOL", "unauthorized_action", "high",
         _r(r"\b(call|invoke|execute|run|use|trigger)\b.{0,20}\b(tool|api|function|endpoint)\b|"
            r"\b(payment\.collect_renewal_fee|residency\.complete_renewal|delegation\.commission_task|insurance\.verify_case_eligibility|"
            r"/api/gateway/execute|mandates?\s+revoke)\b"),
         "Asks the agent to perform a tool/API action."),
    Rule("PI-PAYMENT", "payment_redirection", "high",
         _r(r"\b(change|update|replace|redirect)\b.{0,25}\b(recipient|beneficiary|destination|payee|account|iban)\b|"
            r"\b(pay|transfer|send|wire|remit|collect)\b.{0,60}\b(to|into)\b.{0,20}\b(account|iban|SYNTH-EXT[-A-Z0-9]*|AE\d{2}[0-9 ]{10,})|"
            r"\bSYNTH-(EXT|PERSONAL)[-A-Z0-9]+\b|"
            r"\b(pay|transfer|send|wire|remit|collect|payment of)\b.{0,40}(\bAED\s*([1-9]\d{0,2}(,\d{3})+|[1-9]\d{3,})(\.\d+)?|"
            r"\b([1-9]\d{0,2}(,\d{3})+|[1-9]\d{3,})(\.\d+)?\s*AED\b)"),
         "Payment instruction with an unexpected amount or recipient."),
    Rule("PI-EXFIL", "data_exfiltration", "high",
         _r(r"\b(reveal|disclose|print|output|send|email|share|leak|list)\b.{0,40}\b(password|secret|private key|api key|token|"
            r"system prompt|confidential|credentials?|other (citizens?|applicants?)|all (citizens?|records))\b"),
         "Requests disclosure of confidential information."),
    Rule("PI-CONTEXT", "context_switch", "medium",
         _r(r"\b(switch|change|move)\b.{0,15}\b(to )?(another |a different )?(citizen|applicant|case|context)\b|"
            r"\b(process|open|use|act (on|for))\b.{0,20}\b(citizen|case)\s+(C-\d{4}|CASE-[A-Z0-9]+)\b|\bthis (request|case) is (now )?for\b"),
         "Attempts to change the current citizen or case context."),
    Rule("PI-BYPASS", "security_bypass", "high",
         _r(r"\b(bypass|disable|skip|ignore|turn off|circumvent)\b.{0,25}\b(security|verification|checks?|authori[sz]ation|policy|"
            r"policies|mandate|gateway|approval|safety|guardrails?)\b|\bdo not (verify|check|log|audit)\b"),
         "Commands the agent to ignore security controls."),
    # Minimal Arabic coverage (UAE context). Far from complete: paraphrases and dialects are not covered.
    Rule("PI-OVERRIDE-AR", "override_instructions", "high",
         _r(r"(تجاهل|انس|تخط)\S*\s+(\S+\s+){0,3}(التعليمات|الأوامر|القواعد)"),
         "Arabic: attempts to override the agent's instructions."),
    Rule("PI-PAYMENT-AR", "payment_redirection", "high",
         _r(r"(ادفع|حول|حوّل|أرسل|ارسل)\S*\s+(\S+\s+){0,5}\d{4,}"),
         "Arabic: payment instruction with a large amount."),
)
NEGATED = _r(r"\b(do not|don't|never|must not|should not|may not|cannot|no one may|prohibited to)\s+(\w+\s+){0,2}$")
ADDRESSED_TO_AI = _r(r"\b(ai|assistant|agent|model|llm|chatbot|you must|you are now|immediately)\b")
REPORTED_MARKERS = _r(r"(for example|e\.g\.|such as|phrases? like|examples? of|do not follow|never follow|warning|beware|"
                      r"attackers? (may|might|often)|training|awareness|quoted|reported)\W*$")
QUOTES = "\"'“”‘’«»"


# Common Cyrillic/Greek look-alikes folded to Latin before matching (not a full confusables table).
HOMOGLYPHS = str.maketrans("аеорсухіјѕԁԛԝАВЕКМНОРСТХІЈЅΑΒΕΖΗΙΚΜΝΟΡΤΥΧοιν", "aeopcyxijsdqwABEKMHOPCTXIJSABEZHIKMNOPTYXoiv")
SPACED = re.compile(r"\b(?:[A-Za-z] ){3,}[A-Za-z]\b")


def normalise(text: str) -> str:
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH))


def deobfuscate(text: str) -> str:
    """Second view used only for matching: homoglyphs folded, letter-spaced words joined ("i g n o r e")."""
    return SPACED.sub(lambda m: m.group(0).replace(" ", ""), text.translate(HOMOGLYPHS))


def _quoted(text: str, start: int, end: int) -> bool:
    before, after = text[max(0, start - 3):start], text[end:end + 3]
    if any(q in before for q in QUOTES) and any(q in after for q in QUOTES):
        return True
    return bool(REPORTED_MARKERS.search(text[max(0, start - 60):start]))


def _scan(t: str, obfuscated: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rule in RULES:
        for m in rule.pattern.finditer(t):
            s, e = m.span()
            if e - s < 3:
                continue
            quoted = _quoted(t, s, e)
            negated = bool(NEGATED.search(t[max(0, s - 30):s]))
            addressed = bool(ADDRESSED_TO_AI.search(t[max(0, s - 80):e + 80]))
            sev = rule.severity
            adjustments = []
            if quoted:
                sev = "low"
                adjustments.append("appears quoted or reported (e.g. training/awareness text): downgraded")
            elif negated:
                sev = "low"
                adjustments.append("negated/prohibitive wording (e.g. 'do not bypass'): downgraded")
            elif addressed and sev == "medium":
                sev = "high"
                adjustments.append("addressed to an AI agent: upgraded")
            if obfuscated:
                adjustments.append("matched only after folding look-alike characters / joining spaced letters (obfuscation)")
            out.append({"rule_id": rule.rule_id, "category": rule.category, "description": rule.description, "severity": sev,
                        "base_severity": rule.severity, "quoted_or_reported": quoted, "negated": negated, "addressed_to_ai": addressed,
                        "obfuscated": obfuscated, "excerpt": t[max(0, s - 40):min(len(t), e + 40)].strip()[:240], "match": t[s:e][:160],
                        "start": s, "end": e, "adjustments": adjustments})
            if len([f for f in out if f["rule_id"] == rule.rule_id]) >= 5:
                break
    return out


def detect(text: str) -> list[dict[str, Any]]:
    """Findings for one text unit: rule, excerpt, offsets, severity adjustments (with reasons)."""
    t = normalise(text)
    out = _scan(t, False)
    d = deobfuscate(t)
    if d != t:
        seen = {f["rule_id"] for f in out}
        for f in _scan(d, True):
            if f["rule_id"] not in seen:
                # offsets refer to the de-obfuscated view; point at the whole unit
                out.append({**f, "start": 0, "end": len(t)})
    return out


CONFIDENCE_NOTE = ("Rule-based pattern match: can miss paraphrased, encoded, translated, image-borne or split instructions, "
                   "and can flag legitimate text that uses similar wording. A human should verify.")
