# Getting clips: downloading stock sources and importing a purchased pack

> Part of the `blender-retarget` skill. How a `brt_*` module is called and what every `run`
> returns are in `SKILL.md`.

Clips arrive from two kinds of source: an online stock library, downloaded clip by clip in a
browser, and a purchased pack, imported from an archive. Both end in one manifest that lists every
clip the library needs, checked before any retarget starts.

## The manifest comes first

One entry per clip, written before downloading and completed as files arrive.

| Field | Holds | Example |
|---|---|---|
| `name` | the clip's name in your library | `JogLaneLeft` |
| `source` | `stock` or `pack` | `stock` |
| `search` | the term typed into the library | `jog strafe` |
| `direction` | the direction seen in the preview, not the one in the title | `left` |
| `fps` | the rate it was exported at | 30 |
| `in_place` | travel removed at export | `true` |
| `variant` | for a pack: `standard` or `no_root` | `no_root` |
| `file` | path relative to the clips folder | `stock/JogLaneLeft.fbx` |
| `action` | the action's real name, filled from the result after the retarget: `clips[].action` (`brt_arp`) or `output_action` (`brt_retarget`) | `Runner_JogLaneLeft` |

```json
[
  {"name": "JogLaneLeft", "source": "stock", "search": "jog strafe",
   "direction": "left", "fps": 30, "in_place": true,
   "file": "stock/JogLaneLeft.fbx", "action": null},
  {"name": "GateLatchSwing", "source": "pack", "variant": "no_root", "fps": 30,
   "in_place": true, "file": "pack/no_root/GateLatchSwing.fbx", "action": null}
]
```

Before retargeting, every entry's file exists and is not empty, names are unique, every `fps`
equals the scene's rate, and no two entries share a `name` and `direction`. A missing entry stops
the batch; it is not filled in later by hand.

The manifest is also how an action is found again. `brt_arp` stamps each action it bakes with
`brt_source_file`, the clip's `fbx` exactly as given, and `brt_library` with `manifest` matches an
entry's `file` against that property: equal, or the property's path ends with `file`. So give
`brt_arp` the path inside the clips folder (absolute, or `//clips/` + `file`), never a bare
basename, and `action` can stay `null` until it is filled from the result.

## A stock library through a browser tool

Through computer use or a browser MCP, in the user's own browser.

- **The user logs in.** Never type, read, store or pass on credentials, cookies or session
  tokens. No shared account, no unofficial bulk downloader; one clip at a time through the site's
  own download.
- **Read the page before each action.** Find the search field, result cards, preview and download
  dialog by their meaning in the current UI (label, role, text), never by screen coordinates or
  locators recorded in an earlier session. A redesigned site breaks replayed clicks silently.
- **A search that returns nothing** is a fact about that search on that day. Record the terms tried;
  do not conclude the library lacks the motion.

Per clip:

1. Search by the manifest's `search` term.
2. Open the result and watch the preview for the direction of travel. Left and right, forward and
   backward diagonals can share one display name: the preview decides, not the name. Write the
   `direction` into the manifest now, before downloading.
3. Set the download options (table below).
4. Download, wait for it to finish, confirm the file exists with a plausible size, and move it to
   its manifest `file`, named by the direction from step 2, before starting the next one. The name
   the browser gave the download carries no meaning.

| Option | Value | Why |
|---|---|---|
| Format | FBX for Unity | one file feeds Blender here and Unity later |
| Frames per second | 30 | one rate across the library, equal to the scene's |
| Keyframe reduction | none | reduction drops keys the conversion samples; clips are short anyway |
| In place | on for locomotion | travel belongs to the game's controller, not the clip |
| Trim | full range | cutting a loop's end makes the seam pop |
| Skin | without | the source skeleton is all a retarget needs; with skin only to use the library's own character |
| Motion sliders | defaults | they alter the performance; keep one setting across the library |

The file-naming contract for using such clips on the library's own character in Unity is in
`unity-rigged-character` → `reference/unity-import.md` §2. A stock library covers locomotion, idles,
reactions and warm-ups; a specialised action such as `GateLatchSwing` comes from a pack or is keyed.

## A purchased pack

**1. Keep the archive untouched.** Store it as downloaded in a vendor folder outside the repo.
Unpack into a new, empty folder of its own, never into the project tree. Treat the content as
untrusted data: run nothing that came inside it from that folder.

**2. Inventory before importing.** List every file per folder and variant.

| Variant | The root carries | Use |
|---|---|---|
| standard | the performance's travel through space | a character moved by the animation: cutscenes, set pieces |
| no-root | little or no travel | gameplay, where input and physics move the character |

No-root does not always mean the same thing, so measure it on a representative clip before
choosing. In one pack the pelvis still rose, dropped and swayed. In another, no-root removed
**every** translation curve, the hip's height included: the hip sat at a fixed 1.0 m and the feet
floated 0.28 m in a crouch and 0.55 m in a kneel, while the standard variant's hip height varied 2
to 50 cm per clip. There, take the standard variant for gameplay too, keep its vertical hip
motion, strip non-root positions at import and give the horizontal travel to the game's controller
(`reference/route-bakeoff.md`, *Clip-file behaviour*). Reference files (a T-pose, an A-pose) sit among
the clips; list them, and keep them out of the manifest's clips.

**3. Count takes, not products.** A two-actor interaction comes as one file per actor, so a pack
holds more takes than its advertised motion count. Reconcile the inventory against the product
description by explaining every extra file before concluding anything is missing. Retargeting each
actor file onto `Runner` gives two separate clips; the interaction itself (a second character,
spacing, timing) is not done by that.

**4. Import one representative clip** into the session and check it before any batch.

| Check | How | Wrong looks like |
|---|---|---|
| skeleton | `brt_arp` op `source_bones` (stock Blender, no add-on): bone names, parents, a `skeleton` hash, and with the planned map `map_missing`; rest pose (T or A) in a still | names the map does not cover; a map made for another skeleton |
| units | the armature object's scale, hip height against the expected | a 0.01 scale; a giant or a doll |
| fps | the file's rate against the scene's `render.fps` | the clip plays fast or slow |
| curves | per bone, the first key's frame and whether a curve exists at all | curves that start late (Unity and Blender read the gap differently), bones with no curve, root nodes named differently between clips: `reference/route-bakeoff.md` |
| frame range | the imported action's `frame_range`: `brt_arp` bakes over it unless the clip gives `frame_start` and `frame_end` | starts at 0, or carries extra frames |
| extras | demo meshes and props imported with the skeleton | delete only those new objects; keep the armature and its action |

Then the map, the rest correction and one clip baked and looked at (`reference/arp-route.md`);
only then the batch. `brt_arp`'s `retarget` reads each `fbx` as a local file through Blender's FBX
importer and never writes to it; never delete or edit the pack's original FBX files.

**5. Read the vendor documentation** for its variants and the engine settings it recommends, for
example Apply Root Motion off when input drives movement, or root height based on the feet for
crouching clips. These are the vendor's recommendations; confirm them in the engine before relying
on them.

**6. Vendor batch editor scripts** change the import settings of every FBX they are pointed at:
props and scene files can end up imported as Humanoid. Read the script before installing it, scope
it to one path or an explicit selection, and run it first on a copied folder. Never point it at the
whole project.

**7. Clips that assume props.** An entrance that picks up a bag, a swing that holds a `Mallet`: the
clip carries the motion, not the prop. Showing, hiding and handing over the prop are gameplay
events to plan; a clip with an empty hand must not show the prop.

**8. Licence.** The pack and its files stay out of the repo and are never redistributed. Commit
only your own scripts, maps and manifests, with paths relative to a clips folder the user supplies,
and list that folder in `.gitignore`.

## Only download what the manifest lacks

Before any download, compare the manifest with the files on disk:

```python
import json, pathlib
clips = pathlib.Path("clips")
entries = json.loads((clips / "manifest.json").read_text())
missing = [e["name"] for e in entries
           if not (clips / e["file"]).is_file() or (clips / e["file"]).stat().st_size == 0]
```

- One clip missing: download that one. Never re-download the library to refresh it: every
  direction label would have to be checked again from the previews.
- A download that replaces an existing file is a new source: retarget it again and replace the
  action, and recompute any `K` taken from it (`reference/rest-pose-and-conjugation.md`).
  `brt_retarget` refuses an `output_action` that already exists unless the call passes
  `overwrite_action: True`; `brt_arp` warns before the run that the clip name is taken and gives
  the new action a `.001` suffix, listed in `duplicate_suffixes`. Remove the old take first, or
  bake under a staging name and rename deliberately; either way `brt_arp`'s `brt_clip` property
  finds it (`brt_library` with `provenance_key: "brt_clip"`).
- Run the check again after downloading, then start the retarget.
