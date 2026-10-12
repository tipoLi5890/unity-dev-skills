"""bcr_common.py — helpers shared by the bcr_* modules.

Runs inside Blender; not a command-line script. Every bcr_* module exposes
`run(params: dict) -> dict` and is called from a short stub sent through the
MCP server's code tool:

    import sys, importlib
    p = "<skill>/scripts"
    if p not in sys.path: sys.path.insert(0, p)
    import bcr_common, bcr_skin
    importlib.reload(bcr_common); importlib.reload(bcr_skin)
    result = bcr_skin.run({"mesh": "Runner", "armature": "RunnerRig"})

What every `run` returns:

    {"ok": bool,                      # every gate passed
     "gates": [{"name", "value", "limit", "pass"}, ...],
     "created": {"objects": [...], ...},   # datablocks this call added
     "blender": [major, minor, patch], ...}

`report_path` in params also writes that dict as JSON.

A call that raises removes the datablocks it had created before re-raising, so
a failed step leaves no orphan collection or material behind. Edits to
datablocks that already existed are not undone: each module says which it makes.
"""
from __future__ import annotations

import functools
import json

import bpy
from mathutils import Matrix, Vector

# removal order matters: objects before the data they use
_KINDS = ("objects", "meshes", "armatures", "cameras", "lights", "materials", "images",
          "textures", "actions", "collections", "worlds", "scenes")


def scene_of(params: dict):
    name = params.get("scene")
    return bpy.data.scenes[name] if name else bpy.context.scene


def collection(name: str, scene):
    """Get or create a collection and make sure it is linked into the scene."""
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if col not in scene.collection.children_recursive:
        scene.collection.children.link(col)
    return col


def move_to_collection(obj, col) -> None:
    for other in list(obj.users_collection):
        other.objects.unlink(obj)
    col.objects.link(obj)


def node_of(tree, idname: str):
    """Find a node by type. Display names are translated with the UI language."""
    return next((n for n in tree.nodes if n.bl_idname == idname), None)


def rotation(steps) -> Matrix:
    """[["Y", 40], ["X", -85]] -> 3x3 matrix; the first step is applied first."""
    from math import radians
    out = Matrix.Identity(3)
    for axis, degrees in steps or []:
        out = Matrix.Rotation(radians(degrees), 3, axis) @ out
    return out


def world_coords(obj) -> list[Vector]:
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def islands(mesh) -> list[int]:
    """Sizes of the connected components, largest first."""
    parent = list(range(len(mesh.vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for edge in mesh.edges:
        a, b = find(edge.vertices[0]), find(edge.vertices[1])
        if a != b:
            parent[a] = b
    sizes: dict[int, int] = {}
    for i in range(len(parent)):
        root = find(i)
        sizes[root] = sizes.get(root, 0) + 1
    return sorted(sizes.values(), reverse=True)


def safe(value, digits: int = 5):
    """Make a value JSON-serialisable."""
    if isinstance(value, dict):
        return {str(k): safe(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, Vector)):
        return [safe(v, digits) for v in value]
    if isinstance(value, Matrix):
        return [safe(row, digits) for row in value]
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    return str(value)


def gate(name: str, value, limit, passed) -> dict:
    return {"name": name, "value": safe(value), "limit": safe(limit), "pass": bool(passed)}


def report(params: dict, gates: list[dict], **extra) -> dict:
    out = {"ok": all(g["pass"] for g in gates), "gates": gates, "blender": list(bpy.app.version)}
    out.update(safe(extra))
    return out


class Tracker:
    """Which datablocks appeared during one call, and how to take them back."""

    def __init__(self):
        self.before = {kind: set(getattr(bpy.data, kind)) for kind in _KINDS}

    def new(self, kind: str) -> list:
        return [d for d in getattr(bpy.data, kind) if d not in self.before[kind]]

    def created(self) -> dict:
        out = {kind: sorted(d.name for d in self.new(kind)) for kind in _KINDS}
        return {kind: names for kind, names in out.items() if names}

    def rollback(self) -> dict:
        removed = self.created()
        for kind in _KINDS:
            for block in self.new(kind):
                getattr(bpy.data, kind).remove(block)
        return removed


def step(fn):
    """Wrap `fn(params, tracker)` as `run(params)`: track, roll back on failure, report."""

    @functools.wraps(fn)
    def run(params: dict) -> dict:
        tracker = Tracker()
        try:
            out = fn(params, tracker)
        except Exception as exc:
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            removed = tracker.rollback()
            raise RuntimeError(f"{fn.__module__}: {exc} (rolled back: {removed or 'nothing created'})") from exc
        out["created"] = tracker.created()
        if params.get("report_path"):
            with open(params["report_path"], "w", encoding="utf-8") as handle:
                json.dump(out, handle, indent=2)
        return out

    return run
