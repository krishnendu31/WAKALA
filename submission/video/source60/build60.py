"""Edit the 60-second WAKALA film from verified raw footage (capture/) and local TTS (tts/).

Scene boundaries are fixed (0,5,14,25,35,44,51,57,60 s). Each shot's visible time is set so the scenes start exactly
on those boundaries; 0.4 s cross-fades overlap the joins. Narration clips are placed per line from their measured
length; subtitles share those timings.

Outputs: ../WAKALA_60s_Final.mp4 (voice + burned-in subtitles), ../WAKALA_60s_Silent.mp4, ../WAKALA_60s_Subtitles.srt
Usage: python build60.py   (ffmpeg on PATH; NODE_PATH with puppeteer-core)
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parent
BUILD = HERE / "build"
FPS, XF, LEAD, GAP = 30, 0.4, 0.35, 0.25

narr = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
run = json.loads((HERE / "capture" / "run_log.json").read_text(encoding="utf-8"))
lab = json.loads((HERE / "capture" / "attack_lab_run.json").read_text(encoding="utf-8"))["summary"]
S = run["shots"]
ev5 = json.loads((ROOT / "evidence/phase5/summary.json").read_text(encoding="utf-8"))
ev7 = json.loads((ROOT / "evidence/phase7/recovery_repeatability.json").read_text(encoding="utf-8"))

# ---- refuse to build claims the footage does not support
nc, ic, uc = run["normal_case"], run["incident_case"], run["unrelated_case"]
assert nc["state"] == "COMPLETED" and nc["allowed"] == 6 and nc["delegations"], "normal case not verified"
assert ic["denied"] and ic["final_state"] == "COMPLETED" and ic["recovery_status"] == "recovered" and "allowed" in ic["standby"], "recovery not verified"
assert uc["state"] == "COMPLETED" and run["audit_chain_valid"], "unrelated case / audit not verified"
assert S["p17_portal_recovered"]["case_id"] == ic["case_id"], "portal shot is not the incident case"
C, A = ev5["configurations"]["C"], ev5["configurations"]["A"]
fr = lambda d: f"{d['numerator']}/{d['denominator']}"  # noqa: E731
long50 = ev7["long_shared_50"]["recovered"]


def bx(shot, key):
    b = S[shot]["boxes"].get(key)
    assert b, f"missing box {shot}.{key}"
    return b


def app(sid, shot, crop, chip, head, focus=(), tone="", head_tone=""):
    x, y, w = crop
    return {"id": sid, "stage": {"kind": "app", "img": f"capture/{S[shot]['file']}", "css": S[shot]["css"], "crop": {"x": x, "y": y, "w": w},
            "focus": list(focus), "chip": chip, "head": head, "tone": tone, "headTone": head_tone}}


def f(b, tone="", pad=10):
    return {**b, "tone": tone, "pad": pad}


OMAR = {"x": 121, "y": 979, "w": 490, "h": 137}            # Omar's card in g10 (same layout as the guided step 4)
DOC_VERDICT = {"x": 308, "y": 1690, "w": 1092, "h": 288}  # quarantine verdict header + findings in the Document Shield capture
VERIFIED = {"x": 1025, "y": 275, "w": 375, "h": 450}       # "What WAKALA verified" card in the portal viewport capture

# (shot, visible seconds) per scene; visible seconds sum to the scene length
SCENES = {
    "s1": [({"id": "s1_title", "stage": {"kind": "title", "big": "WHO AUTHORIZES AUTONOMOUS AI?"}}, 2.2),
           (app("s1_welcome", "w01_welcome", (100, 60, 1240), "Real prototype", "WHO AUTHORIZES AUTONOMOUS AI?"), 2.8)],
    "s2": [(app("s2_normal", "g02_normal_done", (70, 200, 1300), "Verified agent identity",
                f"Case-bound authority — {nc['allowed']} signed agent actions checked and allowed", [f(bx("g02_normal_done", "result"))]), 4.4),
           (app("s2_deleg", "d04_delegation", (650, 470, 780), "Secure delegation",
                "Residency Agent → Insurance Agent, for Mariam's case only", [f({"x": 688, "y": 800, "w": 700, "h": 82}, "", 6)]), 4.6)],
    "s3": [(app("s3_block", "g05_blocked", (100, 170, 1240), "Separate test case", "UNAUTHORIZED ACCESS BLOCKED",
                [f(bx("g05_blocked", "panel"), "deny", 6)], tone="deny", head_tone="deny"), 6.0),
           (app("s3_facts", "g05_blocked", (120, 260, 1200), "Gateway decision", "Valid agent. Invalid action. No protected data returned.",
                [f(bx("g05_blocked", "facts"), "navy")], tone="deny"), 5.0)],
    "s4": [(app("s4_watch", "soc07_watch", (290, 380, 1110), "Detect · Behaviour Watch", "Cross-citizen access flagged as an incident",
                [], tone="navy"), 3.2),
           (app("s4_invest", "soc08_investigation", (290, 1880, 1150), "Contain", "Gateway evidence and the affected delegated mandate",
                [f(bx("soc08_investigation", "chain"), "navy", 6)], tone="navy"), 3.4),
           (app("s4_officer", "g09_intervention", (600, 520, 800), "Authorized human review", "Signed-in officer reassigns the task to the standby agent",
                [f(bx("g09_intervention", "reassign"))], tone="navy"), 3.4)],
    "s5": [(app("s5_recovered", "g10_recovered", (0, 300, 1440), "Legitimate service recovered", "Unrelated case unaffected — both completed",
                [f(bx("g10_recovered", "citizen")), f(OMAR, "navy")]), 3.2),
           (app("s5_portal", "p17_portal_recovered", (180, 60, 1260), "Traceable", "Every decision recorded — including the blocked one",
                [f(VERIFIED, "", 8)]), 2.9),
           (app("s5_receipt", "g12_receipt", (300, 40, 840), "Citizen AI Activity", "Privacy-filtered receipt built from the audit trail"), 2.9)],
    "s6": [(app("s6_lab", "a13_attack_lab", (300, 300, 1100), "8 security scenarios",
                f"Weak baseline executed {lab['baseline_executed']} · WAKALA {lab['wakala_executed']} · {lab['denied_in_both']} denied by both",
                [f(bx("a13_attack_lab", "tiles"), "navy", 6)]), 3.6),
           (app("s6_doc", "ds14_document", (290, 1676, 1130), "Document injection detection", "Hidden white-text instruction found — PDF quarantined",
                [f(DOC_VERDICT, "deny", 4)], tone="deny"), 3.4)],
    "s7": [(app("s7_shadow", "sh15_shadow", (290, 240, 1130), "Shadow Mode for safer pilots", "Observes copies only — nothing executed; flags policies to tune",
                [f(bx("sh15_shadow", "tiles"), "navy", 6)], tone="navy"), 3.0),
           (app("s7_evidence", "ev16_evidence", (290, 330, 1130), "Tested with 1,200 synthetic requests",
                f"{fr(C['unauthorized_operations_executed'])} unauthorized executed · {fr(C['legitimate_incorrectly_denied'])} wrongly denied · {fr(long50)} recovery",
                [f(bx("ev16_evidence", "tiles"), "navy", 6), f(bx("ev16_evidence", "recovery"), "", 6)], tone="gold"), 3.0)],
    "s8": [({"id": "s8_close", "stage": {"kind": "closing", "lines": ["VERIFY AUTHORITY.", "BLOCK THE UNAUTHORIZED.", "KEEP SERVICES MOVING."],
             "fine": "Fictional prototype · Synthetic data · Deterministic offline workflow"}}, 3.0)],
}


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).decode())


def sh(cmd):
    subprocess.run(cmd, check=True, cwd=BUILD)


def ts(t, srt):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",") if srt else f"{h}:{m:02d}:{s:05.2f}"


def split(text):
    if len(text) <= 80:
        return [text]
    cands = [m.end() for m in re.finditer(r"[,.] ", text)]
    if not cands:
        return [text]
    cut = min(cands, key=lambda i: abs(i - len(text) / 2))
    return [text[:cut].strip(), text[cut:].strip()]


def main():
    BUILD.mkdir(exist_ok=True)
    (HERE / "tts_trim").mkdir(exist_ok=True)
    for w in sorted((HERE / "tts").glob("*.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                        "-ar", "48000", "-ac", "1", str(HERE / "tts_trim" / w.name)], check=True)
    shots, t = [], 0.0
    for sc in narr["scenes"]:
        assert abs(t - sc["start"]) < 1e-6, (sc["id"], t)
        vis = sum(v for _, v in SCENES[sc["id"]])
        assert abs(vis - (sc["end"] - sc["start"])) < 1e-6, (sc["id"], vis)
        for shot, v in SCENES[sc["id"]]:
            shots.append({**shot, "scene": sc["id"], "start": t, "v": v, "d": v + XF})
            t += v
    shots[-1]["d"] = shots[-1]["v"]
    total = t
    audio, subs = [], []
    for sc in narr["scenes"]:
        lens = [dur(HERE / "tts_trim" / f"{sc['id']}_{i}.wav") for i in range(1, len(sc["lines"]) + 1)]
        speech = sum(lens) + GAP * max(0, len(lens) - 1)
        # centre the narration in its scene window (between 0.35 s and 1.0 s lead) to avoid long gaps at scene joins
        lead = min(1.0, max(LEAD, (sc["end"] - sc["start"] - speech) / 2 - 0.15))
        cur = sc["start"] + lead
        for i, text in enumerate(sc["lines"], 1):
            wav = HERE / "tts_trim" / f"{sc['id']}_{i}.wav"
            ln = dur(wav)
            assert cur + ln <= sc["end"] + 0.05, f"{sc['id']} line {i} overruns its scene"
            audio.append((wav, cur))
            parts = split(text)
            tot = sum(len(p) for p in parts)
            c = cur
            for p in parts:
                dd = ln * len(p) / tot
                subs.append((c, c + dd, p))
                c += dd
            cur += ln + GAP
    (BUILD / "plan.json").write_text(json.dumps({"shots": shots}, indent=1), encoding="utf-8")
    (BUILD / "timeline.json").write_text(json.dumps({"total": total, "shots": [{"id": s["id"], "scene": s["scene"], "start": round(s["start"], 3), "visible": s["v"]} for s in shots],
        "narration": [{"file": w.name, "start": round(st, 3), "length": round(dur(w), 3)} for w, st in audio],
        "subtitles": [{"start": round(a, 3), "end": round(b, 3), "text": x} for a, b, x in subs]}, indent=1), encoding="utf-8")
    print(f"total {total:.2f}s, {len(shots)} shots")
    subprocess.run(["node", str(HERE / "render_stages.js"), str(BUILD / "plan.json"), str(BUILD / "stages")], check=True, cwd=HERE)
    for s in shots:
        n = round(s["d"] * FPS)
        z = f"1+0.03*on/{n}" if s["stage"]["kind"] == "app" else f"1+0.012*on/{n}"
        sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", f"stages/{s['id']}.png", "-frames:v", str(n), "-vf",
            f"scale=3840:2160:flags=lanczos,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS},format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "14", f"clip_{s['id']}.mp4"])
    inputs, fc, prev = [], [], "0:v"
    for s in shots:
        inputs += ["-i", f"clip_{s['id']}.mp4"]
    for i in range(1, len(shots)):
        # offset is measured on the accumulated output: shot i starts fading in exactly at its scene time (clip i-1 is v + XF long)
        out = f"x{i}"
        fc.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={shots[i]['start']:.3f}[{out}]")
        prev = out
    sh(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", f"[{prev}]", "-r", str(FPS), "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "base.mp4"])
    ain, af = [], []
    for i, (w, st) in enumerate(audio):
        ain += ["-i", str(w)]
        af.append(f"[{i}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}]")
    af.append("".join(f"[a{i}]" for i in range(len(audio))) + f"amix=inputs={len(audio)}:normalize=0,apad=whole_dur={total:.3f},atrim=0:{total:.3f},"
              "highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,loudnorm=I=-16:TP=-1.5:LRA=7[out]")
    sh(["ffmpeg", "-v", "error", "-y", *ain, "-filter_complex", ";".join(af), "-map", "[out]", "-ar", "48000", "-ac", "2", "narration.wav"])
    srt = "\n".join(f"{i}\n{ts(a, True)} --> {ts(b, True)}\n{x}\n" for i, (a, b, x) in enumerate(subs, 1))
    (OUT / "WAKALA_60s_Subtitles.srt").write_text(srt, encoding="utf-8")
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 0", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Sub,Segoe UI,36,&H00FFFFFF,&H00FFFFFF,&H00603E19,&H10603E19,0,0,0,0,100,100,0,0,3,12,0,2,260,260,30,1", "",
           "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ass += [f"Dialogue: 0,{ts(a, False)},{ts(b, False)},Sub,,0,0,0,,{x}" for a, b, x in subs]
    (BUILD / "subtitles.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    sh(["ffmpeg", "-v", "error", "-y", "-i", "base.mp4", "-i", "narration.wav", "-vf", "ass=subtitles.ass,setsar=1", "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-profile:v", "high", "-aspect", "16:9",
        "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(OUT / "WAKALA_60s_Final.mp4")])
    sh(["ffmpeg", "-v", "error", "-y", "-i", "base.mp4", "-an", "-vf", "setsar=1", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-profile:v", "high", "-aspect", "16:9", "-t", f"{total:.3f}", "-movflags", "+faststart", str(OUT / "WAKALA_60s_Silent.mp4")])
    print("done")


if __name__ == "__main__":
    main()
