# Courier Run — art manifest

Written by hand, row by row. Paths are relative to `ArtDirection/` unless they start at the
project root. A struck path is an old version.

## Palette

| Name | Hex |
|---|---|
| courier orange | #E8762B |
| night asphalt | #2B2F36 |

## 2D

| Date | Path | Type | Spec version | Prompt | Status | Anchor | Notes |
|---|---|---|---|---|---|---|---|
| 2026-03-02 | `anchors/master.png` | anchor | v2 | `prompts/master.txt` | LOCKED | - | the look every sheet starts from |
| 2026-03-03 | ~~`anchors/runner_v1.png`~~ `anchors/runner.png` | anchor | v2 | | approved | `anchors/master.png` | the first face read too young |
| 2026-03-04 | `sheets/runner_{run,idle}.png` | sheet | v2 | `prompts/runner_sheets.txt` | approved | `anchors/master.png` | run and idle loops |
| 2026-03-05 | frames/runner_run/run_1..6.png | frames | v2 | | approved | - | cut from the run sheet |
| 2026-03-06 | `turnarounds/mallet_front.png` + `turnarounds/mallet_side.png` | turnaround | v2 | | PENDING | `anchors/master.png` | the Mallet, front and side |
| ~~2026-02-20~~ | ~~`sheets/runner_run_v1.png`~~ | ~~sheet~~ | ~~v1~~ | | | | ~~legs too short~~ |
| 2026-03-07 | `previews/runner_run.gif` | preview | v2 | | **unused** | | kept for the pitch |
| 2026-03-08 | `sheets/runner_jump.png` | sheet | v2 | | approved | `anchors/master.png` | queued, not drawn yet |
| 2026-03-09 | TBD | sheet | v2 | | PENDING | | a wave loop, no file yet |

## 3D 資產

| 日期 | 路徑 | 類型 | 規格版本 | 狀態 | 備註 |
|---|---|---|---|---|---|
| 2026-03-10 | `Assets/Models/HeroProp/Mallet/Mallet.glb`<br>`raw/3d/Mallet/mallet_raw.glb` | 模型 | 2 | 已核准 | 出貨網格與未減面原檔 |
| 2026-03-11 | sources/runner_rig_v1.blend, sources/runner_rig_v1.fbx | 骨架 | 1 | 已歸檔 | 第一版骨架 |
| 2026-03-14 | `Assets/Models/Character/Runner/Runner@*.fbx` | 動作 | 2 | 已核准 | GateLatchSwing 與 Run |
| 2026-03-15 | `Assets/Models/Character/Runner/Runner.fbx` and `ArtDirection/sources/Runner.blend` | 骨架 | 2 | 已核准 | RunnerRig |

A table in a code block is an example, not a row:

```text
| Path | Status |
|---|---|
| sheets/runner_example.png | approved |
```
