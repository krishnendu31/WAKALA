# WAKALA 2.0 — Video narration script

**Video:** `WAKALA_Final_Demo_1080p.mp4` (narrated, English subtitles burned in) and `WAKALA_Final_Demo_Silent.mp4` (no audio, no subtitles, for live narration).
**Length:** 1:37.8 · 1920×1080 · 30 fps.
**Voice:** local Windows text-to-speech (Microsoft Zira, normal rate). No online voice service was used. The voice is clear but synthetic. **A human voice recording is recommended for the final presentation** (see "Recording your own voice" below).

Spoken words: 210. Time ranges come from `source/meta/timeline.json`. Scenes overlap by 0.6 s cross-fades.

| Scene | Time | On screen | Narration |
|---|---|---|---|
| 1 · The challenge | 0:00–0:13 | WAKALA title card: *"AI agents can now act on behalf of citizens. But who verifies their authority?"* | As government services become more autonomous, AI agents can access records, delegate tasks and carry out transactions. But every action must stay within verified authority. |
| 2 · Normal service | 0:12–0:27 | Real guided demo, step 1: Mariam's request → **"Authorized actions completed — 6 agent actions checked and allowed"** | Meet Mariam, a fictional citizen. She asks to renew her residency permit. Several AI agents work together on her application, and WAKALA checks every protected action before it runs. |
| 3 · The unauthorized action | 0:26–0:45 | Step 2: "Separate test case" → **"UNAUTHORIZED ACCESS BLOCKED"** → the decision facts (denied, not executed, no protected data returned) | Now, in a separate test case, we deliberately trigger a security scenario. The Insurance Agent requests another citizen's record. Its identity is genuine, but this action exceeds its authority. WAKALA blocks the request before any protected data is returned. |
| 4 · Human intervention | 0:44–0:58 | Step 3: "Security review required" sign-in (password field empty) → incident → authority chain and applied responses → reassignment to the standby Insurance Agent | Blocking the request is only the beginning. An authorized security officer signs in, reviews the incident, and reassigns the legitimate work to a replacement agent. The other agents keep their authority. |
| 5 · Safe recovery | 0:57–1:08 | Step 4: held step awaiting approval → Mariam's case completed, recovered after review, with Omar's case completed → step 5 results | After the required officer approval, the application continues. Mariam's renewal completes, and another citizen's application is unaffected. |
| 6 · Measured evidence | 1:07–1:24 | Real Security Evidence page → evidence card from the benchmark files, labelled **synthetic prototype benchmark** | In twelve hundred controlled synthetic tests, WAKALA allowed none of the seven hundred and twenty unauthorized operations, and wrongly denied none of the legitimate ones. Repeated recovery tests also completed under the tested conditions. |
| 7 · Closing | 1:23–1:38 | WAKALA logo · "Verify authority. Stop unauthorized actions. Keep services moving." · tagline · disclosure line | WAKALA is not another government AI assistant. It is the security layer that makes autonomous government services accountable. WAKALA. Autonomous AI. Accountable actions. |

## Wording choices (accuracy)

- **"A deliberately triggered security scenario."** The cross-citizen request is a scripted synthetic test (`/api/portal/scenes/incident`). The narration never says the AI chose to attack.
- **"Before any protected data is returned."** The gateway decision for the request was *denied*, and a denied request is never dispatched to the protected service. The insurance step stayed unfinished and no data was returned.
- **"Wrongly denied none of the legitimate ones"** means 0 of 480 legitimate requests. **"Repeated recovery tests also completed under the tested conditions"** refers to 20/20 in 5 repeats and 50/50 in the extended run. Both are on screen with their source files.
- The video's text says everything is fictional and synthetic, and that the planner is an offline deterministic workflow, not a live AI model.

## Recording your own voice (recommended)

1. Play `WAKALA_Final_Demo_Silent.mp4` and read the narration above, one scene per row, starting each at the time shown.
2. Or play `WAKALA_Video_Subtitles.srt` alongside the silent video as a teleprompter: each subtitle is one phrase at its exact time.
3. To replace the voice track, save your recording as `narration_human.wav` (48 kHz) and run:
   ```bash
   ffmpeg -i WAKALA_Final_Demo_Silent.mp4 -i narration_human.wav -vf "ass=source/meta/subtitles.ass" -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest WAKALA_Final_Demo_1080p_human.mp4
   ```
   Re-time `source/meta/subtitles.ass` if your pacing differs.
