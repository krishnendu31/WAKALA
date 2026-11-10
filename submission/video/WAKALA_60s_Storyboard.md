# WAKALA 2.0 — 60-second film: storyboard (as built)

All app shots are **real screenshots of the running prototype**. They were taken on 10 Nov 2026, 20:27–20:30 UTC (11 Nov, UAE time), by `source60/capture60.js` (raw footage, one fresh demo session, headless Edge at 1920×1080 pixels) and `source60/capture_portal.js` (one read-only portal view). The **attack scenario uses its own synthetic case**, separate from the normal-service case, and the on-screen chip says "Separate test case".

**What was added, and what was not:**
- Shots are cropped, gently zoomed (3%) and joined by 0.4 s cross-fades.
- Outlines mark real elements at the positions the browser reported.
- Only the title and closing cards are graphics.
- Every app shot carries "Real prototype capture · fictional citizens · synthetic data".

**Screen layout:**
- App window: 1440×810 at the top.
- Caption band (lower third): y 860–936.
- Subtitles: y ≈ 1000–1062.
- Nothing is drawn over the application.

| Time | Scene | Shot | Source capture | Lower third (chip · headline) |
|---|---|---|---|---|
| 0:00 | 1 | Title card | graphic | WAKALA logo, tagline, **WHO AUTHORIZES AUTONOMOUS AI?** |
| 0:02.2 | 1 | Welcome page | `w01_welcome` (`/`) | Real prototype · WHO AUTHORIZES AUTONOMOUS AI? |
| 0:05 | 2 | Normal service result | `g02_normal_done` (`/demo` step 1) | Verified agent identity · Case-bound authority — 6 signed agent actions checked and allowed |
| 0:09.4 | 2 | Case View, delegated Insurance Agent | `d04_delegation` (`/delegation?case=…`) | Secure delegation · Residency Agent → Insurance Agent, for Mariam's case only |
| 0:14 | 3 | Blocked panel | `g05_blocked` (`/demo` step 2) | Separate test case · **UNAUTHORIZED ACCESS BLOCKED** |
| 0:20 | 3 | Decision facts (zoom) | `g05_blocked` | Gateway decision · Valid agent. Invalid action. No protected data returned. |
| 0:25 | 4 | Behaviour Watch findings | `soc07_watch` (`/soc` → Behaviour Watch) | Detect · Behaviour Watch · Cross-citizen access flagged as an incident |
| 0:28.2 | 4 | Investigation: gateway evidence + authority chain | `soc08_investigation` (`/soc` → Incidents) | Contain · Gateway evidence and the affected delegated mandate |
| 0:31.6 | 4 | Officer reassigns to standby | `g09_intervention` (`/demo` step 3, signed-in officer) | Authorized human review · Signed-in officer reassigns the task to the standby agent |
| 0:35 | 5 | Mariam + Omar completed | `g10_recovered` (`/demo` step 4) | Legitimate service recovered · Unrelated case unaffected — both completed |
| 0:38.2 | 5 | Portal: every decision listed | `p17_portal_recovered` (`/portal`) | Traceable · Every decision recorded — including the blocked one |
| 0:41.1 | 5 | Citizen AI Activity receipt | `g12_receipt` (`/demo` step 5) | Citizen AI Activity · Privacy-filtered receipt built from the audit trail |
| 0:44 | 6 | Attack Lab, all 8 | `a13_attack_lab` (`/attack-lab`, run LAB-75C9885B) | 8 security scenarios · Weak baseline executed 7 · WAKALA 0 · 1 denied by both |
| 0:47.6 | 6 | Document Shield verdict | `ds14_document` (`/documents`, hidden white-text sample) | Document injection detection · Hidden white-text instruction found — PDF quarantined |
| 0:51 | 7 | Shadow Mode tiles | `sh15_shadow` (`/shadow`) | Shadow Mode for safer pilots · Observes copies only — nothing executed; flags policies to tune |
| 0:54 | 7 | Security Evidence | `ev16_evidence` (`/evidence`) | Tested with 1,200 synthetic requests · 0/720 unauthorized executed · 0/480 wrongly denied · 50/50 recovery |
| 0:57–1:00 | 8 | Closing card | graphic | VERIFY AUTHORITY. · BLOCK THE UNAUTHORIZED. · KEEP SERVICES MOVING. · WAKALA — Autonomous AI. Accountable Actions. · *Fictional prototype · Synthetic data · Deterministic offline workflow* |

**Also captured but not used in the edit** (kept in `source60/capture/`): `g06_incident` (the guided officer view right after sign-in), `g11_results`, `sh16_enforce` (Shadow prediction matched separate enforcement) and `p03_portal` (full-page artifact, replaced by `p17`).

**Rebuild:** run `capture60.js` (needs a working local officer credential file), `capture_portal.js`, `tts.ps1`, then `build60.py`.
