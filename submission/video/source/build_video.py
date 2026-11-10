"""Build the WAKALA demo videos from one real captured run.

Inputs (all in this folder):
  narration.json       final narration, one entry per scene
  tts/*.wav            local-TTS narration clips from tts.ps1 (trimmed into tts_trim/ by this script)
  capture/*.png        real guided-demo screenshots + capture/run_log.json (capture_run.js)
Outputs:
  ../WAKALA_Final_Demo_1080p.mp4   narrated, burned-in English subtitles
  ../WAKALA_Final_Demo_Silent.mp4  no audio, no subtitles (for live narration)
  ../WAKALA_Video_Subtitles.srt
  build/ (stages, clips, plan.json, subtitles.ass, narration.wav, timeline.json)

Usage: python build_video.py   (needs ffmpeg/ffprobe on PATH and NODE_PATH with puppeteer-core)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parent
BUILD = HERE / "build"
FPS = 30
XF = 0.6          # cross-fade seconds
LEAD, GAP, TAIL = 0.6, 0.35, 0.9

narr = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
run = json.loads((HERE / "capture" / "run_log.json").read_text(encoding="utf-8"))
S = run["shots"]


def box(shot: str, key: str) -> dict:
    b = S[shot]["boxes"].get(key)
    if not b:
        raise SystemExit(f"missing box {shot}.{key}")
    return b


def app(shot_id, shot, crop, chip, head, focus=(), tone="", head_tone=""):
    x, y, w = crop
    return {"id": shot_id, "stage": {"kind": "app", "img": f"capture/{S[shot]['file']}", "css": S[shot]["css"],
            "crop": {"x": x, "y": y, "w": w}, "focus": list(focus), "chip": chip, "head": head, "tone": tone, "headTone": head_tone}}


def f(b: dict, tone: str = "", pad: int = 10) -> dict:
    return {**b, "tone": tone, "pad": pad}


# ---- facts from the captured run and the committed evidence files (nothing typed by hand)
nc, ic, uc = run["normal_case"], run["incident_case"], run["unrelated_case"]
assert nc["state"] == "COMPLETED" and ic["final_state"] == "COMPLETED" and ic["recovery_status"] == "recovered", "run did not complete"
assert uc["state"] == "COMPLETED" and ic["denied"] and ic["standby_actions"], "run evidence incomplete"
ev5 = json.loads((ROOT / "evidence/phase5/summary.json").read_text(encoding="utf-8"))
ev7 = json.loads((ROOT / "evidence/phase7/recovery_repeatability.json").read_text(encoding="utf-8"))
C, A = ev5["configurations"]["C"], ev5["configurations"]["A"]
frac = lambda d: f"{d['numerator']} / {d['denominator']}"  # noqa: E731
repeats = [r["shared_20"]["recovered"] for r in ev7["repeats"]]
assert all(r["numerator"] == r["denominator"] for r in repeats)
orig = ev7["original_policy_shared_20"]["recovered"]
long50 = ev7["long_shared_50"]["recovered"]

omar_box = {"x": 121, "y": 979, "w": 490, "h": 137}  # Omar's card in 05b (measured from the capture; eyebrow text is CSS-uppercased)

SCENES = {
    "s1": [({"id": "s1_title", "stage": {"kind": "title", "head": narr["scenes"][0]["headline"]}}, 1)],
    "s2": [
        (app("s2a", "02a_normal_start", (100, 150, 1240), "Normal service", "Mariam asks the AI assistant to renew her residency permit",
             [f(box("02a_normal_start", "request"))]), 1),
        (app("s2b", "02b_normal_done", (70, 200, 1300), "Normal service",
             f"Authorized actions completed — {nc['allowed_actions']} agent actions checked and allowed",
             [f(box("02b_normal_done", "result"))]), 1.5),
    ],
    "s3": [
        (app("s3a", "03a_attack_ready", (100, 150, 1240), "Separate test case", "A deliberately triggered security scenario",
             [f(box("03a_attack_ready", "panel"), "deny")], tone="deny"), 1),
        (app("s3b", "03b_blocked", (100, 170, 1240), "Gateway decision", "UNAUTHORIZED ACCESS BLOCKED",
             [f(box("03b_blocked", "panel"), "deny", 6)], tone="deny", head_tone="deny"), 1.4),
        (app("s3c", "03b_blocked", (120, 260, 1200), "Gateway decision",
             "Authorized for Mariam's case, not another citizen · no protected data returned",
             [f(box("03b_blocked", "facts"), "navy")], tone="deny"), 1.1),
    ],
    "s4": [
        (app("s4a", "04a_officer_signin", (100, 150, 1240), "Security officer", "Security review required — an authorized officer signs in",
             [f(box("04a_officer_signin", "officer"), "navy")], tone="navy"), 0.9),
        (app("s4b", "04b_incident", (600, 300, 800), "Security officer", "The officer reviews the incident",
             [f(box("04b_incident", "incident"), "deny")], tone="navy"), 1),
        (app("s4c", "04b_incident", (580, 910, 860), "Security officer", "Authority chain checked: only the delegated mandate was suspended",
             [f(box("04b_incident", "chain"), "navy", 4)], tone="navy"), 1),
        (app("s4d", "04c_reassigned", (600, 560, 800), "Security officer", "Legitimate work reassigned to the standby Insurance Agent",
             [f(box("04c_reassigned", "reassign"))], tone="navy"), 1),
    ],
    "s5": [
        (app("s5a", "05a_held", (600, 330, 800), "Safe recovery", "The sensitive step waits for officer approval",
             [f(box("05a_held", "held"), "warn")]), 1),
        (app("s5b", "05b_recovered", (0, 300, 1440), "Safe recovery", "Mariam's renewal completed — recovered after a security review",
             [f(box("05b_recovered", "citizen")), f(omar_box, "navy")]), 1.2),
        (app("s5c", "05c_results", (100, 150, 1240), "Results",
             "Unauthorized action blocked · Legitimate service recovered · Unrelated citizen unaffected",
             [f(box("05c_results", "results"))]), 1.1),
    ],
    "s6": [
        (app("s6a", "06_evidence", (280, 300, 1150), "Security Evidence", "The real Security Evidence page — synthetic benchmark",
             [f(box("06_evidence", "recovery"), "", 6)], tone="gold"), 1),
        ({"id": "s6b", "stage": {"kind": "evidence", "head": "What the synthetic tests showed", "source":
            "evidence/phase5/summary.json · evidence/phase7/recovery_repeatability.json", "tiles": [
                {"big": f"{ev5['dataset']['total_requests']:,}", "text": "synthetic authorization requests", "tone": "navy"},
                {"big": frac(C["unauthorized_operations_executed"]), "text": "unauthorized operations executed under full WAKALA",
                 "small": f"intentionally weak baseline: {frac(A['unauthorized_operations_executed'])}"},
                {"big": frac(C["legitimate_incorrectly_denied"]), "text": "legitimate requests wrongly denied"},
                {"big": f"{orig['numerator']}/{orig['denominator']} → {repeats[0]['numerator']}/{repeats[0]['denominator']}",
                 "text": "shared-environment recovery, before → after the fix", "small": f"{len(repeats)} repeated runs, all {repeats[0]['numerator']}/{repeats[0]['denominator']}"},
                {"big": frac(long50), "text": "extended synthetic recovery test"},
                {"big": "Synthetic", "text": "fixed-seed benchmark on one developer machine", "small": "not production government data", "tone": "navy"},
            ]}}, 1.5),
    ],
    "s7": [({"id": "s7_close", "stage": {"kind": "closing"}}, 1)],
}


def dur(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).decode())


def sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, cwd=BUILD)


def ts(t: float, srt: bool) -> str:
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",") if srt else f"{h}:{m:02d}:{s:05.2f}"


def split_line(text: str) -> list[str]:
    """Split a long narration line into at most two subtitle events at a natural break near the middle."""
    if len(text) <= 95:
        return [text]
    cands = [m.end() for m in re.finditer(r"[,.] ", text)]
    if not cands:
        return [text]
    cut = min(cands, key=lambda i: abs(i - len(text) / 2))
    return [text[:cut].strip(), text[cut:].strip()]


def trim_tts() -> None:
    """tts/*.wav (raw SAPI output) -> tts_trim/*.wav with leading/trailing silence removed, 48 kHz mono."""
    (HERE / "tts_trim").mkdir(exist_ok=True)
    for w in sorted((HERE / "tts").glob("*.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                        "-ar", "48000", "-ac", "1", str(HERE / "tts_trim" / w.name)], check=True)


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    trim_tts()
    # 1) scene durations from the real narration audio
    shots, timeline, audio, subs = [], [], [], []
    for sc in narr["scenes"]:
        lines = [HERE / "tts_trim" / f"{sc['id']}_{i + 1}.wav" for i in range(len(sc["lines"]))]
        lens = [dur(p) for p in lines]
        extra_tail = 1.6 if sc["id"] == "s7" else 0.0
        D = LEAD + sum(lens) + GAP * (len(lens) - 1) + TAIL + extra_tail
        parts = SCENES[sc["id"]]
        W = sum(w for _, w in parts)
        for shot, w in parts:
            shots.append({**shot, "scene": sc["id"], "d": D * w / W + XF})
        timeline.append({"scene": sc["id"], "lines": list(zip(sc["lines"], lines, lens)), "D": D})
    shots[-1]["d"] -= XF  # last shot has no outgoing transition
    starts, t = [], 0.0
    for s_ in shots:
        starts.append(t)
        t += s_["d"] - XF
    total = sum(s_["d"] for s_ in shots) - XF * (len(shots) - 1)
    # scene start = start of its first shot
    for sc in timeline:
        k = next(i for i, s_ in enumerate(shots) if s_["scene"] == sc["scene"])
        cur = starts[k] + (0 if k == 0 else XF / 2) + LEAD
        for text, wav, ln in sc["lines"]:
            audio.append((wav, cur))
            pieces = split_line(text)
            tot = sum(len(p) for p in pieces)
            c = cur
            for p in pieces:
                dd = ln * len(p) / tot
                subs.append((c, c + dd, p))
                c += dd
            cur += ln + GAP
    (BUILD / "plan.json").write_text(json.dumps({"shots": shots}, indent=1), encoding="utf-8")
    (BUILD / "timeline.json").write_text(json.dumps({"total": total, "shots": [{"id": s_["id"], "start": round(st, 3), "d": round(s_["d"], 3)} for s_, st in zip(shots, starts)],
        "narration": [{"file": w.name, "start": round(st, 3)} for w, st in audio], "subtitles": [{"start": round(a, 3), "end": round(b, 3), "text": x} for a, b, x in subs]}, indent=1), encoding="utf-8")
    print(f"total {total:.2f}s, {len(shots)} shots")

    # 2) render stages from the real captures
    subprocess.run(["node", str(HERE / "render_stages.js"), str(BUILD / "plan.json"), str(BUILD / "stages")], check=True, cwd=HERE)

    # 3) one clip per stage with a gentle zoom
    for s_ in shots:
        n = round(s_["d"] * FPS)
        zin = s_["id"] not in ("s1_title", "s7_close", "s6b")
        z = f"1+0.035*on/{n}" if zin else f"1+0.015*on/{n}"
        sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", f"stages/{s_['id']}.png", "-frames:v", str(n),
            "-vf", f"scale=3840:2160:flags=lanczos,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "14", f"clip_{s_['id']}.mp4"])
        print("clip", s_["id"], n, "frames")

    # 4) cross-fade chain -> silent master
    inputs, fc, prev, off = [], [], "0:v", 0.0
    for i, s_ in enumerate(shots):
        inputs += ["-i", f"clip_{s_['id']}.mp4"]
    for i in range(1, len(shots)):
        off += shots[i - 1]["d"] - XF
        out = f"x{i}"
        fc.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[{out}]")
        prev = out
    sh(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{prev}]", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "base.mp4"])

    # 5) narration track (real TTS clips placed on the timeline)
    ain, af = [], []
    for i, (w, st) in enumerate(audio):
        ain += ["-i", str(w)]
        af.append(f"[{i}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}]")
    af.append("".join(f"[a{i}]" for i in range(len(audio))) + f"amix=inputs={len(audio)}:normalize=0,apad=whole_dur={total:.3f},atrim=0:{total:.3f},"
              "highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,loudnorm=I=-16:TP=-1.5:LRA=7[out]")
    sh(["ffmpeg", "-v", "error", "-y", *ain, "-filter_complex", ";".join(af), "-map", "[out]", "-ar", "48000", "-ac", "2", "narration.wav"])

    # 6) subtitles (SRT deliverable + ASS for burning into the lower band, below the app window)
    srt = "\n".join(f"{i}\n{ts(a, True)} --> {ts(b, True)}\n{x}\n" for i, (a, b, x) in enumerate(subs, 1))
    (OUT / "WAKALA_Video_Subtitles.srt").write_text(srt, encoding="utf-8")
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 0", "",
           "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Sub,Segoe UI,36,&H00FFFFFF,&H00FFFFFF,&H00603E19,&H10603E19,0,0,0,0,100,100,0,0,3,12,0,2,260,260,30,1", "",
           "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ass += [f"Dialogue: 0,{ts(a, False)},{ts(b, False)},Sub,,0,0,0,,{x}" for a, b, x in subs]
    (BUILD / "subtitles.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")

    # 7) deliverables
    sh(["ffmpeg", "-v", "error", "-y", "-i", "base.mp4", "-i", "narration.wav", "-vf", "ass=subtitles.ass", "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(OUT / "WAKALA_Final_Demo_1080p.mp4")])
    sh(["ffmpeg", "-v", "error", "-y", "-i", "base.mp4", "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-profile:v", "high", "-movflags", "+faststart", str(OUT / "WAKALA_Final_Demo_Silent.mp4")])
    print("done", OUT / "WAKALA_Final_Demo_1080p.mp4")


if __name__ == "__main__":
    os.environ.setdefault("NODE_PATH", "")
    main()
