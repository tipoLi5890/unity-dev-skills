"""bcr_import_prep.py — import a generated GLB and make it fit to rig.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

An image-to-3D GLB arrives as one mesh under import helpers, centred on its
bounding box, about one unit tall, with every UV seam splitting a vertex. This
puts it in a named collection as one object whose transform is identity, origin
at the base of the feet, at a real height, welded by position.

    result = bcr_import_prep.run({
        "glb": "/abs/path/runner.glb", "name": "Runner", "collection": "Character",
        "height": 1.2,              # metres; omit to keep the file's size
        "location": [0, 0, 0],
        "weld_distance": 1e-5,      # None skips the weld (a prop that will not be skinned)
        "normal_strength": 0.5,     # None leaves the material alone
        "backface_culling": True,   # the mesh is a double shell
    })

Calling it again with the same `name` reuses the object and imports nothing.

Returns `vertices_before`, `vertices_after`, `islands`, `extents`, `height`,
`custom_normals_before`/`_after`. The weld keeps every face and every island:
UVs live on face corners, so seams survive it. Gates: one_mesh, identity
transform, origin_at_base, weld_kept_faces.
"""
from __future__ import annotations

import bmesh
import bpy
from mathutils import Matrix, Vector

import bcr_common as C


def _bounds(mesh):
    xs, ys, zs = zip(*((v.co.x, v.co.y, v.co.z) for v in mesh.vertices))
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    scene = C.scene_of(params)
    name = params["name"]
    col = C.collection(params["collection"], scene)
    obj = bpy.data.objects.get(name)
    reused = obj is not None
    stats = {}

    if not reused:
        bpy.ops.import_scene.gltf(filepath=params["glb"])
        new = tracker.new("objects")
        meshes = [o for o in new if o.type == 'MESH']
        if len(meshes) != 1:
            raise ValueError(f"expected one mesh in the file, found {len(meshes)}")
        obj = meshes[0]
        mesh = obj.data
        world = obj.matrix_world.copy()
        obj.parent = None
        for other in new:
            if other is not obj:
                bpy.data.objects.remove(other)
        mesh.transform(world)                     # bake the importer's axis conversion
        obj.matrix_world = Matrix.Identity(4)
        C.move_to_collection(obj, col)
        obj.name = mesh.name = name
        for index, material in enumerate(mesh.materials):
            material.name = f"{name}Mat" if index == 0 else f"{name}Mat{index}"

        low, high = _bounds(mesh)
        mesh.transform(Matrix.Translation(-Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))))
        if params.get("height"):
            mesh.transform(Matrix.Scale(params["height"] / (high.z - low.z), 4))

        stats["vertices_before"] = len(mesh.vertices)
        stats["faces_before"] = len(mesh.polygons)
        stats["custom_normals_before"] = mesh.has_custom_normals
        if params.get("weld_distance", 1e-5) is not None:
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=params.get("weld_distance", 1e-5))
            bm.to_mesh(mesh)
            bm.free()
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            mesh.update()

        for material in mesh.materials:
            material.use_backface_culling = params.get("backface_culling", True)
            strength = params.get("normal_strength", 0.5)
            node = C.node_of(material.node_tree, "ShaderNodeNormalMap") if material.node_tree else None
            if strength is not None and node is not None:
                node.inputs["Strength"].default_value = strength
        obj.location = params.get("location", (0, 0, 0))

    mesh = obj.data
    low, high = _bounds(mesh)
    sizes = C.islands(mesh)
    stats.setdefault("vertices_before", len(mesh.vertices))
    stats.setdefault("faces_before", len(mesh.polygons))
    scale_ok = all(abs(s - 1) < 1e-6 for s in obj.scale) and all(abs(a) < 1e-6 for a in obj.rotation_euler)
    gates = [
        C.gate("one_mesh", obj.type, "MESH", obj.type == 'MESH'),
        C.gate("identity_scale_rotation", [list(obj.scale), list(obj.rotation_euler)], "scale 1, rotation 0", scale_ok),
        C.gate("origin_at_base", low.z, "|z| < 1e-4", abs(low.z) < 1e-4),
        C.gate("weld_kept_faces", len(mesh.polygons), stats["faces_before"], len(mesh.polygons) == stats["faces_before"]),
    ]
    return C.report(
        params, gates, object=obj.name, reused=reused,
        vertices_before=stats["vertices_before"], vertices_after=len(mesh.vertices),
        faces=len(mesh.polygons), islands=sizes[:8], island_count=len(sizes),
        extents=high - low, height=high.z - low.z,
        custom_normals_before=stats.get("custom_normals_before"), custom_normals_after=mesh.has_custom_normals,
        materials=[m.name for m in mesh.materials],
    )
