#!/usr/bin/env python3
"""probe.py — read GameProbe from a live Editor, and wait on readiness instead of sleeping.

Wraps:

    unity command eval 'return GameProbe.Json();' --format json

and unwraps BOTH envelope levels before believing anything: the outer `success` only means the
command reached the Editor, and the eval's return value lands at data.result.result. A harness
that checks the outer flag alone reports a snapshot it never received.

Outside Play mode GameProbe answers {"schema":1,"playing":false} rather than throwing, so a
poll loop keeps polling while the Editor enters Play mode.

Examples:
  probe.py --project-path .                       # pretty-print the snapshot
  probe.py --key state                            # one value, for a shell test
  probe.py --key custom.gateDist                  # dotted paths work
  probe.py --watch 0.5                            # one line per poll until Ctrl-C
  probe.py --wait-ready --timeout 20              # exit 1 naming the members that never arrived

Requires the `unity` CLI on PATH and a running Editor with the CLI package installed.
Exit codes: 0 fine · 1 not ready / not playing when required · 2 the Editor could not be read.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time

EXPR = "return GameProbe.Json();"
MISSING = object()


def run_eval(unity, project_path, expression, timeout):
    cmd = [unity, "command", "eval", expression, "--format", "json"]
    if project_path:
        cmd += ["--project-path", project_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "the eval did not return within %ss" % timeout
    except OSError as e:
        return None, "could not run %s: %s" % (unity, e)

    raw = proc.stdout.strip()
    if not raw:
        return None, "no output from `unity command eval` (stderr: %s)" % proc.stderr.strip()[:200]
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return None, "output is not JSON: %s" % raw[:200]

    # Level 1: did the command reach the Editor at all.
    if not envelope.get("success"):
        errors = envelope.get("errors") or []
        code = errors[0].get("code") if errors and isinstance(errors[0], dict) else "?"
        message = errors[0].get("message") if errors and isinstance(errors[0], dict) else raw[:200]
        return None, "the Editor rejected the command [%s]: %s" % (code, message)

    # Level 2: the eval's own return value.
    result = (envelope.get("data") or {}).get("result") or {}
    payload = result.get("result")
    if payload is None:
        return None, "the eval returned nothing — is GameProbe.cs in a Runtime assembly? (%s)" % raw[:200]
    if isinstance(payload, dict):
        return payload, None
    try:
        return json.loads(payload), None
    except (json.JSONDecodeError, TypeError):
        return None, "the eval returned a value that is not a probe snapshot: %r" % payload


def resolve(snapshot, key):
    """Value of a dotted or bare key, or MISSING when the key is absent.

    A key that is present and null is NOT missing: `cam` goes null on the frame the camera
    disappears, and that is the answer, not a failure to read it.
    """
    if "." in key:
        head, rest = key.split(".", 1)
        if head in ("pos", "vel"):
            vec = snapshot.get(head)
            index = {"x": 0, "y": 1, "z": 2}.get(rest)
            if isinstance(vec, list) and index is not None and index < len(vec):
                return vec[index]
            return MISSING
        container = snapshot.get(head)
        if isinstance(container, dict) and rest in container:
            return container[rest]
        return MISSING
    for bucket in ("custom", "counts", "ready"):
        container = snapshot.get(bucket)
        if isinstance(container, dict) and key in container:
            return container[key]
    return snapshot[key] if key in snapshot else MISSING


def missing_members(snapshot):
    ready = snapshot.get("ready")
    if not isinstance(ready, dict) or not ready:
        return ["(no readiness members registered)"]
    return sorted(name for name, ok in ready.items() if not ok)


def one_line(snapshot):
    if not snapshot.get("playing"):
        return "playing=false"
    ready = snapshot.get("ready") or {}
    ok = sum(1 for v in ready.values() if v)
    parts = [
        "frame=%s" % snapshot.get("frame"),
        "t=%s" % snapshot.get("t"),
        "state=%s" % snapshot.get("state"),
        "situation=%s" % snapshot.get("situation"),
        "speed=%s" % snapshot.get("speed"),
        "ready=%d/%d" % (ok, len(ready)),
    ]
    if ok != len(ready):
        parts.append("missing=" + ",".join(missing_members(snapshot)))
    return " ".join(parts)


def build_parser():
    p = argparse.ArgumentParser(
        prog="probe.py",
        description="Read GameProbe from a live Editor; wait on readiness rather than on a clock.",
        epilog="Exit 0 fine, 1 not ready, 2 the Editor could not be read.",
    )
    p.add_argument("--project-path", metavar="PATH", help="passed through to `unity command`")
    p.add_argument("--unity", default="unity", metavar="BIN", help="the CLI to call (default: unity)")
    p.add_argument("--key", metavar="KEY",
                   help="print one value instead of the snapshot: state, speed, custom.gateDist")
    p.add_argument("--watch", type=float, metavar="SECONDS",
                   help="poll forever at this interval, one line per poll")
    p.add_argument("--wait-ready", action="store_true",
                   help="poll until allReady; exit 1 naming the members that never arrived")
    p.add_argument("--timeout", type=float, default=20.0, metavar="SECONDS",
                   help="budget for --wait-ready (default 20)")
    p.add_argument("--interval", type=float, default=0.5, metavar="SECONDS",
                   help="poll interval for --wait-ready (default 0.5)")
    p.add_argument("--eval-timeout", type=float, default=30.0, metavar="SECONDS",
                   help="give up on one eval after this long (default 30)")
    p.add_argument("--raw", action="store_true", help="print the snapshot as one JSON line")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if not shutil.which(args.unity):
        print("ERROR %r is not on PATH" % args.unity, file=sys.stderr)
        return 2

    def read():
        return run_eval(args.unity, args.project_path, EXPR, args.eval_timeout)

    if args.wait_ready:
        deadline = time.time() + args.timeout
        missing, snapshot = ["(never read the probe)"], None
        while time.time() < deadline:
            snapshot, error = read()
            if error:
                missing = ["(%s)" % error]
            elif not snapshot.get("playing"):
                missing = ["(not in play mode)"]
            elif snapshot.get("allReady"):
                print("[PROBE] ready " + one_line(snapshot))
                return 0
            else:
                missing = missing_members(snapshot)
            time.sleep(args.interval)
        print("[PROBE] NOT READY after %.1fs: %s" % (args.timeout, ", ".join(missing)),
              file=sys.stderr)
        return 1

    if args.watch:
        while True:
            snapshot, error = read()
            print(("ERROR " + error) if error else one_line(snapshot), flush=True)
            time.sleep(args.watch)

    snapshot, error = read()
    if error:
        print("ERROR " + error, file=sys.stderr)
        return 2

    if args.key:
        value = resolve(snapshot, args.key)
        if value is MISSING:
            print("ERROR key %r is not in the snapshot; keys: %s"
                  % (args.key, ",".join(sorted(snapshot))), file=sys.stderr)
            return 1
        print("null" if value is None else value)
        return 0

    if args.raw:
        print(json.dumps(snapshot, separators=(",", ":")))
    else:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0 if snapshot.get("playing") else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
