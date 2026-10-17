"""brt_retarget.py — convert the rotation of mapped bones from a source skeleton onto a target.

Runs inside Blender; not a command-line script (the stub is in brt_common.py).
Stock bpy only: Auto-Rig Pro is not needed.

Scope: rotation conjugation of mapped bones, nothing else. Location and scale
curves are not read or written (`translation: "not retargeted"` in every
result; `translation_keyed` lists mapped source bones whose clip moves them).
Travel through space comes from the clip variant or another tool.

A key is a rotation from the bone's own rest, and two skeletons rest
differently, so copying the four numbers turns the target the wrong way. Each
mapped bone is converted by conjugation with one constant K:

  1. T, the target bone at rest: the target rig's world rotation × the bone's
     matrix_local rotation.
  2. S, the source reference: the source bones walked parents first,
     ref[root] = W × R[root], ref[child] = ref[parent] × inv(R[parent]) × R[child],
     each aimed bone swung by the shortest arc from its own axis (+Y) onto its
     target bone's head→tail direction. The swing sets direction; roll stays the source's.
     The aimed bones are `reference_map` ({target: source}, default `map`)
     less `no_aim` (target bones); the written bones are `map`. S of a bone
     depends on every aimed ancestor, so K of a hand needs the arm aimed.
  3. K = inv(T) × S; per integer frame q_t = K × q_s × inv(K), normalised, and
     negated when its dot with the previous key is negative (the first key gets w >= 0).

    result = brt_retarget.run({
        "source": "MocapRig", "target": "RunnerRig", "source_action": "Jog",
        "map": {"Hips": "hips", "Spine": "spine_01", "UpperArm.L": "arm_l"},   # target: source
        "frame_range": [1, 33], "output_action": "RunnerJog", "loop": True,
    })
    # one bone into an action that already exists (one Auto-Rig Pro baked):
    # the body is aimed for the walk, the hand written and left unaimed
    # (a fitted hand tail need not lie along the palm)
    result = brt_retarget.run({
        "source": "JogLaneLeft_Source", "target": "RunnerRig", "map": {"c_hand_fk.r": "RightHand"},
        "reference_map": {"c_root_master.x": "Hips", "c_spine_01.x": "Spine",
                          "c_shoulder.r": "RightShoulder", "c_arm_fk.r": "RightArm",
                          "c_forearm_fk.r": "RightForeArm"},
        "into_action": "JogLaneLeft",
    })

Orientations are world-space (rig world rotation × matrix_local); with both
rigs unrotated that is armature space. `source_action` defaults to the source's
assigned action, `frame_range` to that action's range (with `into_action`, to
the range of the action written into), `output_action` to "<target>_<source_action>".

`reference_frame` (default None: the source's rest, every pose bone at
identity) names a frame of the clip where the source stands in the target's
rest pose. The walk then takes the source's pose at that frame as its rest, and
every key is rebased on it, q_s = inv(q_ref) × q_s, so the target sits at rest
on that frame. Without it, a rest that differs in pose (T-pose against A-pose)
is only swung into line, and the arms keep the difference in every frame.

The source is read from its F-curves (fcurve.evaluate), never by stepping the
scene: rotation only, no constraints, full rotation inheritance. A source bone
may be in QUATERNION, any Euler order or AXIS_ANGLE mode, converted to a
quaternion per frame; a channel without a curve is its rest value, and a mapped
bone with no curve for its mode raises. Map from the root outward: K reproduces
motion relative to the parent, so a bone is right only under a converted parent.

Two ways to write, four LINEAR rotation_quaternion curves per mapped bone with
one key per frame either way. Both set the mapped target pose bones to
QUATERNION mode (not undone) and store K, per written bone the bones aimed
for its K (`aim`), and a hash of both rests and the maps on the action as the
`brt_retarget` property.

  new action (default)  `output_action`, fake user on, assigned to the target
          through its slot. A name already taken refuses (gate
          retarget.output_is_new failing, a `message`) before anything changes.
          `overwrite_action: True` replaces it: the new action is built under a
          free name, and the old one is removed only once the new one exists.
  `into_action: NAME`   an action that already exists, for instance the one an
          Auto-Rig Pro retarget baked. The curves go on the slot the target plays
          it through, else the slot named after the target, else its first slot
          (an action without a slot refuses). What the target plays is not
          changed. A mapped bone that already has a rotation curve there
          (quaternion, Euler or axis-angle) refuses (gate retarget.channels_free
          failing, `existing` lists them) before anything changes; `replace: True`
          removes those bones' rotation curves first. Every other curve is left
          as it was. `output_action` and `overwrite_action` are refused with it.
          A `brt_retarget` record already on the action from the same source,
          source action and reference_frame is merged per bone (map, K, aim);
          one from another conversion is replaced, with a warning.

Gates: retarget.output_is_new (new action) or retarget.channels_free
(into_action); retarget.finite_keys (no NaN or infinite value in the curves
written); retarget.first_equals_last when `loop` is set. Reported, not gated:
max_step (largest rotation between consecutive written keys) with max_step_at,
and source_max_step. Conjugation keeps angles, so the two are equal by
construction: they show how fast the clip moves, never whether the map is right.
A near-pi max_step is a lost sign. Whether the conversion is right is a picture:
stills beside the source.
"""
from __future__ import annotations

import hashlib
import json
import math

import bpy
from mathutils import Euler, Quaternion, Vector

import brt_common as C

_Y = Vector((0.0, 1.0, 0.0))
_LINEAR = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
_REST = {"rotation_quaternion": (1.0, 0.0, 0.0, 0.0), "rotation_euler": (0.0, 0.0, 0.0),
         "rotation_axis_angle": (0.0, 0.0, 1.0, 0.0)}
_ROTATIONS = tuple(_REST)


def _bone_path(name: str, prop: str) -> str:
    return f'pose.bones["{bpy.utils.escape_identifier(name)}"].{prop}'


def _world_rotation(obj) -> Quaternion:
    return obj.matrix_world.to_3x3().normalized().to_quaternion()


def _rest(bone) -> Quaternion:
    return bone.matrix_local.to_3x3().normalized().to_quaternion()


def _step(a: Quaternion, b: Quaternion) -> float:
    """Rotation travelled from key a to key b; past pi when the sign flipped between them."""
    d = a.conjugated() @ b
    return 2.0 * math.atan2(math.hypot(d.x, d.y, d.z), d.w)


class _Channels:
    """One source bone's rotation at any frame, read from the clip's F-curves."""

    def __init__(self, curves: dict, pose_bone):
        self.mode = pose_bone.rotation_mode
        self.prop = {"QUATERNION": "rotation_quaternion",
                     "AXIS_ANGLE": "rotation_axis_angle"}.get(self.mode, "rotation_euler")
        path = _bone_path(pose_bone.name, self.prop)
        self.rest = _REST[self.prop]
        self.curves = [curves.get((path, i)) for i in range(len(self.rest))]
        self.keyed = any(fc is not None for fc in self.curves)
        self.name = pose_bone.name

    def at(self, frame) -> Quaternion:
        v = [fc.evaluate(frame) if fc is not None else r for fc, r in zip(self.curves, self.rest)]
        if self.prop == "rotation_quaternion":
            q = Quaternion(v)
        elif self.prop == "rotation_euler":
            q = Euler(v, self.mode).to_quaternion()
        else:
            axis = Vector(v[1:])
            q = Quaternion(axis.normalized(), v[0]) if axis.length > 1e-12 else Quaternion()
        if not q.magnitude > 1e-9:      # also catches NaN
            raise ValueError(f"source bone {self.name!r} has a zero or non-finite rotation at frame {frame}")
        return q.normalized()


def _slot_for(action, rig):
    """The slot `rig` plays `action` through, else the one named after it, else the first."""
    ad = rig.animation_data
    if ad and ad.action == action and getattr(ad, "action_slot", None) is not None:
        return ad.action_slot
    slots = list(getattr(action, "slots", []))
    return next((s for s in slots if s.name_display == rig.name), slots[0] if slots else None)


def _channelbags(action, slot) -> list:
    """The channelbags of `slot` in every layer and strip of a layered action."""
    if slot is None or not hasattr(action, "layers"):
        return []
    return [bag for layer in action.layers for strip in layer.strips
            for bag in getattr(strip, "channelbags", []) if bag.slot_handle == slot.handle]


def _source_reference(rig, aim: dict, pose_at_ref: dict) -> dict:
    """S for every source bone: its world orientation laid into the target's rest."""
    world = _world_rotation(rig)
    ref = {}
    stack = [(bone, None) for bone in rig.data.bones if bone.parent is None]
    while stack:                                  # parents before children, whatever the list order
        bone, parent_ref = stack.pop()
        if parent_ref is None:
            q = world @ _rest(bone)
        else:
            q = parent_ref @ _rest(bone.parent).inverted() @ _rest(bone)
        q = q @ pose_at_ref.get(bone.name, Quaternion())
        d = aim.get(bone.name)
        if d is not None and d.length > 1e-9:
            q = (q @ _Y).rotation_difference(d) @ q
        q.normalize()
        ref[bone.name] = q
        stack.extend((child, q) for child in bone.children)
    return ref


def _rest_hash(src, tgt, mapping: dict, aim: dict) -> str:
    """Identifies both rests and the maps; K is valid only while this is unchanged."""
    h = hashlib.sha1()
    for rig in (src, tgt):
        values = list(_world_rotation(rig))
        for bone in rig.data.bones:
            h.update(bone.name.encode())
            values += [v for row in bone.matrix_local for v in row]
        h.update(",".join(f"{round(v, 5) + 0.0:.5f}" for v in values).encode())
    h.update(json.dumps([sorted(mapping.items()),
                         sorted((t, sorted(a.items())) for t, a in aim.items())]).encode())
    return h.hexdigest()[:16]


def _refusal(params, gate, message, **extra) -> dict:
    return C.report(params, [gate], translation="not retargeted", message=message, **extra)


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    src = bpy.data.objects[params["source"]]
    tgt = bpy.data.objects[params["target"]]
    for rig in (src, tgt):
        if rig.type != 'ARMATURE':
            raise ValueError(f"{rig.name!r} is a {rig.type}, not an armature")
    mapping = dict(params.get("map") or {})
    if not mapping:
        raise ValueError("map is empty: give {target_bone: source_bone}")
    unknown = ([f"target {t}" for t in mapping if t not in tgt.data.bones]
               + [f"source {s}" for s in mapping.values() if s not in src.data.bones])
    if unknown:
        raise KeyError(f"bones not found: {unknown}")
    sources = list(mapping.values())
    twice = sorted({s for s in sources if sources.count(s) > 1})
    if twice:
        raise ValueError(f"source bones mapped to more than one target: {twice}")
    given_ref = params.get("reference_map")
    reference = dict(mapping if given_ref is None else given_ref)
    unknown = ([f"target {t}" for t in reference if t not in tgt.data.bones]
               + [f"source {s}" for s in reference.values() if s not in src.data.bones])
    if unknown:
        raise KeyError(f"reference_map bones not found: {unknown}")
    ref_sources = list(reference.values())
    twice = sorted({s for s in ref_sources if ref_sources.count(s) > 1})
    if twice:
        raise ValueError(f"reference_map aims a source bone at more than one target: {twice}")
    no_aim = params.get("no_aim") or []
    if isinstance(no_aim, str) or not all(isinstance(t, str) for t in no_aim):
        raise ValueError("no_aim is a list of target bone names")
    no_aim = sorted(set(no_aim))
    stray = [t for t in no_aim if t not in mapping and t not in reference]
    if stray:
        raise KeyError(f"no_aim names bones in neither map nor reference_map: {stray}")
    aimed = {t: s for t, s in reference.items() if t not in no_aim}

    ad = src.animation_data
    name = params.get("source_action") or (ad.action.name if ad and ad.action else None)
    if not name:
        raise ValueError(f"no source_action given and {src.name!r} has no action assigned")
    clip = bpy.data.actions[name]
    warnings = []
    if "max_step_rad" in params:
        warnings.append("max_step_rad is ignored: max_step is reported, not gated")

    into_name = params.get("into_action")
    into = None
    if into_name:
        if params.get("output_action") or params.get("overwrite_action"):
            raise ValueError("into_action writes into an existing action: drop output_action / overwrite_action")
        into = bpy.data.actions.get(into_name)
        if into is None:
            raise KeyError(f"into_action {into_name!r} is not an action in this file")
        if into == clip:
            raise ValueError(f"into_action {into_name!r} is the source clip")
    out_name = into_name or params.get("output_action") or f"{tgt.name}_{clip.name}"
    if out_name == clip.name:
        raise ValueError(f"output_action {out_name!r} would replace the source clip")

    # everything above only reads: a refusal here leaves the file as it was
    exists = False
    if into is None:
        overwrite = bool(params.get("overwrite_action", False))
        exists = bpy.data.actions.get(out_name) is not None
        first_gate = C.gate("retarget.output_is_new", "exists" if exists else "new",
                            "new, or overwrite_action", not exists or overwrite)
        if not first_gate["pass"]:
            return _refusal(params, first_gate,
                            f"an action named {out_name!r} already exists; nothing was changed. "
                            "Pass overwrite_action: True to replace it, choose another output_action, "
                            "or write into it with into_action.",
                            source=src.name, target=tgt.name, source_action=clip.name,
                            output_action=out_name, reason="output_exists", warnings=warnings)
        out_slot = None
    else:
        out_slot = _slot_for(into, tgt)
        if out_slot is None or not hasattr(into, "layers"):
            raise ValueError(f"into_action {into.name!r} has no slot to write the target's curves to")
        paths = {_bone_path(t, prop): t for t in mapping for prop in _ROTATIONS}
        existing = sorted({f"{fc.data_path}[{fc.array_index}]" for fc in C.action_slot_fcurves(into, out_slot)
                           if fc.data_path in paths})
        replace = bool(params.get("replace", False))
        first_gate = C.gate("retarget.channels_free", len(existing), "0, or replace",
                            not existing or replace)
        if not first_gate["pass"]:
            return _refusal(params, first_gate,
                            f"{into.name!r} already has rotation curves for mapped bones; nothing was "
                            "changed. Pass replace: True to replace them.",
                            source=src.name, target=tgt.name, source_action=clip.name,
                            into_action=into.name, existing=existing, reason="channels_exist",
                            warnings=warnings)

    slot_in = _slot_for(clip, src)
    curves = {(fc.data_path, fc.array_index): fc for fc in C.action_slot_fcurves(clip, slot_in)}

    if params.get("frame_range"):
        start, end = (int(v) for v in params["frame_range"])
    else:
        start, end = (int(round(v)) for v in (into or clip).frame_range)
    if end < start:
        raise ValueError(f"frame_range [{start}, {end}] is empty")
    frames = list(range(start, end + 1))

    channels = {s: _Channels(curves, src.pose.bones[s]) for s in sources}
    unkeyed = [f"{s} ({ch.prop})" for s, ch in channels.items() if not ch.keyed]
    if unkeyed:
        raise ValueError(f"{clip.name!r} has no curve for the rotation mode of: {unkeyed}")
    moved = sorted(s for s in sources
                   if any((_bone_path(s, "location"), i) in curves for i in range(3)))
    ref_frame = params.get("reference_frame")
    pose_at_ref = {}
    if ref_frame is not None:
        pose_at_ref = {pb.name: _Channels(curves, pb).at(ref_frame) for pb in src.pose.bones}

    # constant per bone: K from both rests, before any key is read
    tw = _world_rotation(tgt)
    aim = {s: tw @ (tgt.data.bones[t].tail_local - tgt.data.bones[t].head_local) for t, s in aimed.items()}
    ref = _source_reference(src, aim, pose_at_ref)
    K = {t: ((tw @ _rest(tgt.data.bones[t])).inverted() @ ref[s]).normalized() for t, s in mapping.items()}

    keys, source_step = {}, 0.0
    for t, s in mapping.items():
        k, k_inv = K[t], K[t].inverted()
        rebase = pose_at_ref.get(s, Quaternion()).inverted()
        out, prev, prev_src = [], None, None
        for f in frames:
            qs = channels[s].at(f)
            if prev_src is not None:
                if qs.dot(prev_src) < 0:
                    qs.negate()
                source_step = max(source_step, _step(prev_src, qs))
            prev_src = qs
            qt = (k @ rebase @ qs @ k_inv).normalized()
            if (prev is None and qt.w < 0) or (prev is not None and qt.dot(prev) < 0):
                qt.negate()
            out.append(qt)
            prev = qt
        keys[t] = out

    removed = []
    if into is None:
        # built under a free name; with overwrite_action the old one goes only once this one exists
        action = bpy.data.actions.new(out_name)
        action.use_fake_user = True
        slot = C.assign_slot(tgt, action)
    else:
        action, slot = into, out_slot
        for bag in _channelbags(action, slot):
            for fc in list(bag.fcurves):
                if fc.data_path in paths:
                    removed.append(f"{fc.data_path}[{fc.array_index}]")
                    bag.fcurves.remove(fc)
    n = len(frames)
    for t, quats in keys.items():
        tgt.pose.bones[t].rotation_mode = 'QUATERNION'
        path = _bone_path(t, "rotation_quaternion")
        for i in range(4):
            fc = C.ensure_fcurve(action, slot, path, i, group_name=t)
            fc.keyframe_points.add(n)
            fc.keyframe_points.foreach_set("co", [x for f, q in zip(frames, quats) for x in (f, q[i])])
            fc.keyframe_points.foreach_set("interpolation", [_LINEAR] * n)
            fc.update()
    if into is None and action.name != out_name:
        old = bpy.data.actions.get(out_name)
        if old is not None:
            bpy.data.actions.remove(old)
        action.name = out_name

    record = {"source": src.name, "target": tgt.name, "source_action": clip.name,
              "reference_frame": ref_frame, "map": mapping,
              "K": {t: [round(v, 7) for v in K[t]] for t in mapping},
              "aim": {t: dict(aimed) for t in mapping}}
    if into is not None and "brt_retarget" in action.keys():
        try:
            before = json.loads(action["brt_retarget"])
        except (TypeError, ValueError):
            before = None
        same = isinstance(before, dict) and all(
            before.get(k) == record[k] for k in ("source", "target", "source_action", "reference_frame"))
        if same:
            record["map"] = {**before.get("map", {}), **mapping}
            record["K"] = {**before.get("K", {}), **record["K"]}
            record["aim"] = {**before.get("aim", {}), **record["aim"]}
        else:
            warnings.append(f"replaced the brt_retarget record of another conversion on {action.name!r}")
    if into is not None:
        record["into_action"] = True
    record["rest_hash"] = _rest_hash(src, tgt, record["map"], record["aim"])
    action["brt_retarget"] = json.dumps(record)

    # every gate reads what was written, not the lists above
    bone_of = {_bone_path(t, "rotation_quaternion"): t for t in mapping}
    written = [fc for fc in C.action_slot_fcurves(action, slot) if fc.data_path in bone_of]
    values, bad = {}, 0
    for fc in written:
        co = [0.0] * (2 * len(fc.keyframe_points))
        fc.keyframe_points.foreach_get("co", co)
        bad += sum(1 for v in co if not math.isfinite(v))
        values.setdefault(fc.data_path, {})[fc.array_index] = (co[0::2], co[1::2])
    max_step, step_at, seam = 0.0, None, 0.0
    for path, comps in values.items():
        if bad or sorted(comps) != [0, 1, 2, 3]:
            continue
        times = comps[0][0]
        quats = [Quaternion(q).normalized() for q in zip(*(comps[i][1] for i in range(4)))]
        for j in range(1, len(quats)):
            step = _step(quats[j - 1], quats[j])
            if step > max_step:
                max_step, step_at = step, {"bone": bone_of[path], "frame": times[j]}
        d = quats[0].conjugated() @ quats[-1]
        seam = max(seam, 2.0 * math.atan2(math.hypot(d.x, d.y, d.z), abs(d.w)))

    gates = [first_gate, C.gate("retarget.finite_keys", bad, 0, bad == 0)]
    if params.get("loop"):
        gates.append(C.gate("retarget.first_equals_last", seam, "< 1e-4", not bad and seam < 1e-4))
    target_key = {"into_action": action.name, "curves_removed": removed} if into is not None \
        else {"output_action": action.name, "replaced": exists}
    return C.report(params, gates, source=src.name, target=tgt.name, source_action=clip.name,
                    **target_key, slot=slot.identifier if slot else None,
                    curves_written=len(written), frame_range=[start, end], frames=n,
                    map=mapping, reference_map=reference, no_aim=no_aim,
                    aimed=sorted(aimed), reference_frame=ref_frame,
                    translation="not retargeted", translation_keyed=moved,
                    max_step=max_step if not bad else None, max_step_at=step_at,
                    source_max_step=source_step,
                    source_modes={s: ch.mode for s, ch in channels.items()},
                    K={t: list(K[t]) for t in mapping}, warnings=warnings)
