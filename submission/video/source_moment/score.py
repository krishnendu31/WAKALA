"""Original score and sound design for "WAKALA — The Moment Before" (60 s), synthesised from scratch with numpy/scipy.
No samples, loops or third-party music are used, so the WAKALA team owns it outright. Writes build/score.wav (48 kHz stereo).

Cue sheet (seconds):
  0–10   wonder: warm D-major-9 pad swelling with a high shimmer
  10–20  tension: pad darkens (D minor colour), low pulse that slowly quickens, filtered riser
  20–27.3 the moment before: everything thins to a low drone and a high held tone ("time slows")
  27.3–27.45 near-silence
  27.45  impact: sub thump + soft noise burst + glassy ping, long tail (the block)
  28–40  hush under the real-prototype proof: sparse low pad
  40–55  recovery: warm progression D – G – Bm – A – D with a gentle pulse, swelling
  55–60  resolution: D major chord, chime on the logo reveal, fade
"""
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR, DUR = 48000, 60.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(2026)


def hz(m):  # MIDI note -> Hz
    return 440.0 * 2 ** ((m - 69) / 12)


def env(a, b, fade_in=1.0, fade_out=1.0):
    """0..1 envelope that is 1 between a and b with raised-cosine fades."""
    e = np.zeros(N)
    i0, i1 = int(a * SR), int(b * SR)
    e[i0:i1] = 1.0
    fi, fo = int(fade_in * SR), int(fade_out * SR)
    if fi:
        r = np.arange(fi)
        e[i0:i0 + fi] *= 0.5 - 0.5 * np.cos(np.pi * r / fi)
    if fo:
        r = np.arange(fo)
        e[i1 - fo:i1] *= 0.5 + 0.5 * np.cos(np.pi * r / fo)
    return e


def lowpass(x, f, order=2):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def bandpass(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def pad(notes, a, b, amp=0.06, bright=1800, fade=2.0, detune=0.004):
    """Soft detuned pad: several slightly detuned partial-rich voices per note, low-passed."""
    out = np.zeros(N)
    for m in notes:
        f0 = hz(m)
        for d in (-detune, 0, detune):
            ph = rng.uniform(0, 2 * np.pi)
            v = sum(np.sin(2 * np.pi * f0 * (1 + d) * k * t + ph * k) / k ** 1.6 for k in (1, 2, 3, 4))
            out += v
    out = lowpass(out, bright) * env(a, b, fade, fade) * amp / len(notes)
    return out


def tone(f, a, b, amp, fade_in=0.5, fade_out=1.5, vib=0.0):
    ph = 2 * np.pi * f * t + vib * np.sin(2 * np.pi * 4.5 * t)
    return np.sin(ph) * env(a, b, fade_in, fade_out) * amp


def hit(at, amp=1.0):
    """Restrained impact: pitch-dropping sub, a short filtered noise burst and a glassy ping."""
    out = np.zeros(N)
    i = int(at * SR)
    L = int(2.8 * SR)
    tt = np.arange(L) / SR
    sub = np.sin(2 * np.pi * (38 + 60 * np.exp(-tt * 9)) * tt) * np.exp(-tt * 2.2)
    noise = bandpass(rng.standard_normal(L), 200, 3500) * np.exp(-tt * 18) * 0.35
    ping = (np.sin(2 * np.pi * 1318.5 * tt) + 0.5 * np.sin(2 * np.pi * 1975.5 * tt)) * np.exp(-tt * 3.5) * 0.10
    out[i:i + L] += (0.9 * sub + noise + ping) * amp
    return out


def thump(at, amp):
    out = np.zeros(N)
    i = int(at * SR)
    L = int(0.6 * SR)
    tt = np.arange(L) / SR
    out[i:i + L] = np.sin(2 * np.pi * (48 + 30 * np.exp(-tt * 20)) * tt) * np.exp(-tt * 9) * amp
    return out


def chime(at, notes, amp=0.07):
    out = np.zeros(N)
    for j, m in enumerate(notes):
        i = int((at + 0.09 * j) * SR)
        L = min(N - i, int(4.0 * SR))
        tt = np.arange(L) / SR
        f = hz(m)
        out[i:i + L] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 1.3) * amp
    return out


mix = np.zeros(N)
# 1 · wonder (D maj9 voicing) + shimmer
mix += pad([50, 57, 62, 64, 66, 69], 0.0, 11.0, amp=0.075, bright=2200, fade=2.5)
mix += tone(hz(86), 1.5, 10.5, 0.010, 2.5, 2.5, vib=0.002) + tone(hz(81), 3.0, 10.5, 0.008, 2.5, 2.0)
# 2 · tension: darker pad + quickening pulse + riser
mix += pad([50, 53, 57, 60], 9.5, 20.8, amp=0.070, bright=1200, fade=1.8)
beat, k = 10.6, 0
while beat < 20.2:
    mix += thump(beat, 0.18 + 0.02 * k)
    beat += max(0.42, 0.95 - 0.06 * k)
    k += 1
riser = bandpass(rng.standard_normal(N), 300, 2400) * env(13.0, 20.6, 7.0, 0.6) * 0.035
mix += riser
# 3 · the moment before: drone + held high tone, thinning to near-silence
mix += tone(hz(38), 20.0, 27.3, 0.11, 0.8, 0.35) + tone(hz(45), 20.0, 27.3, 0.05, 1.2, 0.35)
mix += tone(hz(93), 20.6, 27.3, 0.012, 2.0, 0.3, vib=0.004)
mix += hit(27.45, 1.0)
# 4 · hush under the proof
mix += pad([50, 57, 62], 28.6, 40.6, amp=0.040, bright=900, fade=2.0)
# 5 · recovery progression D – G – Bm – A – D, gentle pulse, swelling
prog = [(40.0, [50, 57, 62, 66]), (43.0, [43, 55, 59, 62]), (46.0, [47, 54, 59, 62]), (49.0, [45, 57, 61, 64]), (52.0, [50, 57, 62, 66])]
for i, (a, ch) in enumerate(prog):
    b = prog[i + 1][0] + 0.8 if i + 1 < len(prog) else 56.0
    mix += pad(ch, a, b, amp=0.050 + 0.008 * i, bright=2000 + 300 * i, fade=1.2)
for k in range(30):
    at = 40.5 + 0.5 * k
    if at > 54.5:
        break
    mix += chime(at, [74 if k % 4 == 0 else 69 if k % 4 == 2 else 66], amp=0.012 + 0.0006 * k)
# 6 · resolution and logo chime
mix += pad([38, 50, 57, 62, 66, 69], 54.6, 60.0, amp=0.085, bright=2600, fade=1.5)
mix += chime(55.35, [74, 78, 81, 86], amp=0.06)

# room: short stereo reverb from decaying noise impulses
L = int(2.6 * SR)
tt = np.arange(L) / SR
irs = [rng.standard_normal(L) * np.exp(-tt * 2.4) for _ in range(2)]
wet = [fftconvolve(mix, ir)[:N] for ir in irs]
wet = [w / (np.max(np.abs(w)) + 1e-9) * np.max(np.abs(mix)) * 0.55 for w in wet]
st = np.stack([0.75 * mix + 0.35 * wet[0], 0.75 * mix + 0.35 * wet[1]], axis=1)
st *= env(0, 60, 0.4, 1.2)[:, None]
st = st / np.max(np.abs(st)) * 0.70
out = Path(__file__).resolve().parent / "build"
out.mkdir(exist_ok=True)
pcm = (st * 32767).astype(np.int16)
import wave  # noqa: E402

with wave.open(str(out / "score.wav"), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("score.wav written", pcm.shape)
