#!/usr/bin/env python3
"""Submit one ComfyUI asset graph, wait, download outputs, and safely unload.

Prints one JSON object on success: prompt_id, uploads, outputs, elapsed_seconds,
vram_free_min, vram_after_unload, then what pins the run for skill
art-asset-registry — workflow_sha256, workflow_name (the file name only),
overrides (each --set target with its value: a number, a boolean, null or a
["node", slot] link as it is; text, and any other list or object, as
"sha256:<first 12 hex>" of its text, so no prompt or key is printed there),
server_label (--server-label, else null), output_files (each output with its
sha256 and bytes), and record (the partial ledger record: tool, params, inputs,
files, verdict). Each upload entry gains the local file's sha256. An upload the
server stored under another name than the local one is a warning on stderr: a
graph input naming the local file reads the older one the server already held. A failure prints its reason to stderr and
exits 1.

--job-log PATH appends one JSON line per run, success or failure, with ts and
exit_code. No server address is written to stdout or to the log: name the
machine with --server-label. In a log line's `error`, every --set text (a
number, boolean or null excepted) and every graph text holding whitespace is
replaced by its hash wherever it appears, so a server error that echoes the
graph back does not put a prompt in the log. The other keys are the report's
own, with --set texts already hashed in `overrides`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path.home() / ".codex" / "comfyui-asset-generation" / "config.json"


class ComfyError(RuntimeError):
    pass


def request(
    base: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 30,
) -> bytes:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ComfyError(f"HTTP {exc.code} for {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        # The address is private; keep it out of logs and transcripts.
        raise ComfyError(f"Cannot reach the configured ComfyUI server: {exc.reason}") from exc


def request_json(
    base: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    payload = request(base, path, body, timeout=timeout)
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ComfyError(f"Expected JSON from {path}") from exc


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComfyError(f"Invalid config file: {path}") from exc
    if not isinstance(value, dict):
        raise ComfyError(f"Config must contain a JSON object: {path}")
    return value


def resolve_server(explicit: str | None, config: dict[str, Any]) -> str:
    value = explicit or os.environ.get("COMFYUI_SERVER_URL") or config.get("server_url")
    if not isinstance(value, str) or not value.strip():
        raise ComfyError(
            "No ComfyUI server URL. Use --server, COMFYUI_SERVER_URL, "
            f"or {DEFAULT_CONFIG}"
        )
    return value.rstrip("/")


def queue_empty(base: str) -> bool:
    queue = request_json(base, "/queue")
    return not queue.get("queue_running") and not queue.get("queue_pending")


def device_summary(stats: dict[str, Any]) -> list[dict[str, Any]]:
    devices = stats.get("devices")
    if not isinstance(devices, list):
        return []
    return [
        {key: device.get(key) for key in ("name", "vram_free", "vram_total")}
        for device in devices
        if isinstance(device, dict)
    ]


def upload_asset(base: str, source: Path, *, overwrite: bool = False) -> dict[str, Any]:
    if not source.is_file():
        raise ComfyError(f"Upload source is not a file: {source}")
    boundary = f"----CodexComfyAsset{uuid.uuid4().hex}"
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{source.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    suffix = (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="type"\r\n\r\n'
        "input"
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        f"{str(overwrite).lower()}"
        f"\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        base + "/upload/image",
        data=prefix + source.read_bytes() + suffix,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ComfyError(f"Upload failed for {source}: {detail}") from exc


def iter_output_items(value: Any):
    if isinstance(value, dict):
        if isinstance(value.get("filename"), str):
            yield value
        else:
            for child in value.values():
                yield from iter_output_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_output_items(child)


def download_outputs(
    base: str,
    outputs: dict[str, Any],
    destination: Path,
) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []
    used_names: set[str] = set()
    for node_id, node_output in outputs.items():
        for item in iter_output_items(node_output):
            filename = Path(item["filename"]).name
            target_name = filename
            if target_name in used_names:
                target_name = f"{node_id}_{filename}"
            used_names.add(target_name)
            target = destination / target_name
            query = urllib.parse.urlencode(
                {
                    "filename": item["filename"],
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output"),
                }
            )
            target.write_bytes(request(base, "/view?" + query, timeout=120))
            if target.stat().st_size == 0:
                raise ComfyError(f"Downloaded empty output: {target}")
            downloaded.append(str(target))
    if not downloaded:
        raise ComfyError("Workflow succeeded but declared no downloadable outputs")
    return downloaded


def apply_overrides(prompt: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Set each NODE.INPUT=VALUE in the graph; returns {NODE.INPUT: value} as applied."""
    applied: dict[str, Any] = {}
    for item in overrides:
        target, sep, raw = item.partition("=")
        node_id, dot, input_name = target.partition(".")
        if not sep or not dot or not node_id or not input_name:
            raise ComfyError(f"--set expects NODE.INPUT=VALUE, got: {item}")
        node = prompt.get(node_id)
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            raise ComfyError(f"--set names a node that is not in the graph: {node_id}")
        # @path reads the value from a text file: a caption or lyrics with line breaks.
        # Otherwise JSON first, so numbers, booleans and ["node", slot] links keep their
        # type; anything else is a plain string.
        if raw.startswith("@"):
            try:
                value = Path(raw[1:]).read_text(encoding="utf-8").strip("\n")
            except OSError as exc:
                raise ComfyError(f"--set cannot read {raw[1:]}: {exc.strerror}") from exc
        else:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw
        node["inputs"][input_name] = value
        applied[target] = value
    return applied


URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>]*")


def sha256_file(path: Path) -> str | None:
    """The file's sha256, or None when it cannot be read: a hash never fails a run."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def short_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()[:12]


def is_link(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2 and isinstance(value[0], str)
            and isinstance(value[1], int) and not isinstance(value[1], bool))


def describe_overrides(applied: dict[str, Any]) -> dict[str, Any]:
    """{NODE.INPUT: value} with a number, a boolean, null or a ["node", slot] link kept as it
    is, and any text, list or object replaced by "sha256:<12 hex>" of its text: a prompt, a
    caption or a key never reaches the output or the log."""
    out: dict[str, Any] = {}
    for key, value in applied.items():
        if value is None or isinstance(value, (bool, int, float)) or is_link(value):
            out[key] = value
        else:
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False,
                                                                     separators=(",", ":"))
            out[key] = short_hash(text)
    return out


def secret_texts(prompt: dict[str, Any], applied: dict[str, Any], keep: set[str]) -> list[str]:
    """The texts a log line must not carry: every --set text, and every graph input text
    holding whitespace (a prompt, a caption), except the upload names in `keep`; longest
    first, so a text inside another is replaced after it."""
    found: set[str] = set()

    def walk(value: Any, from_set: bool) -> None:
        if is_link(value):
            return
        if isinstance(value, str):
            if len(value) >= 4 and (from_set or any(ch.isspace() for ch in value)):
                found.add(value)
        elif isinstance(value, list):
            for child in value:
                walk(child, from_set)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child, from_set)

    walk(list(applied.values()), True)
    for node in prompt.values():
        if isinstance(node, dict):
            walk(node.get("inputs"), False)
    return sorted(found - keep, key=len, reverse=True)


def set_secret(item: str) -> str | None:
    """The text of one raw --set that a log line must not carry: the whole item when it has no
    `=`, the value when it is @file or parses to text, a list or an object; None for a number,
    a boolean or null."""
    target, sep, raw = item.partition("=")
    if not sep:
        return item
    if raw.startswith("@"):
        return raw
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return raw if isinstance(value, (str, list, dict)) else None


def redact(value: Any, secrets: list[str]) -> Any:
    """`value` with each secret text replaced by its short hash, in every string it holds."""
    if not secrets:
        return value
    if isinstance(value, str):
        for secret in secrets:
            # A server error quotes the graph as JSON: match the escaped forms too.
            for form in {secret, json.dumps(secret, ensure_ascii=False)[1:-1], json.dumps(secret)[1:-1]}:
                if form in value:
                    value = value.replace(form, short_hash(secret))
        return value
    if isinstance(value, list):
        return [redact(child, secrets) for child in value]
    if isinstance(value, dict):
        return {key: redact(child, secrets) for key, child in value.items()}
    return value


def scrub(text: str, base: str | None) -> str:
    """`text` without the server's address or any other URL."""
    if base:
        text = text.replace(base, "<server>")
        netloc = urllib.parse.urlsplit(base).netloc
        if netloc:
            text = text.replace(netloc, "<server>")
    return URL.sub("<url>", text)


def append_job_log(path: Path, entry: dict[str, Any]) -> None:
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
        print(f"comfy_asset_client: job log {path} not written: {exc}", file=sys.stderr)


def provenance(args: argparse.Namespace, state: dict[str, Any], files: list[dict[str, Any]],
               verdict: str) -> dict[str, Any]:
    """The keys that pin a run, and its partial ledger record (skill art-asset-registry)."""
    params = {
        "workflow_sha256": state.get("workflow_sha256"),
        "workflow_name": args.workflow.name,
        "overrides": state.get("overrides"),
        "server_label": args.server_label,
    }
    inputs = [{"path": str(source.resolve()), "sha256": sha256_file(source)}
              for source in args.upload if source.is_file()]
    record = {
        "tool": {"skill": "comfyui-asset-generation", "script": "comfy_asset_client.py"},
        "params": params,
        "inputs": inputs,
        "files": [{"path": str(Path(f["path"]).resolve()), "sha256": f["sha256"], "bytes": f["bytes"]}
                  for f in files],
        "verdict": verdict,
    }
    return {**params, "record": record}


def unfilled_placeholders(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if "REPLACE_WITH_" in value else []
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return [found for child in children for found in unfilled_placeholders(child)]


def vram_free(base: str) -> int | None:
    try:
        devices = request_json(base, "/system_stats").get("devices")
    except ComfyError:
        return None
    values = [
        device.get("vram_free")
        for device in devices or []
        if isinstance(device, dict) and isinstance(device.get("vram_free"), int)
    ]
    return min(values) if values else None


def wait_for_result(
    base: str,
    prompt_id: str,
    *,
    poll_seconds: float,
    timeout_seconds: float,
) -> tuple[dict[str, Any], int | None]:
    deadline = time.monotonic() + timeout_seconds
    vram_free_min: int | None = None
    while time.monotonic() < deadline:
        result = request_json(base, f"/history/{prompt_id}").get(prompt_id)
        if result:
            status = result.get("status", {})
            # An errored prompt is terminal too: it never sets completed, so waiting
            # on that flag alone turns every runtime failure into a timeout.
            if status.get("completed") or status.get("status_str") == "error":
                return result, vram_free_min
        # The low-water mark over the run is the only view of peak VRAM use.
        free = vram_free(base)
        if free is not None and (vram_free_min is None or free < vram_free_min):
            vram_free_min = free
        time.sleep(poll_seconds)
    raise ComfyError(f"Timed out waiting for {prompt_id}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one API-format ComfyUI audio, video or 3D workflow safely."
    )
    parser.add_argument("--workflow", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--server")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--upload",
        action="append",
        type=Path,
        default=[],
        help="Authorized local image, video, or audio input; repeat as needed",
    )
    parser.add_argument("--overwrite-uploads", action="store_true")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NODE.INPUT=VALUE",
        help="Override one graph input; VALUE is @file for text, JSON when it parses, else a string",
    )
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--keep-loaded",
        action="store_true",
        help="Keep the model loaded for a known next job in the same model family",
    )
    parser.add_argument(
        "--server-label",
        help="A name for the machine (studio-gpu), recorded instead of its address",
    )
    parser.add_argument(
        "--job-log",
        type=Path,
        metavar="PATH",
        help="Append one JSON line per run, success or failure, to PATH",
    )
    args = parser.parse_args()
    if args.server_label is not None and "://" in args.server_label:
        parser.error("--server-label names the machine (studio-gpu), never its address")

    state: dict[str, Any] = {"base": None, "submitted": False}
    try:
        return run(args, state)
    except Exception as exc:
        if args.job_log is not None:
            reason = str(exc) if isinstance(exc, ComfyError) else f"{type(exc).__name__}: {exc}"
            # Only the free text is redacted: every other key is built here, its texts already
            # hashed by describe_overrides, and a number replaced inside it would corrupt it.
            append_job_log(args.job_log, {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "exit_code": 1,
                "error": redact(scrub(reason, state["base"]), state.get("secrets", [])),
                **provenance(args, state, [], "failed" if state["submitted"] else "harness"),
            })
        raise


def run(args: argparse.Namespace, state: dict[str, Any]) -> int:
    # Before anything can fail: a malformed --set is quoted whole in its error. A value that
    # parses as a number, boolean or null is not a secret (describe_overrides keeps it too).
    state["secrets"] = sorted({t for t in map(set_secret, args.set) if t and len(t) >= 4}
                              - {s.name for s in args.upload}, key=len, reverse=True)
    config = load_config(args.config)
    base = resolve_server(args.server, config)
    state["base"] = base
    max_jobs = config.get("max_concurrent_jobs", 1)
    if max_jobs != 1:
        raise ComfyError("This skill requires max_concurrent_jobs to be 1")

    request_json(base, "/system_stats")
    if not queue_empty(base):
        raise ComfyError("Refusing to submit: ComfyUI has a running or pending job")

    payload = json.loads(args.workflow.read_text(encoding="utf-8"))
    state["workflow_sha256"] = sha256_file(args.workflow)
    applied = apply_overrides(payload.get("prompt", {}), args.set)
    state["overrides"] = describe_overrides(applied)
    state["secrets"] = sorted(set(state["secrets"]) | set(secret_texts(
        payload.get("prompt", {}), applied, {source.name for source in args.upload})), key=len, reverse=True)
    unfilled = unfilled_placeholders(payload.get("prompt", {}))
    if unfilled:
        raise ComfyError(f"Refusing to submit: unfilled placeholders {unfilled}")

    uploads = [
        upload_asset(base, source, overwrite=args.overwrite_uploads)
        for source in args.upload
    ]
    for source, uploaded in zip(args.upload, uploads):
        if isinstance(uploaded, dict):
            uploaded.setdefault("sha256", sha256_file(source))
            stored = uploaded.get("name")
            if isinstance(stored, str) and stored != source.name:
                print(f"comfy_asset_client: {source.name} was stored as {stored}; a graph input "
                      f"naming {source.name} reads the file already there. Name uploads per asset, "
                      "view and run, or pass --overwrite-uploads.", file=sys.stderr)
    started = time.monotonic()
    state["submitted"] = True
    submitted = request_json(base, "/prompt", payload)
    if submitted.get("node_errors") or "prompt_id" not in submitted:
        raise ComfyError(json.dumps(submitted, indent=2, ensure_ascii=False))

    prompt_id = submitted["prompt_id"]
    result, vram_free_min = wait_for_result(
        base,
        prompt_id,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    elapsed_seconds = round(time.monotonic() - started, 1)
    status = result.get("status", {})
    if status.get("status_str") != "success":
        raise ComfyError(json.dumps(status, indent=2, ensure_ascii=False))

    downloaded = download_outputs(base, result.get("outputs", {}), args.output_dir)
    unload_when_idle = bool(config.get("unload_when_idle", True))
    vram: list[dict[str, Any]] = []
    if not args.keep_loaded and unload_when_idle and queue_empty(base):
        request(base, "/free", {"unload_models": True, "free_memory": True})
        try:
            vram = device_summary(request_json(base, "/system_stats"))
        except ComfyError:
            vram = []

    # `outputs` stays a list of paths; the hashes go in the parallel `output_files`.
    output_files = [
        {"path": path, "sha256": sha256_file(Path(path)), "bytes": Path(path).stat().st_size}
        for path in downloaded
    ]
    report = {
        "prompt_id": prompt_id,
        "uploads": uploads,
        "outputs": downloaded,
        "elapsed_seconds": elapsed_seconds,
        "vram_free_min": vram_free_min,
        "vram_after_unload": vram,
    }
    pinned = provenance(args, state, output_files, "green")
    report.update({key: value for key, value in pinned.items() if key != "record"})
    report["output_files"] = output_files
    report["record"] = pinned["record"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.job_log is not None:
        append_job_log(args.job_log, {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      "exit_code": 0, **report})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ComfyError as exc:
        raise SystemExit(str(exc))
