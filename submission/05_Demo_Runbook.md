<div class="cover"><div class="eyebrow">UAE Hackathon 2026 · Challenge #27</div><h1>Demo runbook <span class="ar">وكالة</span></h1><p>Run the live prototype for Q&amp;A, a judges' booth or a backup. The 3-minute pitch uses the slide 4 screenshots and needs no live demo. First-time visitors should use the <b>Guided Demo</b> (§3).</p></div>

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

Rehearse the whole flow below once. Then click **Restart demo** in the guided demo header so it starts clean. This deletes nothing, and the audit history is kept.

## 2. On the day (start about 15 minutes before)

| Step | Action | Check |
|---|---|---|
| 1 | Terminal 1: `cd backend` then `.venv\Scripts\python run_dev.py` | Backend starts on port 8000 |
| 2 | Terminal 2: `cd frontend` then `npm run dev` | Vite serves http://localhost:5173 |
| 3 | Open **http://localhost:5173/** | The welcome page shows "Start Guided Demo" and "Explore Security Console" |
| 4 | Optional check: open **Advanced tools** → Government AI Portal | Header shows "Enforcement engine: connected" and the assistant "deterministic offline planner (no AI model)", which needs no internet |
| 5 | Turn on Do Not Disturb; set the browser zoom to 100–110 % | |
| 6 | Have `submission/WAKALA_Pitch_Deck.pdf` open as a fallback | |

## 3. Live flow — Guided Demo (recommended, about 4 minutes)

Route: **http://localhost:5173/** → **Start Guided Demo** (or go straight to **/demo**). The demo has no console menu, only five steps.
Each step has one main button. Every status shown is read from the backend, and nothing is marked done until WAKALA confirms it.
**Technical details (optional)** in each step shows case IDs, gateway events, reason codes and the mandate chain.

| Step | Who | Click | What appears |
|---|---|---|---|
| 1 · Normal service | Citizen | **Submit Mariam's request** | Case status: Completed. 6 agent actions, each checked and allowed by WAKALA; fee recorded to the synthetic treasury. |
| 2 · Unauthorized access | Citizen | **Run the unauthorized request** | A new case for Mariam. Red **"Unauthorized access blocked."** with attempted action, decision (denied), executed (no), data returned (none) and incident status. Case paused; nothing charged. |
| 3 · Officer intervention | Officer | Sign in on the right (**OFF-0101** + password), then **Mark incident under review** → **Reassign the insurance check to AGT-INS-002 (standby)** → **Resume Mariam's case** | The panel says "Security review required. Switch to the officer console." Each item is ticked only when WAKALA confirms it. |
| 4 · Safe recovery | Citizen ↔ Officer | **Continue Mariam's renewal** → **Approve & re-authorize** → **Resolve incident** → **Continue Mariam's renewal**; optionally **Continue Omar's case** | The held step is re-authorized by the gateway and runs once. Mariam's case: "Completed — recovered after a security review". Omar's case is unaffected. |
| 5 · Results and evidence | Both | **Open Mariam's AI Activity receipt**; links to Security Evidence, Case View and Attack Lab | Final status of every case, the standby agent's action, the receipt and the synthetic benchmark (1,200 requests; 0/720 vs 624/720). |

Use **Previous step** / **Next step** to move between steps. If a call fails, a red box explains it and offers **Try again**.
**Advanced tools** (top right) opens the full console with every page below.

## 3b. Advanced flow (console pages)

Use this when a judge asks to see the full officer console. Route: **/portal** → Presenter panel ("Guided demonstration").

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
| Want a clean slate | **Restart demo** (guided demo header) or **New demo session** (portal presenter panel). Nothing is deleted |
| Guided demo says "Officer ID or password is not correct" | Re-issue the password with `officers set-password OFF-0101` and sign in again |
| A guided step shows a red "did not complete" box | Read the message, check the status shown on the page (it is read from WAKALA), then click **Try again** |
| Venue Wi-Fi down | Nothing is needed. The default planner runs offline. If a model was configured and is unreachable, the portal falls back to the labelled offline planner before any gateway step |
| Judge asks for a live AI model | Explain honestly: no model credential was configured and no live model run is claimed. The *Real-model injection test* button reports "not run" instead of faking a result |

## 5. Do not

- Do not type real personal data into the portal. It is a synthetic, developer-mode demo with no citizen login.
- Do not show terminals that contain officer passwords.
- Do not describe the benchmark as government statistics, or the prototype as production-ready.
