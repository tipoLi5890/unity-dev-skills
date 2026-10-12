# Scene discipline — working inside a file that belongs to someone else

> Part of the `blender-character-rig` skill. Reaching Blender and the shape of a result are in
> `reference/mcp-session.md`.

The Blender on the other end of the connection has the user's file open, possibly unsaved. Every
rule here follows from one position: **the work is additive, repeatable and reported.**

## Additive work

| Instead of | Do |
|---|---|
| Putting new objects in the user's collections | create one collection for the work (`Character`) and link everything new there |
| Deleting an object that is in the way | hide it in the viewport **and** from the render; restore both afterwards |
| Editing the user's camera, lights or world | add a camera, a light, a world of your own and point the scene at it for the check |
| Applying, joining or re-parenting what the user made | leave it; ask when the task cannot proceed without it |
| Saving | never unasked — report the save state instead |

A camera of your own, aimed at the character's middle, for every check render in this skill:

```python
import bpy
from mathutils import Vector
col = bpy.data.collections["Character"]
cam = bpy.data.objects.get("PreviewCamera")
if cam is None:
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    col.objects.link(cam)
cam.location = (-3.0, -2.2, 1.0)                 # the side the prop is on, a little in front
aim = Vector((0.0, -0.3, 0.7))
cam.rotation_euler = (aim - cam.location).to_track_quat('-Z', 'Y').to_euler()
result = {"camera": cam.name}
```

`bcr_preview` renders through it when `camera` names it and puts the scene's own camera back.
Without `camera` it renders through the scene's camera.

- **A World left with zero users is purged on save.** Pointing the scene at a new world orphans the
  old one: give the old world a fake user before switching, and switch back when the check is over.
- **Check the user count before editing shared data.** A mesh or material used by two objects
  changes on both.
- **Removing an object does not remove its mesh, material or images.** Remove the data the work
  created too, and each datablock only when it has zero users — an image shared with something of
  the user's stays.
- **Three visibility states are independent**: hidden in the viewport, excluded from the view
  layer, disabled for render. An object that an operator skips or a render omits is in one of them.

## Repeatable calls

A step that fails half-way is run again, so every call has to be safe to run twice.

**Rollback.** Each `bcr_*` `run` records which datablocks exist before it starts. When it raises, it
returns Blender to object mode, removes every datablock that appeared during the call — objects
first, then the data they used — and re-raises with the module name and
`(rolled back: {...})` in the text. A successful call lists the same thing under `created`.

- **Edits to datablocks that already existed are not undone.** A call that raises after changing a
  material setting or a pose leaves that change in place; each module's docstring names what it
  edits.
- Hand-written code sent through the code tool has no such net. Create inside a `try`, remove in
  the `except`, or do the work through a module.

**Idempotent by name.**

| Call | Run again with the same name |
|---|---|
| `bcr_import_prep` | reuses the object, imports nothing, returns `reused: true` |
| `bcr_armature` | rebuilds the bones of that armature in place |
| `bcr_attach` | returns `reused: true` |
| `bcr_pose` op `key` | replaces the action of that name |
| `bcr_preview` | deletes the files in the range, then renders them again |

Names are therefore the state: `Runner`, `RunnerRig`, `Mallet`, `GateLatchSwing`. Blender renames
a clash to `.001` without saying so — read the name back from the result (`object`, `created`)
instead of assuming the one that was asked for.

## Names that change with the UI language

Default node names are translated with the interface. In a non-English UI
`material.node_tree.nodes["Principled BSDF"]` raises `KeyError: 'Principled BSDF'`.

```python
import bcr_common
bsdf = bcr_common.node_of(material.node_tree, "ShaderNodeBsdfPrincipled")
bsdf.inputs["Roughness"].default_value = 0.9      # socket names stay English
```

Find nodes by `bl_idname` — `ShaderNodeBsdfPrincipled`, `ShaderNodeBackground`,
`ShaderNodeNormalMap`. `node_of` returns `None` when the tree has no such node: test for it. The
same caution covers anything else Blender names by default; look a thing up by type or by a name the
work assigned, not by a default name.

## Operators that are worth their side effects

Operators depend on the mode, the selection and the active object, and change all three as they
run. The data API and `bmesh` do not, so they are the default: a weld is `bmesh.ops.remove_doubles`
on a `bmesh` built from the mesh, a transform is `mesh.transform`, a weight is a vertex-group call.

Operators are kept for what only an operator does:

| Operator use | Bookkeeping |
|---|---|
| glTF import | find what arrived by diffing `bpy.data.objects` before and after, not by reading the selection |
| FBX export and import | import into a second scene; set the options explicitly rather than trusting defaults |
| Edit mode, to create bones | deselect, make the armature active and selected, enter edit mode, leave it, restore the previous selection and active object |
| Rendering | pass the scene by name; save and restore path, resolution percentage, format, camera, frame |

After changing transforms or parents, update the view layer before reading a world matrix; a
matrix read too early is the old one.

## A second scene for a check

A re-import or a comparison has no place in the user's scene.

1. Create a scene, keep a reference to the window's current one.
2. Set `window.scene` to the new scene while working: objects outside the active view layer cannot
   be selected, edited in edit mode or evaluated.
3. Do the check; collect numbers, not objects.
4. Set `window.scene` back — in a `finally`, so a raise does not leave the user looking at an
   empty scene.
5. Remove the scene and what was imported into it, data included.

`bcr_import_prep`, `bcr_armature`, `bcr_pose`, `bcr_probe` and `bcr_preview` take an optional
`scene` name and otherwise use the scene in the window. `scene` picks whose settings are read
and written; the scene must still be the window's for `bcr_armature` and `bcr_probe`.

## What to report

Every non-additive change, stated plainly at the end of the task, with its state now:

| Changed | Say |
|---|---|
| Active camera | which it was, which it is, whether it was put back |
| World | the same, and that the old one holds a fake user |
| Render settings | engine, resolution, percentage, output path, format |
| Frame range, fps | old and new — keying an action sets both |
| Window scene | that it is back on the user's scene |
| Hidden objects | which, and in which of viewport and render |
| The file | saved or not, and that nothing was saved unasked |

Next to it: the collection the work lives in, the names created, and the files written outside
Blender. A change that is not in this report did not happen with the user's knowledge.
