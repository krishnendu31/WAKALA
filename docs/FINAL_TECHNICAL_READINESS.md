# WAKALA — Final Technical Readiness (Phase 7)

**Branch:** `phase-7-final-validation`. Checkpoints `checkpoint-pre-phase7` (= `5769a05`) and `checkpoint-pre-phase6`.

**Status:** a technically credible, synthetic-data prototype for UAE Hackathon 2026, Challenge #27. It is **not
production-ready** and has **no official government integration**.

## 1. Verification results

| Check | Result |
|---|---|
| Backend test suite | **493 passed** (Phase 6 baseline 455, plus 34 security invariants and 4 readiness checks; one portal test updated for the model-outage fallback) |
| Frontend typecheck (`tsc -b`) | clean |
| Frontend production build (`vite build`) | succeeds |
| Frontend bundle secret scan | no keys, API tokens or issued dev passwords in `frontend/src` or `frontend/dist` |
| Live demo database audit chain | `chain verified` after repeated demo runs |
| UI route sweep (15 routes + an unknown route) | no render crash; an unknown route falls back to the Command Center |

## 2. Real-model tool calling — status: **UNVERIFIED**

No model credential was configured for this project: there is no `ANTHROPIC_API_KEY`, no
`WAKALA_AGENT_MODEL_PROVIDER` and no `.env`. Claude Code's own session credentials were deliberately **not** reused. So:
- **No live-model call was made.** Tests A–F against a real model were not run, and **no model behaviour is claimed**.
  In particular, nothing is claimed about whether a real model follows or refuses injected document text.
- **What is verified** uses a recording fake client (`tests/test_portal_integration.py`):
  - strict tool schemas and server-side re-validation;
  - signing by the server-side adapter and authorization by `Gateway.execute()`;
  - unknown or invalid tools never reach the gateway;
  - unauthorized proposals (an AED 50,000 transfer to an external account, another citizen) are denied with no change
    to the ledger or case prerequisites;
  - timeouts, refusals and runaway loops end with an honest status;
  - the injection test is reported "not run" rather than faked when no model is configured.
- **Demo safety:** the default is the clearly labelled deterministic offline planner. If a model is later configured
  and becomes unreachable before its first gateway step, the portal falls back to the labelled deterministic planner.
  The failed model run stays recorded. The fallback never runs after a gateway step and never overrides a model
  refusal.

To run the live test later (billed to your Anthropic account), set `WAKALA_AGENT_MODEL_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY` in the shell; clear `ANTHROPIC_BASE_URL` if another tool sets it. Then use the portal's
*Real-model injection test*, which records exactly what the model proposed.

## 3. Security invariants (`tests/test_p7_invariants.py`, real gateway, isolated environments)

| Invariant | Evidence |
|---|---|
| Every unauthorized request variant is denied and changes no protected record (ledger, renewals, case state and prerequisites) | 28 parametrised variants: wrong citizen ×6, wrong-case mandate ×2, unauthorized tool ×3, excessive amount ×3, wrong recipient ×2, tampered signature ×2, forged identity ×2, expired, revoked, replay, delegation escalation ×4, forged/self-signed child ×2, revoked ancestor |
| Agents cannot issue their own authority | Self-signed child mandate rejected; model tool list has no mandate/permission/officer/gateway tool; no non-officer, non-dev route writes mandates |
| Replay, expansion, expiry, revocation, case isolation | Covered by the variants above, plus a test that the unrelated case is not gated or suspended and completes |
| Document Shield quarantine is enforced | Quarantined PDF: agent view `content: null`, injected amount absent |
| Protected services only through the gateway | Static check: no API or agent module calls a protected-service mutation directly |
| Officer interventions need authenticated authorization | Every officer POST route returns 401 without a session or with a forged token; auditor gets 403 |
| Audit reflects real operations | Every ledger row traces to an allowed decision with an `executed` outcome; no denied decision has an execution; chain verifies |

## 4. Behaviour Watch — recovery results

| Run | Policy | Shared back-to-back | Legit. denied | Legit. held | Unrelated case completed |
|---|---|---|---|---|---|
| Phase 5 (historical, `evidence/phase5`) | original | **2/20** | — | — | — |
| Phase 6 before/after (`evidence/phase6`) | original / watch-2.0 | 2/20 → **20/20** | 24 → 0 | 10 → 0 | — |
| Phase 7 re-run of the original policy | original | **2/20** (reproduced) | 24 | — | — |
| Phase 7 repeats ×5 (`evidence/phase7`) | watch-2.0 | 20/20 every time | 0 | 0 | 20/20 every time |
| Phase 7 long run | watch-2.0 | **50/50** | 0 | 0 | 50/50 |

- **Independent** incidents: 20/20 in every repetition.
- **The same malicious behaviour is still contained every time.** All 20 attacks were denied and not executed in each
  run. Each one was contained: 2 suspensions and 18 revocations, because the repeat attacker escalates to critical
  from its third attempt.
- **Caveat:** this is a deterministic, machine-speed, single-process benchmark. Repeated identical results show
  reproducibility, **not production reliability**.

## 5. Full demonstration — executed in the real frontend and backend

1. **Citizen renewal:** case COMPLETED through 6 gateway-allowed signed steps, with an AED 500 receipt to the synthetic
   treasury.
2. **Signed delegation:** the Insurance Agent ran under a child mandate whose parent is the Residency root.
3. **Wrong-citizen request blocked:** "Blocked: this AI agent was authorized to check insurance for Mariam, not another
   citizen's record (C-1003)."
4. **Security Operations shows the incident:** the same case ID, a verified chain with the child SUSPENDED, the
   violated rule and the evidence.
5. **Officer intervention** (OFF-0101): under review → reassign to AGT-INS-002 → resume. The delegation was held, then
   approved and re-authorized (`ALLOW_WITHIN_MANDATE`) and executed. The incident was resolved.
6. **The original case completed** as "recovered after a security review".
7. **The unrelated C-1002 case continued** to COMPLETED.
8. **Attack Lab, all eight:** baseline executed 7, WAKALA executed 0, 1 denied in both (B). Each run used fresh
   isolated environments.
9. **Document Shield:** the hidden white-text PDF was QUARANTINED with findings located on the hidden layer.
10. **My AI Activity:** 3 agents, 1 delegated task, 1 blocked request (no data returned), the security pause and the
    officer review, all matching the audit trail.
11. **Security Evidence:** the actual Phase 5 figures (1,200 requests; full WAKALA executed 0/720 unauthorized, 0/480
    false denials) plus the new before/after recovery panel.
12. **Shadow Mode:** 11 events; source state unchanged during observation; predictions matched separate enforcement
    11/11.

Also tested:
- An invalid session at load is cleared and the sign-in form shown.
- A session killed server-side mid-use now shows a clear "session expired or was revoked" notice.

## 6. Security weaknesses and demo risks discovered in Phase 7

| # | Finding | Impact | Status |
|---|---|---|---|
| 1 | If a model were configured and unreachable (e.g. venue Wi-Fi), the case would stall at CREATED with `model_error` | Demo failure | **Fixed** (labelled fallback before any gateway step) |
| 2 | An officer session expiring mid-use returned silently to sign-in | Confusing during a live demo | **Fixed** (explicit notice) |
| 3 | Security Evidence showed the historical 2/20 back-to-back recovery with no indication that it was diagnosed and fixed | Misleading to judges | **Fixed** (before/after panel from committed evidence; history kept) |
| 4 | `ANTHROPIC_BASE_URL` set by another tool would redirect the optional model client | Credential/endpoint confusion | Documented (clear it before enabling the model) |
| 5 | The audit hash chain does not detect tail truncation or a consistent rewrite by the database owner | Integrity limitation | Stated in the API's own scope note; not fixed (needs external anchoring) |
| 6 | Officer sessions survive a backend restart until their fixed expiry | Expected for server-side sessions | Accepted; sign-out and expiry work |

No security rule was weakened, and no reset that erases audit records was added. "New demo session" deletes nothing.

## 7. Remaining production limitations

- **Single-process enforcement.** The gateway, monitoring and services run in one process; there is no distributed
  enforcement or HA.
- **SQLite** storage; no external audit anchoring.
- **Development signing keys** in `backend/.dev_keys` (git-ignored), and development officer passwords issued by the
  CLI.
- **No real government integration.** Fictional entities, synthetic citizens, synthetic treasury.
- **No citizen authentication.** Portal writes are developer-mode, loopback-only endpoints.
- **Limited cross-platform validation.** Validated on Windows 11 with Python 3.13, PyMuPDF 1.25.5 and Node/Vite;
  `scripts/bootstrap.sh` exists but has not been re-validated on macOS/Linux in this phase.
- **Document Shield detection limits.** Rule-based: misses paraphrases, translations and images (no OCR); limited
  Arabic; worker isolation is a separate process, not an OS sandbox; PyMuPDF is AGPL-licensed.
- **Policy drafts are not enforced.** Approved drafts are signed but do not change authorization.
- **Live model unverified** (section 2).
- **Behaviour Watch thresholds are hand-set;** the operating schedule is off by default.
- **Agent-version revocation is not available,** because there is no cryptographically bound deployment version.

## 8. Launch (offline, deterministic)

One-time setup:

```bash
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

Terminal 1 — backend, with developer/demo mode:

```bash
cd backend
.venv\Scripts\python run_dev.py
```

Terminal 2 — frontend:

```bash
cd frontend
npm run dev
```

Issue the officer passwords; each is shown once, so note them:

```bash
cd backend
.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101
```

```bash
cd backend
.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0900
```

Then open http://localhost:5173/portal, click **New demo session**, and follow the presenter panel. Use **Open Security
Operations side by side**: sign in as OFF-0101 for recovery, or OFF-0900 for the Revocation tab.

**Known default state:**
- The deterministic offline assistant.
- Policy `watch-2.0`, with no operating-hours schedule.
- Officers OFF-0101 (case officer, residency), OFF-0202 (case officer, insurance), OFF-0900 (supervisor) and OFF-0950
  (auditor, read-only). None has a password until you issue one.
- All data is synthetic, and every page carries a synthetic label.

Reproduce the evidence:

```bash
cd backend
.venv\Scripts\python -m app.evaluation.recovery_repeat
```
