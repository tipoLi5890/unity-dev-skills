# Greybox — blocking out from a metrics sheet

> Part of the `unity-3d-level` skill. How a room is built from numbers before any art exists:
> the sheet, the blocks (primitives with no package, or ProBuilder shapes from script), the
> colour code, why the greybox's colliders are the level's colliders, and the journey that
> proves the room before a single prop is modelled. Worked setting: the **gate room** — a
> corridor, a door, a room with a step, a ramp, a jump gap, a switch, a gate and a sentry post.

A greybox is not a rough draft of the art. It is the level's collision and its measurements,
finished, with the art missing. Art that arrives later is fitted to it; it is never fitted to
the art.

## 1. The metrics sheet

Written before the first cube, one row per number, each derived from the body or the jump —
never from a real building. `W` is the body's width (0.8), `B` its height (1.8).

| Number | Gate room | Derived from | Checked by |
|---|---|---|---|
| Unit | 1 unit = 1 metre | Physics, lighting and imported models all assume it | A 1.8 capsule standing in the room |
| Body | height 1.8, radius 0.4, step offset 0.3, slope limit 45° | The controller | — |
| Door | 1.2 wide × 2.2 high, clear | `1.5·W` wide; `B + 0.4` high so the lintel is off the head | `--door 1.2` |
| Corridor | 2.4 clear | `3·W`: two bodies pass with room between. In third person, at least the camera's follow distance instead — 4.0 | Journey; the camera never ends a frame behind a wall |
| Step | 0.3 | Equal to the step offset. Taller is a ledge and belongs in the jump rows | `--step 0.3 --step-offset 0.3` |
| Ramp | 30° or less | 15° under the slope limit, and under the 45° a NavMesh bake accepts by default — neither the runner nor the sentry stalls on a ramp built a degree out | Journey; `grounded` holds on the ramp |
| Ledge | 1.0 | Under 90% of the apex (1.2 → 1.08) | `--height 1`, in a run of its own |
| Jump gap | 3.0 | Under 90% of level reach with the controller's fall multiplier and coyote time (3.679 → 3.311) | `--gap 3` |
| Ceiling | 3.0 | At least `B + apex` (3.0), or the head ends every jump early | `--ceiling 3` |

The jump rows come from the controller's numbers through `unity-gameplay` →
`scripts/level_metrics.py`; the formulas are in `unity-gameplay` → `reference/level-metrics.md`.

```bash
JUMP="--apex 1.2 --time-to-apex 0.35 --run-speed 5 --fall-multiplier 1.5 --coyote 0.1 \
      --integrator exact --body-width 0.8 --body-height 1.8 --step-offset 0.3"
python3 scripts/level_metrics.py $JUMP --step 0.3 --door 1.2 --ceiling 3.0 --gap 3
python3 scripts/level_metrics.py $JUMP --height 1      # the ledge, alone
```

`--integrator exact` matches the `unity-3d-controller` controllers, which move by the mean
velocity. The ledge runs alone because `--height` beside `--gap` means a gap to a landing that
much higher — a 3.0 gap up onto a 1.0 ledge is out of reach (2.833). Exit 0 and
`"verdict":"ok"` is the sheet holding; exit 1 names the row that left reach. Re-run it whenever
a jump number moves — the greybox is rebuilt from the sheet, not nudged.

Every number is a **clear** dimension, measured between collider faces: the door is 1.2 between
its jambs, the corridor 2.4 between its walls. Wall thickness is added outside the number.

## 2. Blocks from primitives — no package

`GameObject.CreatePrimitive(PrimitiveType.Cube)` gives a unit cube with a `BoxCollider`; its
`localScale` is its size in metres. That is the whole toolkit:

| Block | Built as |
|---|---|
| Floor, wall, step, ledge, pedestal | A cube at `centre`, scaled to `size` |
| A wall with a door | Two cubes either side of the opening and a lintel cube above it |
| Ramp | A cube 0.2 thick, as long as the slope's hypotenuse, rotated `−angle` about X, placed so its **top face** runs from the low edge to the high edge. Both ends sink into their neighbours, so no lip is left for a foot to catch |
| Marker (spawn, hazard pad, sentry post) | A cube 0.02 high with its collider removed |
| Ruler | A capsule 1.8 high, radius 0.4, no collider, left standing by the door for the life of the level |

A non-uniformly scaled cube is safe: a `BoxCollider` follows the scale exactly. A scaled sphere
or capsule collider does not — `unity-physics-3d` §5.

`resources/Editor/GreyboxBuilder.cs` builds the whole gate room this way from one
`GreyboxMetrics` struct whose defaults are the sheet above:

```csharp
GreyboxMetrics m = GreyboxMetrics.GateRoom;
m.jumpGap = 2.5f;                                   // the jump was shortened
Debug.Log(GreyboxBuilder.Plan(m));                  // what it would create, and every WARNING
GameObject room = GreyboxBuilder.Build(m);          // after the plan has been read
```

`Plan` lists the blocks and prints a `WARNING` line for each number that disagrees with the
body (a door under `1.5·W`, a step over the step offset, a ramp within 10° of the slope limit).
The menu command `Tools/Unity Dev/3D Level/Build Gate-Room Greybox` shows the plan and waits.
`GreyboxBuilder.Layout(m)` returns the same blocks as data — a list of name, function, shape,
centre and size — for a tool that wants to build them some other way.

## 3. Blocks from ProBuilder — when the shape will be edited

ProBuilder earns its place when a block is going to be pushed, cut or extruded in the Scene
view. For boxes that stay boxes it adds nothing over a cube.

| Call (`UnityEngine.ProBuilder`) | Gives | Note |
|---|---|---|
| `ShapeGenerator.GenerateCube(PivotLocation.Center, size)` | A box of `size` | Size is baked into the vertices; the transform keeps scale 1 |
| `ShapeGenerator.GenerateStair(PivotLocation.Center, size, steps, buildSides)` | Stairs filling a box of `size`, climbing towards +Z | Riser = `size.y / steps`; keep it at or under 0.3: a 1.0 rise is 4 steps of 0.25 |
| `ShapeGenerator.GenerateDoor(pivot, totalWidth, totalHeight, ledgeHeight, legWidth, depth)` | A wall section with an opening | Opening = `totalWidth − 2·legWidth` wide, `totalHeight − ledgeHeight` high: `(2, 3, 0.8, 0.4, 0.2)` is the 1.2 × 2.2 door |
| `ShapeGenerator.GeneratePrism(pivot, size)` | A triangular prism with the ridge on top | A roof, not a ramp |
| `ProBuilderMesh.Create(positions, faces)` | Any shape from vertices and `Face` index lists | The wedge ramp in the builder is five faces made this way |
| `mesh.ToMesh(); mesh.Refresh();` | Writes the `Mesh` and rebuilds normals, UVs and the `MeshCollider`'s mesh | Call both after any edit from code |
| `mesh.Optimize()` (`UnityEditor.ProBuilder`) | Collapses shared vertices; builds lightmap UVs when the object is Contribute GI and ProBuilder's Auto Lightmap UVs preference is on, or when called as `Optimize(true)` | Editor only; last |

Three things the generator does not do, each a silent fault:

- **No material.** The generator leaves the renderer's material unset; assign
  `BuiltinMaterials.defaultMaterial` or the function's colour before the block is shown.
- **No collider.** Add a `MeshCollider` *before* `Refresh()`, which hands it the mesh. Prefer it
  to a `BoxCollider` on anything that will be edited: the box keeps the size the block had
  before the edit.
- **`PivotLocation.FirstVertex` is the shape's first vertex, not a named corner** — on stairs it
  is the bottom corner on +X at the foot. Use `Center` and position by the centre.

`resources/Editor/GreyboxBuilderProBuilder.cs` is the same room from these calls. It is a
separate file on purpose: `GreyboxBuilder.cs` then compiles in a project without the package,
and the ProBuilder file is simply left out. It needs an Editor asmdef that references
`Unity.ProBuilder` and `Unity.ProBuilder.Editor`.

## 4. Colour by function

One material per function, so a screenshot of the room reads without labels and a missing
collider is visible as a colour in the wrong place.

| Function | Colour | Collider |
|---|---|---|
| Floor — walkable | Mid grey | Yes |
| Wall — blocks | Dark grey | Yes |
| Climb — step, ramp, stairs | Blue | Yes |
| Jump — ledges either side of a gap | Orange | Yes |
| Gate — what a switch removes | Yellow | Yes |
| Interact — switch, pickup dispenser | Green | Yes |
| Hazard | Red | No: a marker; the trigger is the game's |
| Sentry — post, patrol point | Purple | No |
| Marker — spawn, ruler | White | No |

The builder creates these materials inside the scene from the active pipeline's default
material, so they light correctly on any pipeline and no asset is written. Keep the code to
nine colours; a tenth means a function nobody has named.

## 5. The greybox's colliders are the level's colliders

Until art lands, the blocks are what the runner stands on, what the camera collides with and
what the NavMesh is baked from. So:

- Solid blocks sit on one layer, `World`; markers have no collider at all. Every ground check,
  camera boom and line-of-sight test names that one layer.
- When art replaces a block, the block's collider is replaced by a proxy on the same layer —
  `reference/collision-proxies.md` — in the same change. Never both, never neither.
- Keep the greybox root in the scene, disabled, until the last block has been replaced. It is
  the measured reference the art is checked against.
- A gap or a ledge is measured between collider bounds, never between pivots or by eye.

## 6. Playtest with a journey before art

`templates/GreyboxJourneyTest.cs` walks a body-sized `CharacterController` through a room
built at the sheet's numbers. It builds its own blocks and its own minimal walker, so it runs
in an empty project that has the harness and the input struct.

| Test | Asserts |
|---|---|
| `Walk_PassesTheDoor_ClimbsTheStepAndTheRamp_AndArrives` | The runner reaches the ledge; it stands on top of it; `JourneyAsserts.NeverInside` on the block layer reports nothing; planar speed never passes the run speed; it is never off the ground for more than 5 samples |
| `Door_AdmitsOneAndAHalfBodyWidths` | A capsule 1.5 bodies wide stood in the doorway overlaps nothing — the door measured between colliders |

Show the gate can fail before trusting it: `GREYBOX_JOURNEY_BREAK=door` (0.7 wide), `=step`
(1.0 high) and `=ramp` (60°) each stop the walk, and the failure names where it stopped.

Then point the same asserts at the real room: replace the test's blocks with the scene the
builder made and its walker with the game's controller (`unity-3d-controller`). The jump gap
is proven by measurement, not by walking — `unity-gameplay` → `scripts/jump_report.py` against
a journey that jumps it.

## 7. Done when

- The sheet exists, and `level_metrics.py` exits 0 on its rows.
- Every block in the scene came from the sheet; none was scaled by hand afterwards.
- Solid blocks are on `World`; markers have no collider; the ruler capsule is still standing.
- The walk journey passes, and each break switch has been seen to fail it.
- A person has walked the room once and agreed it reads — the journey proves it is passable,
  not that it is a good room.

## Traps

- **Real-world dimensions.** A 0.9 m door and a 1.2 m corridor are right for a building and
  wrong for a capsule with a camera behind it. Build to the sheet.
- **Scaling a finished block to "make it fit".** The sheet and the scene now disagree, and the
  next rebuild puts the old size back. Change the number, rebuild.
- **A ramp built as a rotated cube resting on the floor.** Its lower edge is a 0.2 lip. Place
  the top face on the slope line and let the slab sink.
- **A ramp steeper than the sheet "because it looks fine".** At 44° it works on a level frame
  and stalls the frame the capsule meets it at an angle.
- **Greybox on Default.** Every query then also hits props, pickups and the runner. Create the
  `World` layer first; the builder says when it is missing.
- **Deleting the greybox the day the first kit piece arrives.** Half the room then has no
  collision. Replace block by block.

## Where each need is answered

| Need | Answer |
|---|---|
| Reach formulas, the reach table, the level check | `unity-gameplay` → `reference/level-metrics.md` |
| The capsule numbers, grounding and slopes | `unity-3d-controller` → `reference/grounding-and-slopes.md` |
| The jump the gap is cut for | `unity-3d-controller` → `reference/jump-and-air.md` |
| Corridor width against a camera boom | `unity-camera` → `reference/follow-3d.md` |
| Journeys, the never-inside invariant, break switches | `unity-play-harness` → `reference/journeys.md` |
| The scripted input the walker reads | `unity-input` → `reference/reading-input.md` |
| Replacing blocks with kit pieces on the same grid | `reference/modular-kit.md` |
| Replacing block colliders with proxies; the layer scheme | `reference/collision-proxies.md` |
| What the NavMesh bake collects from the greybox | `unity-navigation` → `reference/recipes.md` |
| Lighting the greybox so depth reads | `unity-lighting` → `reference/light-modes.md` |
