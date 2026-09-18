#!/usr/bin/env python3
"""Submit one ComfyUI asset graph, wait, download outputs, and safely unload."""

from __future__ import annotations

import argparse
import json
import os
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
        raise ComfyError(f"Cannot reach ComfyUI at {base}: {exc.reason}") from exc


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


def wait_for_result(
    base: str,
    prompt_id: str,
    *,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = request_json(base, f"/history/{prompt_id}").get(prompt_id)
        if result:
            status = result.get("status", {})
            # An errored prompt is terminal too: it never sets completed, so waiting
            # on that flag alone turns every runtime failure into a timeout.
            if status.get("completed") or status.get("status_str") == "error":
                return result
        time.sleep(poll_seconds)
    raise ComfyError(f"Timed out waiting for {prompt_id}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one API-format ComfyUI audio or video workflow safely."
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
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--keep-loaded",
        action="store_true",
        help="Keep the model loaded for a known next job in the same model family",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    base = resolve_server(args.server, config)
    max_jobs = config.get("max_concurrent_jobs", 1)
    if max_jobs != 1:
        raise ComfyError("This skill requires max_concurrent_jobs to be 1")

    request_json(base, "/system_stats")
    if not queue_empty(base):
        raise ComfyError("Refusing to submit: ComfyUI has a running or pending job")

    uploads = [
        upload_asset(base, source, overwrite=args.overwrite_uploads)
        for source in args.upload
    ]
    payload = json.loads(args.workflow.read_text(encoding="utf-8"))
    submitted = request_json(base, "/prompt", payload)
    if submitted.get("node_errors") or "prompt_id" not in submitted:
        raise ComfyError(json.dumps(submitted, indent=2, ensure_ascii=False))

    prompt_id = submitted["prompt_id"]
    result = wait_for_result(
        base,
        prompt_id,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
    )
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

    print(
        json.dumps(
            {
                "prompt_id": prompt_id,
                "uploads": uploads,
                "outputs": downloaded,
                "vram_after_unload": vram,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ComfyError as exc:
        raise SystemExit(str(exc))
