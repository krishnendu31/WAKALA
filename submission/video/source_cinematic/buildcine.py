"""Assemble the 60-second cinematic explainer.

Conceptual illustrations (ill.html, rendered frame by frame) tell the story; the blocked decision, the officer
review and the completed recovery are GENUINE prototype captures reused from ../source60/capture (one verified demo
session, see ../WAKALA_60s_Verification.md). Narration: local TTS clips in tts/ (tts.ps1).

Outputs: ../WAKALA_Cinematic_60s.mp4 (voice + burned-in subtitles), ../WAKALA_Cinematic_60s_Silent.mp4,
         ../WAKALA_Cinematic_Subtitles.srt ; build/ intermediates ; meta/ timeline.
Usage: python buildcine.py   (ffmpeg on PATH; NODE_PATH with puppeteer-core)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
CAP = OUT / "source60" / "capture"
BUILD = HERE / "build"
FPS, XF, GAP = 30, 0.5, 0.25

narr = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
run = json.loads((CAP / "run_log.json").read_text(encoding="utf-8"))
S = run["shots"]

# genuine outcomes the real shots depict — refuse to build if the footage does not support them
ic, uc = run["incident_case"], run["unrelated_case"]
assert ic["denied"] and ic["denied"][0]["reason_codes"] == ["DENY_SCOPE_VIOLATION", "DENY_CASE_SCOPE_VIOLATION"]
assert ic["final_state"] == "COMPLETED" and ic["recovery_status"] == "recovered" and "allowed" in ic["standby"]
assert uc["state"] == "COMPLETED" and run["audit_chain_valid"]
assert S["p17_portal_recovered"]["case_id"] == ic["case_id"]


def bx(shot, key):
    b = S[shot]["boxes"].get(key)
    assert b, f"missing box {shot}.{key}"
    return b


def real(sid, shot, crop, head, focus=(), tone="", head_tone=""):
    x, y, w = crop
    return {"id": sid, "kind": "still", "stage": {"kind": "app", "img": str((CAP / S[shot]["file"]).resolve()), "css": S[shot]["css"],
            "crop": {"x": x, "y": y, "w": w}, "focus": list(focus), "chip": "Real prototype", "head": head, "tone": tone, "headTone": head_tone}}


def anim(sid, scene):
    return {"id": sid, "kind": "anim", "ill": scene}


def f(b, tone="", pad=10):
    return {**b, "tone": tone, "pad": pad}


OMAR = {"x": 121, "y": 979, "w": 490, "h": 137}
VERIFIED = {"x": 1025, "y": 275, "w": 375, "h": 450}

SCENES = {
    "s1": [(anim("a", "a"), 11.0)],
    "s2": [(anim("b", "b"), 9.0)],
    "s3": [(anim("c", "c"), 3.5),
           (real("r_block", "g05_blocked", (100, 170, 1240), "UNAUTHORIZED ACCESS BLOCKED", [f(bx("g05_blocked", "panel"), "deny", 6)], "deny", "deny"), 4.5),
           (real("r_facts", "g05_blocked", (120, 260, 1200), "Valid agent. Invalid action. No protected data returned.", [f(bx("g05_blocked", "facts"), "navy")], "deny"), 4.0)],
    "s4": [(anim("d", "d"), 3.0),
           (real("r_invest", "soc08_investigation", (290, 1880, 1150), "The officer reviews the incident and the affected authority",
                 [f(bx("soc08_investigation", "chain"), "navy", 6)], "navy"), 3.4),
           (real("r_officer", "g09_intervention", (600, 520, 800), "Task handed to the trusted standby agent", [f(bx("g09_intervention", "reassign"))], "navy"), 3.6)],
    "s5": [(real("r_recovered", "g10_recovered", (0, 300, 1440), "Mariam's service completed — the unrelated case continued",
                 [f(bx("g10_recovered", "citizen")), f(OMAR, "navy")]), 5.5),
           (real("r_portal", "p17_portal_recovered", (180, 60, 1260), "Every decision on record — the blocked one included", [f(VERIFIED, "", 8)]), 5.5)],
    "s6": [({"id": "close", "kind": "still", "stage": {"kind": "closing", "lines": ["VERIFY AUTHORITY.", "BLOCK THE UNAUTHORIZED.", "KEEP SERVICES MOVING."],
             "fine": "Illustrations are conceptual · Prototype footage uses fictional citizens and synthetic data · Deterministic offline workflow"}}, 7.0)],
}


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).decode())


def sh(cmd, cwd=BUILD):
    subprocess.run(cmd, check=True, cwd=cwd)


def ts(t, srt):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",") if srt else f"{h}:{m:02d}:{s:05.2f}"


def split(text):
    if len(text) <= 80:
        return [text]
    cands = [m.end() for m in re.finditer(r"[,.:] ", text)]
    cut = min(cands, key=lambda i: abs(i - len(text) / 2)) if cands else len(text)
    return [text[:cut].strip(), text[cut:].strip()] if cands else [text]


def main():
    BUILD.mkdir(exist_ok=True)
    (HERE / "tts_trim").mkdir(exist_ok=True)
    for w in sorted((HERE / "tts").glob("*.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                        "-ar", "48000", "-ac", "1", str(HERE / "tts_trim" / w.name)], check=True)
    shots, t = [], 0.0
    for sc in narr["scenes"]:
        assert abs(t - sc["start"]) < 1e-6, sc["id"]
        assert abs(sum(v for _, v in SCENES[sc["id"]]) - (sc["end"] - sc["start"])) < 1e-6, sc["id"]
        for shot, v in SCENES[sc["id"]]:
            shots.append({**shot, "scene": sc["id"], "start": t, "v": v, "d": v + XF})
            t += v
    shots[-1]["d"] = shots[-1]["v"]
    total = t
    audio, subs = [], []
    for sc in narr["scenes"]:
        lens = [dur(HERE / "tts_trim" / f"{sc['id']}_{i}.wav") for i in range(1, len(sc["lines"]) + 1)]
        speech = sum(lens) + GAP * max(0, len(lens) - 1)
        lead = max(0.35, (sc["end"] - sc["start"] - speech) / 2 - 0.15)  # centre the line in its scene
        cur = sc["start"] + lead
        for i, (text, ln) in enumerate(zip(sc["lines"], lens), 1):
            assert cur + ln <= sc["end"] + 0.05, f"{sc['id']} line {i} overruns"
            audio.append((HERE / "tts_trim" / f"{sc['id']}_{i}.wav", cur))
            parts = split(text)
            tot = sum(len(p) for p in parts)
            c = cur
            for p in parts:
                dd = ln * len(p) / tot
                subs.append((c, c + dd, p))
                c += dd
            cur += ln + GAP

    # 1) stills (real captures + closing card) through the shared stage, animations frame by frame
    stills = [s for s in shots if s["kind"] == "still"]
    (BUILD / "plan.json").write_text(json.dumps({"shots": [{"id": s["id"], "stage": s["stage"]} for s in stills]}, indent=1), encoding="utf-8")
    subprocess.run(["node", str(HERE / "render_stages.js"), str(BUILD / "plan.json"), str(BUILD / "stages")], check=True, cwd=HERE)
    for s in shots:
        n = round(s["d"] * FPS)
        if s["kind"] == "anim":
            fr = BUILD / f"frames_{s['id']}"
            shutil.rmtree(fr, ignore_errors=True)
            subprocess.run(["node", str(HERE / "render_anim.js"), s["ill"], f"{s['d']:.4f}", str(fr)], check=True, cwd=HERE)
            sh(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(fr / "f%05d.png"), "-frames:v", str(n), "-vf", "format=yuv420p",
                "-c:v", "libx264", "-preset", "medium", "-crf", "14", f"clip_{s['id']}.mp4"])
        else:
            z = f"1+0.03*on/{n}" if s["stage"]["kind"] == "app" else f"1+0.012*on/{n}"
            sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", f"stages/{s['id']}.png", "-frames:v", str(n), "-vf",
                f"scale=3840:2160:flags=lanczos,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS},format=yuv420p",
                "-c:v", "libx264", "-preset", "medium", "-crf", "14", f"clip_{s['id']}.mp4"])
        print("clip", s["id"], n)
    inputs, fc, prev = [], [], "0:v"
    for s in shots:
        inputs += ["-i", f"clip_{s['id']}.mp4"]
    for i in range(1, len(shots)):
        fc.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={shots[i]['start']:.3f}[x{i}]")
        prev = f"x{i}"
    sh(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{prev}]", "-r", str(FPS), "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "base.mp4"])
    ain, af = [], []
    for i, (w, st) in enumerate(audio):
        ain += ["-i", str(w)]
        af.append(f"[{i}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}]")
    af.append("".join(f"[a{i}]" for i in range(len(audio))) + f"amix=inputs={len(audio)}:normalize=0,apad=whole_dur={total:.3f},atrim=0:{total:.3f},"
              "highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,loudnorm=I=-16:TP=-1.5:LRA=7[out]")
    sh(["ffmpeg", "-v", "error", "-y", *ain, "-filter_complex", ";".join(af), "-map", "[out]", "-ar", "48000", "-ac", "2", "narration.wav"])
    (OUT / "WAKALA_Cinematic_Subtitles.srt").write_text("\n".join(f"{i}\n{ts(a, True)} --> {ts(b, True)}\n{x}\n" for i, (a, b, x) in enumerate(subs, 1)), encoding="utf-8")
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 0", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Sub,Segoe UI,36,&H00FFFFFF,&H00FFFFFF,&H00603E19,&H10603E19,0,0,0,0,100,100,0,0,3,12,0,2,260,260,30,1", "",
           "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ass += [f"Dialogue: 0,{ts(a, False)},{ts(b, False)},Sub,,0,0,0,,{x}" for a, b, x in subs]
    (BUILD / "subtitles.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    common = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-profile:v", "high", "-aspect", "16:9",
              "-t", f"{total:.3f}", "-movflags", "+faststart"]
    sh(["ffmpeg", "-v", "error", "-y", "-i", "base.mp4", "-i", "narration.wav", "-vf", "ass=subtitles.ass,setsar=1", "-map", "0:v", "-map", "1:a",
        *common, "-c:a", "aac", "-b:a", "192k", str(OUT / "WAKALA_Cinematic_60s.mp4")])
    sh(["ffmpeg", "-v", "error", "-y", "-i", "base.mp4", "-an", "-vf", "setsar=1", *common, str(OUT / "WAKALA_Cinematic_60s_Silent.mp4")])
    meta = HERE / "meta"
    meta.mkdir(exist_ok=True)
    (meta / "timeline.json").write_text(json.dumps({"total": total, "shots": [{"id": s["id"], "kind": s["kind"], "scene": s["scene"], "start": round(s["start"], 3),
        "visible": s["v"]} for s in shots], "narration": [{"file": w.name, "start": round(st, 3), "length": round(dur(w), 3)} for w, st in audio],
        "subtitles": [{"start": round(a, 3), "end": round(b, 3), "text": x} for a, b, x in subs]}, indent=1), encoding="utf-8")
    shutil.copy(BUILD / "subtitles.ass", meta / "subtitles.ass")
    print(f"done total {total:.2f}s")


if __name__ == "__main__":
    main()
