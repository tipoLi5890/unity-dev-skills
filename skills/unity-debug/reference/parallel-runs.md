# Test lanes: several Editors on one project at once

> Part of the `unity-debug` skill. `scripts/lanes.sh` builds the lanes and hands them out,
> `scripts/merge_results.py` turns a split suite back into one verdict, and
> `resources/LaneDataPath.cs` keeps each lane's saves apart.

One Editor per project means every test run, compile check and screenshot batch queues behind one
lock, `Temp/UnityLockfile` (`reference/harness-trust.md`). That lock belongs to the **project
folder**, not the machine. A second folder that links the same `Assets` has its own `Temp`, so it
holds a second Editor, and its own `Library`, so it compiles the same code from its own cache.
This page calls that folder a **test lane**: a project folder, not one of the courier run's three
lanes. ParrelSync's clones work the same way; here a script builds them.

## Lane layout

Lane 0 is the repo. Clone lane K is `<repo>.lanes/laneK/`, beside the repo and never inside it,
marked `.lane-ready` once setup finishes.

| Folder | Linked or copied | Why |
|---|---|---|
| `Assets`, `ProjectSettings` | linked | The code under test: a copy tests yesterday's code. So one lane's settings edits reach every lane (below) |
| `Packages` | linked | One manifest and `packages-lock.json`: change packages on lane 0, and the clones resolve on their next start. ParrelSync copies it |
| `Library` | copied | Import cache, compiled assemblies, asset databases: two Editors writing one corrupt it. The copy starts a lane warm |
| `Temp`, `Logs`, `UserSettings` | the lane's own | `Temp` holds the lock; sharing it brings the one-Editor rule back |

**Copying `Library`.** `lanes.sh setup` copies it holding lane 0's lock (refusing while an Editor
has the repo open), then deletes `Library/ArtifactDB-lock` and `SourceAssetDB-lock`, which belong
to the repo's Editor. macOS uses `cp -cR` (APFS clonefile: seconds, no extra disk until a block
changes), Linux `cp -a --reflink=auto`. Confirm that a fresh lane's first run is warm: no full
import in its log.

- **Windows:** `lanes.sh` does not build lanes; ParrelSync uses junctions (`mklink /J`). On a
  throwaway project, confirm that deleting a hand-built lane removes the junction, not the repo
  folder behind it.
- **`file:../` dependencies** in `manifest.json` resolve relative to `Packages`, a link in a lane.
  Confirm that the lane's log resolves them; if not, add that folder to `LANE_LINKS`, as ParrelSync
  links `LocalPackages`.
- **After an Editor upgrade or a package change on lane 0,** `lanes.sh clean`, then `setup 2`: the
  lanes copy the reimported `Library` instead of each reimporting.

## The lane pool

Run `scripts/lanes.sh` from the repo root; its header lists the environment variables it reads.
Each lane has one lock: a directory made with `mkdir`, which is atomic, with the holder's pid
inside.

- **A lock whose holder is gone is reclaimed.** Liveness is checked with `ps`, not `kill -0`.
- **A lane an Editor has open is skipped:** an Editor process with that `-projectPath`, or a
  `Temp/UnityLockfile` no run holds. `status` names both.
- **Read-only runs try the clone lanes first and lane 0 last,** keeping lane 0 for the work only it
  may do.
- **When every lane is taken, a run queues** (every 10 s, up to an hour): in a pool, busy is
  normal. `--no-wait` exits 6 instead.

```bash
lanes.sh setup 2                 # lanes 1 and 2, beside the repo
lanes.sh status                  # free · busy (pid) · Editor open · lockfile nobody claims
lanes.sh run -- -batchmode -nographics -projectPath '{project}' -runTests -testPlatform EditMode \
  -testResults '/tmp/courier_edit_lane{lane}.xml' -logFile '/tmp/courier_edit_lane{lane}.log'
```

`run` replaces `{project}` and `{lane}` in the arguments (quote them: zsh reads `{project} >file`
as a redirection), deletes the results file before launching, and returns Unity's own exit code
with no pipe in between. It prints `[LANE] lane=1 project=…` first and
`[LANE] lane=1 exit=0 log=4180 lines results=present` last: the three signals from
`reference/harness-trust.md`, per lane. Any other script that opens the repo in an Editor goes
through `lanes.sh run --main-only`, or it races the pool for lane 0.

## Two ways to use it

**1. A pool shared by many agents or jobs.** Each job runs with `{lane}` in every output path,
reads back the paths its run printed, never a glob (`reference/test-verdicts.md`), and judges its
own run.

**2. One suite split across lanes, then merged.** The lane a shard lands on is not known in
advance, so name the outputs by shard in a per-run folder:

```bash
RUN=/tmp/courier_split_$$; mkdir -p "$RUN"; START=$(date +%s)
leg() { lanes.sh run -- "$@"; local rc=$?; restore_rib; return $rc; }   # restore_rib: below
leg -batchmode -nographics -projectPath '{project}' -runTests -testPlatform EditMode \
    -testResults "$RUN/edit.xml" -logFile "$RUN/edit.log" &
leg -projectPath '{project}' -runTests -testPlatform PlayMode -testCategory Smoke \
    -testResults "$RUN/play-smoke.xml" -logFile "$RUN/play-smoke.log" &
leg -projectPath '{project}' -runTests -testPlatform PlayMode -testCategory Full \
    -testResults "$RUN/play-full.xml" -logFile "$RUN/play-full.log" &
wait
git status --short -- ProjectSettings Assets      # once, after every leg
python3 merge_results.py --since "$START" --inventory /tmp/courier_full_play.xml \
    --inventory /tmp/courier_full_edit.xml "$RUN"/edit.xml "$RUN"/play-smoke.xml "$RUN"/play-full.xml
```

The merge treats a missing piece as the harness failing:

| `merge_results.py` finds | Exit |
|---|---|
| A shard file missing, unreadable, or older than `--since` | 3 |
| A shard with `total=0` (its filter matched nothing) | 3 |
| One test fullname in two shards (the split overlaps) | 3 |
| A test in the `--inventory` report that ran in no shard (the split has a gap) | 3 |
| `inconclusive` > 0: a gate that did not run (`reference/test-verdicts.md`) | 3. `--allow-inconclusive` lists them instead, for a test that is expected to skip itself |
| `failed` > 0 | 2, a verdict: do not retry |
| `skipped` | listed by name |

3 outranks 2, and the failures are still listed. The last line is
`[MERGE] shards=3 total=… passed=… failed=… inconclusive=… skipped=… missing=… dup=… verdict=green|failed|harness`.
The inventory is a report from an earlier full, unsplit run; refresh it after deleting tests, or
they read as missing. Unlike `unity test --shard`, where separate CI jobs share nothing, lanes share
one checkout and everything it links (`unity-cli` → `reference/ci-surface.md` §4).

## What runs where

> **Clone lanes read; lane 0 writes.** Two Editors writing one `Assets` folder race for `.meta`
> files and generated assets. Neither reports the race; it shows up later as a broken reference.

| Work | Lane |
|---|---|
| A compile check, EditMode and PlayMode tests that write only to `/tmp` and `LaneDataPath` | any |
| A soak or long journey (`unity-play-harness` → `reference/soak.md`): a good tenant for a clone lane | any |
| Import or reimport, asset generators, scene builders, screenshot batches that save into `Assets` | 0 |
| Adding or removing packages, editing Player Settings | 0 |
| A platform switch (`-buildTarget`), a Player build, tests on a player platform (`reference/player-tests.md`) | 0, or a lane kept for that target, outside the pool |

Use `lanes.sh run --main-only` for every lane-0 row. A lane kept for one build target gets its own
lanes root and the **same** lock prefix: `LANES_ROOT=<repo>.android lanes.sh setup 1`, then always
`LANES_ROOT=<repo>.android lanes.sh run --lane 1 -- …`. Lane 0 stays one lock both see; its lane 1
shares a lock name with the pool's lane 1, so the two wait for each other: throughput, never safety.

## What each lane keeps to itself

- **Results, logs, verdicts:** `{lane}` or a per-run folder in every output path, printed when the
  run starts (`run` does).
- **Save data:** `persistentDataPath` comes from the company and product name in the shared
  `ProjectSettings`, so every lane's Editor saves to one folder. `resources/LaneDataPath.cs` reads
  `GAME_DATA_DIR` in the Editor only; `lanes.sh` sets it to `<prefix>_data_lane<K>` per clone lane.
  Route every runtime path through `LaneDataPath.Root`, the save store first, and confirm
  `[LANE] data=…` in each lane's log.
- **PlayerPrefs** are keyed by the same names, so the lanes share them and `LaneDataPath` does not
  help: the `[SetUp]` reset `reference/test-verdicts.md` asks for tramples a neighbouring lane
  mid-run. Confirm whether tests touch them (`grep -rn "PlayerPrefs\." Assets --include=*.cs`). If
  they do, suffix those keys with `LANE` in the Editor, or keep those tests in one category that
  runs on one lane at a time.
- **EditorPrefs** belong to the user, so every Editor on the machine shares them (ParrelSync, below).

## Shared ProjectSettings

Every PlayMode run on every lane flips `runInBackground` to 1 in the one shared
`ProjectSettings.asset` (`SKILL.md`). Restore it after every leg; one `git status` at the end:

```bash
restore_rib() {   # changes only a 1, so two lanes restoring at once cannot conflict
  local f=ProjectSettings/ProjectSettings.asset
  grep -q '^  runInBackground: 1$' "$f" && sed -i '' 's/^  runInBackground: 1$/  runInBackground: 0/' "$f"
  return 0
}
```

Confirm that a restore landing mid-run does not stall another lane's windowed PlayMode run when its
window loses focus; if it does, restore once after `wait` instead.

The PlayMode runner's temporary `Assets/InitTestScene<guid>.unity` lands in the shared `Assets`
too. Confirm that one lane's log does not import another lane's temporary scene, and keep
`Assets/InitTestScene*` ignored in git either way (`SKILL.md`).

## New files: compile once on lane 0

A new `.cs` file or asset without a `.meta` gets its GUID from whichever Editor imports it first.
Two lanes importing it at once can each write a different GUID: one `.meta` wins on disk, the other
lane's `Library` keeps the losing GUID, and references break in that lane only. After adding files,
compile once on lane 0 before fanning out (`CIProbe` is in `reference/cli-harness.md`):

```bash
lanes.sh run --main-only -- -batchmode -nographics -projectPath '{project}' \
  -executeMethod CIProbe.Ping -logFile /tmp/courier_ping.log
git status --short -- '*.meta'          # the new .meta files: commit them with their files
```

## How many lanes

Each Editor holds a few GB once a PlayMode scene is loaded, and after a code change every lane
compiles at once. **On a 16 GB machine, lane 0 plus two clones is a sensible default.** Past what
RAM allows the machine swaps, and every lane runs slower than one alone. Count from free memory,
not cores: lanes ≈ (free GB − 2 GB headroom) ÷ one Editor's peak, read with `ps -o rss= -p <pid>`
during a PlayMode run. Then confirm that `sysctl vm.swapusage` holds still during a parallel run,
and that the run beats the same legs one after another.

## Splitting a suite: tier it first

A split is only as good as its seams. Tag tests by cost, then split along the tags:

```csharp
[Test, Category("Smoke")]      public void GateOpensWithKey() { … }
[UnityTest, Category("Full")]  public IEnumerator SentrySpotsRunnerAtRange() { … }
[UnityTest, Category("Perf")]  public IEnumerator LaunchFrameTime() { … }
[UnityTest, Category("Soak")]  public IEnumerator Soak(string situation) { … }
```

No everyday run includes Perf or Soak: a soak holds a lane for minutes, and Perf needs the machine
to itself (below).

| Split | Arguments | Watch for |
|---|---|---|
| EditMode on one lane, PlayMode on another | `-testPlatform EditMode` · `-testPlatform PlayMode` | Nothing: disjoint and complete by construction. Start here |
| PlayMode by tier | `-testCategory Smoke` · `-testCategory Full` | A test with no category runs in neither. `--inventory` finds it |
| By assembly | `-assemblyNames CourierRun.Tests.Gates` · `CourierRun.Tests.Sentry` | The suite has to be split into assemblies first |
| By name | `-testFilter <name>` | Pulling one slow fixture out on its own |

How Test Framework 1.6 reads these arguments (`RuntimeTestRunnerFilter.cs` in its package; check
yours before relying on it):

- **Values are `;`-separated, each a regular expression matched anywhere in the name.**
  `-testCategory Full` also selects `FullScreen`. Anchor it (`-testCategory '^Full$'`) or keep tier
  names that never appear inside another category name.
- **A leading `!` excludes, and several exclusions must all hold:** `-testCategory '!Perf;!Soak'`
  is every test outside both tiers. Single quotes: an interactive shell expands `!` inside double
  quotes.
- **A test with no category carries `Uncategorized`**, so `-testCategory Uncategorized` runs
  exactly the tests the tiers forgot.
- **A filter that matches nothing exits 0** with `total=0` in the results file; the merge refuses
  that shard. So pass a category only to the leg it slices, and check each shard's `total=`
  against the inventory.

> **Perf never shares the machine.** A frame time taken beside other Editors includes their load.
> Run Perf alone, every other lane idle: `unity-profiling` → `reference/perf-tests.md`.

## The ParrelSync package

A project may already have ParrelSync for manual multiplayer play. Its clones carry a `.clone` file
and their role in `.parrelsyncarg` (default `client`), link `Assets` and `ProjectSettings`, and
copy `Library` and `Packages`. In a clone, ParrelSync's
`AssetModificationProcessor.OnWillSaveAssets` returns an empty array while the EditorPrefs bool
`ParrelSync_DisableClonesAssetSaving` is true, the default: every asset save is dropped, and the
log says `Attempting to save <path> are blocked.` The PlayMode runner saves its temporary
InitTestScene into `Assets`, so the block can stop a test run. **Check on your project:** run one
PlayMode Smoke test in a ParrelSync clone; exit 0 with no results file and `are blocked` in the log
is this block. Two ways out, preferred first:

1. **Keep test lanes script-built.** `lanes.sh` writes no `.clone` file, so even with the package
   arriving through the linked `Packages`, each lane is an original project to it. Confirm that a
   lane's log has no `are blocked` line.
2. **Turn the preference off** on ParrelSync's preferences page. It is an EditorPrefs value, so it
   applies to every ParrelSync clone this user opens, the hand-played ones included.

## Multiplayer: one role per lane

Two lanes give you a host and a client on one machine, both under test, no human in the loop. It is
a first pass: two Editors on one machine share a network and a clock (`unity-multiplayer` §4).

**One role per lane:** an environment variable on each run, or a role file in the lane folder like
ParrelSync's `.parrelsyncarg`, read through one helper:

```csharp
public static class LaneRole                        // Runtime assembly, beside LaneDataPath
{
    public static string Get(string fallback = "host")
    {
#if UNITY_EDITOR
        string role = Environment.GetEnvironmentVariable("GAME_ROLE");
        if (!string.IsNullOrEmpty(role)) return role.Trim();
        string file = Path.Combine(Directory.GetCurrentDirectory(), ".lane-role");
        if (File.Exists(file)) return File.ReadAllText(file).Trim();
#endif
        return fallback;
    }
}
```

Confirm once, by logging it, that the Editor's working directory is the lane folder and not the
repo behind the `Assets` link.

**Launch both together, each pinned to a lane** (a pool could queue the client while the host
waits), once `lanes.sh status` shows both free. Give each role its own test name so the merge sees
no duplicate.

```bash
START=$(date +%s); RUN=/tmp/courier_mp_$$; mkdir -p "$RUN"
GAME_ROLE=host lanes.sh run --lane 0 -- -batchmode -projectPath '{project}' -runTests \
  -testPlatform PlayMode -testFilter CourierRun.Tests.TwoPlayer.Host_SeesClientLaunch \
  -testResults "$RUN/host.xml" -logFile "$RUN/host.log" &
GAME_ROLE=client lanes.sh run --lane 1 -- -batchmode -projectPath '{project}' -runTests \
  -testPlatform PlayMode -testFilter CourierRun.Tests.TwoPlayer.Client_ReachesGate \
  -testResults "$RUN/client.xml" -logFile "$RUN/client.log" &
wait
python3 merge_results.py --since "$START" "$RUN/host.xml" "$RUN/client.xml"
```

**Wait on readiness, never on a sleep.** Each side enters a situation whose ready set names its
conditions (`unity-play-harness` → `reference/situations.md`), with a timeout that covers the
other Editor's cold start. The host's set is `listening`, `clientConnected` and `remoteRunner`,
each read from your transport; a timeout names what is missing:
`two-player-host not ready after 180.0s: clientConnected, remoteRunner`. One pair uses one fixed
port; two pairs on one machine need a port each, passed the same way as the role.

## Symptom → cause

| Symptom | Cause |
|---|---|
| Every run queues forever | A lane's holder is alive but hung, or every lane is skipped for an open Editor or an unclaimed lockfile. `lanes.sh status` names which |
| One lane is never picked | A human opened that lane's folder in the Hub, or a killed run left `Temp/UnityLockfile` there. Delete it only once nothing runs |
| A clone lane: exit 0, no results file, log ~45 lines | A stale lockfile inside that lane (`reference/harness-trust.md`) |
| A clone lane: exit 0, no results file, `are blocked` in the log | ParrelSync's save block in a `.clone` folder (above) |
| Tests pass alone and fail in parallel | Shared save data or PlayerPrefs: a path that skips `LaneDataPath`, or a prefs key with no lane suffix |
| A reference is missing in one lane only; a `.meta` GUID changed in `git status` | Two lanes imported a new file at once. Compile once on lane 0 after adding files |
| A fresh lane reimports everything | Its `Library` was copied from an older Editor version, or while an Editor wrote it. Clean and set up again |
| The host times out naming `clientConnected` | The client lane queued, or is still compiling. Pin both lanes and cover a cold start in the timeout |
