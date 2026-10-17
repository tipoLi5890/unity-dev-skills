#!/usr/bin/env python3
"""graph_diff.py — compare two ComfyUI API graphs node by node and input by input.

Diff the project's graph against the official template BEFORE tuning a knob:
a setting the template carries and the project dropped (a padding, a bias, a
resolution tied to another node) looks like a model fault from the output.

usage:
    graph_diff.py OFFICIAL_api.json PROJECT_api.json            # text, one line per difference
    graph_diff.py A.json B.json --json                           # one JSON object
    graph_diff.py A.json B.json --common-only                    # only nodes both graphs hold
    graph_diff.py A.json B.json --ignore filename_prefix --ignore image   # leave out run-specific inputs
    graph_diff.py --selftest

Each file is an API-format graph: `{"prompt": {id: node}}` as this skill's
templates and `/prompt` take it, or the bare `{id: node}` that "Export (API)"
writes. A UI workflow (`nodes` and `links` arrays) is not one: export it in API
format first. Nodes are matched by id; `_meta` (titles) is ignored.

Reported: nodes added (only in B) and removed (only in A), a changed
`class_type`, and per input: added, removed, a changed literal, a link that
points elsewhere, and a link replaced by a literal or the reverse (`kind`) —
the template feeds `224.resolution` from node 288 where a copy may hold 2048.

Exit codes: 0 the graphs are the same; 1 they differ; 3 a file cannot be read
or is not an API graph; 2 a usage error. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


class Unreadable(Exception):
    pass


def load_graph(path: Path) -> dict[str, dict[str, Any]]:
    """The {id: node} graph in `path`, or Unreadable with the reason."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Unreadable(f"{path}: {exc.strerror or exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Unreadable(f"{path}: not JSON ({exc})") from exc
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        raise Unreadable(f"{path}: a UI workflow, not an API graph; export it in API format")
    if isinstance(data, dict) and isinstance(data.get("prompt"), dict):
        data = data["prompt"]
    if not isinstance(data, dict) or not data:
        raise Unreadable(f"{path}: no graph (expected {{id: node}} or {{\"prompt\": {{id: node}}}})")
    for node_id, node in data.items():
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
            raise Unreadable(f"{path}: node {node_id} has no class_type")
        if not isinstance(node.get("inputs", {}), dict):
            raise Unreadable(f"{path}: node {node_id} inputs is not an object")
    return data


def is_link(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int))
            and isinstance(value[1], int) and not isinstance(value[1], bool))


def show(value: Any) -> str:
    if is_link(value):
        return f"link {value[0]}:{value[1]}"
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "..."


def id_order(node_id: str) -> tuple[int, Any]:
    return (0, int(node_id)) if node_id.isdigit() else (1, node_id)


def diff(a: dict[str, dict], b: dict[str, dict], common_only: bool = False,
         ignore: frozenset[str] = frozenset()) -> dict[str, Any]:
    ids_a, ids_b = set(a), set(b)
    added = [] if common_only else [{"id": i, "class_type": b[i]["class_type"]}
                                    for i in sorted(ids_b - ids_a, key=id_order)]
    removed = [] if common_only else [{"id": i, "class_type": a[i]["class_type"]}
                                      for i in sorted(ids_a - ids_b, key=id_order)]
    class_changed: list[dict] = []
    inputs: list[dict] = []
    for node_id in sorted(ids_a & ids_b, key=id_order):
        na, nb = a[node_id], b[node_id]
        if na["class_type"] != nb["class_type"]:
            class_changed.append({"id": node_id, "a": na["class_type"], "b": nb["class_type"]})
        ia, ib = na.get("inputs", {}), nb.get("inputs", {})
        for name in sorted((set(ia) | set(ib)) - ignore):
            row = {"id": node_id, "class_type": nb["class_type"], "input": name}
            if name not in ib:
                inputs.append({**row, "change": "removed", "a": ia[name]})
            elif name not in ia:
                inputs.append({**row, "change": "added", "b": ib[name]})
            else:
                va, vb = ia[name], ib[name]
                if is_link(va) != is_link(vb):
                    inputs.append({**row, "change": "kind", "a": va, "b": vb,
                                   "a_kind": "link" if is_link(va) else "literal",
                                   "b_kind": "link" if is_link(vb) else "literal"})
                elif is_link(va):
                    if [str(va[0]), va[1]] != [str(vb[0]), vb[1]]:
                        inputs.append({**row, "change": "relinked", "a": va, "b": vb})
                elif va != vb or type(va) is bool and type(vb) is not bool or \
                        type(vb) is bool and type(va) is not bool:
                    inputs.append({**row, "change": "changed", "a": va, "b": vb})
    counts = {"added": len(added), "removed": len(removed), "class_changed": len(class_changed),
              "inputs": len(inputs), "common_nodes": len(ids_a & ids_b)}
    same = not (added or removed or class_changed or inputs)
    return {"same": same, "counts": counts, "added": added, "removed": removed,
            "class_changed": class_changed, "inputs": inputs}


def as_text(result: dict[str, Any], name_a: str, name_b: str) -> str:
    lines = [f"A = {name_a}", f"B = {name_b}"]
    for n in result["removed"]:
        lines.append(f"node {n['id']} removed ({n['class_type']}): only in A")
    for n in result["added"]:
        lines.append(f"node {n['id']} added ({n['class_type']}): only in B")
    for n in result["class_changed"]:
        lines.append(f"node {n['id']} class_type {n['a']} -> {n['b']}")
    for r in result["inputs"]:
        head = f"node {r['id']} {r['class_type']}.{r['input']}"
        if r["change"] == "removed":
            lines.append(f"{head}: removed (A {show(r['a'])})")
        elif r["change"] == "added":
            lines.append(f"{head}: added (B {show(r['b'])})")
        else:
            lines.append(f"{head}: {show(r['a'])} -> {show(r['b'])}"
                         + (f"  [{r['a_kind']} -> {r['b_kind']}]" if r["change"] == "kind" else ""))
    c = result["counts"]
    lines.append("same" if result["same"] else
                 f"differ: {c['removed']} removed, {c['added']} added, {c['class_changed']} class changes, "
                 f"{c['inputs']} input changes over {c['common_nodes']} common nodes")
    return "\n".join(lines)


def selftest() -> int:
    official = {"client_id": "x", "prompt": {
        "186": {"class_type": "DecimateMesh", "inputs": {"mesh": ["241", 0], "target_face_count": 700000}},
        "196": {"class_type": "UnwrapMesh", "inputs": {"mesh": ["238", 0], "padding": 1}},
        "224": {"class_type": "BakeNormalMapFromMesh", "inputs": {"resolution": ["288", 0]}},
        "233": {"class_type": "BakeAmbientOcclusion", "inputs": {"bias": 0.01, "samples": 64}},
        "500": {"class_type": "Switch", "inputs": {"on": True}},
        "_x": {"class_type": "Note", "inputs": {}, "_meta": {"title": "a"}}}}
    project = {
        "186": {"class_type": "DecimateMesh", "inputs": {"mesh": ["241", 0], "target_face_count": 20000}},
        "196": {"class_type": "UnwrapMesh", "inputs": {"mesh": ["238", 0], "padding": 4}},
        "224": {"class_type": "BakeNormalMapFromMesh", "inputs": {"resolution": 2048}},
        "233": {"class_type": "BakeAmbientOcclusion", "inputs": {"bias": 0.01, "samples": 64, "strength": 1}},
        "900": {"class_type": "RenderMesh", "inputs": {"mesh": ["186", 1]}},
        "_x": {"class_type": "Note", "inputs": {}, "_meta": {"title": "b"}}}
    checks: list[tuple[str, bool]] = []
    r = diff(official["prompt"], project)
    by = {(x["id"], x["input"]): x for x in r["inputs"]}
    checks.append(("differ", r["same"] is False))
    checks.append(("literal changed", by[("186", "target_face_count")]["change"] == "changed"))
    checks.append(("padding changed", by[("196", "padding")]["b"] == 4))
    checks.append(("link -> literal", by[("224", "resolution")]["change"] == "kind"
                   and by[("224", "resolution")]["b_kind"] == "literal"))
    checks.append(("input added", by[("233", "strength")]["change"] == "added"))
    checks.append(("unchanged input absent", ("233", "bias") not in by and ("186", "mesh") not in by))
    checks.append(("node added", [n["id"] for n in r["added"]] == ["900"]))
    checks.append(("node removed", [n["id"] for n in r["removed"]] == ["500"]))
    checks.append(("_meta ignored", ("_x", "_meta") not in by))
    checks.append(("common-only", diff(official["prompt"], project, True)["counts"]["added"] == 0))
    checks.append(("ignore", ("196", "padding") not in
                   {(x["id"], x["input"]) for x in diff(official["prompt"], project, ignore=frozenset({"padding"}))["inputs"]}))
    checks.append(("same graph", diff(project, json.loads(json.dumps(project)))["same"]))
    swapped = json.loads(json.dumps(project))
    swapped["900"]["inputs"]["mesh"] = ["224", 1]
    checks.append(("relinked", diff(project, swapped)["inputs"][0]["change"] == "relinked"))
    retyped = json.loads(json.dumps(project))
    retyped["196"]["class_type"] = "UnwrapMeshAdvanced"
    checks.append(("class changed", diff(project, retyped)["class_changed"][0]["b"] == "UnwrapMeshAdvanced"))
    checks.append(("bool vs int", diff({"1": {"class_type": "N", "inputs": {"v": 1}}},
                                       {"1": {"class_type": "N", "inputs": {"v": True}}})["counts"]["inputs"] == 1))
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "ui.json").write_text(json.dumps({"nodes": [], "links": []}))
        (t / "bad.json").write_text("{not json")
        (t / "wrapped.json").write_text(json.dumps(official))
        for name in ("ui.json", "bad.json", "missing.json"):
            try:
                load_graph(t / name)
                checks.append((f"unreadable {name}", False))
            except Unreadable:
                checks.append((f"unreadable {name}", True))
        checks.append(("wrapped graph loads", "186" in load_graph(t / "wrapped.json")))
    failed = [name for name, ok in checks if not ok]
    print(json.dumps({"selftest": "pass" if not failed else "fail", "checks": len(checks), "failed": failed}))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("a", nargs="?", type=Path, help="The reference graph (the official template)")
    parser.add_argument("b", nargs="?", type=Path, help="The graph compared with it (the project's)")
    parser.add_argument("--json", action="store_true", help="Print one JSON object instead of text")
    parser.add_argument("--common-only", action="store_true",
                        help="Leave out nodes only one graph holds (QA renders, UI switch nodes)")
    parser.add_argument("--ignore", action="append", default=[], metavar="INPUT",
                        help="An input name to leave out on every node (filename_prefix, image); repeatable")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.a is None or args.b is None:
        parser.error("two graphs are required (or --selftest)")
    try:
        a, b = load_graph(args.a), load_graph(args.b)
    except Unreadable as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"graph_diff: {exc}", file=sys.stderr)
        return 3
    result = diff(a, b, args.common_only, frozenset(args.ignore))
    if args.json:
        print(json.dumps({"a": str(args.a), "b": str(args.b), **result}, ensure_ascii=False, indent=2))
    else:
        print(as_text(result, str(args.a), str(args.b)))
    return 0 if result["same"] else 1


if __name__ == "__main__":
    sys.exit(main())
