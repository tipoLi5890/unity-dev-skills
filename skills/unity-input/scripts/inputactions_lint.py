#!/usr/bin/env python3
"""inputactions_lint.py — read a .inputactions file and name every hole a device would fall through.

The asset importer accepts an action nobody on a gamepad can trigger, a WASD composite with three
keys and a binding whose action was renamed away. None of them is an error in the Editor; each is
a button that does nothing on one device. This reads the JSON and reports them.

What counts as "in a control scheme": a binding whose `groups` (split on ';', empties dropped)
contains the scheme's `bindingGroup`. A composite is credited to a scheme only when every part it
requires has a part row in that scheme — the composite row itself carries no groups.

Findings (exit 1):
  action-unbound-in-scheme   an action with no binding in one control scheme
  action-unbound             an action with no binding at all
  composite-incomplete       a known composite missing a required part
  composite-part-orphan      a part row with no composite row before it
  binding-missing-action     a binding pointing at an action the map does not have
  binding-unknown-group      a group that is no scheme's bindingGroup
  binding-empty-path         a plain binding with no path
  duplicate-action           two actions with one name in one map
  duplicate-id               one id used twice in the file

Warnings (never change the exit code):
  ungrouped-binding          no groups in an asset that has schemes — dropped under a scheme mask
  device-not-in-scheme       the path's device layout is not one of the scheme's devices
  unknown-composite          a composite this script has no part list for

Examples:
  inputactions_lint.py Assets/Input/RunActions.inputactions
  inputactions_lint.py RunActions.inputactions --allow Pause:Touch     # a deliberate gap
  inputactions_lint.py RunActions.inputactions --scheme Gamepad        # check one scheme only
  inputactions_lint.py RunActions.inputactions --pretty

Prints one JSON object on stdout.
Exit codes: 0 fine · 1 at least one finding · 2 usage error, or the file is unreadable or not an
actions asset.
"""
import argparse
import json
import re
import sys

# Required parts of the composites that ship with the Input System. Names are case-insensitive
# in the package, so everything is compared lower-cased.
COMPOSITE_PARTS = {
    "2dvector": ("up", "down", "left", "right"),
    "dpad": ("up", "down", "left", "right"),
    "1daxis": ("negative", "positive"),
    "axis": ("negative", "positive"),
    "3dvector": ("up", "down", "left", "right", "forward", "backward"),
    "onemodifier": ("modifier", "binding"),
    "twomodifiers": ("modifier1", "modifier2", "binding"),
    "buttonwithonemodifier": ("modifier", "button"),
    "buttonwithtwomodifiers": ("modifier1", "modifier2", "button"),
}

DEVICE_IN_PATH = re.compile(r"^<([A-Za-z0-9_]+)>")

# A path naming the left layout is satisfied by a scheme device naming the right one.
DEVICE_BASES = {
    "Mouse": ("Pointer",),
    "Pen": ("Pointer",),
    "Touchscreen": ("Pointer",),
}


def split_groups(raw):
    return [g for g in (raw or "").split(";") if g]


def composite_name(path):
    """'2DVector(mode=2)' -> '2dvector'."""
    return (path or "").split("(", 1)[0].strip().lower()


def device_matches(layout, scheme_devices):
    if not scheme_devices:
        return True
    names = {layout} | set(DEVICE_BASES.get(layout, ()))
    for wanted in scheme_devices:
        if wanted in names or layout in DEVICE_BASES.get(wanted, ()):
            return True
    return False


def lint(doc, only_schemes=None, allow=()):
    findings, warnings = [], []
    schemes = doc.get("controlSchemes") or []
    scheme_group = {}      # bindingGroup -> scheme name
    scheme_devices = {}    # bindingGroup -> [layout, ...]
    for s in schemes:
        group = s.get("bindingGroup") or s.get("name") or ""
        scheme_group[group] = s.get("name") or group
        layouts = []
        for d in s.get("devices") or []:
            m = DEVICE_IN_PATH.match(d.get("devicePath") or "")
            if m:
                layouts.append(m.group(1))
        scheme_devices[group] = layouts

    checked = [g for g in scheme_group if not only_schemes or scheme_group[g] in only_schemes]
    allowed = set(allow)
    seen_ids = {}
    summary = {"maps": 0, "actions": 0, "bindings": 0, "schemes": [scheme_group[g] for g in checked]}

    def note_id(value, where):
        if not value:
            return
        if value in seen_ids:
            findings.append({"code": "duplicate-id", "id": value, "first": seen_ids[value], "second": where})
        else:
            seen_ids[value] = where

    for m in doc.get("maps") or []:
        map_name = m.get("name") or "?"
        summary["maps"] += 1
        note_id(m.get("id"), "map %s" % map_name)

        by_key = {}         # action name (lower) or id -> canonical action name
        covered = {}        # canonical action name -> set of groups it is bound in
        bound_at_all = set()
        for a in m.get("actions") or []:
            name = a.get("name") or "?"
            summary["actions"] += 1
            note_id(a.get("id"), "action %s/%s" % (map_name, name))
            if name.lower() in by_key:
                findings.append({"code": "duplicate-action", "map": map_name, "action": name})
            by_key[name.lower()] = name
            if a.get("id"):
                by_key[a["id"]] = name
            covered[name] = set()

        def resolve(binding):
            ref = binding.get("action") or ""
            return by_key.get(ref) or by_key.get(ref.lower())

        def check_groups(binding, where):
            groups = split_groups(binding.get("groups"))
            for g in groups:
                if scheme_group and g not in scheme_group:
                    findings.append({"code": "binding-unknown-group", "map": map_name, "binding": where,
                                     "group": g})
            if scheme_group and not groups:
                warnings.append({"code": "ungrouped-binding", "map": map_name, "binding": where})
            layout = DEVICE_IN_PATH.match(binding.get("path") or "")
            if layout:
                for g in groups:
                    if g in scheme_devices and not device_matches(layout.group(1), scheme_devices[g]):
                        warnings.append({"code": "device-not-in-scheme", "map": map_name, "binding": where,
                                         "scheme": scheme_group[g], "device": layout.group(1)})
            return groups

        def close_composite(c):
            if c is None:
                return
            kind = composite_name(c["path"])
            required = COMPOSITE_PARTS.get(kind)
            where = "%s/%s" % (c["action"] or "?", c["label"] or c["path"])
            if required is None:
                warnings.append({"code": "unknown-composite", "map": map_name, "binding": where,
                                 "composite": c["path"]})
                required = tuple(sorted(c["parts"]))
            missing = [p for p in required if p not in c["parts"]]
            if missing:
                findings.append({"code": "composite-incomplete", "map": map_name, "binding": where,
                                 "missing": missing})
            if c["action"] is None:
                return
            bound_at_all.add(c["action"])
            if not required:
                return
            # In a scheme only when every required part has a row in it.
            for g in scheme_group:
                if all(g in c["parts"].get(p, set()) for p in required):
                    covered[c["action"]].add(g)

        current = None
        for index, b in enumerate(m.get("bindings") or []):
            summary["bindings"] += 1
            where = "%s[%d] %s" % (map_name, index, b.get("path") or b.get("name") or "")
            note_id(b.get("id"), "binding %s" % where)
            action = resolve(b)

            if b.get("isPartOfComposite"):
                if current is None:
                    findings.append({"code": "composite-part-orphan", "map": map_name, "binding": where})
                    continue
                if not b.get("path"):
                    findings.append({"code": "binding-empty-path", "map": map_name, "binding": where})
                    continue
                groups = check_groups(b, where)
                current["parts"].setdefault((b.get("name") or "").lower(), set()).update(groups)
                continue

            close_composite(current)
            current = None
            if b.get("action") and action is None:
                findings.append({"code": "binding-missing-action", "map": map_name, "binding": where,
                                 "action": b.get("action")})
            if b.get("isComposite"):
                current = {"path": b.get("path") or "", "label": b.get("name") or "", "action": action,
                           "parts": {}}
                continue
            if not b.get("path"):
                findings.append({"code": "binding-empty-path", "map": map_name, "binding": where})
                continue
            groups = check_groups(b, where)
            if action is not None:
                bound_at_all.add(action)
                covered[action].update(groups)
        close_composite(current)

        for name, groups in covered.items():
            if name not in bound_at_all:
                findings.append({"code": "action-unbound", "map": map_name, "action": name})
                continue
            for g in checked:
                key = "%s:%s" % (name, scheme_group[g])
                if g not in groups and key not in allowed:
                    findings.append({"code": "action-unbound-in-scheme", "map": map_name, "action": name,
                                     "scheme": scheme_group[g]})

    return findings, warnings, summary


def build_parser():
    p = argparse.ArgumentParser(
        description="Lint an Input System .inputactions file: scheme coverage, composites, dangling bindings.")
    p.add_argument("path", help="the .inputactions file")
    p.add_argument("--scheme", action="append", default=[], metavar="NAME",
                   help="check coverage for this control scheme only (repeatable)")
    p.add_argument("--allow", action="append", default=[], metavar="ACTION:SCHEME",
                   help="accept that ACTION has no binding in SCHEME (repeatable)")
    p.add_argument("--pretty", action="store_true", help="indent the JSON")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        with open(args.path, "r", encoding="utf-8-sig") as f:
            doc = json.load(f)
    except OSError as e:
        print("ERROR cannot read %s: %s" % (args.path, e), file=sys.stderr)
        return 2
    except ValueError as e:
        print("ERROR %s is not JSON: %s" % (args.path, e), file=sys.stderr)
        return 2
    if not isinstance(doc, dict) or not isinstance(doc.get("maps"), list) or not doc["maps"]:
        print("ERROR %s has no maps[] — not an actions asset" % args.path, file=sys.stderr)
        return 2

    known = {s.get("name") for s in doc.get("controlSchemes") or []}
    for name in args.scheme:
        if name not in known:
            print("ERROR --scheme %s is not a control scheme in this file (has: %s)"
                  % (name, ", ".join(sorted(n for n in known if n)) or "none"), file=sys.stderr)
            return 2
    for pair in args.allow:
        if ":" not in pair:
            print("ERROR --allow takes ACTION:SCHEME, got %r" % pair, file=sys.stderr)
            return 2

    findings, warnings, summary = lint(doc, set(args.scheme), args.allow)
    out = {
        "file": args.path,
        "ok": not findings,
        "summary": summary,
        "findings": findings,
        "warnings": warnings,
    }
    print(json.dumps(out, indent=2 if args.pretty else None, sort_keys=False))
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
