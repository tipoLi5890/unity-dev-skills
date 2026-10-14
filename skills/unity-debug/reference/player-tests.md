# The player leg: PlayMode tests inside a built player

An Editor PlayMode run executes the game inside the Editor: `UNITY_EDITOR` defined, editor-only code
loaded, the AssetDatabase underneath, nothing stripped. Give `-testPlatform` a `BuildTarget` name
and the Test Framework builds a player with the tests inside and launches it. The player reports
back over the network, and the Editor writes `-testResults` as usual. It costs a build per run, and
it is the only run that sees what the build does to your code and content.

## The run

| Target | `-testPlatform` | `-buildTarget` | Also needs |
|---|---|---|---|
| macOS desktop | `StandaloneOSX` | `OSXUniversal` | Mac build support (its IL2CPP variant for an IL2CPP player) |
| Android | `Android` | `Android` | Android build support; a device past the pre-flight in `unity-device-testing` |

The two flag columns come from different lists, a `BuildTarget` enum name and the Editor's command-line
names, so check both spellings on your version's command-line page. Never add `-quit`.

```bash
# One player leg from the lane's project root. bash 3.2. Never pipe it into tail.
TARGET="${TARGET:-Android}"; BUILD_TARGET="${BUILD_TARGET:-$TARGET}"
OUT="${OUT:-/tmp/courier_player_$TARGET}"; xml="$OUT.xml"; log="$OUT.log"
rm -f "$xml" "$log"; touch "$OUT.start"           # nothing stale may read as this run's
"$UNITY" -batchmode -projectPath "$PWD" -buildTarget "$BUILD_TARGET" \
  -runTests -testPlatform "$TARGET" -testCategory Player \
  -playerHeartbeatTimeout 300 -testResults "$xml" -logFile "$log"
rc=$?
run=$(grep -m1 -oE '<test-run [^>]*>' "$xml" 2>/dev/null)
n() { printf '%s\n' "$run" | sed -nE "s/.* $1=\"([0-9]+)\".*/\1/p"; }
t=$(n total); f=$(n failed); i=$(n inconclusive)
if [ -z "$run" ] || [ "${t:-0}" -eq 0 ]; then v=harness; code=3    # nothing was verified
elif [ -n "${EXPECT:-}" ] && [ "$t" -ne "$EXPECT" ]; then v=harness; code=3   # stopped part-way
elif [ "${i:-0}" -gt 0 ]; then v=harness; code=3                   # a check skipped itself
elif [ "${f:-0}" -gt 0 ]; then v=failed; code=2                    # a real verdict: no retry
else v=green; code=0; fi                                           # 3 outranks 2; failed= still prints
echo "[PLAYER] target=$TARGET verdict=$v total=${t:-0} failed=${f:-0} inconclusive=${i:-0}" \
     "expect=${EXPECT:--} unity_exit=$rc log=$(cat "$log" 2>/dev/null | wc -l | tr -d ' ')"
exit $code
```

- **`-buildTarget`** makes the target switch happen once, at startup. If every run on the same lane
  reimports for minutes, the two flags disagree.
- **`-playerHeartbeatTimeout`** is in seconds: how long the Editor waits for a sign of life from the
  player (documented default: 10 minutes). Set it lower so a player that never connects frees the
  lane. Time one run where the player cannot connect: if the clock also covers the build, set the
  value above your build time.
- **`-testCategory Player`** keeps the leg small, and `EXPECT` pins its size.

## What only a player run catches

| Fault | Why the Editor misses it | What the leg shows |
|---|---|---|
| Stripping removed a type reached only by reflection or named only in data | Nothing is stripped | A loader returns null. Fix: `[Preserve]` or `link.xml` → `unity-android-release` → `reference/size-and-stripping.md` |
| Code under a platform define (`#if UNITY_ANDROID && !UNITY_EDITOR`) | Never compiled in the Editor | The build fails; no results file |
| A serialized field inside `#if UNITY_EDITOR` | The two read different layouts | Player log: `different serialization layout` |
| State filled by `OnValidate`, `[InitializeOnLoad]` or another editor-only hook | They never run in a player | The state is empty after a scene load |
| `Application.isEditor` branches | Always `true` | The player takes the other branch |
| Content missing from the build: a scene outside the build list, an `AssetDatabase` load, Addressables in AssetDatabase play mode | The Editor reads `Assets/` | The runtime load fails |
| Start-up order: `Awake` order with no execution order set; statics kept with domain reload off | It keeps its own order and old statics | A cold start in a fresh process |

The player strips only what its target's Player Settings say, and a desktop Mono player may strip
nothing at all. Read the settings before believing a green: backend `1` is IL2CPP, and a target
missing from a map (`{}`) is on its default. `-testSettingsFile` can set `scriptingBackend` for the
test build; the stripping level is not among its keys.

```bash
grep -A8 -E '^  (scriptingBackend|managedStrippingLevel):' ProjectSettings/ProjectSettings.asset
```

## Example: the sentry roster survives the build

`Resources/Config/sentry_roster.json` names each lane's sentry patrol
(`"patrol":"Courier.Sentries.SweepPatrol, Courier.Runtime"`), and `SentryRoster.CreatePatrol`
resolves it with `Type.GetType` and `Activator.CreateInstance`. No code names the type, so a stripped
player loses it unless the class carries `[Preserve]`.

```csharp
// PlayMode test assembly: includePlatforms [], no UnityEditor reference (reference/cli-harness.md)
[Test, Category("Player")]
public void SentryRosterSurvivesTheBuild()
{
    RosterData roster = SentryRoster.Load();                    // the game's own Resources path
    Assert.IsNotNull(roster, "Resources/Config/sentry_roster.json is not in this build");
    Assert.Greater(roster.lanes.Length, 0, "the roster parsed to zero lanes");
    foreach (var e in roster.lanes)
    {
        // Never typeof(SweepPatrol) here: the test assembly would keep the type alive by itself.
        Assert.IsNotNull(SentryRoster.CreatePatrol(e.patrol),
            $"lane {e.lane}: '{e.patrol}' is not in the player; add [Preserve] or a link.xml entry");
        Assert.Greater(e.sweepSpeed, 0f, $"lane {e.lane}: sweepSpeed did not survive the build");
    }
    Debug.Log($"[PLAYER-ENV] backend={Backend} dev={Debug.isDebugBuild}");
}
#if ENABLE_IL2CPP
const string Backend = "IL2CPP";
#else
const string Backend = "Mono";
#endif
```

> **Prove the leg can go red.** Remove `[Preserve]` from one patrol type and expect `failed="1"`
> from the player, with the Editor still green. If the player stays green too, it does not strip
> that type at its current settings, and the leg is not guarding what you think.

## What it costs, and when to pay it

Each run pays for a player build, which takes minutes with IL2CPP, against seconds for a warm Editor
run. A Library on another target also reimports its platform-dependent assets first. Android adds
an install on an awake, unlocked device. The build is CPU-heavy, so never run it beside a
performance run. Run the leg after touching stripping, `link.xml`, asmdefs, defines, `#if` blocks,
Addressables groups or start-up code; before each release build; and nightly. Not on every edit.

## It writes into the project, so choose its lane

A player run is not read-only. It switches the active build target, which `Library/` keeps. It may
also change and restore settings and the scene list in `ProjectSettings/`, and leave a temp test
scene in `Assets/`. If Addressables builds content with the player, it writes content state under
`Assets/` as well. See `reference/parallel-runs.md` for lanes and the read-only rule.

> **Run the player leg on lane 0, or on one dedicated clone lane that only ever builds that
> target. Never run it on a general pool lane.** A pool lane flips its Library to the target of
> whichever job gets it next, and that job pays a reimport.

A dedicated lane is built like a pool lane, in its own directory outside the pool. Its Library stays
on the target, but it still links to the shared `Assets/` and `ProjectSettings/`. Confirm on your
project what one run touches: `git status --short` once mid-build and once after. Anything beyond
the `runInBackground` line (the restore is in `SKILL.md`) makes the leg asset-writing work. Then it
belongs on lane 0, and no other lane starts while it builds.

## Trusting the verdict

`reference/harness-trust.md` still applies, with three differences:

- **The Editor writes the results file only after the player reports back.** A missing file means
  the build failed or the player never connected: exit 3, not a retry.
- **The log includes the whole build.** Thousands of lines prove the Editor started, not that a
  single test ran.
- **Unity's exit code** is printed and not used. The codes in `reference/test-verdicts.md` were
  derived from Editor runs.

When the file is missing, look here. Calibrate the first pattern on one deliberately broken run:

```bash
grep -nE "error CS|Build completed with a result|Aborting batchmode|[Hh]eartbeat" "$log" | tail -8
find ~/Library/Logs -name Player.log -newer "$OUT.start"   # the macOS player's own log
adb logcat -d -s Unity | tail -40                          # Android; adb logcat -c before the run
```

The test's `[PLAYER-ENV]` line is in the player's log, and may also come back in the XML's test
output. Check which on your version.

**On Android, prove the channel before trusting a green.** One deliberately failing test must
arrive as `failed="1"`. The player and the Editor must share a network; when they cannot connect,
the device shows the tests passing and no XML is written. Prefer USB, because a build can restart
the adb server and drop a Wi-Fi device.

## Symptom → cause

| Symptom | Cause |
|---|---|
| No results file; the build succeeded and the player started | The player never reached the Editor (another network, a firewall, adb dropped) |
| `total="0"` | The test assembly is not in the player (`includePlatforms` limited to Editor), or the category matched nothing |
| `total` under `EXPECT` | The player died part-way; read the tail of its log |
| `git status` shows Player Settings edits | A run died before restoring them: restore the lines, never the whole file |

## When to move on to a real device

The player leg answers one question: do the code and content survive the build for this target? It
does not test the device. Move to `unity-device-testing` for hardware, permission dialogs,
lifecycle, anything a human does, and the artifact you actually ship. The test player carries test
assemblies and connects to the Editor, so release-only settings such as minification, log stripping
and signing are never exercised. `dev=` in `[PLAYER-ENV]` shows whether it is a development build.
Frame time on the device belongs to `unity-profiling`. A device failure that reproduces in the
player leg is cheaper to fix there.
