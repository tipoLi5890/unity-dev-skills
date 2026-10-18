# Synthesised effects, and a hard ceiling on frequency

> Part of the `unity-audio` skill. For a project that makes its effects in code (placeholders, a
> procedural style, or a hard technical limit), and for any project with a rule that no game
> sound may carry energy above some frequency: a microphone-based input that listens above it, a
> hearing-safety requirement, a broadcast spec. Worked setting: a tennis game whose input listens
> in the 18–23 kHz band, so every game sound must stay under 16 kHz.

A frequency limit is not met by choosing low-pitched sounds. White noise runs flat to Nyquist; a
sound that starts or stops on a sharp edge sprays energy across the whole spectrum; a loop with a
jump at its seam clicks once per cycle. Each is broadband whatever its pitch. The limit has to be
designed into the synthesis and then **measured**, with a measurement that has first been shown
to catch a failure.

## 1. Synthesis rules that keep the spectrum clean

Pure C#, no engine calls, so an EditMode test can call it directly. One function
`float[] Make(string name, int rate)`; the runtime wraps the result in
`AudioClip.Create(name, data.Length, 1, rate, false)` + `SetData` at
`AudioSettings.outputSampleRate`, and the test calls the same function at 48 000 and 44 100.

| Rule | How | Why |
|---|---|---|
| Tonal parts low | Sines and their harmonics under about 6 kHz | Harmonics are where a "click" or "ping" puts its energy |
| Noise filtered before use | Two cascaded second-order low-passes (about −24 dB/octave), cutoff ≤ 6 kHz, or a band-pass for a whoosh | Raw noise is flat to Nyquist |
| Attacks shaped | A raised-cosine rise over at least 3 ms, then exponential decay | A step onset is a broadband click |
| Endings shaped | A Hann fade to exactly zero over the last part of every one-shot | An abrupt end is a click at the end |
| A final safety filter | Every one-shot through two more 7 kHz low-pass stages | About 30 dB more above 16 kHz, inaudible on short effects |
| Loops cross-faded | Synthesise `fade` seconds extra; blend the tail into the head with an equal-power curve (sin/cos); low-pass **before** the cross-fade | A filter's start-up transient must not land on the seam |
| Deterministic | Fixed seeds for every noise source | The same clip at the same rate every run; tests are stable |

The tennis game made hit (pitched by ball speed), perfect hit, bounce, net, whiff, UI click and
tick, point chime, beat, applause, and three venue ambience loops (breeze with birds, waves, wind
and water) this way. Every one measured about −120 dB above 16 kHz against a −60 dB gate.

## 2. The measurement, and proving it can fail

The gate: energy above the cutoff, divided by total energy, in dB, from one FFT of the whole clip
zero-padded to a power of two. Fail at −60 dB or above.

- **Calibrate first.** A 1 kHz tone with a 17 kHz tone at 1% amplitude mixed in must read about
  −40 dB (within 1.5 dB). If it does not, the FFT, the bin-to-frequency mapping or the window is
  wrong, and every pass after it means nothing.
- **No window on one-shots.** A Hann window tapers the start of the clip, which is where a sharp
  attack lives; windowing would hide the fault being tested for. Assert instead that every
  one-shot ends at zero (|last sample| < 1e-3).
- **Hann on loops**, which are steady sounds measured as if they continued.
- **Loop seam.** The step from the last sample to the first must be no bigger than 1.5 × the
  largest step in the first 0.1 s, plus 1e-4.
- **Both output rates.** 48 000 and 44 100: filter coefficients depend on the rate.
- **Imported clips too.** The same test loads every `AudioClip` under `Resources` with
  `GetData` (it needs the clip readable: Load Type Decompress On Load) and applies the gate.
- **Mind the bit depth.** 16-bit quantisation alone sits at about −90 dB above 16 kHz for a clean
  tone, so a −60 dB gate still has room; a −100 dB gate would fail every 16-bit file.

`scripts/spectrum_check.py` runs the same gate over a folder of WAV files from the command line,
with a `selftest` that includes the calibration tone, a noise clip that must fail, a click that
must fail and a seam that must fail. In Unity the equivalent is an EditMode test over
`Make(name, rate)` for every name, plus the `Resources` scan.

## 3. A last line at runtime

Put an `AudioLowPassFilter` at 15 kHz (resonance Q 1) on the one `AudioListener`: every sound in
the game passes through it, including any file added later without anyone running the check.
It is a safety net, not the control. A single filter's slope is gentle, so a sound with real
energy at 18 kHz would still leak through. The synthesis rules and the test are what hold the
limit. Generated or recorded files are band-limited at import (for example ffmpeg
`lowpass=f=15000`, resampled to 48 kHz) and then go through the same gate.

## Traps

| Symptom | Cause | Fix |
|---|---|---|
| A low thud fails the gate | A square attack or an abrupt end | Raised-cosine attack, Hann fade to zero |
| A whoosh fails the gate | Unfiltered noise | Low-pass or band-pass noise before shaping it |
| The loop clicks once per cycle | A jump at the seam, or a filter transient on it | Equal-power cross-fade of extra material; filter first |
| Every clip passes, including one known to be bad | The measurement is blind (wrong bins, windowed one-shots) | The 17 kHz calibration test first |
| `GetData` returns false on an imported clip | Streaming or compressed in memory | Decompress On Load for the clips the test reads |
