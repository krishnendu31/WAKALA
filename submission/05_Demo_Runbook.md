<div class="cover"><div class="eyebrow">UAE Hackathon 2026 · Challenge #27</div><h1>Demo runbook <span class="ar">وكالة</span></h1><p>Run the live prototype for Q&amp;A, a judges' booth or a backup. The 3-minute pitch uses the slide 4 screenshots and needs no live demo.</p></div>

## 1. The night before (one-time setup, about 10 minutes)

```bash
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

Issue the officer passwords. Each is **shown once**, so write it down on paper and do not put it in any file or slide:

```bash
cd backend
.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101
```

```bash
cd backend
.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0900
```

Rehearse the whole flow below once. Then click **New demo session** so the portal starts clean. This deletes nothing, and the audit history is kept.

## 2. On the day (start about 15 minutes before)

| Step | Action | Check |
|---|---|---|
| 1 | Terminal 1: `cd backend` then `.venv\Scripts\python run_dev.py` | Backend starts on port 8000 |
| 2 | Terminal 2: `cd frontend` then `npm run dev` | Vite serves http://localhost:5173 |
| 3 | Open **http://localhost:5173/portal** | Header shows "Enforcement engine: connected"; footer shows "API online" |
| 4 | Check the assistant label | "deterministic offline planner (no AI model)". This is the default and needs no internet |
| 5 | Turn on Do Not Disturb; set the browser zoom to 100–110 % | |
| 6 | Have `submission/WAKALA_Pitch_Deck.pdf` open as a fallback | |

## 3. Live flow (about 4 minutes; use any part of it)

Route: **/portal** → Presenter panel ("Guided demonstration").

| # | Where | Click | What to say / what appears |
|---|---|---|---|
| 1 | /portal, Scene 1 *Normal service* | **Send "I want to renew my res…"** | Six signed steps are allowed; the case reaches COMPLETED with an AED 500 synthetic receipt. "Every step was checked by the gateway." |
| 2 | Scene 2 *Cross-citizen incident* | **Run the unauthorized request** | "Blocked: this AI agent was authorized to check insurance for Mariam, not another citizen's record (C-1003)." The case shows PAUSED_FOR_REVIEW; nothing was charged. |
| 3 | Scene 3 | **Open Security Operations** (or *Open Security Operations side by side* in the header) | /soc opens. **Sign in** as `OFF-0101`. |
| 4 | /soc → **Incidents** tab | Open the HIGH `CROSS_CITIZEN_ACCESS` incident | Violated rule, gateway evidence, verified chain: roots AUTHORIZED, the child mandate SUSPENDED. |
| 5 | Same incident | **Mark under review** → **Reassign … → AGT-INS-002** (the standby agent) → **Resume case** | "Only one delegated mandate was touched. Nothing agent-wide." |
| 6 | Back on /portal | **Continue my case** | The new delegation is **held** for an officer. Nothing ran yet. |
| 7 | /soc → **Approvals** | **Approve & re-authorize** | The stored signed request is re-checked (ALLOW_WITHIN_MANDATE) and executes once. |
| 8 | /soc → **Incidents** | **Resolve incident** | |
| 9 | /portal | **Continue my case** | "Your residency renewal is complete — recovered after a security review." The unrelated case line shows COMPLETED. |
| 10 | /portal | **My AI Activity** | Citizen receipt: 3 agents, 1 delegated task, 1 blocked request (no data returned), the officer review. |
| 11 | /portal, Scene 4 | **Attach hidden-text PDF** | Document Shield marks the PDF QUARANTINED; the hidden-layer finding is shown. Optionally **Inspect in Document Shield**. |
| 12 | **/attack-lab** | **Run all 8** | Summary tiles: 8 run · executed without WAKALA **7** · with WAKALA **0** · denied in both **1**. |
| 13 | **/evidence** | Scroll to the before/after recovery panel | 1,200 requests; 0/720 and 0/480; recovery 2/20 → 20/20. Say "synthetic benchmark". |
| 14 | Optional: **/shadow** | **Run shadow evaluation, then enforcement** | 11 events; predictions matched enforcement 11/11; source state unchanged. |
| 15 | Optional: **/delegation** | Case View | Citizen request → Residency Agent → delegated Insurance Agent → services, with the recovered state. |

Officer roles: `OFF-0101` is the residency case officer (recovery). `OFF-0900` is the supervisor (the **Revocation** tab). `OFF-0950` is the read-only auditor: the API refuses its actions with 403, which is useful to show role separation.

## 4. If something goes wrong

| Problem | Fix (≤ 30 s) |
|---|---|
| Backend or frontend will not start | Present slide 4 and the `submission/screenshots/` folder. They are genuine captures of the same flow |
| "Session expired or was revoked" notice on /soc | Sign in again; the work is kept |
| Forgot an officer password | Re-run `officers set-password OFF-0101` (this ends existing sessions) |
| Case stuck after step 6 | It is waiting in **Approvals**: approve it, resolve the incident, then **Continue my case** |
| Want a clean slate | **New demo session** (top right of the presenter panel). Nothing is deleted |
| Venue Wi-Fi down | Nothing is needed. The default planner runs offline. If a model was configured and is unreachable, the portal falls back to the labelled offline planner before any gateway step |
| Judge asks for a live AI model | Explain honestly: no model credential was configured and no live model run is claimed. The *Real-model injection test* button reports "not run" instead of faking a result |

## 5. Do not

- Do not type real personal data into the portal. It is a synthetic, developer-mode demo with no citizen login.
- Do not show terminals that contain officer passwords.
- Do not describe the benchmark as government statistics, or the prototype as production-ready.
