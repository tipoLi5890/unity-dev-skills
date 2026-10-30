"""brt_common.py — helpers shared by the brt_* modules.

Runs inside Blender; not a command-line script. Every brt_* module exposes
`run(params: dict) -> dict` and is called from a short stub sent through the
MCP server's code tool:

    import sys, importlib
    p = "<skill>/scripts"
    if p not in sys.path: sys.path.insert(0, p)
    import brt_common, brt_<tool>
    importlib.reload(brt_common); importlib.reload(brt_<tool>)
    result = brt_<tool>.run({"armature": "RunnerRig"})

What every `run` returns:

    {"schema": "gate/1",              # gate/1 (schemas/gate-1.json); absent with no gates
     "pass": bool,                    # every gate passed; absent with no gates
     "ok": bool,                      # pass's old name, equal to it, for one release
     "gates": [{"name", "value", "limit", "pass"}, ...],
     "created": {"objects": [...], ...},   # datablocks this call added
     "blender": [major, minor, patch], ...,
     "file": {"path", "saved", "dirty"},   # the loaded .blend; path "" before the first save
     "warnings": [...],               # notes that do not fail the call
     "record": {"tool": {"skill", "script"}, "params", "gates", "verdict"}}

`report_path` in params also writes that dict as JSON. `record` is a partial
ledger row: its params leave out every key naming a path except `backup_path`,
and verdict is "green" or "failed". The `file` key is always that dict, also
for brt_audit, whose audited path is `file.path`.

A call that raises removes the datablocks it had created before re-raising, so
a failed step leaves no orphan collection or action behind. Edits to
datablocks that already existed are not undone: each module says which it makes.
An op that overwrites existing data can call `destructive_guard` first (the
brt_weights ops transfer, normalize and restore do): on a file with unsaved
edits it adds a warning, `acknowledge_destructive: True` silences it, and
`strict: True` raises before anything is written.
`save_state` / `restore_state` put back the scene state a render or a batch
edit disturbs (frame, selection, mode, assigned actions, NLA mutes, visibility).

Actions are Blender 5.x layered actions: F-curves live in
action.layers[0].strips[0].channelbags, one channelbag per slot, and an object
plays the action only through `animation_data.action` plus `action_slot`.
"""
from __future__ import annotations

import math

# No function here needs Auto-Rig Pro: everything runs on stock Blender.
ARP_NOT_REQUIRED = True

# Named in the record of every result (report() reads it).
SKILL = "blender-retarget"

__all__ = [
    "ARP_NOT_REQUIRED", "SKILL", "scene_of", "collection", "move_to_collection", "node_of",
    "rotation", "world_coords", "islands", "safe", "gate", "file_state", "destructive_guard",
    "report", "Tracker", "step",
    "action_slot_fcurves", "ensure_fcurve", "assign_slot", "save_state", "restore_state",
    "sample_finite",
]

# Between the shared:blender_common markers: a copy of tools/shared-blocks/blender_common.py
# in the repository, which tools/check-consistency.py keeps equal to it. Edit that file,
# then copy it here and into the other skill's copy.
# >>> shared:blender_common
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

    With gates it is a gate/1 report: `schema` "gate/1" and `pass`, true only when
    every gate's `pass` is true (`ok`, its old name, equals it for one release).
    With no gates it is an op's result, not a verdict: no `schema` or `pass`, and
    `ok` is true. schema, pass, ok, file and record are set after the extras, so an
    extra with one of those names cannot replace them. `record` is this call's
    partial ledger row: the tool, the params without any key naming a path
    (`backup_path` is kept), the gates and the verdict.
    """
    ok = all(g.get("pass") is True for g in gates)
    warnings = [str(w) for w in extra.pop("warnings", None) or []]
    out = {"gates": gates, "blender": list(bpy.app.version)}
    out.update(safe(extra))
    for k in ("schema", "pass"):
        out.pop(k, None)
    kept = {k: v for k, v in safe(params).items() if "path" not in k or k == "backup_path"}
    if gates:
        out.update({"schema": "gate/1", "pass": ok})
    out.update({
        "ok": ok,
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
# <<< shared:blender_common


# --- layered actions -------------------------------------------------------

def _slot_of(action, slot):
    """An ActionSlot, its identifier ("OBRunner") or display name ("Runner"), or None."""
    if slot is None or not isinstance(slot, str):
        return slot
    for candidate in action.slots:
        if slot in (candidate.identifier, candidate.name_display):
            return candidate
    raise KeyError(f"action {action.name!r} has no slot {slot!r} "
                   f"(slots: {[s.identifier for s in action.slots]})")


def action_slot_fcurves(action, slot=None) -> list:
    """Every F-curve of the action, or only those of one slot.

    Walks layers -> strips -> channelbags. A pre-4.4 action without `layers`
    falls back to `action.fcurves`, and there `slot` is ignored.
    """
    if not hasattr(action, "layers"):
        return list(getattr(action, "fcurves", []))
    slot = _slot_of(action, slot)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                if slot is None or bag.slot_handle == slot.handle:
                    out.extend(bag.fcurves)
    return out


def ensure_fcurve(action, slot, data_path: str, index: int, group_name: str | None = None):
    """Get or create the F-curve `data_path[index]` on the slot's channelbag.

    `slot` None means the action's first slot. The first layer and its keyframe
    strip are created when missing; Blender allows one of each, so they are
    reused, never added twice.
    """
    if not hasattr(action, "layers"):
        found = action.fcurves.find(data_path, index=index)
        return found or action.fcurves.new(data_path, index=index, action_group=group_name or "")
    slot = _slot_of(action, slot)
    if slot is None:
        if not len(action.slots):
            raise ValueError(f"action {action.name!r} has no slot; add one with "
                             "action.slots.new(id_type='OBJECT', name=...)")
        slot = action.slots[0]
    layer = action.layers[0] if len(action.layers) else action.layers.new("Layer")
    strip = layer.strips[0] if len(layer.strips) else layer.strips.new(type='KEYFRAME')
    bag = strip.channelbag(slot, ensure=True)
    found = bag.fcurves.find(data_path, index=index)
    # group_name must be a string: None raises TypeError
    return found or bag.fcurves.new(data_path, index=index, group_name=group_name or "")


def assign_slot(obj, action, slot_index: int = 0):
    """Play `action` on `obj` through slot `slot_index`; returns that slot.

    Blender does not pick a slot by itself when an action moves to another
    object, so the slot is always set here. An action with no slot gets one for
    this object.
    """
    ad = obj.animation_data or obj.animation_data_create()
    if ad.use_tweak_mode:
        raise RuntimeError(f"{obj.name!r} is in NLA tweak mode; its action is read-only until it exits")
    if not hasattr(action, "slots"):
        ad.action = action
        return None
    if not len(action.slots) and slot_index == 0:
        action.slots.new(id_type=obj.id_type, name=obj.name)
    if not 0 <= slot_index < len(action.slots):
        raise IndexError(f"action {action.name!r} has {len(action.slots)} slot(s), no index {slot_index}")
    slot = action.slots[slot_index]
    ad.action = action
    ad.action_slot = slot
    return slot


# --- scene state -----------------------------------------------------------

_RESOLUTION = ("resolution_x", "resolution_y", "resolution_percentage")


def _view_layer_of(scene):
    if scene == bpy.context.scene:
        return bpy.context.view_layer
    return scene.view_layers[0]


def save_state(scene, objects) -> dict:
    """Snapshot what a render or a batch edit can disturb, as plain names and values.

    `objects` are objects or their names; actions, slots, NLA mutes and
    visibility are kept for those. Frame, selection, active object and its mode
    are kept for the whole view layer.
    """
    layer = _view_layer_of(scene)
    active = layer.objects.active
    state = {
        "scene": scene.name,
        "view_layer": layer.name,
        "frame": scene.frame_current,
        "active": active.name if active else None,
        "mode": active.mode if active else 'OBJECT',
        "selected": [o.name for o in layer.objects if o.select_get(view_layer=layer)],
        "resolution": {k: getattr(scene.render, k) for k in _RESOLUTION if hasattr(scene.render, k)},
        "objects": {},
    }
    for item in objects:
        obj = bpy.data.objects[item] if isinstance(item, str) else item
        ad = obj.animation_data
        slot = getattr(ad, "action_slot", None) if ad else None
        state["objects"][obj.name] = {
            "action": ad.action.name if ad and ad.action else None,
            "slot": slot.identifier if slot else None,
            "tweak": bool(ad and ad.use_tweak_mode),
            "nla_mute": {t.name: t.mute for t in ad.nla_tracks} if ad else {},
            "hide_render": obj.hide_render,
            "hide_viewport": obj.hide_viewport,
            "hide": obj.hide_get(view_layer=layer) if obj.name in layer.objects else False,
        }
    return state


def restore_state(state: dict) -> dict:
    """Put back a `save_state` snapshot. Best effort, so it is safe in a `finally:`.

    Returns {"missing": [names no longer in bpy.data], "errors": [messages]}.
    An object saved in NLA tweak mode gets tweak mode back on its active strip;
    the action underneath it is not reassigned.
    """
    missing, errors = [], []
    scene = bpy.data.scenes.get(state["scene"])
    if scene is None:
        return {"missing": [state["scene"]], "errors": []}
    layer = scene.view_layers.get(state["view_layer"]) or _view_layer_of(scene)

    current = bpy.context.object
    if current is not None and current.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError as exc:
            errors.append(f"mode OBJECT: {exc}")

    for name, saved in state["objects"].items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
            continue
        try:
            obj.hide_render = saved["hide_render"]
            obj.hide_viewport = saved["hide_viewport"]
            if obj.name in layer.objects:
                obj.hide_set(saved["hide"], view_layer=layer)
        except RuntimeError as exc:
            errors.append(f"{name} visibility: {exc}")
        ad = obj.animation_data
        if ad is None and saved["action"] is None and not saved["nla_mute"]:
            continue
        ad = ad or obj.animation_data_create()
        try:
            if ad.use_tweak_mode:
                ad.use_tweak_mode = False
            if not saved["tweak"]:
                action = bpy.data.actions.get(saved["action"]) if saved["action"] else None
                if saved["action"] and action is None:
                    missing.append(saved["action"])
                ad.action = action
                if action is not None and hasattr(ad, "action_slot"):
                    slot = next((s for s in action.slots if s.identifier == saved["slot"]), None)
                    ad.action_slot = slot
            for track in ad.nla_tracks:
                if track.name in saved["nla_mute"]:
                    track.mute = saved["nla_mute"][track.name]
            if saved["tweak"]:
                ad.use_tweak_mode = True
        except (RuntimeError, AttributeError, TypeError) as exc:
            errors.append(f"{name} animation: {exc}")

    wanted = set(state["selected"])
    for obj in layer.objects:
        if obj.select_get(view_layer=layer) != (obj.name in wanted):
            obj.select_set(obj.name in wanted, view_layer=layer)
    active = bpy.data.objects.get(state["active"]) if state["active"] else None
    if state["active"] and active is None:
        missing.append(state["active"])
    layer.objects.active = active if active is None or active.name in layer.objects else None

    scene.frame_set(state["frame"])
    for key, value in state["resolution"].items():
        setattr(scene.render, key, value)

    if active is not None and state["mode"] != 'OBJECT' and active.mode != state["mode"]:
        try:
            bpy.ops.object.mode_set(mode=state["mode"])
        except RuntimeError as exc:
            errors.append(f"mode {state['mode']}: {exc}")
    return {"missing": missing, "errors": errors}


# --- evaluation ------------------------------------------------------------

def sample_finite(obj, frames, bone_names=None) -> dict:
    """Step the context scene through `frames` and check every value is finite.

    Reads the evaluated `matrix_world`, or with `bone_names` the world-space
    head of each named pose bone. The frame is put back afterwards.
    Returns {"frames", "finite", "max_abs", "first_bad_frame"}; max_abs is
    over the finite values only.
    """
    scene = bpy.context.scene
    if bone_names:
        if obj.type != 'ARMATURE':
            raise ValueError(f"{obj.name!r} is a {obj.type}, not an armature; bone_names needs one")
        unknown = [n for n in bone_names if n not in obj.pose.bones]
        if unknown:
            raise KeyError(f"{obj.name!r} has no pose bone(s) {unknown}")
    frame, subframe = scene.frame_current, scene.frame_subframe
    count, max_abs, first_bad = 0, 0.0, None
    try:
        for f in frames:
            whole = math.floor(f)
            scene.frame_set(int(whole), subframe=float(f - whole))
            ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mw = ev.matrix_world
            if bone_names:
                values = [c for n in bone_names for c in mw @ ev.pose.bones[n].head]
            else:
                values = [c for row in mw for c in row]
            count += 1
            for value in values:
                if math.isfinite(value):
                    max_abs = max(max_abs, abs(value))
                elif first_bad is None:
                    first_bad = f
    finally:
        scene.frame_set(frame, subframe=subframe)
    return {"frames": count, "finite": first_bad is None, "max_abs": max_abs, "first_bad_frame": first_bad}
