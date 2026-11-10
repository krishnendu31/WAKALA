# WAKALA — The Moment Before · narration

**Film:** `WAKALA_The_Moment_Before_60s.mp4`. The silent version is `WAKALA_The_Moment_Before_Silent.mp4`, and the subtitles are in `WAKALA_The_Moment_Before_Subtitles.srt`.

**Voice:** local Windows text-to-speech (Microsoft Zira), with warm EQ, gentle compression and a light room reverb. **It is not a professional human voice.** No natural-sounding voice engine was available offline, and the script was not sent to any online service. For the pitch, a team member reading this script over the silent version, or a recorded human voice, will sound better (see below).

**Length:** 102 spoken words. Each line was timed to the cut, not forced into it.

| Time | Scene | Line |
|---|---|---|
| 0:00.8 | 1 · Autonomous government | Imagine government services where AI agents don't just respond. |
| 0:05.0 | | They act, collaborate, and complete tasks for citizens. |
| 0:11.2 | 2 · The unexpected request | But even a trusted agent can attempt an action it was never authorized to perform. |
| 0:20.1 | 3 · The moment before | WAKALA verifies who the agent is, what authority it was given, and whether this specific action is permitted. |
| 0:27.0–0:27.45 | | *(hush; the impact lands at 0:27.45 as the request stops at the boundary)* |
| 0:27.7 | | If it exceeds that authority, WAKALA stops it, before execution. |
| 0:32.6 | 4 · Real prototype: the proof | And this isn't just a concept. Our working prototype enforces that decision through a real authorization gateway. |
| 0:40.7 | 5 · Accountable recovery | An authorized officer can contain the incident, restore valid authority, and let the legitimate service continue. |
| 0:50.2 | 6 · Real prototype: recovery | Security, without unnecessary disruption. |
| 0:55.5 | 7 · Reveal | WAKALA. Autonomous AI. Accountable actions. |

## Why each line can be said

| Line | Basis |
|---|---|
| "Even a trusted agent can attempt an action it was never authorized to perform" | The scene is labelled a conceptual visualization. In the prototype, this is a deliberately triggered synthetic scenario (`/api/portal/scenes/incident`). Nothing claims a live AI model chose to do it |
| "Who the agent is, what authority it was given, and whether this specific action is permitted" | The gateway verifies the agent's signed identity, its case-bound mandate and delegation chain, and the action's scope. The real denial reason codes were `DENY_SCOPE_VIOLATION` and `DENY_CASE_SCOPE_VIOLATION` |
| "Our working prototype enforces that decision through a real authorization gateway" | Real capture of case `CASE-78E2166E`: the gateway decision was **denied** before execution (`source60/capture/run_log.json`) |
| "An authorized officer can contain the incident, restore valid authority…" | Real officer session OFF-0101 marked the incident under review, reassigned the task to standby agent AGT-INS-002 and resumed the case. The standby agent's later action was **allowed** |
| "Security, without unnecessary disruption" | Mariam's case **COMPLETED** (recovered); unrelated case `CASE-DC10AD4B` **COMPLETED** |

## Reading it live over the silent version

Speak each row at its start time, warmly and unhurried (about 115–125 words per minute). Leave the hush at 0:27. Let the closing card breathe after "Accountable actions."
