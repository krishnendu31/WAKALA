"""Final assembly of "WAKALA — The Moment Before".

Inputs: build/seg/seg0..5.mp4 (render_film.js, 6 x 300 frames), build/score.wav (score.py), tts/*.wav (tts.ps1), narration.json.
Outputs: ../WAKALA_The_Moment_Before_60s.mp4 (score + narration + burned-in subtitles)
         ../WAKALA_The_Moment_Before_Silent.mp4 (picture only: no audio, no subtitles)
         meta/timeline.json, meta/subtitles.ass, ../WAKALA_The_Moment_Before_Subtitles.srt
"""
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
B = HERE / "build"
GAP = 0.35
narr = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))


def run(cmd):
    subprocess.run(cmd, check=True, cwd=B)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).decode())


def ts(t, srt):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",") if srt else f"{h}:{m:02d}:{s:05.2f}"


def split(text):
    if len(text) <= 70:
        return [text]
    cands = [m.end() for m in re.finditer(r"[,.] ", text)]
    if not cands:
        return [text]
    cut = min(cands, key=lambda i: abs(i - len(text) / 2))
    return [text[:cut].strip(), text[cut:].strip()]


def main():
    import time
    rid = time.strftime("%H%M%S")
    # trimmed voice clips
    (HERE / "tts_trim").mkdir(exist_ok=True)
    for w in sorted((HERE / "tts").glob("*.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w), "-af",
                        "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                        "-ar", "48000", "-ac", "1", str(HERE / "tts_trim" / w.name)], check=True)
    place, subs = [], []
    for sc in narr["scenes"]:
        cur = sc["start"]
        for i, text in enumerate(sc["lines"], 1):
            w = HERE / "tts_trim" / f"{sc['id']}_{i}.wav"
            ln = dur(w)
            place.append((w, cur, ln))
            parts = split(text)
            tot = sum(len(p) for p in parts)
            c = cur
            for p in parts:
                d = ln * len(p) / tot
                subs.append((c, c + d, p))
                c += d
            cur += ln + GAP
    assert place[-1][1] + place[-1][2] <= 60.0, "narration overruns the film"
    # picture
    (B / "segs.txt").write_text("".join(f"file 'seg/seg{i}.mp4'\n" for i in range(6)), encoding="utf-8")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "segs.txt", "-c", "copy", f"picture_{rid}.mp4"])
    # voice: warm EQ, gentle compression, light room
    ins, fc = [], []
    for k, (w, st, _) in enumerate(place):
        ins += ["-i", str(w)]
        fc.append(f"[{k}:a]adelay={int(st * 1000)}|{int(st * 1000)}[v{k}]")
    fc.append("".join(f"[v{k}]" for k in range(len(place))) + f"amix=inputs={len(place)}:normalize=0,apad=whole_dur=60,atrim=0:60,"
              "highpass=f=85,equalizer=f=210:t=q:w=1.1:g=2.5,equalizer=f=3300:t=q:w=1.4:g=1.8,equalizer=f=7500:t=q:w=1.5:g=-2,"
              "acompressor=threshold=-22dB:ratio=3:attack=6:release=150,aecho=0.85:0.5:38|71:0.10|0.06,aformat=channel_layouts=stereo[vo]")
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fc), "-map", "[vo]", "-ar", "48000", "voice.wav"])
    # mix: score ducked under the voice, then loudness-normalised
    run(["ffmpeg", "-v", "error", "-y", "-i", "score.wav", "-i", "voice.wav", "-filter_complex",
         "[1:a]asplit=2[vk][vm];[0:a]volume=1.15[mu];[mu][vk]sidechaincompress=threshold=0.03:ratio=5:attack=25:release=450[duck];"
         "[duck][vm]amix=inputs=2:normalize=0:weights='0.85 1.0',loudnorm=I=-16:TP=-1.5:LRA=9[out]",
         "-map", "[out]", "-ar", "48000", "-ac", "2", "mix.wav"])
    # subtitles: cinematic, in a soft navy band at the bottom
    (OUT / "WAKALA_The_Moment_Before_Subtitles.srt").write_text("\n".join(f"{i}\n{ts(a, True)} --> {ts(b, True)}\n{x}\n" for i, (a, b, x) in enumerate(subs, 1)), encoding="utf-8")
    ass = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 0", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
           "Style: Sub,Segoe UI,40,&H00F4F1EA,&H00FFFFFF,&H50220E07,&H50220E07,0,0,0,0,100,100,0.5,0,3,14,0,2,280,280,46,1", "",
           "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ass += [f"Dialogue: 0,{ts(a, False)},{ts(b, False)},Sub,,0,0,0,,{x}" for a, b, x in subs]
    meta = HERE / "meta"
    meta.mkdir(exist_ok=True)
    (meta / "subtitles.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    (B / "subtitles.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    common = ["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", "30", "-profile:v", "high", "-aspect", "16:9", "-t", "60", "-movflags", "+faststart", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
    run(["ffmpeg", "-v", "error", "-y", "-i", f"picture_{rid}.mp4", "-i", "mix.wav", "-vf", "scale=in_range=full:out_range=tv,format=yuv420p,ass=subtitles.ass,setsar=1", "-map", "0:v", "-map", "1:a",
         *common, "-c:a", "aac", "-b:a", "224k", str(B / f"final_60s_{rid}.mp4")])
    run(["ffmpeg", "-v", "error", "-y", "-i", f"picture_{rid}.mp4", "-an", "-vf", "scale=in_range=full:out_range=tv,format=yuv420p,setsar=1", *common, str(B / f"final_silent_{rid}.mp4")])
    import shutil
    for src, dst in ((f"final_60s_{rid}.mp4", "WAKALA_The_Moment_Before_60s.mp4"), (f"final_silent_{rid}.mp4", "WAKALA_The_Moment_Before_Silent.mp4")):
        shutil.copyfile(B / src, OUT / dst)
    (meta / "timeline.json").write_text(json.dumps({"total": 60.0, "narration": [{"file": w.name, "start": round(st, 3), "length": round(ln, 3)} for w, st, ln in place],
        "subtitles": [{"start": round(a, 3), "end": round(b, 3), "text": x} for a, b, x in subs],
        "scenes": {"1 Autonomous government": [0, 10], "2 The unexpected request": [10, 20], "3 The moment before": [20, 32], "4 Real prototype: proof": [32, 40],
                   "5 Accountable recovery": [40, 49], "6 Real prototype: recovery": [49, 55], "7 Reveal": [55, 60]},
        "real_footage_seconds": {"proof (31.6–40.6 incl. fades)": 9.0, "recovery proof (48.9–55.4 incl. fades)": 6.5}}, indent=1), encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
