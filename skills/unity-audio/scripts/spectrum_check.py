#!/usr/bin/env python3
"""spectrum_check.py — is every sound in a folder quiet above a cutoff frequency?

For a project with a hard upper limit on game audio: a microphone-based input that listens
above 16 kHz, a hearing-safety rule, a broadcast spec. For each WAV file it measures the energy
above --cutoff as a share of the clip's total energy, in dB, and fails any clip above --max-db.

  ratio_db = 10 log10( sum |X[k]|^2 for f_k >= cutoff  /  sum |X[k]|^2 for k >= 1 )

over one FFT of the whole clip, zero-padded to a power of two, after mixing to mono.

  * One-shots are measured without a window. A Hann window would hide a sharp attack, which is
    exactly the high-frequency energy being looked for. Instead every one-shot must already end
    at zero (|last sample| < 1e-3): an abrupt end is a click, and a click is broadband.
  * Loops (--loop, or file names matching --loop-glob) are steady sounds and are measured with a
    Hann window. Their seam is checked too: the jump from the last sample to the first must be no
    larger than 1.5 x the largest sample-to-sample step in the first 0.1 s, plus 1e-4.

Before trusting a pass, the measurement proves it can see a failure: `selftest` mixes a 17 kHz
tone at 1% amplitude into a 1 kHz tone and expects about -40 dB (within 1.5 dB).

Worked numbers: a tennis game's synthesised effects and ambience loops (attack and fade shaped,
noise low-passed, a final 7 kHz low-pass) measured about -120 dB above 16 kHz, against a gate
of -60 dB.

Examples:
  spectrum_check.py Assets/Audio
  spectrum_check.py Assets/Audio --cutoff 16000 --max-db -60 --loop-glob 'amb_*'
  spectrum_check.py hit.wav --json
  spectrum_check.py selftest

Reads PCM WAV (8, 16, 24 or 32-bit integer, any channel count) with the standard library; float
WAV and compressed formats are refused, so export or convert to PCM first. Needs numpy.
Prints one [SPECTRUM] line per file and a summary, or one JSON object with --json.
Exit codes: 0 every file passes · 1 a file fails · 2 usage or IO error, or no files.
"""
import argparse
import fnmatch
import json
import pathlib
import sys
import wave

import numpy as np


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if w.getcomptype() != "NONE":
            raise ValueError(f"{path}: compressed WAV ({w.getcomptype()}) is not supported")
        raw = w.readframes(n)
    if width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v.astype(np.float64) / float(1 << 23)
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float64) / float(1 << 31)
    else:
        raise ValueError(f"{path}: {8 * width}-bit samples are not supported")
    x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def high_band_db(x, rate, cutoff, hann):
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 2:
        return 0.0
    if hann:
        x = x * (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(len(x)) / (len(x) - 1)))
    n = 1 << int(np.ceil(np.log2(len(x))))
    p = np.abs(np.fft.rfft(x, n)) ** 2
    f = np.arange(len(p)) * rate / n
    total = p[1:].sum()
    high = p[f >= cutoff].sum()
    return float(10 * np.log10(high / max(total, 1e-30) + 1e-30))


def seam_ok(x, rate):
    head = x[: max(2, int(0.1 * rate))]
    typical = float(np.max(np.abs(np.diff(head)))) if len(head) > 1 else 0.0
    jump = float(abs(x[0] - x[-1]))
    return jump <= typical * 1.5 + 1e-4, jump, typical


def check(x, rate, cutoff, max_db, loop):
    r = {"rate": rate, "seconds": round(len(x) / rate, 3), "loop": loop}
    r["high_db"] = round(high_band_db(x, rate, cutoff, hann=loop), 1)
    problems = []
    if rate < 2 * cutoff:
        problems.append(f"sample rate {rate} cannot represent {cutoff} Hz; nothing to measure")
    if r["high_db"] >= max_db:
        problems.append(f"energy above {cutoff:.0f} Hz is {r['high_db']} dB, limit {max_db}")
    if np.max(np.abs(x)) > 1.0 + 1e-9 or not np.all(np.isfinite(x)):
        problems.append("clips or contains NaN")
    if loop:
        ok, jump, typical = seam_ok(x, rate)
        r["seam_jump"], r["seam_typical"] = round(jump, 5), round(typical, 5)
        if not ok:
            problems.append(f"loop seam jumps {jump:.4f} (typical step {typical:.4f})")
    elif abs(x[-1]) >= 1e-3:
        problems.append(f"does not end at zero (last sample {x[-1]:.4f}): a click")
    r["problems"] = problems
    r["pass"] = not problems
    return r


# ---------------------------------------------------------------- selftest fixtures

def shaped_tone(rate, freq=1000.0, seconds=0.4, attack=0.003, tau=0.08, fade=0.05):
    t = np.arange(int(seconds * rate)) / rate
    env = np.where(t < attack, 0.5 - 0.5 * np.cos(np.pi * t / attack), 1.0) * np.exp(-np.maximum(0, t - attack) / tau)
    x = 0.8 * env * np.sin(2 * np.pi * freq * t)
    nf = int(fade * rate)
    x[-nf:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(1, nf + 1) / nf)   # Hann fade to exactly 0
    return x


def selftest():
    fails = []
    rate = 48000
    t = np.arange(rate) / rate
    cal = np.sin(2 * np.pi * 1000 * t) + 0.01 * np.sin(2 * np.pi * 17000 * t)
    db = high_band_db(cal, rate, 16000, hann=True)
    if abs(db + 40) > 1.5:
        fails.append(f"calibration: 17 kHz at 1% should read about -40 dB, read {db:.1f}")
    for r_ in (48000, 44100):
        good = check(shaped_tone(r_), r_, 16000, -60, loop=False)
        if not good["pass"]:
            fails.append(f"a shaped 1 kHz tone at {r_} should pass: {good}")
    rng = np.random.default_rng(1)
    noise = 0.5 * rng.uniform(-1, 1, rate // 2)
    noise[-2400:] *= np.linspace(1, 0, 2400)
    bad = check(noise, rate, 16000, -60, loop=False)
    if bad["pass"]:
        fails.append(f"white noise must fail: {bad}")
    hard = shaped_tone(rate)
    hard[: int(0.003 * rate)] = 0.8 * np.sin(2 * np.pi * 1000 * t[: int(0.003 * rate)])   # square attack
    hard[0] = 0.8
    if check(hard, rate, 16000, -60, loop=False)["high_db"] <= check(shaped_tone(rate), rate, 16000, -60, False)["high_db"]:
        fails.append("a hard attack must measure more high-band energy than a raised-cosine one")
    cut = shaped_tone(rate)[: int(0.2 * rate)]
    if check(cut, rate, 16000, -60, loop=False)["pass"]:
        fails.append("a one-shot that ends mid-waveform must fail (click)")
    loop = 0.5 * np.cos(2 * np.pi * 220 * np.arange(rate) / rate)            # 220 whole cycles
    if not check(loop, rate, 16000, -60, loop=True)["pass"]:
        fails.append("a whole-cycle 220 Hz loop should pass the seam check")
    broken = 0.5 * np.cos(2 * np.pi * 220.5 * np.arange(rate) / rate)        # ends at -0.5, starts at +0.5
    if check(broken, rate, 16000, -60, loop=True)["pass"]:
        fails.append("a loop that ends half a cycle out must fail the seam check")
    if fails:
        print("selftest FAILED:\n  " + "\n  ".join(fails))
        return 1
    print(f"selftest OK: calibration {db:.1f} dB (expect -40), shaped tone passes at 48 and 44.1 kHz, "
          "noise fails, hard attack measures higher, click fails, loop seam passes and fails")
    return 0


def main(argv):
    if argv[:1] in (["selftest"], ["--selftest"]):
        return selftest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="WAV files or folders (searched recursively)")
    ap.add_argument("--cutoff", type=float, default=16000.0)
    ap.add_argument("--max-db", type=float, default=-60.0)
    ap.add_argument("--loop", action="store_true", help="treat every file as a loop")
    ap.add_argument("--loop-glob", action="append", default=[], help="file-name pattern of loops, repeatable")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    files = []
    for p in map(pathlib.Path, a.paths):
        if p.is_dir():
            files += sorted(q for q in p.rglob("*") if q.suffix.lower() == ".wav")
        elif p.is_file():
            files.append(p)
        else:
            print(f"error: {p} not found", file=sys.stderr)
            return 2
    if not files:
        print("error: no .wav files", file=sys.stderr)
        return 2
    results = {}
    for f in files:
        try:
            x, rate = read_wav(f)
        except (OSError, ValueError, wave.Error) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        loop = a.loop or any(fnmatch.fnmatch(f.name, g) for g in a.loop_glob)
        results[str(f)] = check(x, rate, a.cutoff, a.max_db, loop)
    failed = [k for k, v in results.items() if not v["pass"]]
    if a.json:
        print(json.dumps({"cutoff": a.cutoff, "max_db": a.max_db, "files": results, "failed": failed}, indent=1))
    else:
        for k, v in results.items():
            print(f"[SPECTRUM] {k} {v['rate']} Hz {'loop' if v['loop'] else 'one-shot'} "
                  f"above {a.cutoff:.0f} Hz: {v['high_db']} dB {'PASS' if v['pass'] else 'FAIL: ' + '; '.join(v['problems'])}")
        print(f"[SPECTRUM] {len(results) - len(failed)}/{len(results)} pass, gate {a.max_db} dB above {a.cutoff:.0f} Hz")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
