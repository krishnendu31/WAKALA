# WAKALA 2.0 — Video storyboard (as built)

Every app shot is a **real screenshot** of the running prototype from one coherent guided-demo run. The run was captured on 10 Nov 2026 at 19:22 UTC in demo session `DEMO-DF18B2` by `source/capture_run.js` in headless Edge (1440×810 CSS layout at 4/3 scale = 1920×1080 pixels).

Shots are cropped and gently zoomed. Outlines mark real elements, placed from the element positions the browser reported. No UI was drawn or edited. Title, evidence and closing cards are graphics; the evidence card's numbers are read from the committed benchmark files by `source/build_video.py`.

**Layout of every app shot:**
- App window: 1440×810 at the top.
- Caption band below it: scene chip, headline, and "Real prototype capture · fictional citizens · synthetic data".
- Subtitles in their own band at the bottom.
- Nothing is drawn over the application.

| # | Shot | Source capture | Crop / focus | Caption | Time |
|---|---|---|---|---|---|
| 1 | Title card | — (graphic) | — | "AI agents can now act on behalf of citizens. But who verifies their authority?" | 0:00 |
| 2 | s2a | `02a_normal_start.png` (`/demo`, step 1) | Request quote | Mariam asks the AI assistant to renew her residency permit | 0:12 |
| 3 | s2b | `02b_normal_done.png` | "What happened" card, 6 allowed decisions, AED 500 to the synthetic treasury | Authorized actions completed — 6 agent actions checked and allowed | 0:18 |
| 4 | s3a | `03a_attack_ready.png` (step 2) | Scenario panel (red) | Separate test case · A deliberately triggered security scenario | 0:26 |
| 5 | s3b | `03b_blocked.png` | Blocked panel (red) | UNAUTHORIZED ACCESS BLOCKED | 0:31 |
| 6 | s3c | `03b_blocked.png` (zoom) | Decision facts: denied · not executed · no protected data · incident HIGH open | Authorized for Mariam's case, not another citizen · no protected data returned | 0:38 |
| 7 | s4a | `04a_officer_signin.png` (step 3, **password field empty**) | Officer panel | Security review required — an authorized officer signs in | 0:44 |
| 8 | s4b | `04b_incident.png` | Incident card | The officer reviews the incident | 0:47 |
| 9 | s4c | `04b_incident.png` (zoom) | Technical details: root mandates ACTIVE, `SUSPEND_MANDATE` on the delegated mandate only, applied responses | Authority chain checked: only the delegated mandate was suspended | 0:51 |
| 10 | s4d | `04c_reassigned.png` | "Replace only the agent that overstepped" — done | Legitimate work reassigned to the standby Insurance Agent | 0:54 |
| 11 | s5a | `05a_held.png` (step 4) | "Officer approves the held step" (amber) | The sensitive step waits for officer approval | 0:57 |
| 12 | s5b | `05b_recovered.png` | Mariam's card (Completed — recovered) and Omar's card (Completed) | Mariam's renewal completed — recovered after a security review | 1:00 |
| 13 | s5c | `05c_results.png` (step 5) | Result cards | Unauthorized action blocked · Legitimate service recovered · Unrelated citizen unaffected | 1:04 |
| 14 | s6a | `06_evidence.png` (`/evidence`) | Back-to-back recovery panel (2/20 → 20/20, repeats, 50/50) | The real Security Evidence page — synthetic benchmark | 1:08 |
| 15 | s6b | — (evidence card graphic) | 1,200 · 0/720 (baseline 624/720) · 0/480 · 2/20 → 20/20 (5 runs) · 50/50 · "Synthetic" | What the synthetic tests showed | 1:14 |
| 16 | Closing | — (graphic) | — | Verify authority. Stop unauthorized actions. Keep services moving. · WAKALA — Autonomous AI. Accountable Actions. · disclosure | 1:23–1:38 |

**Transitions and audio:**
- Transitions are 0.6 s cross-fades, with a slow zoom of 1.5–3.5% per shot.
- There is no music.
- The narration is placed per sentence from the real voice clips, and the subtitles use the same timing.

**Rebuild:** run `source/capture_run.js` (needs a working officer credential file), then `source/tts.ps1`, the trim step, and `source/build_video.py`. The capture step uses the live backend and starts a new demo session; nothing is deleted.
