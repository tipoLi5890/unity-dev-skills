#!/usr/bin/env python3
"""save_check.py — read a save file and say whether it is a save: versioned, complete, and free of
anything that only meant something in the session that wrote it.

A save is plain data that outlives the process. This script checks the five ways one stops being
that: no version, a version the checker does not know, a key the version requires that is missing
or of the wrong type, an object reference serialised by accident (JsonUtility writes one as
{"instanceID": 12345}), and world flags that are not addressable — an empty id, or one id twice.

Examples:
  python3 save_check.py ~/Library/Application\\ Support/Studio/CourierRun/save.json
  python3 save_check.py save.json --indent 2
  python3 save_check.py save.json --max-version 3      # accept a version this script has no schema for
  python3 save_check.py save.json --forbid entityId    # one more session-only key to refuse

Exit codes: 0 fine · 1 a verdict about the subject (at least one finding) · 2 usage or harness/IO error
"""
import argparse
import json
import sys

# Required keys per version, as "dotted.path": type. A list path ends in [] and describes each
# element. Keep in step with SaveData / SaveDataV1 in resources/SaveStore.cs: a new version adds
# an entry here on the day it adds a migration step there.
NUMBER = (int, float)
SCHEMAS = {
    1: {
        "version": int,
        "savedAtUnix": int,
        "scene": str,
        "lane": int,
        "distance": NUMBER,
        "collected": list,
        "collected[]": str,
    },
    2: {
        "version": int,
        "savedAtUnix": int,
        "scene": str,
        "player": dict,
        "player.lane": int,
        "player.position": dict,
        "player.position.x": NUMBER,
        "player.position.y": NUMBER,
        "player.position.z": NUMBER,
        "player.checkpoint": str,
        "flags": list,
        "flags[]": dict,
        "flags[].id": str,
        "flags[].value": int,
    },
}

# Keys that only exist when a UnityEngine.Object, or a number naming one, was serialised.
# Compared case-insensitively, anywhere in the document.
SESSION_ONLY_KEYS = ("instanceID", "m_InstanceID", "m_FileID", "m_PathID", "fileID", "guid")


def build_parser():
    p = argparse.ArgumentParser(
        prog="save_check.py",
        description="Check that a save file is versioned, complete for its version and free of "
                    "session-only values.",
        epilog="Exit codes: 0 fine, 1 at least one finding, 2 usage or IO error.",
    )
    p.add_argument("save", help="path to the save JSON")
    p.add_argument("--max-version", type=int, default=max(SCHEMAS),
                   help="highest version accepted (default: the highest this script has a schema "
                        "for, %(default)s). A higher known-good version is checked for the version "
                        "field and session-only keys only.")
    p.add_argument("--forbid", action="append", default=[], metavar="KEY",
                   help="an additional key that must not appear anywhere; repeatable")
    p.add_argument("--indent", type=int, default=None, help="pretty-print the JSON result")
    return p


def type_name(expected):
    if expected is NUMBER:
        return "number"
    return {int: "integer", str: "string", dict: "object", list: "array"}[expected]


def matches(value, expected):
    # bool is an int in Python, and true is not a lane.
    if isinstance(value, bool):
        return False
    if expected is int:
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    return isinstance(value, expected)


def resolve(doc, path):
    """Yield (display path, value or MISSING) for every place a schema path points at."""
    nodes = [("", doc)]
    for part in path.replace("[]", ".[]").split("."):
        if not part:
            continue
        found = []
        for shown, node in nodes:
            if node is MISSING:
                continue
            if part == "[]":
                if isinstance(node, list):
                    found.extend(("%s[%d]" % (shown, i), item) for i, item in enumerate(node))
            elif isinstance(node, dict):
                key = (shown + "." + part).lstrip(".")
                found.append((key, node.get(part, MISSING)))
        nodes = found
    return nodes


class _Missing:
    def __repr__(self):
        return "MISSING"


MISSING = _Missing()


def session_only(node, forbidden, where=""):
    """Every forbidden key in the document, with the path it sits at."""
    hits = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = (where + "." + key).lstrip(".")
            if key.lower() in forbidden:
                hits.append(here)
            hits.extend(session_only(value, forbidden, here))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits.extend(session_only(item, forbidden, "%s[%d]" % (where, i)))
    return hits


def check(doc, max_version, extra_forbidden):
    findings = []

    def find(rule, path, detail):
        findings.append({"rule": rule, "path": path, "detail": detail})

    if not isinstance(doc, dict):
        find("not-an-object", "", "the top level is %s; a save is one JSON object" % type(doc).__name__)
        return None, findings

    version = doc.get("version", MISSING)
    if version is MISSING:
        find("no-version", "version", "no version field: nothing can migrate this file")
        version = None
    elif not matches(version, int) or version < 1:
        find("bad-version", "version", "version is %r; it is a whole number from 1" % (version,))
        version = None
    elif version > max_version:
        find("unknown-version", "version",
             "version %d is above %d, the highest accepted" % (version, max_version))

    schema = SCHEMAS.get(version) if version is not None else None
    if schema:
        for path, expected in schema.items():
            for shown, value in resolve(doc, path):
                if value is MISSING:
                    find("missing-key", shown, "version %d requires it" % version)
                elif not matches(value, expected):
                    find("wrong-type", shown,
                         "expected %s, found %s" % (type_name(expected), type(value).__name__))

    forbidden = {k.lower() for k in SESSION_ONLY_KEYS} | {k.lower() for k in extra_forbidden}
    for path in session_only(doc, forbidden):
        find("session-only-value", path,
             "this key holds a value from the session that wrote the file: store a persistent id")

    flags = doc.get("flags")
    if isinstance(flags, list):
        seen = {}
        for i, flag in enumerate(flags):
            if not isinstance(flag, dict) or not isinstance(flag.get("id"), str):
                continue
            ident = flag["id"]
            if not ident:
                find("empty-flag-id", "flags[%d].id" % i, "a flag with no id cannot be applied to anything")
            elif ident in seen:
                find("duplicate-flag-id", "flags[%d].id" % i,
                     "%r is also flags[%d]: which value wins depends on read order" % (ident, seen[ident]))
            else:
                seen[ident] = i

    return version, findings


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        with open(args.save, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as e:
        print("ERROR cannot read %s: %s" % (args.save, e), file=sys.stderr)
        return 2

    result = {"file": args.save, "bytes": len(text.encode("utf-8"))}
    try:
        doc = json.loads(text)
    except ValueError as e:
        # A file that is not JSON is a verdict about the save, not a failure of this script:
        # it is what a write cut short leaves behind.
        result.update({"ok": False, "version": None, "findings": [
            {"rule": "not-json", "path": "", "detail": "the file does not parse (%s): cut off or damaged" % e}]})
        print(json.dumps(result, indent=args.indent, ensure_ascii=False))
        return 1

    version, findings = check(doc, args.max_version, args.forbid)
    result.update({
        "ok": not findings,
        "version": version,
        "schema": "known" if version in SCHEMAS else "none",
        "findings": findings,
    })
    print(json.dumps(result, indent=args.indent, ensure_ascii=False))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
