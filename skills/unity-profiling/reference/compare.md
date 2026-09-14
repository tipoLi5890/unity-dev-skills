# Before and after: the table that settles it

> Part of the `unity-profiling` skill. "It feels smoother now" is not a result. Two windows from
> the same situation on the same instrument, with one thing changed between them, is.

## The protocol

1. **Save the baseline first.** Before touching anything. The commonest way to lose a day is to
   make the change, like it, and then have nothing to compare against.
2. **One change per comparison.** Two changes in one window mean the table cannot attribute the
   result, and the wrong one gets kept.
3. **Hold the instrument fixed.** Same run mode, same graphics device, same screen size, same
   vsync and `targetFrameRate`, same warm-up. These all sit in `run{}` in every record, and the
   script refuses the comparison when they differ.
4. **Same situation, same seed.** A driven moment with a fixed seed, not "I played it for a bit".
   Booting straight into a named moment is `unity-play-harness` → `reference/situations.md`.
5. **Three windows per side.** One window each way is a coin toss at anything under about 10%.
   Three lets the script print the spread and tell you when the run is too noisy to read.
6. **Delete the JSONL before each side.** It is appended to.

```bash
rm -f /tmp/perf/base.jsonl
UNITY_PERF_OUT=/tmp/perf/base.jsonl  <driven run ×3>
# ... make exactly one change ...
rm -f /tmp/perf/cand.jsonl
UNITY_PERF_OUT=/tmp/perf/cand.jsonl  <the same driven run ×3>
python3 scripts/compare_windows.py /tmp/perf/base.jsonl /tmp/perf/cand.jsonl --label hazard-lane
```

## The script

```
compare_windows.py BASELINE.jsonl CANDIDATE.jsonl
    [--label L] [--stat median|p95|max|sum|delta|mean|min|p90|p99]
    [--threshold 10] [--counters "Render/*,Game/*"] [--higher-better GLOBS]
    [--format table|md|json] [--allow-mode-mismatch]
compare_windows.py --show FILE.jsonl
```

- **Alignment is by label.** Windows with the same label are compared; a label present on only one
  side is reported rather than silently dropped. Several windows sharing a label on one side
  collapse to their median, and the spread between them is printed as a note.
- **`--stat` picks the counter statistic.** Cumulative counters always compare their `delta`; a
  statistic a counter does not carry (`sum` on a level) falls back to `median`.
- **`--threshold` is the noise band**, in percent. Default 10.
- **`--higher-better`** inverts the direction for counters where more is better.
- **`--show`** prints one line per window in a file — the fastest way to check what a run actually
  wrote before comparing anything.

Columns are `counter | stat | baseline | candidate | delta | % | flag`, and the flags are:

| Flag | Means |
|---|---|
| `better` | Moved the right way by more than the threshold |
| `same` | Unchanged, or inside the noise band the right way |
| `worse` | Inside the noise band, wrong way |
| `REGRESSION` | Moved the wrong way by more than the threshold |
| `missing-left` / `missing-right` | The counter exists on one side only — a rename, or a build that stopped exposing it |
| `missing-both` | The key is in the file but carries no readable number on either side |
| `zero-both` | Zero on both sides: an absence, not a result |

Only `REGRESSION` changes the exit code. `worse` is a row to read, not a failure: a 3% drift on a
count is what an unchanged game looks like twice.

Exit codes, so a script can gate on it:

| Code | Meaning |
|---|---|
| 0 | Compared, nothing regressed past the threshold |
| 1 | Usage error, missing file, or a line that is not a perf window |
| 2 | At least one metric regressed |
| 3 | Not comparable — different mode, graphics device, screen, vsync or warm-up |

Exit 3 is the one that saves you. Two windows from different instruments subtract cleanly and mean
nothing; the script prints both fingerprints and stops.

## What a report looks like

Six lines. No prose about how it feels, and the situation named so it can be re-run:

```
Situation  hazard-lane seed=7 · editor-windowed · 90 frames, 30 warm-up, 3 windows each
Change     lane selector: 0.2-unit hysteresis on the lane boundary
Frame time median 8.31 → 8.20 ms · p95 12.90 → 9.10 (-29.5%) · max 41.2 → 11.0 · hitches 2 → 0
Work       pickup-pool scheduled 231 → 25 · completed 17 → 18 · discarded 214 → 7
Rendering  draw calls 412 → 409 · triangles 51200 → 51100 (unchanged — this was not a render cost)
Open       release player not measured yet; the same window on a device build is the next step
```

The last line is not optional. A comparison that does not say what it did **not** cover invites
the reader to assume it covered everything.

## Gotchas that produce a confident wrong answer

- **The candidate is faster because it does less.** The most common false win. Check
  `Game/*.completed` and `Game/*.scheduled` before celebrating: fewer pickups built is not the
  same as pickups built more cheaply, and the table will not tell you which happened unless the
  work counters are in it.
- **Mismatched warm-up.** A candidate with 30 warm-up frames against a baseline with 0 is a
  comparison between "playing" and "starting". This is part of the fingerprint for that reason.
- **A stale baseline file.** Appended-to JSONL from last week, with a label that still matches.
  `--show` it first; the `utc` field is there so a window can be dated.
- **Vsync on one side.** A frame-time floor at 16.67 or 8.33 ms is the display, and it hides both
  improvements and regressions under it. Turn it off for measurement, and record that you did.
- **A 9% improvement with a 12% spread between windows on one side.** The script prints that note;
  it means the run is not repeatable enough to read the change. Make the situation more
  deterministic, or take more windows.
- **Comparing an Editor window against a player window.** Editor overhead is inside every Editor
  number. The mode check catches it; `--allow-mode-mismatch` exists for when you deliberately want
  the shape of the difference, and then the report has to say so.
- **The change moved the cost rather than removing it.** Frame time down, `Memory/Total Used
  Memory` up by 60 MB is a trade, not a win, and on a memory-constrained target it is a loss.
  Read the whole table, not the row you were hoping for.

When the table says the frame got slower and nothing explains why, the next step is not another
window — it is finding which marker owns the time, in `reference/raw-capture.md`. When it says
which subsystem is expensive, `reference/where-the-time-goes.md` routes it to the skill that owns
that cost.
