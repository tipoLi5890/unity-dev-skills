#!/usr/bin/env python3
"""fingerprint.py — read a Unity project's perspective and movement model off its files.

Walks Assets/ (text-serialised scenes, prefabs, scripts, sprite .meta files), ProjectSettings/
and Packages/, and prints ONE JSON object: dimension, projection, view, movement-model hints,
grid layout, input handling, and the packages that change which API names are correct —
including the Cinemachine major. Every verdict carries the counts it was derived from, so a
reader can overrule it. Nothing is written and Unity is not started.

The verdicts are hints. Read the object as a whole (`reference/perspective-fingerprint.md`):
a package being installed says what a template added, not what the game uses.

Exit codes: 0 fine (also when a verdict is "unknown") · 2 the path is not a Unity project,
or it could not be read. There is no exit 1: a fingerprint has no pass or fail.

Examples:
  fingerprint.py .
  fingerprint.py ~/games/courier-run --indent 2
  fingerprint.py . --exclude Plugins --exclude 'TextMesh Pro' --exclude Vendor
  fingerprint.py . | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['dimension']['value'], d['packages']['cinemachine'])"
"""
import argparse
import json
import math
import os
import re
import sys

DEFAULT_EXCLUDES = ("Plugins", "TextMesh Pro", "ThirdParty", "Samples", "StreamingAssets")

# Component headers as they appear at column zero in a text-serialised scene or prefab.
PHYSICS_2D = ("Rigidbody2D",)
COLLIDERS_2D = ("BoxCollider2D", "CircleCollider2D", "CapsuleCollider2D", "PolygonCollider2D",
                "EdgeCollider2D", "CompositeCollider2D", "TilemapCollider2D", "CustomCollider2D")
COLLIDERS_3D = ("BoxCollider", "SphereCollider", "CapsuleCollider", "MeshCollider",
                "TerrainCollider", "WheelCollider")
COUNTED = set(PHYSICS_2D + COLLIDERS_2D + COLLIDERS_3D + (
    "Rigidbody", "CharacterController", "NavMeshAgent", "SpriteRenderer", "MeshRenderer",
    "SkinnedMeshRenderer", "Tilemap", "TilemapRenderer", "Grid", "Camera", "PlatformEffector2D",
    "Terrain", "Animator", "SpriteMask", "SortingGroup"))

CELL_LAYOUTS = {0: "rectangle", 1: "hexagon", 2: "isometric", 3: "isometric-z-as-y"}
INPUT_HANDLERS = {0: "input-manager", 1: "input-system", 2: "both"}

# Script patterns: name → regex. Counted per occurrence across Assets/**/*.cs.
SCRIPT_PATTERNS = {
    "Rigidbody2D": r"\bRigidbody2D\b",
    "Rigidbody": r"\bRigidbody\b",
    "CharacterController": r"\bCharacterController\b",
    "NavMeshAgent": r"\bNavMeshAgent\b",
    "Physics2D": r"\bPhysics2D\.",
    "Physics": r"\bPhysics\.",
    "MovePosition": r"\.MovePosition\(",
    "cell_api": r"\b(WorldToCell|CellToWorld|GetCellCenterWorld|LocalToCell|CellToLocal)\(",
    "Tilemap": r"\bTilemap\b",
    "legacy_input": r"\bInput\.(GetAxis|GetAxisRaw|GetKey|GetKeyDown|GetKeyUp|GetButton|"
                    r"GetButtonDown|GetButtonUp|GetMouseButton|GetMouseButtonDown|GetTouch|"
                    r"mousePosition|touchCount)\b",
    "input_system": r"\bUnityEngine\.InputSystem\b|\bInputAction\b|\bPlayerInput\b|"
                    r"\bInputActionReference\b",
    "cinemachine_2x": r"^\s*using\s+Cinemachine\s*;|\bCinemachineVirtualCamera\b|"
                      r"\bCinemachineFreeLook\b",
    "cinemachine_3x": r"^\s*using\s+Unity\.Cinemachine\s*;|\bCinemachineCamera\b",
    "screen_to_world": r"\bScreenToWorldPoint\(|\bScreenPointToRay\(",
    "root_motion": r"\bapplyRootMotion\b|\bOnAnimatorMove\b",
}
SCRIPT_RE = {k: re.compile(v, re.MULTILINE) for k, v in SCRIPT_PATTERNS.items()}

PACKAGES_OF_INTEREST = {
    "cinemachine": "com.unity.cinemachine",
    "inputsystem": "com.unity.inputsystem",
    "feature_2d": "com.unity.feature.2d",
    "tilemap": "com.unity.2d.tilemap",
    "tilemap_extras": "com.unity.2d.tilemap.extras",
    "pixel_perfect": "com.unity.2d.pixel-perfect",
    "animation_2d": "com.unity.2d.animation",
    "spriteshape": "com.unity.2d.spriteshape",
    "ai_navigation": "com.unity.ai.navigation",
    "animation_rigging": "com.unity.animation.rigging",
    "timeline": "com.unity.timeline",
    "probuilder": "com.unity.probuilder",
    "splines": "com.unity.splines",
    "urp": "com.unity.render-pipelines.universal",
    "hdrp": "com.unity.render-pipelines.high-definition",
    "test_framework": "com.unity.test-framework",
}

HEADER = re.compile(r"^([A-Za-z0-9_]+):\s*$")
FILE_ID = re.compile(r"fileID:\s*(-?\d+)")
VEC = re.compile(r"([xyzw]):\s*(-?[0-9.eE+-]+)")


# ---------------------------------------------------------------- small readers


def read_text(path, limit=None):
    """File contents as text, or None when unreadable. Undecodable bytes are replaced."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit) if limit else fh.read()
    except OSError:
        return None


def parse_vector(text):
    return {k: float(v) for k, v in VEC.findall(text)}


def number_after(line):
    try:
        return float(line.split(":", 1)[1].strip())
    except (IndexError, ValueError):
        return None


def walk_assets(assets, excludes):
    """Yield every file path under Assets/, skipping excluded, hidden and `~` folders."""
    excluded = {e.lower() for e in excludes}
    for root, dirs, files in os.walk(assets):
        dirs[:] = sorted(d for d in dirs
                         if d.lower() not in excluded and not d.startswith(".")
                         and not d.endswith("~"))
        for name in sorted(files):
            yield os.path.join(root, name)


# ---------------------------------------------------------------- scenes and prefabs


def camera_angles(rotation):
    """(pitch_down_deg, yaw_deg) of a camera from its local rotation quaternion."""
    x, y, z, w = (rotation.get(k, 0.0) for k in "xyzw")
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-9:
        return 0.0, 0.0
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    # forward = q * (0, 0, 1)
    fx = 2.0 * (x * z + w * y)
    fy = 2.0 * (y * z - w * x)
    fz = 1.0 - 2.0 * (x * x + y * y)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -fy))))
    yaw = math.degrees(math.atan2(fx, fz))
    return round(pitch, 1) + 0.0, round(yaw, 1) + 0.0   # + 0.0 turns -0.0 into 0.0


def scan_yaml(path, rel, tally):
    """Count components in one text-serialised scene or prefab. False when it is binary."""
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return False
    with fh:
        first = fh.readline()
        if not first.startswith("%YAML"):
            return False

        counts = tally["components"]
        kind, doc = None, None
        cameras, transforms = [], {}

        def close():
            if kind == "Camera" and doc is not None:
                cameras.append(doc)
            elif kind in ("Transform", "RectTransform") and doc is not None:
                if doc.get("go") is not None:
                    transforms[doc["go"]] = doc

        for line in fh:
            if line.startswith("--- "):
                close()
                kind, doc = None, None
                continue
            if kind is None:
                m = HEADER.match(line)
                if not m:
                    continue
                kind = m.group(1)
                if kind in COUNTED:
                    counts[kind] = counts.get(kind, 0) + 1
                doc = {} if kind in ("Camera", "Transform", "RectTransform", "Grid",
                                     "Rigidbody2D", "Rigidbody") else None
                continue
            if doc is None:
                continue
            s = line.strip()
            if kind == "Camera":
                if s.startswith("orthographic size:"):
                    doc["size"] = number_after(s)
                elif s.startswith("orthographic:"):
                    doc["orthographic"] = number_after(s) == 1.0
                elif s.startswith("field of view:"):
                    doc["fov"] = number_after(s)
                elif s.startswith("m_GameObject:"):
                    m = FILE_ID.search(s)
                    doc["go"] = m.group(1) if m else None
            elif kind in ("Transform", "RectTransform"):
                if s.startswith("m_GameObject:"):
                    m = FILE_ID.search(s)
                    doc["go"] = m.group(1) if m else None
                elif s.startswith("m_LocalRotation:"):
                    doc["rot"] = parse_vector(s)
                elif s.startswith("m_Father:"):
                    m = FILE_ID.search(s)
                    doc["parented"] = bool(m and m.group(1) != "0")
            elif kind == "Grid":
                if s.startswith("m_CellLayout:"):
                    value = number_after(s)
                    name = CELL_LAYOUTS.get(int(value), "unknown") if value is not None else "unknown"
                    tally["cell_layouts"][name] = tally["cell_layouts"].get(name, 0) + 1
                elif s.startswith("m_CellSize:"):
                    v = parse_vector(s)
                    key = "%g x %g" % (v.get("x", 0.0), v.get("y", 0.0))
                    tally["cell_sizes"][key] = tally["cell_sizes"].get(key, 0) + 1
            elif kind == "Rigidbody2D":
                if s.startswith("m_GravityScale:"):
                    value = number_after(s)
                    key = "gravity_scale_zero" if value == 0.0 else "gravity_scale_nonzero"
                    tally["bodies_2d"][key] += 1
                elif s.startswith("m_BodyType:"):
                    value = number_after(s)
                    key = {0.0: "dynamic", 1.0: "kinematic", 2.0: "static"}.get(value, "dynamic")
                    tally["bodies_2d"][key] += 1
            elif kind == "Rigidbody":
                if s.startswith("m_IsKinematic:"):
                    key = "kinematic" if number_after(s) == 1.0 else "dynamic"
                    tally["bodies_3d"][key] += 1
        close()

    for cam in cameras:
        if "orthographic" not in cam:
            continue
        entry = {"file": rel, "orthographic": cam["orthographic"]}
        if cam["orthographic"]:
            entry["orthographic_size"] = cam.get("size")
        else:
            entry["fov"] = cam.get("fov")
        tr = transforms.get(cam.get("go"))
        if tr and "rot" in tr:
            entry["pitch_down_deg"], entry["yaw_deg"] = camera_angles(tr["rot"])
            entry["parented"] = bool(tr.get("parented"))
        tally["cameras"].append(entry)
    return True


# ---------------------------------------------------------------- settings and packages


def read_packages(project):
    """Resolved versions from packages-lock.json, else declared ones from manifest.json."""
    out = {"source": "absent"}
    lock = os.path.join(project, "Packages", "packages-lock.json")
    manifest = os.path.join(project, "Packages", "manifest.json")
    versions = {}
    for path, source in ((lock, "packages-lock.json"), (manifest, "manifest.json")):
        text = read_text(path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        deps = data.get("dependencies")
        if not isinstance(deps, dict):
            continue
        for name, value in deps.items():
            version = value.get("version") if isinstance(value, dict) else value
            versions[name] = str(version)
        out["source"] = source
        break

    for key, package in PACKAGES_OF_INTEREST.items():
        out[key] = versions.get(package)

    version = out.get("cinemachine")
    major = None
    if version:
        m = re.match(r"(\d+)\.", version)
        major = int(m.group(1)) if m else None
    out["cinemachine"] = {"version": version, "major": major}
    out["count"] = len(versions)
    return out


def read_gravity(path):
    text = read_text(path)
    if text is None:
        return None
    m = re.search(r"^\s*m_Gravity:\s*(\{.*\})", text, re.MULTILINE)
    return parse_vector(m.group(1)) if m else None


def read_settings(project):
    settings = os.path.join(project, "ProjectSettings")
    out = {"unity": None, "active_input_handler": "unknown",
           "gravity_2d": read_gravity(os.path.join(settings, "Physics2DSettings.asset")),
           "gravity_3d": read_gravity(os.path.join(settings, "DynamicsManager.asset"))}
    text = read_text(os.path.join(settings, "ProjectVersion.txt"))
    if text:
        m = re.search(r"m_EditorVersion:\s*(\S+)", text)
        out["unity"] = m.group(1) if m else None
    text = read_text(os.path.join(settings, "ProjectSettings.asset"))
    if text:
        m = re.search(r"^\s*activeInputHandler:\s*(\d+)", text, re.MULTILINE)
        if m:
            out["active_input_handler"] = INPUT_HANDLERS.get(int(m.group(1)), "unknown")
    return out


# ---------------------------------------------------------------- verdicts


def top(counter, n=3):
    return [k for k, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def decide_dimension(c, scripts, cameras):
    physics_2d = c.get("Rigidbody2D", 0) + sum(c.get(k, 0) for k in COLLIDERS_2D)
    physics_3d = (c.get("Rigidbody", 0) + c.get("CharacterController", 0)
                  + c.get("NavMeshAgent", 0) + sum(c.get(k, 0) for k in COLLIDERS_3D))
    render_2d = c.get("SpriteRenderer", 0) + c.get("TilemapRenderer", 0)
    render_3d = c.get("MeshRenderer", 0) + c.get("SkinnedMeshRenderer", 0) + c.get("Terrain", 0)
    code_2d = scripts.get("Rigidbody2D", 0) + scripts.get("Physics2D", 0)
    code_3d = (scripts.get("Rigidbody", 0) + scripts.get("CharacterController", 0)
               + scripts.get("NavMeshAgent", 0) + scripts.get("Physics", 0))
    evidence = {"physics_2d": physics_2d, "physics_3d": physics_3d,
                "renderers_2d": render_2d, "renderers_3d": render_3d,
                "script_refs_2d": code_2d, "script_refs_3d": code_3d}

    def pick(a, b):
        if a and not b:
            return "2d"
        if b and not a:
            return "3d"
        if a and b:
            return "mixed"
        return None

    # Physics is the strongest signal: it is what a controller is written against. Renderers
    # come last, because a 3D game has sprites in its UI and a 2D game has a mesh or two.
    value, basis = None, None
    for basis, (a, b) in (("physics components", (physics_2d, physics_3d)),
                          ("script references", (code_2d, code_3d)),
                          ("renderers", (render_2d, render_3d))):
        value = pick(a, b)
        if value:
            break
    if not value:
        ortho = sum(1 for cam in cameras if cam["orthographic"])
        persp = len(cameras) - ortho
        value, basis = pick(ortho, persp), "camera projection"
        if value == "mixed" or not value:
            value, basis = "unknown", "no evidence"
    evidence["decided_by"] = basis
    out = {"value": value, "evidence": evidence}
    if value == "mixed":
        out["leans"] = "2d" if physics_2d + code_2d > physics_3d + code_3d else "3d"
    return out


def decide_projection(cameras):
    ortho = sum(1 for cam in cameras if cam["orthographic"])
    persp = len(cameras) - ortho
    if ortho and persp:
        value = "mixed"
    elif ortho:
        value = "orthographic"
    elif persp:
        value = "perspective"
    else:
        value = "unknown"
    return {"value": value, "evidence": {"orthographic_cameras": ortho,
                                         "perspective_cameras": persp}}


def decide_view(dimension, tally, settings):
    candidates, evidence = [], {}
    layouts = tally["cell_layouts"]
    bodies = tally["bodies_2d"]
    gravity_2d = settings.get("gravity_2d") or {}
    pitches = [cam["pitch_down_deg"] for cam in tally["cameras"] if "pitch_down_deg" in cam]
    evidence["camera_pitch_down_deg"] = sorted(set(pitches))[:8]

    lean = dimension.get("leans", dimension["value"])
    if lean == "2d":
        zero_gravity = bool(gravity_2d) and abs(gravity_2d.get("y", 0.0)) < 1e-6
        falling = bodies["gravity_scale_nonzero"]
        floating = bodies["gravity_scale_zero"]
        evidence.update({"gravity_2d_y": gravity_2d.get("y"),
                         "bodies_gravity_scale_nonzero": falling,
                         "bodies_gravity_scale_zero": floating,
                         "platform_effectors": tally["components"].get("PlatformEffector2D", 0)})
        if layouts.get("isometric") or layouts.get("isometric-z-as-y"):
            candidates.append("isometric")
        if layouts.get("hexagon"):
            candidates.append("top-down")
        if zero_gravity or (floating and not falling):
            candidates.append("top-down")
        elif falling or evidence["platform_effectors"]:
            candidates.append("side")
    elif lean == "3d":
        ortho = any(cam["orthographic"] for cam in tally["cameras"])
        if pitches:
            steepest = max(pitches)
            if steepest >= 50.0:
                candidates.append("top-down")
            elif ortho and 20.0 <= steepest < 50.0:
                candidates.append("isometric")
            elif steepest < 50.0:
                candidates.append("behind-or-eye-level")

    seen = []
    for cand in candidates:
        if cand not in seen:
            seen.append(cand)
    return {"value": seen[0] if len(seen) == 1 else ("ambiguous" if seen else "unknown"),
            "candidates": seen, "evidence": evidence}


def movement_hints(tally, scripts):
    c, hints = tally["components"], []

    def add(model, **evidence):
        hints.append({"model": model, "evidence": evidence})

    b2, b3 = tally["bodies_2d"], tally["bodies_3d"]
    if scripts.get("cell_api") and c.get("Grid"):
        add("cell-step", cell_api_calls=scripts["cell_api"], grids=c["Grid"])
    if c.get("CharacterController") or scripts.get("CharacterController"):
        add("character-controller", components=c.get("CharacterController", 0),
            script_refs=scripts.get("CharacterController", 0))
    if c.get("NavMeshAgent") or scripts.get("NavMeshAgent"):
        add("navmesh-agent", components=c.get("NavMeshAgent", 0),
            script_refs=scripts.get("NavMeshAgent", 0))
    if b2["kinematic"]:
        add("kinematic-body-2d", bodies=b2["kinematic"],
            move_position_calls=scripts.get("MovePosition", 0))
    if b2["dynamic"]:
        add("dynamic-body-2d", bodies=b2["dynamic"],
            gravity_scale_zero=b2["gravity_scale_zero"])
    if b3["kinematic"]:
        add("kinematic-body-3d", bodies=b3["kinematic"],
            move_position_calls=scripts.get("MovePosition", 0))
    if b3["dynamic"]:
        add("dynamic-body-3d", bodies=b3["dynamic"])
    if scripts.get("root_motion"):
        add("root-motion", script_refs=scripts["root_motion"])
    return hints


# ---------------------------------------------------------------- main


def fingerprint(project, excludes):
    assets = os.path.join(project, "Assets")
    tally = {"components": {}, "cameras": [], "cell_layouts": {}, "cell_sizes": {},
             "bodies_2d": {"dynamic": 0, "kinematic": 0, "static": 0,
                           "gravity_scale_zero": 0, "gravity_scale_nonzero": 0},
             "bodies_3d": {"dynamic": 0, "kinematic": 0}}
    scripts = {k: 0 for k in SCRIPT_PATTERNS}
    scanned = {"scenes": 0, "prefabs": 0, "scripts": 0, "binary_skipped": 0,
               "inputactions": 0, "sprite_metas": 0}
    ppu = {}

    for path in walk_assets(assets, excludes):
        lower = path.lower()
        rel = os.path.relpath(path, project)
        if lower.endswith(".unity") or lower.endswith(".prefab"):
            if scan_yaml(path, rel, tally):
                scanned["scenes" if lower.endswith(".unity") else "prefabs"] += 1
            else:
                scanned["binary_skipped"] += 1
        elif lower.endswith(".cs"):
            text = read_text(path)
            if text is None:
                continue
            scanned["scripts"] += 1
            for key, rx in SCRIPT_RE.items():
                found = len(rx.findall(text))
                if found:
                    scripts[key] += found
        elif lower.endswith(".inputactions"):
            scanned["inputactions"] += 1
        elif lower.endswith((".png.meta", ".psd.meta", ".psb.meta", ".aseprite.meta",
                             ".ase.meta")):
            text = read_text(path, 20000)
            if text and re.search(r"^\s*textureType:\s*8\s*$", text, re.MULTILINE):
                m = re.search(r"^\s*spritePixelsToUnits:\s*([0-9.]+)", text, re.MULTILINE)
                if m:
                    scanned["sprite_metas"] += 1
                    key = "%g" % float(m.group(1))
                    ppu[key] = ppu.get(key, 0) + 1

    settings = read_settings(project)
    packages = read_packages(project)
    cameras = tally["cameras"]
    dimension = decide_dimension(tally["components"], scripts, cameras)
    notes = []

    if not (scanned["scenes"] or scanned["prefabs"] or scanned["scripts"]):
        notes.append("nothing under Assets/ was scanned: an empty project, the wrong directory, "
                     "or every folder excluded — the verdicts below mean 'no evidence'")
    if scanned["binary_skipped"]:
        notes.append("%d scene or prefab files are not text YAML and were skipped; set Asset "
                     "Serialization to Force Text to make them readable" % scanned["binary_skipped"])
    if dimension["value"] == "mixed":
        notes.append("2D and 3D physics both present: route the controller by the body the "
                     "player object carries, and the camera by projection")
    if dimension["value"] == "3d" and any(cam["orthographic"] for cam in cameras):
        notes.append("3D physics under an orthographic camera: a 2.5D project — the controller "
                     "follows the physics, the camera follows the projection")
    major = packages["cinemachine"]["major"]
    if scripts["cinemachine_2x"] and major == 3:
        notes.append("scripts use Cinemachine 2.x names but 3.x is resolved")
    if scripts["cinemachine_3x"] and major == 2:
        notes.append("scripts use Cinemachine 3.x names but 2.x is resolved")
    if packages["source"] == "manifest.json":
        notes.append("no packages-lock.json: versions are the declared ones, not the resolved ones")
    handler = settings["active_input_handler"]
    if packages.get("inputsystem") and handler == "input-manager":
        notes.append("Input System is installed but Active Input Handling is the old Input "
                     "Manager: its devices produce no input until that setting changes")
    if scripts["legacy_input"] and handler == "input-system":
        notes.append("scripts call UnityEngine.Input while Active Input Handling is Input "
                     "System only: those calls throw InvalidOperationException at runtime")

    return {
        "project": os.path.abspath(project),
        "unity": settings["unity"],
        "dimension": dimension,
        "projection": decide_projection(cameras),
        "view": decide_view(dimension, tally, settings),
        "movement_model": {"hints": movement_hints(tally, scripts)},
        "grid": {"cell_layouts": tally["cell_layouts"], "cell_sizes": tally["cell_sizes"],
                 "tilemaps": tally["components"].get("Tilemap", 0)},
        "sprites": {"pixels_per_unit": ppu, "most_common": top(ppu, 1)},
        "input": {"active_input_handler": handler,
                  "package": packages.get("inputsystem"),
                  "inputactions_files": scanned["inputactions"],
                  "legacy_input_calls": scripts["legacy_input"],
                  "input_system_refs": scripts["input_system"]},
        "packages": packages,
        "cameras": cameras[:20],
        "components": dict(sorted(tally["components"].items())),
        "bodies_2d": tally["bodies_2d"],
        "bodies_3d": tally["bodies_3d"],
        "script_refs": {k: v for k, v in sorted(scripts.items()) if v},
        "physics_settings": {"gravity_2d": settings["gravity_2d"],
                             "gravity_3d": settings["gravity_3d"]},
        "scanned": scanned,
        "excluded": list(excludes),
        "notes": notes,
    }


def build_parser():
    p = argparse.ArgumentParser(
        prog="fingerprint.py",
        description="Print one JSON object describing a Unity project's perspective, movement "
                    "model and the packages that change API names.",
        epilog="Exit 0 fine, 2 the path is not a readable Unity project.",
    )
    p.add_argument("project", metavar="PROJECT",
                   help="the project root: the directory holding Assets/ and ProjectSettings/")
    p.add_argument("--exclude", action="append", metavar="FOLDER",
                   help="a folder name to skip anywhere under Assets/; repeatable. Giving any "
                        "replaces the default set (%s)" % ", ".join(DEFAULT_EXCLUDES))
    p.add_argument("--indent", type=int, default=None, metavar="N",
                   help="pretty-print with this indent (default: one line)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    project = os.path.expanduser(args.project)
    missing = [d for d in ("Assets", "ProjectSettings")
               if not os.path.isdir(os.path.join(project, d))]
    if missing:
        print("ERROR %s is not a Unity project root: no %s directory"
              % (project, " or ".join(missing)), file=sys.stderr)
        return 2
    excludes = tuple(args.exclude) if args.exclude else DEFAULT_EXCLUDES
    try:
        result = fingerprint(project, excludes)
    except OSError as e:
        print("ERROR could not read the project: %s" % e, file=sys.stderr)
        return 2
    if args.indent is None:
        print(json.dumps(result, separators=(",", ":"), sort_keys=False))
    else:
        print(json.dumps(result, indent=args.indent, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
