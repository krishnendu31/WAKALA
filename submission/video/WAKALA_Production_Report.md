# WAKALA — The Moment Before · production report

## Delivered

| File | What it is |
|---|---|
| `WAKALA_The_Moment_Before_60s.mp4` | The film: picture, original score and sound design, narration, burned-in English subtitles |
| `WAKALA_The_Moment_Before_Silent.mp4` | Picture only, with no audio and no subtitles, for a live presenter |
| `WAKALA_The_Moment_Before_Subtitles.srt` | 12 subtitle cues |
| `WAKALA_Cinematic_Narration.md` · `WAKALA_Cinematic_Storyboard.md` · `WAKALA_Asset_Prompts.md` | Script, shot-by-shot storyboard, prompts for an external generator |
| `source_moment/` | `film.html` (motion engine), `render_film.js`, `score.py`, `tts.ps1`, `build_moment.py`, `narration.json`, `meta/timeline.json`, validation frames |

All earlier video files are preserved. The previous explainer's storyboard was renamed to `WAKALA_Cinematic_Explainer_Storyboard.md` so this film could use the requested name.

## Export settings (verified with ffprobe)

| | Narrated | Silent |
|---|---|---|
| Duration | **60.000 s** (1,800 frames) | **60.000 s** (1,800 frames) |
| Video | H.264 High, **1920×1080**, square pixels, **16:9**, **30 fps**, yuv420p, TV range, BT.709, faststart | same |
| Audio | AAC-LC 224 kb/s, 48 kHz stereo; **−16.4 LUFS** integrated, LRA 7.0 LU, peak −1.5 dBFS | none |
| Size | 39.5 MB | 38.0 MB |
| Decode errors | 0 | 0 |

## What is what

| Element | Source | Authentic AI-generated video? |
|---|---|---|
| City, network, boundary, officer, reveal scenes (~75%) | **Original local 2.5D motion graphics**, rendered frame by frame on a canvas in headless Edge | **No.** No text-to-video tool was available; prompts are in `WAKALA_Asset_Prompts.md` |
| "Unauthorized access blocked" (0:32–0:40) and recovery (0:49–0:55), about 15 s with fades | **Genuine prototype captures** from the verified session (`source60/capture/`); real backend outcomes, shown in frames | No (real screenshots of real states) |
| Score and sound design | **Original**, synthesised from scratch in numpy/scipy (`score.py`); no samples or third-party music, so the team owns it | No |
| Narration | **Local Windows text-to-speech** (Microsoft Zira), warmed with EQ, compression and reverb | No. **Synthetic voice, not the "warm professional" voice requested** |
| WAKALA logo | The product's own shield mark and wordmark (same geometry as the app) | No |

## Validation

| Check | Result |
|---|---|
| Within 59–61 s | 60.000 s |
| Scene timing | 0–10, 10–20, 20–32, 32–40, 40–49, 49–55, 55–60 s, with cross-fades of 0.6–1.2 s |
| Blank or frozen frames | blackdetect (≥ 0.2 s): 0; freezedetect (≥ 2 s): 0. The opening is a 0.6 s fade up from black |
| Frames inspected | 24 frames from the final export across every scene, every boundary and the impact moment, plus the silent version (`source_moment/validation_frames/`) |
| Problems found during review, and fixed | Check labels overlapping the boundary; the officer's room hiding the contained agent; the officer's signature line looping through a label; full-range JPEG colour (re-exported as standard yuv420p) |
| Audio and subtitle sync | Subtitles come from the measured voice-clip timings (`meta/timeline.json`) |
| Pauses | No silence ≥ 1 s at −45 dB. The intended hush before the block measures −29 dB against −10 dB for the impact |
| Narration intelligibility | Windows speech recognizer matched **92%** of script words. This is an automated proxy, not a human listening test |
| Security outcomes in real footage | Match `source60/capture/run_log.json`: denied (`DENY_SCOPE_VIOLATION`, `DENY_CASE_SCOPE_VIOLATION`); Mariam's case COMPLETED and recovered; unrelated case COMPLETED |
| Honesty labels | "CONCEPTUAL VISUALIZATION" on every conceptual scene; "REAL PROTOTYPE — SYNTHETIC DATA" on both proof scenes; closing footer "Conceptual visualization + working synthetic-data prototype · No real government integration" |
| Credentials | None appear; this film uses existing captures and logged nothing new |
| Application code | Unchanged (no edits under `backend/` or `frontend/`) |
| Real-time viewing | **Not done by a person. Please watch the film once with sound on the presentation laptop and projector before the pitch** |

## Not achieved, and why

1. **Photoreal or AI-generated cinematic footage.** No text-to-video generator was connected. The film uses original motion graphics instead; `WAKALA_Asset_Prompts.md` has exact prompts if plates are generated later.
2. **Professional human narration.** Only the Windows desktop voices were available offline, and the script was not sent to an online service. The voice is clear (92% recognised) but synthetic. Recommended: read the narration live over the silent version, or record a team member and remix with `build_moment.py`.
3. **A realistic officer.** The officer is a stylized silhouette in a suggested operations room, not a photoreal person.
4. **Continuous screen recording of the prototype.** The proof scenes are real still captures of real states, framed with gentle movement, as in the earlier films.
5. **Within the 15 s real-footage target.** About 15 s including cross-fades (7.6 s fully visible block proof, 5.8 s fully visible recovery proof).
