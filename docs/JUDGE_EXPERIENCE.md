# Judge Experience

The opening page (`/`, also `/demo`) is one connected story on one screen: a headline, a **Live Authority Map**, the
current step with one main button, a compact status summary, a collapsed **Technical details** section and an
**Advanced Tools** panel that links to every other feature. Nothing is simulated in the browser: every state is read
from the running backend and every button calls the same endpoint the Government AI Portal and the officer console
call.

Earlier entry points are kept: the five-scene walkthrough is at `/demo/classic`, the previous welcome page at
`/welcome`, and all console pages (`/command-center`, `/soc`, `/attack-lab`, `/documents`, `/delegation`, `/shadow`,
`/policies`, `/evidence`, …) are unchanged.

## Running the demonstration (about 3 minutes)

Before presenting: start the backend (`python run_dev.py`) and the frontend (`npm run dev`), and issue the officer
password (`.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101`; it is shown once). Open
`http://localhost:5173/` and press **Restart** if an earlier run is on screen.

| Stage | Press | What the judge sees |
|---|---|---|
| 1 Normal service | **Run Normal Service** | The map lights up green: Mariam's case → Residency Agent and Payment Agent (signed case mandates), Residency → Insurance Agent (delegation), each agent → WAKALA gateway → protected services. Result: *Authorized actions completed.* Then **Next: Unauthorized Request**. |
| 2 Unauthorized access | **Test Unauthorized Request** | A **new** case for Mariam opens (the Stage 1 case stays completed). The Insurance Agent asks for citizen C-1003's record: a red **DENIED** path ends at the gateway, the insurance service stays *Not reached*, the case is *Paused for review*. Then **Next: Officer Review**. |
| 3 Officer intervention | **Sign In as Officer** (OFF-0101 + password) → **Mark Incident Under Review** → **Assign Standby Insurance Agent** → **Resume Mariam's Case** | The Standby Agent appears as *Assigned by officer*; the original Insurance Agent's authority shows as suspended or revoked (whichever the backend applied). Then **Next: Safe Recovery**. |
| 4 Safe recovery | **Continue Mariam's Service** → **Approve Held Step** → **Resolve Incident** → **Finish Mariam's Renewal** | The hand-off is held (amber) until the officer approves; WAKALA re-authorizes it and the Standby delegation turns green. The renewal completes as *Recovered*. Results list the denial, the recovery, the replacement agent's work and the unaffected unrelated case (Omar), with **View Technical Evidence**, **Explore Advanced Features** and **Restart Guided Demo**. |

The stage pills under the headline can be clicked to revisit an earlier result. A presenter can also deep-link to a
stage with `/?stage=2` (it only chooses which step is shown; it never performs an action).

## How the map updates

The map shows one case at a time (tabs switch between the normal case, the security-test case and Omar's unrelated
case). It is rebuilt every few seconds from two reads of that case:

- **Nodes** — Mariam's case (from the case record), the four agents (from their signed mandate lanes), the WAKALA
  gateway and the three fictional protected services. The gateway and the services are fixed conceptual roles.
- **Case → agent edges** — the Residency and Payment agents' signed mandates bound to this case (`mandate_refs`),
  green when the mandate verifies.
- **Delegation edges** — drawn green **only** when a stored delegation record exists. Amber while a delegation is
  held for officer approval (a real pending approval). Grey when suspended/revoked or not yet created. A denied request
  never creates a delegation edge.
- **Agent → gateway edges** — coloured by that agent's latest real gateway decision on the case: green *n allowed*,
  red **DENIED** with a block marker at the gateway, amber *held*.
- **Gateway → service edges** — green only when an allowed action reached that service.

Clicking any box opens Technical details with the agent ID, signed mandate ID, issuer, signature algorithm, the
mandate's current verification result, the last gateway decision, its reason codes and audit event ID.

## Which API supplies each state

| Displayed state | Source |
|---|---|
| Demo session, which cases belong to it | `GET /api/portal/demo`; restart: `POST /api/portal/demo/reset` (nothing is deleted) |
| Stage 1 run | `POST /api/portal/requests` |
| Stage 2 run (new case + unrelated case) | `POST /api/portal/scenes/incident` |
| Case state, gateway decisions, delegations, assignments, pending approvals, fee ledger | `GET /api/portal/cases/{id}` |
| Signed mandate lanes and verification, denied request target | `GET /api/workflow/cases/{id}/case-view` |
| Officer sign-in / identity | `POST /api/officer/session`, `GET /api/officer/me` |
| Incident, standby candidates | `GET /api/officer/incidents/{id}` |
| Review / resolve | `POST /api/officer/incidents/{id}/status` |
| Reassign, resume | `POST /api/officer/cases/{id}/reassign`, `POST /api/officer/cases/{id}/resume` |
| Held step and approval | `GET /api/officer/approvals`, `POST /api/officer/approvals/{id}/approve` |
| Continue a citizen's service | `POST /api/portal/cases/{id}/continue` |

Screenshots of one recorded run are in `submission/screenshots/judge-experience/` with `JUDGE_CAPTURE_LOG.json`.
