#!/usr/bin/env python3
"""codex_generate.py — one `codex exec` image generation, and proof that THIS call produced the file.

`codex exec` exits 0 when the agent model is rejected, when the image tool never
ran, and when the agent resized its own copy. This makes the call the way
`reference/codex-runtime.md` §1-§4 says to and reads the result back:

  1. probes the agent model with a one-word prompt, so a rejected slug fails
     here instead of after a batch (skip with --no-probe once it has passed);
  2. runs from a throwaway directory, so the copy the image tool leaves under
     `output/` never lands in the project;
  3. runs under a private, temporary CODEX_HOME by default (auth.json linked,
     config.toml copied, removed afterwards), so another codex job on the same
     machine cannot write into the folder it reads;
  4. takes the ORIGINAL from `generated_images/<session id>/`, the folder of the
     session this call started (codex prints `session id: ...`), never the newest
     file on the machine. With --shared-home the call runs under the real
     CODEX_HOME; only its own session folder counts then, or, when no id can be
     read, only session folders that did not exist before the call;
  5. saves EVERY new image when one call renders more than one: --out, then
     <stem>.2<ext>, <stem>.3<ext>, ... in the order they were written, lists them
     under "images" and exits 5, because which one was meant is a human call;
  6. reads the real pixel size from each file, and whether it carries alpha
     (an RGBA render was keyed by the agent: ask again for an opaque one), and
     with --expect-size WxH exits 6 when a render is another size.

usage:
    codex_generate.py --prompt-file prompt.txt --out DEST.png [-i anchor.png ...] [-m MODEL]
    codex_generate.py --prompt 'STYLE PREAMBLE. Subject: ...' --out DEST.png -i anchors/master.png \\
        --expect-size 1672x941

`$imagegen` is prepended when the prompt does not carry it. Reference images
go in the order the prompt names them. Prints one JSON object.

Exit codes: 0 one new image was written to --out; 2 `codex` is not installed
(ask the user; never auto-install); 3 the agent model was rejected or the
probe failed (pass another -m); 4 the call ran and produced no new image;
5 the call produced more than one new image (all written, see "images");
6 the image is not --expect-size (written anyway, so it can be looked at).
5 wins over 6.

Every object printed also carries `model` (the -m value, null for the
config's), `record` (this call's partial ledger record for skill
art-asset-registry: tool, params, inputs, files, verdict — green on exit 0,
failed on 4/5/6, harness on 2/3), and, once the prompt has been read,
`prompt_sha256` (of the prompt file's bytes, or of --prompt as given) and
`inputs` (each -i with its sha256). A written image adds `out_sha256`.
`--job-log PATH` appends that object as one JSON line, with `ts` and
`exit_code` (this script's; `exit` on exit 4 is codex's own), and with the
prompt text, and each of its lines, replaced by "<prompt>" wherever an ERROR
line quoted it, and every URL by "<url>". The object carries the prompt's
hash, not its text.

Stdlib only. A private home needs `auth.json` in the real CODEX_HOME; with
none (keyring or API-key login) the call falls back to the shared home and
says so under "isolation_skipped".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>]*")
SESSION_ID = re.compile(r"^session id:\s*([0-9A-Za-z][0-9A-Za-z_-]*)\s*$", re.MULTILINE)


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def parse_session_id(text: str) -> str | None:
    """The id from the `session id:` header line. The header precedes the echoed
    prompt, so the first match is the session's even if the prompt quotes one."""
    match = SESSION_ID.search(text)
    return match.group(1) if match else None


def snapshot(home: Path) -> tuple[set[str], set[Path]]:
    """Session folder names and PNG files under `home/generated_images` right now."""
    root = home / "generated_images"
    if not root.is_dir():
        return set(), set()
    folders = {d.name for d in root.iterdir() if d.is_dir()}
    return folders, set(root.glob("*/*.png"))


def by_write_order(files) -> list[Path]:
    return sorted(files, key=lambda p: (p.stat().st_mtime_ns, p.name))


def new_images(
    home: Path,
    before_folders: set[str],
    before_files: set[Path],
    session_id: str | None,
    private: bool,
) -> tuple[list[Path], str]:
    """The images this call made, oldest first, and how they were found.

    private  -> every new PNG in the private home: nothing else writes there.
    session  -> the new PNGs in `generated_images/<session id>/`.
    folders  -> no id was printed: PNGs in session folders that did not exist
                before the call (a job started during this one can still land
                here, which is why the private home is the default).
    If an id was printed but its folder does not exist, the call made nothing;
    folders other sessions created meanwhile are not taken."""
    root = home / "generated_images"
    if not root.is_dir():
        return [], "private" if private else ("session" if session_id else "folders")
    if private:
        return by_write_order(set(root.glob("*/*.png")) - before_files), "private"
    if session_id:
        return by_write_order(set((root / session_id).glob("*.png")) - before_files), "session"
    fresh = [d for d in root.iterdir() if d.is_dir() and d.name not in before_folders]
    return by_write_order(p for d in fresh for p in d.glob("*.png")), "folders"


def numbered(out: Path, k: int) -> Path:
    """--out for the first image, <stem>.2<ext> for the second, and so on."""
    return out if k == 0 else out.with_name(f"{out.stem}.{k + 1}{out.suffix}")


def parse_size(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", text)
    if not match:
        raise argparse.ArgumentTypeError(f"expected WxH, got {text!r}")
    return int(match.group(1)), int(match.group(2))


def make_private_home(source: Path) -> Path | None:
    """A temporary CODEX_HOME that shares the login and the config, or None when
    there is no auth.json to share."""
    auth = source / "auth.json"
    if not auth.is_file():
        return None
    home = Path(tempfile.mkdtemp(prefix="codex-home-"))
    (home / "auth.json").symlink_to(auth.resolve())
    config = source / "config.toml"
    if config.is_file():
        shutil.copyfile(config, home / "config.toml")
    return home


def errors(text: str) -> list[str]:
    seen: list[str] = []
    for line in text.splitlines():
        if line.startswith("ERROR") and line not in seen:
            seen.append(line[:400])
    return seen


def run_codex(args: list[str], cwd: Path, timeout: float, env: dict[str, str]) -> tuple[int, str]:
    try:
        done = subprocess.run(
            ["codex", "exec", *args],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,  # a non-TTY `codex exec` otherwise waits on stdin
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        return 124, partial + "\nERROR: timed out"
    return done.returncode, done.stdout


def png_info(path: Path) -> tuple[list[int] | None, bool | None]:
    head = path.read_bytes()[:33]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    width, height, _depth, colour_type = struct.unpack_from(">IIBB", head, 16)
    return [width, height], colour_type in (4, 6)


def size_ok(size: list[int] | None, expect: tuple[int, int] | None, tolerance: int) -> bool | None:
    if expect is None:
        return None
    if size is None:
        return False
    return abs(size[0] - expect[0]) <= tolerance and abs(size[1] - expect[1]) <= tolerance


def sha256_file(path: Path) -> str | None:
    """The file's sha256, or None when it cannot be read: a hash never fails a call."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def make_record(params: dict, inputs: list[dict], files: list[dict], verdict: str) -> dict:
    """This call's partial ledger record (skill art-asset-registry, `record --json`)."""
    return {"tool": {"skill": "codex-visual", "script": "codex_generate.py"},
            "params": params, "inputs": inputs, "files": files, "verdict": verdict}


def append_job_log(path: Path, entry: dict) -> None:
    """One JSON line, appended in one write. A log that cannot be written is reported, never fatal."""
    data = (json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            written = os.write(fd, data)
            while written < len(data):
                written += os.write(fd, data[written:])
        finally:
            os.close(fd)
    except OSError as exc:
        print(f"codex_generate: job log {path} not written: {exc}", file=sys.stderr)


def prompt_texts(raw: str, sent: str) -> list[str]:
    """The prompt as given, as sent, and each of its lines of 12 characters or more: what a
    log line must not carry. Longest first, so a line inside the whole is replaced after it."""
    found = {text for text in (raw, raw.strip(), sent) if len(text) >= 4}
    found.update(line.strip() for line in raw.splitlines() if len(line.strip()) >= 12)
    return sorted(found, key=len, reverse=True)


def redact(value, secrets: list[str]):
    """`value` with each secret text replaced by "<prompt>", and any URL by "<url>", in every
    string it holds."""
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "<prompt>")
        return URL.sub("<url>", value)
    if isinstance(value, list):
        return [redact(child, secrets) for child in value]
    if isinstance(value, dict):
        return {key: redact(child, secrets) for key, child in value.items()}
    return value


def emit(obj: dict, code: int, job_log: Path | None, secrets: list[str] | None = None, **dump) -> int:
    """Print the call's one JSON object, log it when asked (without the prompt text, should an
    ERROR line have quoted it), and pass the exit code through."""
    print(json.dumps(obj, **dump))
    if job_log is not None:
        append_job_log(job_log, redact({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                        "exit_code": code, **obj}, secrets or []))
    return code


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
    parser.add_argument("--shared-home", action="store_true",
                        help="Run under the real CODEX_HOME instead of a private temporary one")
    parser.add_argument("--keep-home", action="store_true",
                        help="Keep the private CODEX_HOME after the call (its path is printed) for debugging")
    parser.add_argument("--expect-size", type=parse_size, metavar="WxH",
                        help="Exit 6 when a render is not this size, e.g. 1672x941 for a 16:9 ask")
    parser.add_argument("--size-tolerance", type=int, default=1, metavar="PX",
                        help="Pixels either axis may differ from --expect-size (default 1: a 16:9 ask "
                             "has come back both 1672x940 and 1672x941)")
    parser.add_argument("--job-log", type=Path, metavar="PATH",
                        help="Append this call's JSON object to PATH as one line, with ts and exit_code")
    args = parser.parse_args()

    if shutil.which("codex") is None:
        return emit({"error": "codex is not on PATH", "model": args.model,
                     "record": make_record({"model": args.model}, [], [], "harness")}, 2, args.job_log)
    missing = [str(p) for p in args.image if not p.is_file()]
    if missing:
        parser.error(f"reference image not found: {', '.join(missing)}")

    raw_prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8")
    prompt = raw_prompt
    prompt_sha256 = hashlib.sha256(
        args.prompt.encode("utf-8", "surrogateescape") if args.prompt is not None
        else args.prompt_file.read_bytes()).hexdigest()
    prompt = prompt.strip()
    if "$imagegen" not in prompt:
        prompt = "$imagegen " + prompt
    secrets = prompt_texts(raw_prompt, prompt)
    model = ["-m", args.model] if args.model else []
    out = args.out.resolve()
    images = [str(p.resolve()) for p in args.image]
    inputs = [{"path": path, "sha256": sha256_file(Path(path))} for path in images]
    params = {"prompt_sha256": prompt_sha256, "model": args.model}

    def provenance(files: list[dict], verdict: str) -> dict:
        """The keys every object printed after the prompt was read carries, after its own."""
        return {"model": args.model, "prompt_sha256": prompt_sha256, "inputs": inputs,
                "record": make_record(params, inputs, files, verdict)}

    real_home = codex_home()
    private_home = None if args.shared_home else make_private_home(real_home)
    skipped = None
    if not args.shared_home and private_home is None:
        skipped = f"no auth.json in {real_home}; ran under the shared home"
        print(f"codex_generate: {skipped}", file=sys.stderr)
    home = private_home or real_home
    env = dict(os.environ, CODEX_HOME=str(home))

    work = Path(tempfile.mkdtemp(prefix="codex-generate-"))
    report: dict = {}
    code, text, session_id, capture = 0, "", None, ""
    fresh: list[Path] = []
    written: list[dict] = []
    keep_home = args.keep_home
    try:
        if not args.no_probe:
            pcode, ptext = run_codex([*model, "--skip-git-repo-check", "Reply with the single word OK."], work, 120, env)
            if pcode != 0 or errors(ptext):
                return emit({"error": "agent model probe failed", "model": args.model, "detail": errors(ptext),
                             "isolated": private_home is not None, **provenance([], "harness")}, 3, args.job_log,
                            secrets)

        before_folders, before_files = snapshot(home)
        started = time.monotonic()
        # prompt FIRST, -i LAST: -i is variadic and swallows a trailing prompt
        call = [*model, "--sandbox", "workspace-write", "--skip-git-repo-check", prompt]
        if images:
            call += ["-i", *images]
        code, text = run_codex(call, work, args.timeout, env)
        elapsed = round(time.monotonic() - started, 1)
        session_id = parse_session_id(text)
        fresh, capture = new_images(home, before_folders, before_files, session_id, private_home is not None)

        out.parent.mkdir(parents=True, exist_ok=True)
        for k, original in enumerate(fresh):
            dest = numbered(out, k)
            shutil.copyfile(original, dest)
            size, alpha = png_info(dest)
            written.append({"out": str(dest), "size": size, "alpha": alpha, "original": str(original),
                            "size_ok": size_ok(size, args.expect_size, args.size_tolerance)})

        if private_home is not None and not (private_home / "auth.json").is_symlink():
            # codex replaced the link with a file (a token refresh written by rename):
            # the fresh login lives only here, so the folder is kept for the user.
            keep_home = True
            report["auth_link_replaced"] = True
            print(f"codex_generate: {private_home}/auth.json is no longer a link to {real_home}/auth.json; "
                  "the private home is kept. Compare the two before deleting it.", file=sys.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if private_home is not None and not keep_home:
            shutil.rmtree(private_home, ignore_errors=True)

    common = {
        "session_id": session_id,
        "isolated": private_home is not None,
        "capture": capture,
    }
    if skipped:
        common["isolation_skipped"] = skipped
    if private_home is not None:
        common["codex_home"] = str(private_home)
        common["codex_home_removed"] = not keep_home
    common.update(report)

    if not fresh:
        detail = errors(text)
        if not session_id and capture != "private":
            detail.append("no 'session id:' line in the codex output; only new session folders were searched")
        status = 3 if any("not supported" in line for line in detail) else 4
        return emit({"error": "no new image in generated_images", "exit": code, "detail": detail, **common,
                     **provenance([], "harness" if status == 3 else "failed")}, status, args.job_log, secrets)

    first = written[0]
    result = {
        "out": first["out"],
        "size": first["size"],
        "alpha": first["alpha"],
        "original": first["original"],
        "new_images": len(fresh),
        "elapsed_seconds": elapsed,
        **common,
        "images": written,
    }
    if args.expect_size is not None:
        result["expect_size"] = list(args.expect_size)
        result["size_tolerance"] = args.size_tolerance
    status = 0
    if len(written) > 1:
        status = 5
        result["error"] = (f"the call produced {len(written)} images; all were written "
                           "(see images) and none was chosen")
    elif first["size_ok"] is False:
        status = 6
        result["error"] = f"the image is {first['size']}, not {list(args.expect_size)}"
    files = [{"path": w["out"], "sha256": sha256_file(Path(w["out"])), "bytes": Path(w["out"]).stat().st_size}
             for w in written]
    result["out_sha256"] = files[0]["sha256"]
    result.update(provenance(files, "green" if status == 0 else "failed"))
    return emit(result, status, args.job_log, secrets, indent=2)


if __name__ == "__main__":
    sys.exit(main())
