# targets: skills/blender-character-rig/scripts/bcr_common.py, skills/blender-retarget/scripts/brt_common.py
import functools
import json
import os
import sys

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


def file_state() -> dict:
    """The loaded .blend: its path ('' before the first save) and whether it has unsaved edits."""
    dirty = bool(bpy.data.is_dirty)
    return {"path": bpy.data.filepath, "saved": bool(bpy.data.filepath) and not dirty, "dirty": dirty}


def destructive_guard(params: dict, label: str):
    """Call before an op overwrites existing data. Returns a warning string, or None.

    Edits that were never saved cannot be got back by reopening the file, so an
    overwrite on top of them is reported: the op puts the string in its result's
    `warnings`. `acknowledge_destructive: True` means the caller knows (None);
    `strict: True` raises instead of warning, before anything is written.
    """
    if params.get("acknowledge_destructive") is True:
        return None
    if not bpy.data.is_dirty:
        return None
    if params.get("strict"):
        raise RuntimeError(f"{label} refused: the file has unsaved edits and strict is set; "
                           "save first or pass acknowledge_destructive")
    return f"{label} on a dirty file: pass acknowledge_destructive or strict"


def _script_name(module_globals: dict) -> str:
    name = module_globals.get("__name__", "")
    if name == "__main__" and module_globals.get("__file__"):
        return os.path.splitext(os.path.basename(module_globals["__file__"]))[0]
    return name


def report(params: dict, gates: list[dict], **extra) -> dict:
    """The dict every op returns. A `warnings` list in `extra` becomes the result's warnings.

    schema, file and record are set after the extras, so an extra with one of
    those names cannot replace them. `record` is this call's partial ledger row:
    the tool, the params without any key naming a path (`backup_path` is kept),
    the gates and the verdict.
    """
    ok = all(g["pass"] for g in gates)
    warnings = [str(w) for w in extra.pop("warnings", None) or []]
    out = {"ok": ok, "gates": gates, "blender": list(bpy.app.version)}
    out.update(safe(extra))
    kept = {k: v for k, v in safe(params).items() if "path" not in k or k == "backup_path"}
    out.update({
        "schema": 1,
        "file": file_state(),
        "warnings": warnings,
        "record": {"tool": {"skill": SKILL, "script": _script_name(sys._getframe(1).f_globals)},
                   "params": kept, "gates": gates, "verdict": "green" if ok else "failed"},
    })
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
        if isinstance(out.get("record"), dict):
            # the entry point, also when report() was called from a helper module
            out["record"]["tool"]["script"] = _script_name(fn.__globals__)
        if params.get("report_path"):
            with open(params["report_path"], "w", encoding="utf-8") as handle:
                json.dump(out, handle, indent=2)
        return out

    return run
