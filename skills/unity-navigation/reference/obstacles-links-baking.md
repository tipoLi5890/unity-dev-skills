# Obstacles, links, areas and baking

Moved out of SKILL.md, which keeps §1–§3 (inspect, the agent moves, who owns the transform) and §7 (verify); section numbers here continue that order.

## 4. Obstacles: carve or avoid

`NavMeshObstacle` has two very different modes and the wrong one is expensive rather than broken.

| The obstacle | Carve | Why |
|---|---|---|
| Moving vehicle, another character | **Off** | Local avoidance handles it; carving a moving object re-cuts the mesh continuously |
| Stationary crate, barrel | **On** | Agents path around it globally; the cut is recomputed only when it moves |
| Large slow mover (a tank) | **On**, Carve Only Stationary **off** | Re-carves past a movement threshold |
| Many small scattered props | **Off** | Avoidance is far cheaper than many cuts |
| Anything that fully blocks a corridor | **On** | Without a carve, agents keep planning through it and jam at the mouth |

The rule underneath: **carving changes the map; avoidance changes the walk.** If the agent needs
to find a different route, it must be a carve. If it just needs to step aside, it must not be.

Avoidance has two dials: **`avoidancePriority` is 0–99 and the lower number wins** — the agent
that must not be shoved off its lane gets the low one — and **Quality**, the first thing to drop
when a crowd costs frames (`None` switches avoidance off).

**An agent walking through a wall** is almost always that the wall was not in the bake — it was
added later, is on a layer the surface does not collect, or has no collider at all. Navigation does
not consult PhysX at runtime; a collider that was absent at bake time does not exist for pathing.
That is the boundary with `unity-physics-3d`: it will still *collide*, it just will not be *pathed
around*.

## 5. Links, areas and costs

**`NavMeshLink`** connects surfaces that do not touch — stairs between platforms, a jump, a ladder,
a doorway between two separately-baked areas. Width `0` makes it a point-to-point line; positive
gives it a span. It can be one-way (`Bidirectional` off), and it can carry a cost modifier so agents
treat it as a last resort — **`costModifier`**; `costOverride` is deprecated in its favour.

With `autoTraverseOffMeshLink` off you own the crossing, and **forgetting the final
`agent.CompleteOffMeshLink()` leaves the agent stuck on the link forever** — a very common hang.
The sequence, and why `OffMeshLink` is the legacy component:
[`reference/agent-api.md`](agent-api.md) §4.

**Areas and costs** express preference, not possibility. A high-cost "Water" area is still
walkable; agents route around it when a cheaper path exists and through it when one does not.
Per-agent overrides let one character type ignore what another avoids:

```csharp
agent.SetAreaCost(3, 5.0f);     // area index 3 costs 5× for this agent only
```

The built-in area indices, the `distance × cost` arithmetic, `areaMask` and `agent.Raycast`:
[`reference/recipes.md`](recipes.md) §8.

`NavMeshModifier` overrides area or walkability per GameObject; `NavMeshModifierVolume` does it for
a region of space regardless of what is in it — the one for "this doorway is off-limits" where no
object exists to mark. **Where volumes overlap, the highest area index wins, and Not Walkable wins
outright**, so a blocking volume is safe to drop over a hazard (`reference/recipes.md` §7).
Confirm the precedence with a two-volume test bake before a level depends on it.

## 6. Baking, including at runtime

`NavMeshSurface.BuildNavMesh()` bakes; `UpdateNavMesh(navMeshData)` updates incrementally and is
the one for streamed or procedurally-generated levels. Bake quality is a voxelisation: **voxel
size trades accuracy for bake time and memory**.

A surface collects geometry by render meshes or by physics colliders, filtered by layer. Get
that filter wrong and the mesh is either missing your level or full of decorative props.

The knobs and what each one actually costs — voxels per agent radius (**3** by default, 1–2 for
open ground, 4–6 for tight interiors, beyond 8 pointless), **Override Tile Size 64–128** when
many obstacles carve, Minimum Region Area for the litter of unreachable islands, Build Height
Mesh for stairs, and the agent-type **Drop Height / Jump Distance** that decide what
Generate Links can generate — are in [`reference/recipes.md`](recipes.md) §6–§7, with
the runtime baker.

> **A coarse voxel does not produce a broken mesh, it produces no mesh.** Large relative to the
> agent radius, it rounds a doorway shut during rasterisation, so that surface is never generated.
> The report is "the agent refuses to use the door", and nothing about the agent is wrong.
