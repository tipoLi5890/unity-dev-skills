# Contributing to unity-dev-skills

The checks CI runs, and the two rules that keep the manifests honest.

## Working on this repo

```bash
python3 tools/lint-skills.py            # frontmatter + name/dir match + size and listing budgets + executable syntax
python3 tools/run-selftests.py          # every script's selftest this machine can run (SKIP on a missing dep)
python3 tools/check-csharp.py           # C# rules: class = file name, UnityEditor only in Editor code, no new global types
python3 tools/check-consistency.py      # manifests agree, companions declared
python3 tools/check-registry.py         # asset registry selftests and fixtures, the budget table in one place
python3 tools/sync-codex-manifests.py   # regenerate the Codex manifests
claude plugin validate .                # manifest shape
```

Run them from the repository root. CI runs them on Python 3.10 and 3.12 with numpy, Pillow and
ffmpeg installed. Rows that need Blender, torch or OpenCV are skipped there: run them locally
before a release, Blender ones with `python3 tools/run-selftests.py --blender /path/to/blender`.
Before a release, also compile the shipped C# in a scratch Unity project with
`tools/unity-compile-check.sh` (one Editor at a time).

A script that has a selftest takes both `selftest` and `--selftest`, and gets a row in
`SELFTESTS` in [`tools/run-selftests.py`](../tools/run-selftests.py); a selftest with no row fails
the run. A selftest builds its inputs in a temp directory, covers a pass and a fail, and checks
the exit code.

## Exit codes

A gate's exit code is its verdict, so a caller can branch on it without reading the output.
New scripts use this table:

| Code | Meaning |
|---|---|
| 0 | pass: every check ran and held (or the selftest passed) |
| 2 | the check ran and failed — a verdict; retrying will not change it |
| 3 | harness or IO error: nothing was verified (a missing input, an unreadable file, a tool that did not start) |
| 1 | refused input or a usage error (a bad flag, a missing argument), or a failed selftest |

argparse exits 2 on a bad flag, which here reads as "the check failed". A script where 2 is a
verdict subclasses `argparse.ArgumentParser` and overrides `error()` to exit 1; CI runs those
scripts with `--no-such-flag` and requires exit 1.

Older scripts keep the convention their header documents; read it before branching on a code:

- **1 a verdict, 2 usage or IO error**: `level_validate`, `tiled_to_level`, `jump_report`,
  `level_metrics`, `fingerprint`, `journey_report`, `probe`, `inputactions_lint`, `save_check`,
  `camera_jitter`, `screen_smoothness`, `spectrum_check`, `check_instrumental`, `inspect_glb`,
  `audit_3d_source`, `audit_frames`, `rig_gate`, `frames_preview`, `video_motion`,
  `bakeoff_report`.
- **usage errors exit 3 (harness)**: `registry`, `merge_results`, `golden_diff`; `camera_gate`
  exits 64.
- **2 an invalid input or spec, which is also what a usage error gives**: `contact_sheet`,
  `overview_sheet`, `preview_compose`, `preview_reel`.
- **their own tables**, each in the script's header: `graph_diff` (1 the graphs differ),
  `assemble_segments`, `codex_generate`, `sheet_to_frames`, `pixel_snap`, `pick_key`,
  `audit_pixel`, `key_unmix`, `breathe`, `video_loop`, `video_frames`, `video_canvas`.

[`.claude-plugin/*`](../.claude-plugin/) are the sources of truth.
[`.codex-plugin/plugin.json`](../.codex-plugin/plugin.json) and
[`.agents/plugins/marketplace.json`](../.agents/plugins/marketplace.json) are **generated — never
hand-edit them.**

Routing to a plugin outside this repo is a declared dependency: add it to `COMPANIONS` in
[`tools/check-consistency.py`](../tools/check-consistency.py), with the reason. An undeclared one
fails the gate.

What this release contains: [CHANGELOG.md](../CHANGELOG.md).
