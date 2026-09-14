# Query patterns — filters, references, scene objects, phrases

> Part of the `unity-search` skill. The two-line answer format and the rule about opening the
> window live in `SKILL.md`; this file is the vocabulary.

One accurate query beats a long speculative one. Unity Search treats an unknown filter as an
ordinary word rather than an error, so a malformed query comes back empty and looks exactly like
"there are none". Prefer a filter you can name over one you are guessing at.

---

## 1. Asset filters

Asset type names are **lowercase** here; scene component types are Unity type names (§3).

| Wanted | Query |
|---|---|
| Every material | `t:material` |
| Every texture | `t:texture` |
| Materials *and* textures | `t:[material, texture]` |
| Prefabs, scenes, scripts, shaders | `t:prefab` · `t:scene` · `t:script` · `t:shader` |
| Sprites, meshes, fonts | `t:sprite` · `t:mesh` · `t:font` |
| Audio clips, animation clips | `t:audioclip` · `t:animationclip` |
| Render textures | `t:rendertexture` |
| ScriptableObject assets in one folder | `t:ScriptableObject dir:Assets/Config` |
| Anything under a folder | `dir:Assets/Courier/Hazards` |
| Prefabs under a folder | `t:prefab dir:Assets/Courier/Pickups` |
| Assets carrying a label | `l:Hazard` |
| Anything whose name contains a word | `sentry` |

A filename or extension pattern rides along as a keyword — `*.mat`, `*.prefab`, `Lane_` — rather
than as a filter of its own. Quote any path containing a space: `dir:"Assets/Courier Run/UI"`.

> **The Search window itself is the cheapest confirmation there is.** It suggests filters as you
> type, so a filter you are unsure of can be checked in the Editor in less time than it takes to
> reason about it.

## 2. Reference forms

Reach for `ref=` when the question is about usage, dependency, or "what would break if I changed
this".

| Wanted | Query |
|---|---|
| Anything referencing a named asset | `ref=Lane_Asphalt` |
| …where the path is known and the name is ambiguous | `ref="Assets/Courier/Materials/Lane Asphalt.mat"` |
| Prefabs using a material | `t:prefab ref=Lane_Asphalt` |
| Materials using a texture | `t:material ref=GateGlow` |
| Scenes referencing a specific prefab | `t:scene ref="Assets/Courier/Prefabs/Sentry.prefab"` |
| Prefabs referencing *any* texture (expression) | `t:prefab ref={t:texture}` |
| Scenes referencing *any* prefab (expression) | `t:scene ref={t:prefab}` |
| Scenes mentioning a script or component by name | `t:scene RunnerController` |

The braced form is a **search expression**: the inner query produces a set and the outer one keeps
whatever references it. Reach for it only when it clearly beats naming the asset, because it costs
more to evaluate and is easy to mis-read.

When the request names an asset but not its path, query the name first and say a path-qualified
query would be exact. Two assets with the same name are common and `ref=` cannot tell them apart.

## 3. Scene component queries

These use **Unity type names**, matched against components in the loaded scenes.

| Wanted | Query |
|---|---|
| Lights, cameras | `t:Light` · `t:Camera` |
| Rigidbodies, colliders | `t:Rigidbody` · `t:Collider` |
| Canvases, buttons | `t:Canvas` · `t:Button` |
| TextMeshPro UI text | `t:TextMeshProUGUI` |
| RectTransforms | `t:RectTransform` |
| Particle systems | `t:ParticleSystem` |
| Audio sources | `t:AudioSource` |
| Animators | `t:Animator` |
| Mesh and skinned-mesh renderers | `t:MeshRenderer` · `t:SkinnedMeshRenderer` |
| Nav mesh agents | `t:NavMeshAgent` |
| An object by name | `Sentry` |

Combine a name with a type when the request carries both: `Sentry t:Rigidbody` finds the sentries
that have one, which is also how you find the one that does not by comparing against `Sentry`
alone.

## 4. Phrase → query

| The wording | What to build |
|---|---|
| "where is X" | `X` as a keyword, unless X is plainly a type |
| "find all X in Assets/UI" | `t:x dir:Assets/UI`, where X names an asset type |
| "which prefabs use X" | `t:prefab ref=X` for an asset name; `t:prefab X` when X is a script or component name |
| "what references this texture" | `ref=<name>`, or `ref="<path>"` when a path is available |
| "show every light in the scene" | `t:Light`, scene provider |
| "find the scene objects that have X" | `t:X` for a component type; the bare keyword `X` otherwise |
| "everything about X" | the bare keyword `X` across both providers first, then narrow to `t:X` if the type reading is the one they meant |
| "what references the material I have selected" | that asset's name or path **when the conversation supplies one** — otherwise ask |
| "just give me the query" / "do not open Search" | return the query, open nothing |

## 5. What Search will not settle

Say so plainly instead of producing a query that looks authoritative.

- **Material and shader properties.** `t:material Standard` narrows to likely matches; it does not
  prove which materials use a given shader, and the answer varies with Editor version. A scripted
  audit answers it — `unity-debug` → `reference/editor-control.md`.
- **Missing scripts.** `t:prefab missing` is a starting point, not an inventory. A reliable answer
  is a script that walks the components and reports the nulls.
- **A whole-project dependency graph.** Out of scope. `ref=` answers one hop from one asset; a
  transitive graph is a different job.
- **Repository text, build logs, package registries, menu items and settings.** None of these are
  Unity Search's index. Say which tool owns the question and stop.
- **Anything that changes a result.** Selecting, renaming, moving, deleting, re-importing. Find,
  show the query, stop — then ask.

An empty result is the outcome that most often gets over-read. It can mean the assets are not
there, or that a filter was not understood, or that the provider being searched is not the one
holding them. Before reporting "there are none", widen once: drop the filter and keep the keyword.
