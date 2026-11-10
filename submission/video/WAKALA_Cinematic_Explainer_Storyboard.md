# WAKALA 2.0 — 60-second cinematic explainer: storyboard (as built)

**Files**
- `WAKALA_Cinematic_60s.mp4`: voice and burned-in English subtitles.
- `WAKALA_Cinematic_60s_Silent.mp4`: no audio and no subtitles, for a live speaker.
- `WAKALA_Cinematic_Subtitles.srt`: the subtitle file.

**Format:** 60.000 s, 1920×1080 at 16:9 with square pixels, H.264 High, yuv420p, 30 fps (1,800 frames). The narrated version has 48 kHz AAC stereo.

**Two kinds of footage, labelled on screen**
- **Conceptual illustrations** (gold "Illustration" chip plus a "CONCEPTUAL ILLUSTRATION" tag): animated scenes drawn locally in `source_cinematic/ill.html` and rendered frame by frame. No cinematic clips were supplied (`submission/video/cinematic/` did not exist), so these were built on request. They are not product UI and not government footage.
- **Genuine prototype footage** (red or navy "Real prototype" chip, plus "Real prototype capture · fictional citizens · synthetic data"): screenshots of the running WAKALA prototype, reused from the verified capture session of the 60-second product film (`source60/capture/`, demo session `DEMO-15A583`; see `WAKALA_60s_Verification.md`). They show the real blocked decision, the officer intervention and the completed recovery.

**Narration:** 109 words, spoken by the local Windows text-to-speech voice (Microsoft Zira); no online service was used. It is clear but synthetic, so a human recording is recommended. The script is in `source_cinematic/narration.json`, and the timings are in `source_cinematic/meta/timeline.json`.

| Time | Beat | Shot | Source | Lower third | Narration |
|---|---|---|---|---|---|
| 0:00–0:11 | 1 · Agents collaborate | Mariam's request flows to three agents and their services; gold checks appear | Illustration A | Illustration · Government AI agents collaborate on citizen services | "Across government, AI agents are beginning to work together on citizen services: checking eligibility, sharing tasks, and collecting fees." |
| 0:11–0:20 | 2 · A legitimate agent oversteps | The Insurance Agent turns red and a dashed line reaches for "Another citizen's record · C-1003" | Illustration B | Illustration · A legitimate agent reaches for the wrong citizen's record | "But what happens when a legitimate agent, with a genuine identity, reaches for another citizen's record, one it was never authorized to see?" |
| 0:20–0:23.5 | 3 · WAKALA checks authority | A signed mandate ("Case: Mariam only") appears; the gateway shield turns red: **BLOCKED** | Illustration C | Illustration · WAKALA checks signed, case-specific authority | "WAKALA checks every request against signed, case-specific authority." |
| 0:23.5–0:28 | 3 · Real blocked decision | Guided demo step 2: **Unauthorized access blocked.** | Real `g05_blocked` | Real prototype · UNAUTHORIZED ACCESS BLOCKED | "In our working prototype, the request is blocked…" |
| 0:28–0:32 | 3 · Decision facts | Attempted action · denied by the gateway · not executed · no protected data · incident | Real `g05_blocked` (zoom) | Real prototype · Valid agent. Invalid action. No protected data returned. | "…before any protected data is returned." |
| 0:32–0:35 | 4 · Officer restores authority | An authorized officer card appears; the agent is replaced by a standby agent | Illustration D | Illustration · An authorized officer restores valid authority | "An authorized security officer reviews the incident," |
| 0:35–0:38.4 | 4 · Real investigation | Security Operations: gateway evidence and the delegated authority chain (the affected mandate revoked, the roots still authorized) | Real `soc08_investigation` | Real prototype · The officer reviews the incident and the affected authority | "contains only the affected authority," |
| 0:38.4–0:42 | 4 · Real reassignment | "Replace only the agent that overstepped": done, confirmed by WAKALA | Real `g09_intervention` | Real prototype · Task handed to the trusted standby agent | "and hands the task to a trusted standby agent." |
| 0:42–0:47.5 | 5 · Real recovery | Mariam: completed, recovered after a security review; Omar (unrelated): completed | Real `g10_recovered` | Real prototype · Mariam's service completed — the unrelated case continued | "After the required approval, Mariam's renewal completes safely," |
| 0:47.5–0:53 | 5 · Real audit view | Portal: every decision listed, including the blocked one | Real `p17_portal_recovered` | Real prototype · Every decision on record — the blocked one included | "every decision stays on record, and another citizen's application continues untouched." |
| 0:53–1:00 | 6 · Brand | WAKALA logo · VERIFY AUTHORITY. · BLOCK THE UNAUTHORIZED. · KEEP SERVICES MOVING. · tagline · disclosure | Closing card | *"Illustrations are conceptual · Prototype footage uses fictional citizens and synthetic data · Deterministic offline workflow"* | "WAKALA. Autonomous AI. Accountable actions." |

## Genuine outcomes shown (from `source60/capture/run_log.json`)

| On screen | Backend record |
|---|---|
| Unauthorized access blocked | Case `CASE-78E2166E`: Insurance Agent `insurance.verify_case_eligibility` **denied**, reason codes `DENY_SCOPE_VIOLATION` and `DENY_CASE_SCOPE_VIOLATION` ("authorized to check insurance for Mariam, not another citizen's record (C-1003)") |
| No protected data returned | Denied, so not dispatched to the protected service (backend invariant); the insurance step stayed paused |
| Officer reviewed and reassigned | Incident `INC-08A7DDD8` (CROSS_CITIZEN_ACCESS). Real officer session OFF-0101: review, reassign to AGT-INS-002, resume |
| Mariam's service recovered | `CASE-78E2166E` **COMPLETED**, recovery_status **recovered**; standby agent's action **allowed**; incident **resolved** |
| Unrelated case continued | Omar `CASE-DC10AD4B` **COMPLETED** |
| Every decision on record | The portal for `CASE-78E2166E` lists allowed, blocked and held decisions; audit chain **valid** |

`buildcine.py` refuses to build if any of these recorded outcomes is missing. No statistics appear in this film, and no passwords appear in any frame.

## Validation (final export)

| Check | Result |
|---|---|
| Duration / resolution / fps / codec | 60.000 s · 1920×1080 at 16:9 · 30 fps · H.264 High (both files) |
| Decode | 0 errors (full ffmpeg decode of both files) |
| Blank or frozen frames | blackdetect 0 · freezedetect (≥ 3 s) 0, in both files. The film opens with a 0.6 s fade-in from the pearl background |
| Scene boundaries | Frames inspected at every shot's midpoint and 0.25 s after each beat change (0:11, 0:20, 0:32, 0:42, 0:53): clean 0.5 s cross-fades, no gaps. Saved in `source_cinematic/validation_frames/` |
| Audio | −15.9 LUFS integrated, −4.5 dBFS peak, no clipping. The only pause over 1.5 s is a 1.6 s breath before the closing line |
| Narration intelligibility | Windows speech recognizer matched 83% of script words. This is an automated proxy, not a human listening test |
| Subtitles | 12 cues timed from the measured length of each voice clip. They sit in the bottom band (y ≈ 1000–1062), below the lower third, and never cover the illustrations or the app |
| Silent version | No audio stream and no subtitles; checked at 0:24 (real blocked decision) |
| Not done | **No person has watched the film in real time with sound. Please watch it once before the pitch** |

**Rebuild:** `tts.ps1`, then `buildcine.py` (needs ffmpeg and puppeteer-core). No application code, security control or evidence file was changed.
