#!/usr/bin/env python3
"""codex_generate.py — one `codex exec` image generation, and proof that it produced a file.

`codex exec` exits 0 when the agent model is rejected, when the image tool never
ran, and when the agent resized its own copy. This makes the call the way
`reference/codex-runtime.md` §1-§4 says to and reads the result back:

  1. probes the agent model with a one-word prompt, so a rejected slug fails
     here instead of after a batch (skip with --no-probe once it has passed);
  2. runs from a throwaway directory, so the copy the image tool leaves under
     `output/` never lands in the project;
  3. takes the ORIGINAL from `$CODEX_HOME/generated_images` by diffing that
     folder before and after, never the agent's copy;
  4. reads the real pixel size from the file, and whether it carries alpha
     (an RGBA render was keyed by the agent: ask again for an opaque one).

usage:
    codex_generate.py --prompt-file prompt.txt --out DEST.png [-i anchor.png ...] [-m MODEL]
    codex_generate.py --prompt 'STYLE PREAMBLE. Subject: ...' --out DEST.png -i anchors/master.png

`$imagegen` is prepended when the prompt does not carry it. Reference images
go in the order the prompt names them. Prints one JSON object.

Exit codes: 0 a new image was written to --out; 2 `codex` is not installed
(ask the user; never auto-install); 3 the agent model was rejected or the
probe failed (pass another -m); 4 the call ran and produced no new image.

Stdlib only. Parallel jobs: give each its own CODEX_HOME (`reference/codex-runtime.md` §3).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def generated() -> set[Path]:
    return set((codex_home() / "generated_images").glob("*/*.png"))


def errors(text: str) -> list[str]:
    seen: list[str] = []
    for line in text.splitlines():
        if line.startswith("ERROR") and line not in seen:
            seen.append(line[:400])
    return seen


def run_codex(args: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    try:
        done = subprocess.run(
            ["codex", "exec", *args],
            cwd=cwd,
            stdin=subprocess.DEVNULL,  # a non-TTY `codex exec` otherwise waits on stdin
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, (exc.stdout or "") + "\nERROR: timed out"
    return done.returncode, done.stdout


def png_info(path: Path) -> tuple[list[int] | None, bool | None]:
    head = path.read_bytes()[:33]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    width, height, _depth, colour_type = struct.unpack_from(">IIBB", head, 16)
    return [width, height], colour_type in (4, 6)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt")
    source.add_argument("--prompt-file", type=Path)
    parser.add_argument("--out", required=True, type=Path, help="Where the original render is copied")
    parser.add_argument("-i", "--image", action="append", type=Path, default=[], help="Reference image; repeat in prompt order")
    parser.add_argument("-m", "--model", help="Agent model slug; omit to use the config's")
    parser.add_argument("--no-probe", action="store_true", help="Skip the model probe (it already passed in this batch)")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    if shutil.which("codex") is None:
        print(json.dumps({"error": "codex is not on PATH"}))
        return 2
    missing = [str(p) for p in args.image if not p.is_file()]
    if missing:
        parser.error(f"reference image not found: {', '.join(missing)}")

    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8")
    prompt = prompt.strip()
    if "$imagegen" not in prompt:
        prompt = "$imagegen " + prompt
    model = ["-m", args.model] if args.model else []
    out = args.out.resolve()
    images = [str(p.resolve()) for p in args.image]

    work = Path(tempfile.mkdtemp(prefix="codex-generate-"))
    try:
        if not args.no_probe:
            code, text = run_codex([*model, "--skip-git-repo-check", "Reply with the single word OK."], work, 120)
            if code != 0 or errors(text):
                print(json.dumps({"error": "agent model probe failed", "model": args.model, "detail": errors(text)}))
                return 3

        before = generated()
        started = time.monotonic()
        # prompt FIRST, -i LAST: -i is variadic and swallows a trailing prompt
        call = [*model, "--sandbox", "workspace-write", "--skip-git-repo-check", prompt]
        if images:
            call += ["-i", *images]
        code, text = run_codex(call, work, args.timeout)
        elapsed = round(time.monotonic() - started, 1)
        fresh = sorted(generated() - before, key=lambda p: p.stat().st_mtime)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if not fresh:
        detail = errors(text)
        print(json.dumps({"error": "no new image in generated_images", "exit": code, "detail": detail}))
        return 3 if any("not supported" in line for line in detail) else 4

    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fresh[-1], out)
    size, alpha = png_info(out)
    print(
        json.dumps(
            {
                "out": str(out),
                "size": size,
                "alpha": alpha,
                "original": str(fresh[-1]),
                "new_images": len(fresh),
                "elapsed_seconds": elapsed,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
