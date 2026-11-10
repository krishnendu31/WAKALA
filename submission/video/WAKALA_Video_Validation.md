# WAKALA 2.0 — Video validation

Validated on 10 Nov 2026 after the final export. Raw outputs are in `source/meta/` (`timeline.json`, `speech_check.json`) and `source/capture/run_log.json`. Inspected frames are in `source/validation_frames/`.

## 1. Files and format (ffprobe)

| Check | `WAKALA_Final_Demo_1080p.mp4` | `WAKALA_Final_Demo_Silent.mp4` |
|---|---|---|
| Exists, non-zero | yes · 27.3 MB | yes · 24.8 MB |
| Video | H.264 High, yuv420p, **1920×1080**, square pixels (16:9) | same |
| Frame rate | **30/1** (2,934 frames) | **30/1** (2,935 frames) |
| Duration | **97.8 s** (within 90–120 s) | 97.8 s |
| Audio | AAC-LC 48 kHz stereo, integrated loudness −15.9 LUFS, LRA 3.3 LU | **none** (checked: no audio stream) |
| Subtitles | burned in (bottom band) + `WAKALA_Video_Subtitles.srt` (22 cues) | none burned in (for live narration) |
| Watermark / music | none / none | none / none |

## 2. Playback-quality checks

| Check | Result |
|---|---|
| Black frames (blackdetect, ≥0.1 s) | 0 in both files |
| Frozen video ≥ 4 s (freezedetect) | 0 in both files. Every shot has a slow zoom, and cross-fades join shots |
| Long silences in the narrated file (≥ 2 s at −40 dB) | One: 95.6–97.8 s, the planned quiet ending on the closing card. No gaps inside scenes |
| Narration completeness | All 17 narration sentences are on the timeline (`meta/timeline.json`). Total speech is 82.2 s |
| Intelligibility | Each clip was transcribed by the local Windows speech recognizer (`source/check_speech.ps1`): **86% of script words recognised overall**, 64–100% per sentence. The lowest is the numbers sentence, because the recognizer writes "720" for "seven hundred and twenty". This is an automated proxy, not a human listening test |
| Subtitle sync | Subtitles use the measured length of each voice clip; long sentences are split in two at a natural break |
| Subtitles never cover the application | Confirmed on every inspected frame: the app window ends at y = 838, the caption band is at 860–936 and subtitles sit at about 1000–1062 |
| Frames inspected | First, middle and last frames; the middle of all 16 shots; all 15 cross-fades; the silent version's first, middle and last frames. Bugs found and fixed: (1) all shots first rendered the title card, a stage-renderer reload bug; (2) the evidence card's source line overlapped its tiles; (3) double dimming on shots with two outlines |
| Ends with WAKALA identity | Yes: logo, the three messages, the tagline and the disclosure "Fictional government service prototype · Synthetic data · Offline deterministic agent workflow" |
| Real-time playback | **Not done by a person.** I could not watch or listen in real time. The checks above are automated plus frame inspection. **Please watch the video once with sound before judging** |

## 3. Security outcomes vs the real backend (one captured run)

Captured by `source/capture_run.js` through the real guided-demo UI in demo session `DEMO-DF18B2`, starting from **Restart demo**.

| Video claim | Backend evidence (`source/capture/run_log.json`) | Match |
|---|---|---|
| Normal service: authorized actions completed | Case `CASE-FC067A7C` reached **COMPLETED** with **6** allowed actions by the Residency, Insurance and Payment Agents. AED 500.00 went to `SYNTH-GOV-TREASURY-0001` | ✓ |
| Separate test case, deliberately triggered | Case `CASE-E56A7592` was opened by `/api/portal/scenes/incident`, separate from the normal case | ✓ |
| Unauthorized access blocked; authorized for Mariam, not another citizen | One **denied** decision: Insurance Agent, `insurance.verify_case_eligibility`, reason codes `DENY_SCOPE_VIOLATION` and `DENY_CASE_SCOPE_VIOLATION`, with the message "…authorized to check insurance for Mariam, not another citizen's record (C-1003)" | ✓ |
| No protected data returned | The gateway decision was *denied*; denied requests are never dispatched (a tested backend invariant). The insurance step stayed paused and nothing was charged | ✓ (inferred from the denial, as the UI states) |
| Officer signs in, reviews, reassigns | Real sign-in as OFF-0101 through the form, then incident `INC-652FFFFF` (CROSS_CITIZEN_ACCESS, high). Mark under review, reassign to AGT-INS-002 and resume were each confirmed in the UI | ✓ |
| Required approval before continuing | The step was held, then **Approve & re-authorize**, then **Resolve incident**, then continue: the backend's required order | ✓ |
| Replacement agent completed the task | Standby agent action **allowed**: "the Insurance Agent (standby) was authorized to check insurance for Mariam's case" | ✓ |
| Mariam's service recovered | Case `CASE-E56A7592`: **COMPLETED**, recovery_status **recovered**, incident **resolved** | ✓ |
| Unrelated citizen unaffected | Omar Al Mansoori, case `CASE-26AEFC54`: **COMPLETED**, recovery_status none | ✓ |
| Audit trail intact | Audit chain **valid**, 948 events (cumulative demo database) | ✓ |
| 1,200 tests · 0/720 · 0/480 · baseline 624/720 | `evidence/phase5/summary.json` (also served by `/api/evidence/summary` during capture) | ✓ |
| Recovery 2/20 → 20/20 (5 repeats) · 50/50 | `evidence/phase7/recovery_repeatability.json` | ✓ |

## 4. Credentials and privacy

- The only sign-in screenshot was taken **before** the password was typed, and the field is empty in the video.
- The password was read from a local file outside the repository by the capture script. It was never printed, logged or committed.
- A scan of `submission/`, `frontend/src` and `docs/` for the password value found **0 matches**.
- No real personal data: all citizens, entities, accounts and payments are synthetic and labelled as such on screen. Officer names are fictional.
- **Side effect:** with the owner's approval, the OFF-0101 development password was re-issued to make this capture. The previous OFF-0101 password no longer works. Re-issue it before a live demo: `cd backend` then `.venv\Scripts\python -m app.devtools.cli officers set-password OFF-0101`.

## 5. Honest limitations

- **Synthetic voice.** The narration uses the built-in Windows voice (Microsoft Zira). It is clear but sounds synthetic, so a human recording is recommended (see `WAKALA_Video_Script.md`). The silent version is ready for a live speaker.
- **Stills, not screen motion.** The video uses real screenshots of each state with gentle zooms and cross-fades, rather than continuous screen recording of clicks.
- **No live AI model.** The video and the prototype use the labelled deterministic offline planner. No live LLM behaviour or government integration is shown or claimed.
- **Understandable without explanation:** this is a design goal, not something tested with real viewers.
