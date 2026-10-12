#!/usr/bin/env python3
"""check_instrumental.py — prove a music bed has no voice in it.

A song model asked for an instrumental still hums, chants or adds a wordless
"ooh" on some seeds, and a background bed with a voice in it fights the game's
own dialogue and sound effects. Loudness and duration checks cannot see that.

Two stages, because either alone is wrong:

  1. a stem separator pulls out whatever it takes for a voice. On its own it
     also pulls a flute, a synth lead or a horn, so a loud stem proves nothing;
  2. an audio tagger then names what that STEM sounds like. Voice labels on a
     stem that is also loud in the mix are a voice; "Flute" or "Music" is a
     lead instrument the separator mistook.

usage:
    check_instrumental.py out/*/*.flac [--stem-db -20] [--voice-p 0.25] [--keep-stems DIR]

One line per clip: the stem's level against the mix, the strongest voice label
on the stem, and VOCAL or clean. A clip is VOCAL when the stem is louder than
--stem-db relative to the mix AND a voice label scores above --voice-p.
Exit 0 = every clip is clean, 1 = at least one VOCAL, 2 = a clip could not be read.

It is a screen, not a verdict: a clearly sung line can score barely above the
default, so the thresholds lean towards flagging. A false alarm costs one listen
(--keep-stems DIR keeps the stem to play); a miss ships a voice.

Requires a Python with demucs, transformers, librosa and soundfile (and the
torch they bring), plus ffmpeg. The first run downloads the two models. This
is a heavy environment for one check: without it, listen to the intro and the
outro, where a hum or a wordless voice comes in.
"""
import argparse
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

TAGGER = "MIT/ast-finetuned-audioset-10-10-0.4593"
VOICE = ("singing", "speech", "choir", "vocal music", "humming", "chant", "rapping", "a capella",
         "yodel", "whisper", "narration", "conversation", "shout", "scream")
NOT_VOICE = ("bowl", "bird")  # "Singing bowl", "Bird vocalization"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("clips", nargs="+", type=Path)
    parser.add_argument("--stem-db", type=float, default=-20.0, help="Stem level against the mix, dB, above which a voice counts")
    parser.add_argument("--voice-p", type=float, default=0.25, help="Voice-label score on the stem above which it is a voice")
    parser.add_argument("--keep-stems", type=Path, help="Keep the separated stems here, to listen to a flagged clip")
    args = parser.parse_args()

    try:
        import librosa
        import numpy as np
        import soundfile as sf
        import torch
        from transformers import ASTFeatureExtractor, ASTForAudioClassification
        import demucs  # noqa: F401
    except ImportError as exc:
        print(f"missing dependency: {exc.name} (needs demucs, transformers, librosa, soundfile)")
        return 2

    extractor = ASTFeatureExtractor.from_pretrained(TAGGER)
    tagger = ASTForAudioClassification.from_pretrained(TAGGER).eval()
    labels = tagger.config.id2label
    voice_ids = [i for i, name in labels.items()
                 if any(k in name.lower() for k in VOICE) and not any(k in name.lower() for k in NOT_VOICE)]

    stems_root = args.keep_stems or Path(tempfile.mkdtemp(prefix="stems-"))
    failed = False
    for index, clip in enumerate(args.clips):
        out = stems_root / f"{index:03d}_{clip.stem}"
        done = subprocess.run(
            [sys.executable, "-m", "demucs", "--two-stems", "vocals", "-o", str(out), str(clip)],
            capture_output=True, text=True,
        )
        found = list(out.glob("*/*/vocals.wav"))
        if done.returncode != 0 or not found:
            print(f"{clip}: could not be separated")
            return 2
        stem, rate = sf.read(found[0])
        rest, _ = sf.read(found[0].with_name("no_vocals.wav"))
        stem, rest = stem.mean(axis=1), rest.mean(axis=1)

        def rms(x):
            return max(float(np.sqrt((x ** 2).mean())), 1e-9)
        level = 20 * np.log10(rms(stem) / rms(stem + rest))

        mono = librosa.resample(stem.astype(np.float32), orig_sr=rate, target_sr=16000)
        mono = mono / max(float(np.abs(mono).max()), 1e-6) * 0.5
        scores = []
        for start in range(0, max(1, len(mono) - 80000), 80000):  # 10 s windows, 5 s hop
            features = extractor(mono[start:start + 160000], sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                scores.append(torch.sigmoid(tagger(**features).logits)[0].numpy())
        scores = np.array(scores)
        per_label = scores[:, voice_ids].max(axis=0)
        best = int(np.argmax(per_label))
        voice = float(per_label[best])
        vocal = level > args.stem_db and voice > args.voice_p
        failed = failed or vocal
        print(f"{'VOCAL' if vocal else 'clean'}  stem {level:6.1f} dB  {labels[voice_ids[best]]} {voice:.2f}  {clip}")
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
