# The modules — what each one does, its gates, and how to call it

Every module is one call through the Blender MCP server's code tool and returns a dict of gates;
the parameters of each are in its docstring (`scripts/brt_*.py`). A worked call is in
`reference/worked-example.md`.

| Module | Does | Gates |
|---|---|---|
| `brt_common` | shared helpers: the gate and report shape, slot assignment, layered-action F-curves, scene state saved and put back, finite sampling | — |
| `brt_arp` | drives the user's Auto-Rig Pro: ops `probe`, `source_bones` (no add-on), `markers`, `match`, `bind`, `retarget`, `pipeline` (`character-autorig`), `export`; a missing name fails `arp.precondition` with a `reason`, no change | `arp.addon_present`, `arp.source_skeleton_found`, `arp.map_sources_found`, `arp.markers_placed`, `arp.bone_count`, `arp.vertices_without_group`, `arp.retarget_clips`, `arp.metadata_clips` |
| `brt_retarget` | the rotation of mapped bones, conjugated from a source skeleton into a new action or, with `into_action`, one that exists; the root-most moving bone's translation scaled by the hip-height ratio `k` (`translate`) | `retarget.output_is_new` or `retarget.channels_free`, `retarget.finite_keys`, `retarget.translation_kept`, `retarget.first_equals_last` (with `loop`) |
| `brt_weights` | local weight repair: ops `probe`, `snapshot`, `transfer`, `normalize`, `restore` | `weights.region_vertices`, `weights.snapshot_written`, `weights.changed_vertices`, `weights.weight_sum_error`, `weights.deform_only`, `weights.restored` |
| `brt_library` | slots, fake users, asset marks, one review track, a catalog; actions found by name, provenance property or manifest | `library.every_action_has_slot`, `library.finite_at_3_frames`, `library.strips_equal_clips` |
| `brt_drift` | a carried prop against its anchor bone, sampled over every clip, position and rotation | `drift.max_drift`, `drift.max_rotation` |
| `brt_audit` | the saved .blend read back in a fresh Blender; exit 0 pass, 1 fail, 2 refused input | `audit.expect_matches`, `audit.props_parented` (with `props`) |
| `clip_metrics.py` (host, numpy) | a clip on the character against the same clip on the reference body: plants, added foot slide, limb direction, arm pose, pops; exit 0 pass, 2 a gate failed, 1 refused (`motion_metrics`' codes) | `added_slide_p95_m`, `added_slide_max_m`, `limb_direction_p95_deg`, `pops` |
| `motion_metrics.py` (host, numpy) | one clip: plant slide, penetration, jitter, limits, loop seam, drift, pops; exit 0/2/1 | `foot_slide_p95_m`, `loop_seam_ratio`, `pops` |
| `bakeoff_report.py` (host, stdlib) | `clip_metrics` reports per route → one markdown table, misses in bold; exit 0/1/2 | — |

**Calling a module.** Through the Blender MCP server's code tool, put this skill's `scripts`
directory on `sys.path`, import `brt_common` and the module, reload both (Blender keeps
`sys.modules` for the whole session), and assign `result = brt_<module>.run(params)`: the code tool
hands that dict back, and `reference/worked-example.md` has the stub. Every `run` returns `ok`, `gates`
(each with `name`, `value`, `limit`, `pass`), `created` (the datablocks it added) and `blender`,
plus the keys its docstring lists; `report_path` also writes it as JSON. A call that raises removes
what it created; edits to datablocks that already existed are not undone, and each docstring says
which it makes. When Blender cannot read the skill directory, send the sources in one call the way
`blender-character-rig` does, `brt_common` first. `brt_audit` alone also runs from the host shell:
`Blender --background <file>.blend --factory-startup --python brt_audit.py -- --expect '{...}'`.
