# WAKALA — The Moment Before · storyboard (as built)

A 60-second cinematic film built around one idea: *the most important security decision happens in the moment before an action executes.*

**How the picture was made:**
- **Original 2.5D motion graphics**, about 75% of the film. They are drawn frame by frame on a canvas (`source_moment/film.html`) with layered parallax, camera travel, depth particles, glow, a slow-motion section, film grain and vignette. Every conceptual frame carries a **"CONCEPTUAL VISUALIZATION"** tag. None of it imitates WAKALA's user interface.
- **Genuine prototype captures**, about 15 s including fades. These are real screenshots from the verified capture session (`source60/capture/`, demo session `DEMO-15A583`), shown large in a gold-rimmed frame with gentle movement, and labelled **"REAL PROTOTYPE — SYNTHETIC DATA"**. They are stills of real states, not screen recordings.
- **No AI-generated video.** No text-to-video tool was available in this environment. `WAKALA_Asset_Prompts.md` has shot prompts if photoreal plates are wanted later.

**Palette:** sapphire navy, midnight blue, warm gold, emerald teal, pearl highlights, with red only for the unauthorized request.

| Time | Scene | What happens on screen | Movement and craft | Sound |
|---|---|---|---|---|
| 0:00–0:10 | **1 · Autonomous government** | Sunrise over a contemporary, UAE-inspired waterfront skyline (procedural and generic, not a specific real skyline). Gold, teal and blue light paths arc between towers, with pulses travelling along them. | Fade up from black, a slow lateral camera travel with three parallax layers, a reflecting water shimmer, then a push up into the sky that dissolves into the network | A warm D-major-9 pad with a high shimmer |
| 0:09–0:20 | **2 · The unexpected request** | Abstract depth space. Mariam's glowing identity record sends requests through three agents to their services (blue). At 0:13 a second branch leaves the *same* Insurance Agent toward another citizen's locked record and shifts **blue → amber → red**. | The camera follows the branch head; floor perspective and dust parallax give depth | The pad darkens, a slow heartbeat pulse quickens, a filtered riser builds |
| 0:20–0:32 | **3 · The moment before** *(signature)* | Time slows: dust nearly stops while the authorized blue flows keep moving at normal speed. The **authorization boundary** assembles itself: a perpendicular plane of interlocking gold hexagons in an elliptical frame. Three checks travel the request path: **IDENTITY VERIFIED** ✓ (teal) · **AUTHORITY CHECKED** ✓ (teal) · **CASE MISMATCH** ✕ (red). The rim turns red; at **0:27.45** the request stops at the plane, shock rings ripple and it dissolves. **WAKALA / وكالة** is revealed while the network keeps working. | Push-in to 1.7×, desaturating vignette, then a pull-back reveal | A low drone and a held high tone, a hush (−29 dB) just before the block, then a restrained sub-thump impact with a glass ping and a long tail |
| 0:32–0:40 | **4 · Real prototype: the proof** | Genuine capture of guided demo step 2, **"Unauthorized access blocked."** Attempted action, *denied by the gateway*, not executed, no protected data returned. At 0:36 a closer crop makes the decision facts readable from a distance. | The frame drifts and scales gently; a red rim glow | A hushed low pad |
| 0:40–0:49 | **5 · Accountable recovery** | The red branch stays isolated; the original agent is greyed out with **AUTHORITY CONTAINED** and a gold containment ring. An **authorized officer** appears as a silhouette in an operations room with window bokeh and console light. A gold signature stroke travels to a new **REPLACEMENT AGENT**; a new emerald connection forms to Mariam's record (**service resumed**). Other citizens' flows continue throughout, and gold motes rise. | A slow glide along the emerald path | A warm progression D – G – Bm – A – D with soft chimes, swelling |
| 0:49–0:55 | **6 · Real prototype: recovery** | Genuine captures: Mariam's case **Completed — recovered after a security review** and the unrelated citizen's case **Completed**. **BLOCKED. RECOVERED. ACCOUNTABLE.** appears word by word, with factual lines underneath. | The cards drift up; the words slide in | The progression continues |
| 0:55–1:00 | **7 · Final reveal** | Pull back across the city, now lit by blue and emerald service paths, then a dissolve to a neutral pearl background. The **genuine WAKALA logo** draws on, followed by **WAKALA \| وكالة · Autonomous AI. Accountable Actions.** Footer: *Conceptual visualization + working synthetic-data prototype · No real government integration* | Camera pull-back, then a logo stroke animation | A resolving D-major chord and a logo chime |

**Subtitles:** 12 cues timed from the measured voice clips. They sit in a soft navy band at the bottom (40 px), clear of the real-prototype frames and the main motion. They are not burned into the silent version.

**Real-footage outcomes:**
- **Blocked request:** case `CASE-78E2166E`, Insurance Agent `insurance.verify_case_eligibility` **denied** (`DENY_SCOPE_VIOLATION`, `DENY_CASE_SCOPE_VIOLATION`).
- **Mariam's recovery:** the same case finished **COMPLETED**, recovery_status **recovered**, incident **resolved**.
- **Unrelated case:** `CASE-DC10AD4B` **COMPLETED**.

Source: `source60/capture/run_log.json`, also summarised in `WAKALA_60s_Verification.md`.

**Rebuild:**

```bash
python source_moment/score.py
```

```bash
powershell -ExecutionPolicy Bypass -File source_moment/tts.ps1
```

```bash
node source_moment/render_film.js 0 300 build/seg/seg0.mp4
```

Repeat the render command for each of the six 300-frame segments, then:

```bash
python source_moment/build_moment.py
```
