# Prefab architecture — one place where each fact lives

> Part of the `unity-3d-level` skill. When to use a prefab, a variant or a nested prefab; the
> root-and-children shape every level object takes; what an override is and how overrides rot a
> level; when unpacking is right; whether a room is a prefab or a scene; and the `PrefabUtility`
> calls an audit is built from. Worked setting: the **gate room** built from the depot kit.

A level is hundreds of copies of a few dozen things. The architecture question is always the
same: when this thing changes, how many places have to be edited? The answer has to be one.

## 1. Prefab, variant, nested

| Tool | Is | Use it for | Courier example |
|---|---|---|---|
| Prefab | The original: one asset, many instances | Anything placed more than once | `Kit_Depot_Wall_2x3`, `GateSwitch`, `Sentry` |
| Variant | A prefab that inherits another and stores only its differences | The same object with different data or dressing | `Kit_Depot_Wall_2x3_Damaged`; `Sentry_Fast` (speed and colour only) |
| Nested prefab | A prefab instance inside another prefab | A whole made of parts that also exist alone | `Room_Gate` contains walls, a `GateSwitch` and a `Gate` |
| Model prefab | What an FBX or GLB imports as; read-only | Never placed directly | Wrapped: `Kit_Depot_Wall_2x3` contains the model as its `Model` child |

- **Variant when the base should still reach it.** Fix the collision on the base wall and the
  damaged variant gets the fix. A duplicated prefab never does.
- **Nest when the part has its own life.** The switch is tuned once, in `GateSwitch`; every room
  that contains one follows.
- **Keep chains short.** A variant of a variant of a variant is three places to look for one
  value. Two levels of variant and three of nesting is where reading the hierarchy stops being
  quick.

## 2. The shape — gameplay root, visual child, collision child

```
GateSwitch                 root: scale (1,1,1). Scripts, Rigidbody, triggers, the layer gameplay uses
├── Model                  the imported mesh, its materials, its LOD group. Scaled and offset HERE
├── Collision              solid proxies on the World layer — reference/collision-proxies.md
└── Interact               a trigger volume, when the object has one
```

| Rule | Because |
|---|---|
| The root is never scaled | Colliders, joints and child positions all inherit it; a scaled root makes a sphere collider the wrong shape — `unity-physics-3d` §5 |
| Art is replaced by swapping the `Model` child | Scripts, colliders and every scene reference to the root survive the swap — `unity-3d-models` → `reference/import-and-decimate.md` |
| Scripts reference children through serialised fields, not `transform.Find("Model")` | A rename is then a compile-time non-event instead of a null at runtime |
| The pivot is the root's origin | For a kit piece that is the floor corner — `reference/modular-kit.md`; for a prop, the base centre |
| A kit piece carries no gameplay | Geometry and collision only. The thing with behaviour is a prefab that contains it |

The greybox follows the same shape from the first day: a `GateSwitch` prefab whose `Model` is a
green cube is replaced, child for child, when the art exists.

## 3. Overrides, and how they rot

An override is a difference between an instance and its asset, stored in the scene (or in the
outer prefab). Unity records five kinds: a changed property, an added component, a removed
component, an added child and a removed child. On every instance it also records the root's
position, rotation, name and sibling order; it calls those **default overrides** and leaves
them out of the Overrides dropdown.

The rot is this: **an overridden value no longer follows the asset.** Fix the wall's material
in the prefab and the forty instances that someone tinted by hand keep the old one. The level
then holds three kinds of wall that look like one.

| Override | Verdict |
|---|---|
| Root position and rotation | What placing an instance is |
| A serialised field designed to vary: the switch's reference to *its* gate, a sentry's patrol points | Intended. The field exists to be overridden |
| Root **scale** on a kit piece | Rot. The piece is off the grid; the collider scaled with it |
| Material, layer, static flags, enabled state | Rot unless it is a variant's job. Make the variant |
| An added child (a light, a decal, a collider) | Rot. It belongs in the prefab, in a variant, or beside the instance |
| A removed component or child | Rot. The asset's next change to it is silently skipped |

`resources/Editor/PrefabOverrideAudit.cs` lists the instances in the open scene that carry
anything beyond default overrides:

```csharp
string json = PrefabOverrideAudit.Audit();
// {"scene":"Assets/Scenes/GateRoom.unity","instances":212,"withOverrides":9,"scaled":3,"ok":false,
//  "totals":{"added-object":2,"property":31},
//  "overridden":[{"path":"Room/Kit_Depot_Wall_2x3 (14)","asset":"Assets/Kit/Depot/Kit_Depot_Wall_2x3.prefab",
//                 "assetType":"Regular","rootScaled":true,"kinds":{"property":3},
//                 "properties":["Transform.m_LocalScale.x", …],"added":[],"removed":[]}]}
```

Headless: `-executeMethod UnityDev.Cli.BatchAudit.Run -audit PrefabOverrideAudit -scene
Assets/Scenes/GateRoom.unity -out Logs/overrides.json` exits 0 on `"ok": true`, 2 on false
(`unity-cli` → `reference/batch-audit.md`).

Each row gets one of three outcomes — never "leave it":

| Outcome | When | How |
|---|---|---|
| Apply | Every instance should have it | Overrides dropdown ▸ Apply, choosing *which* prefab in a nested or variant chain receives it; `PrefabUtility.ApplyPropertyOverride(property, assetPath, InteractionMode.UserAction)` |
| Revert | It was an accident | Overrides ▸ Revert; `PrefabUtility.RevertPropertyOverride(property, InteractionMode.UserAction)`, or `RevertPrefabInstance(go, InteractionMode.UserAction)` for all of them |
| Make it a variant or a field | Some instances should differ on purpose | A variant for dressing; a serialised field for data |

`"scaled"` counts instances whose root scale is overridden; on a kit scene the target is zero.
Reverting changes the scene: list the rows, agree them, then revert — the audit itself writes
nothing.

## 4. Unpacking

Unpacking cuts an instance from its asset for good. It is right in exactly one case: the
object is becoming something that is no longer that prefab — a unique set piece hand-built from
a wall and never repeated.

| Mode | Leaves |
|---|---|
| Unpack (`PrefabUnpackMode.OutermostRoot`) | The outer prefab's objects become plain; nested instances inside stay connected |
| Unpack Completely (`PrefabUnpackMode.Completely`) | Everything plain, all the way down |

`PrefabUtility.UnpackPrefabInstance(go, PrefabUnpackMode.OutermostRoot, InteractionMode.UserAction)`.

- Never unpack to get rid of a blue override line, to delete a child, or because an edit was
  refused. Each of those has an answer in §3, and the unpacked copy stops receiving every later
  fix to the kit.
- Prefer the outermost mode: a room unpacked that way still has live walls.
- An unpacked kit piece is invisible to §3's audit. Find them by name:
  objects called `Kit_…` for which `PrefabUtility.IsPartOfPrefabInstance` is false.

## 5. A room — prefab or scene?

| | Room as a nested prefab | Room as a scene |
|---|---|---|
| Good for | Rooms that repeat, rooms stitched or generated at runtime, small arenas | A unique, large or heavily lit space; several people working at once |
| Baked lighting | Lightmaps belong to a scene, not to a prefab: an instanced room is lit by realtime lights and probes, or baked again in each scene that holds it — `unity-lighting` → `reference/bake-setup.md` | Baked once with the scene |
| Occlusion data | Baked per scene | Baked with the scene — `unity-scene-optimisation` → `reference/occlusion.md` |
| NavMesh | A `NavMeshSurface` on the room root with its data asset travels with the prefab | One surface for the scene — `unity-navigation` → `reference/recipes.md` |
| References | Anything inside can reference anything else inside | No reference crosses a scene boundary; connect at load through a registry or an event |
| Loading | `Instantiate` | `SceneManager.LoadSceneAsync(name, LoadSceneMode.Additive)`, with the runner and the camera in a scene that stays loaded |

Decide once: **kit pieces and interactive objects are always prefabs; a room that appears once
and is lit by a bake is a scene; a room that repeats is a prefab.** The gate room, used once,
is a scene built from kit prefabs with one `GateSwitch` and one `Gate` instance in it.

## 6. `PrefabUtility` for audits

| Question | Call |
|---|---|
| Is this object part of an instance? | `PrefabUtility.IsPartOfPrefabInstance(obj)` |
| Is it the root of the instance a level designer placed? | `PrefabUtility.IsOutermostPrefabInstanceRoot(go)` |
| Which root owns this child? | `PrefabUtility.GetNearestPrefabInstanceRoot(obj)` · `GetOutermostPrefabInstanceRoot(obj)` |
| Which asset is it an instance of? | `PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(obj)` |
| What is the same object in the asset? | `PrefabUtility.GetCorrespondingObjectFromSource(obj)`; `…FromOriginalSource` follows variants to the base |
| Regular, variant or model? | `PrefabUtility.GetPrefabAssetType(obj)` → `PrefabAssetType.Regular` · `Variant` · `Model` · `MissingAsset` · `NotAPrefab` |
| Is the asset still there? | `PrefabUtility.GetPrefabInstanceStatus(obj)` → `PrefabInstanceStatus.MissingAsset` |
| Any overrides at all? | `PrefabUtility.HasPrefabInstanceAnyOverrides(root, false)` — `false` leaves default overrides out |
| Which properties? | `PrefabUtility.GetPropertyModifications(root)`, skipping those where `PrefabUtility.IsDefaultOverride(mod)` |
| Which structure? | `GetAddedComponents(root)` · `GetRemovedComponents(root)` · `GetAddedGameObjects(root)` · `GetRemovedGameObjects(root)` |
| Edit an asset from code | `LoadPrefabContents(path)` → edit → `SaveAsPrefabAsset(root, path)` → `UnloadPrefabContents(root)` |

```csharp
// Every placed instance of one kit piece in the open scene, however deeply nested its parent.
static List<GameObject> InstancesOf(string assetPath)
{
    var found = new List<GameObject>();
    foreach (GameObject root in SceneManager.GetActiveScene().GetRootGameObjects())
        foreach (Transform t in root.GetComponentsInChildren<Transform>(true))
            if (PrefabUtility.IsAnyPrefabInstanceRoot(t.gameObject) &&
                PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(t.gameObject) == assetPath)
                found.Add(t.gameObject);
    return found;
}
```

For a one-off question — "what uses this prefab" — a search query is quicker than a script:
`unity-search` → `reference/query-patterns.md`.

## Traps

- **Dragging the FBX into the scene.** The instance is of the model prefab: nothing can be added
  to its asset, so every collider and script becomes an override. Wrap it first.
- **Duplicating a prefab to make "the red one".** Two assets to fix from now on. Create a
  variant (right-click the prefab ▸ Create ▸ Prefab Variant).
- **Applying an override "to the prefab" inside a nested chain.** The dropdown offers each level;
  the innermost changes every room in the game, the outermost only this room.
- **A prefab that needs a scene object.** It cannot hold the reference. The scene instance
  overrides one serialised field (intended), or the object finds its partner at start through
  a registry.
- **Scaling an instance to fit a gap.** It reads as a `property` override and counts under
  `scaled`. The gap is a kit fault — `reference/modular-kit.md` §7.
- **Editing in Prefab Mode with Auto Save on and the wrong prefab open.** Check the breadcrumb:
  entering a nested instance *in context* edits the inner asset for every user of it.

## Where each need is answered

| Need | Answer |
|---|---|
| Kit pieces, their pivot and grid | `reference/modular-kit.md` |
| The `Collision` child and its layer | `reference/collision-proxies.md` |
| Wiring an imported model into the `Model` child | `unity-3d-models` → `reference/import-and-decimate.md` |
| Colliders and hit boxes on a rigged character prefab | `unity-rigged-character` → `reference/gameplay-rig.md` |
| Lightmaps, probes and prefab rooms | `unity-lighting` → `reference/probes.md` |
| Static flags, batching and what breaks it | `unity-scene-optimisation` → `reference/batching.md` |
| Baking a NavMesh for a room placed at runtime | `unity-navigation` → `reference/recipes.md` |
| Driving these audits from the command line | `unity-cli` → `reference/batch-audit.md` |
