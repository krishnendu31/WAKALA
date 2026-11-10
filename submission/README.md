# WAKALA وكالة — Final Hackathon Submission

**Autonomous AI. Accountable Actions.**
UAE Hackathon 2026 · Track 2 Pioneers · Challenge #27 *Secure Agentic AI for Government Services*.
Submission deadline: **11 November 2026, 10:00 AM UAE time.** Format: 3-minute pitch + 2 minutes of questions.

WAKALA is an independent authorization gateway for government AI agents. It provides signed agent identities, citizen-case-bound mandates, verified delegation chains, Behaviour Watch, selective officer intervention, safe recovery, a tamper-evident audit trail, Document Shield, Attack Lab, citizen AI-activity receipts, Shadow Mode, and draft-only Policy Drafting.

> **Status:** a working prototype on **synthetic data**. It is **not production-ready**, it is **not integrated with any government system**, and **no live AI model run has been verified**. The demo uses a labelled deterministic offline planner.

## Contents

| # | File | What it is |
|---|---|---|
| 1 | `WAKALA_Pitch_Deck.pptx` | **Final pitch deck**: 8 slides, editable PowerPoint, speaker notes with timings |
| 1 | `WAKALA_Pitch_Deck.pdf` | PDF export of the deck |
| 2 | `01_Pitch_Script.md` · `pdf/01_Pitch_Script.pdf` | Three-minute script with per-slide timing (391 words ≈ 2:36) |
| 3 | `02_Business_Model_Canvas.md` · `pdf/02_Business_Model_Canvas.pdf` | Business Model Canvas: government customers, proposed licensing |
| 4 | `03_Pilot_Roadmap_90_Days.md` · `pdf/03_Pilot_Roadmap_90_Days.pdf` | 90-day pilot: observe → enforce → decide |
| 5 | `04_Evidence_Brief.md` · `pdf/04_Evidence_Brief.pdf` | Every figure traced to its source; synthetic vs official data |
| 6 | `05_Demo_Runbook.md` · `pdf/05_Demo_Runbook.pdf` | Live demo steps with real routes and buttons, plus fallbacks |
| 7 | `06_Judge_QA.md` · `pdf/06_Judge_QA.pdf` | 20 prepared answers |
| 8 | `video/WAKALA_Final_Demo_1080p.mp4` · `video/WAKALA_Final_Demo_Silent.mp4` | 1:38 demo video of one real run (narrated with a local synthetic voice + subtitles; silent version for live narration). Script, storyboard, SRT and validation in `video/` |
| 9 | `video/WAKALA_60s_Final.mp4` · `video/WAKALA_60s_Silent.mp4` | Exactly 60 s film of ten real features (one demo session; synthetic voice + subtitles; silent version). Narration, storyboard, SRT and verification in `video/` |
| 10 | `video/WAKALA_Cinematic_60s.mp4` · `video/WAKALA_Cinematic_60s_Silent.mp4` | 60 s cinematic explainer: labelled conceptual illustrations plus genuine prototype footage of the blocked decision and recovery. Storyboard and SRT in `video/` |
| — | `screenshots/` | 10 genuine captures of the running prototype (`CAPTURE_LOG.json` records the run) |
| — | `source/` | Deck and document build scripts and the shared print stylesheet |

## How to open the pitch deck

- **Present:** open `submission\WAKALA_Pitch_Deck.pptx` in Microsoft PowerPoint and press F5. Use Presenter View (Alt+F5) to see the speaker notes and timings.
- **No PowerPoint:** open `submission\WAKALA_Pitch_Deck.pdf` in any browser or PDF reader.
- Every text box, shape and chart is editable. Screenshots are images.

## Verified figures used in the pitch

All figures are from the synthetic prototype benchmark, not government statistics. Sources are in `04_Evidence_Brief.md`.

| Measure | Result |
|---|---|
| Unauthorized operations executed, full WAKALA | 0 / 720 |
| Legitimate requests denied, full WAKALA | 0 / 480 |
| Intentionally weak role-only baseline, unauthorized executed | 624 / 720 |
| Attack Lab | baseline 7 / 8 executed, WAKALA 0 / 8, 1 denied by both |
| Shared-environment recovery | 2 / 20 → 20 / 20 (5 repeats), 50 / 50 long run |
| Backend tests | 493 passed |
| Demo | 12 / 12 steps verified; 15 pages render |

## Rebuild

Deck (needs Node with `pptxgenjs`, `sharp`, `react`, `react-dom`, `react-icons` on `NODE_PATH`):

```bash
node submission/source/build_deck.js
```

PDF of the deck (needs Microsoft PowerPoint):

```bash
powershell -ExecutionPolicy Bypass -File submission\source\export_pdf.ps1
```

Document PDFs (needs Python `markdown` and Microsoft Edge):

```bash
python submission/source/build_docs.py
```

## Final submission checklist

- [x] Deck: 8 slides, editable PPTX, speaker notes, genuine screenshots, verified figures
- [x] Deck PDF export
- [x] Script fits 3:00 (391 words)
- [x] Business Model Canvas, 90-day roadmap, evidence brief, runbook, judge Q&A
- [x] No credentials, keys or officer passwords in `submission/`
- [ ] Add team member names to slide 1 if the organisers require them
- [ ] Rehearse with a stopwatch at least twice
- [ ] Upload the deck (PPTX and PDF) through the official submission channel **before 10:00 AM on 11 Nov 2026**. Upload this pack too if the organisers accept extra files
- [ ] Before pitching, run the pre-flight in `05_Demo_Runbook.md` §2
