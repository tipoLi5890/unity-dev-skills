#!/usr/bin/env python3
"""rig_gate.py — did the rig survive the FBX? Compare two snapshots.

`bcr_fbx` writes a snapshot of the rig before export and another of what an
import of the file produced. This compares them, so "the export finished" is
never the evidence that the skeleton, the weights and the action are in the
file.

    python3 scripts/rig_gate.py before.json after.json
    python3 scripts/rig_gate.py before.json after.json --allow-leaf-bones --position-tolerance 0.002

Gates:
  bones           the same bone names (extra `*_end` bones pass only with --allow-leaf-bones)
  parents         every bone has the parent it had
  bone_positions  every head within --position-tolerance metres of where it was
  groups          every skinned mesh uses the same vertex groups
  bone_parents    a prop parented to a bone is still on that bone
  influences      no vertex has more than --max-influences weights; none is unweighted
  scale           armature and meshes come back at scale 1 (within --scale-tolerance)
  action          one action, the same frame range, and it has f-curves

Meshes are matched by name, ignoring the `.001` a re-import beside the
originals gets; a vertex count that differs is reported, not failed, because
an exporter may split vertices at seams. A mesh parented to a bone carries no
vertex groups and is checked for presence and scale only.

Prints one JSON object. Exit codes: 0 every gate passed; 1 a gate failed;
2 a snapshot is missing or unreadable.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = data.get("snapshot", data)          # accept a whole bcr_fbx report
    if "bones" not in data or "meshes" not in data:
        raise ValueError(f"{path}: not a rig snapshot")
    # a re-import beside the originals is named Runner.001
    data["meshes"] = {re.sub(r"\.\d{3}$", "", name): mesh for name, mesh in data["meshes"].items()}
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                     epilog="Exit codes: 0 pass, 1 a gate failed, 2 unreadable input.")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--allow-leaf-bones", action="store_true", help="Accept extra *_end bones in the file")
    parser.add_argument("--position-tolerance", type=float, default=0.001, help="Metres (default 0.001)")
    parser.add_argument("--scale-tolerance", type=float, default=0.001)
    parser.add_argument("--max-influences", type=int, default=4)
    args = parser.parse_args()

    try:
        before, after = load(args.before), load(args.after)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    gates = []

    def gate(name, passed, **detail):
        gates.append({"name": name, "pass": bool(passed), **detail})

    want, got = set(before["bones"]), set(after["bones"])
    extra = sorted(got - want)
    leaf = [n for n in extra if n.endswith("_end")]
    unexpected = [n for n in extra if n not in leaf] + ([] if args.allow_leaf_bones else leaf)
    gate("bones", not (want - got) and not unexpected, missing=sorted(want - got), unexpected=unexpected,
         count=[len(want), len(got)])

    shared = sorted(want & got)
    wrong = {n: [before["bones"][n]["parent"], after["bones"][n]["parent"]] for n in shared
             if before["bones"][n]["parent"] != after["bones"][n]["parent"]}
    gate("parents", not wrong, wrong=wrong)

    moved = {}
    for n in shared:
        a, b = before["bones"][n]["head"], after["bones"][n]["head"]
        d = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        if d > args.position_tolerance:
            moved[n] = round(d, 5)
    gate("bone_positions", not moved, moved=moved, tolerance=args.position_tolerance)

    group_diff, influence, vertices = {}, {}, {}
    for name, mesh in before["meshes"].items():
        other = after["meshes"].get(name)
        if other is None:
            group_diff[name] = "mesh missing from the file"
            continue
        if mesh["groups"] and sorted(mesh["groups"]) != sorted(other["groups"]):
            group_diff[name] = {"lost": sorted(set(mesh["groups"]) - set(other["groups"])),
                                "gained": sorted(set(other["groups"]) - set(mesh["groups"]))}
        if mesh["groups"] and (other["max_influences"] > args.max_influences or other["unweighted"]):
            influence[name] = {"max_influences": other["max_influences"], "unweighted": other["unweighted"]}
        vertices[name] = [mesh["vertices"], other["vertices"]]
    gate("groups", not group_diff, different=group_diff)
    unhooked = {name: [mesh.get("parent_bone"), after["meshes"].get(name, {}).get("parent_bone")]
                for name, mesh in before["meshes"].items()
                if mesh.get("parent_bone") and after["meshes"].get(name, {}).get("parent_bone") != mesh["parent_bone"]}
    gate("bone_parents", not unhooked, different=unhooked)
    gate("influences", not influence, over=influence, limit=args.max_influences)

    scales = {"armature": after["armature_scale"]}
    scales.update({name: mesh["scale"] for name, mesh in after["meshes"].items()})
    off = {name: s for name, s in scales.items() if any(abs(x - 1.0) > args.scale_tolerance for x in s)}
    gate("scale", not off, not_one=off)

    a, b = before.get("action"), after.get("action")
    if a is None:
        gate("action", True, note="no action in the source rig")
    else:
        same = b is not None and a["frame_range"] == b["frame_range"] and b["fcurves"] > 0
        gate("action", same, before=a, after=b)

    ok = all(g["pass"] for g in gates)
    print(json.dumps({"ok": ok, "gates": gates, "vertices": vertices}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
