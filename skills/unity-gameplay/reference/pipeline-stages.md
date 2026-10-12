# Production stages — each one ends on a check, not on a feeling

> Part of the `unity-gameplay` skill. Six stages from an idea to a shipped build. Each has one
> question it exists to answer, an exit condition written as something you run, and the skills
> that serve it. A stage is finished when its check passes — not when its work feels done.

| Stage | The question it answers | Exit, in one line |
|---|---|---|
| 1 · Concept | What is this, and seen from where? | A one-page brief with a perspective and movement block; the project opens at a pinned version |
| 2 · 3C prototype | Is moving, looking and pressing good on grey boxes? | One journey per C passes; the jump measures as designed |
| 3 · Vertical slice | Is one complete minute of the game worth making sixty of? | One level, one opponent, one full loop, on the target device |
| 4 · Production | Can content be made at the slice's quality, repeatedly? | Every level passes the reach check and has a journey |
| 5 · Polish and optimise | Does it feel right, inside the frame budget? | A person says yes to the feel; counters sit inside budget on the device |
| 6 · Ship | Does the store build behave like the tested build? | The signed artefact passes acceptance on a real device |

**Do not start a stage's work before the previous stage's check passes.** Art made before the
3C check is art fitted to a jump that will change; levels built before the slice are levels
built for a loop nobody has played.

---

## 1 · Concept

Decide the six constraints and write them down before a project exists.

```bash
test -s GAME_BRIEF.md && grep -n -i 'perspective and movement' GAME_BRIEF.md   # the block exists
grep -c 'INV-' GAME_BRIEF.md                                                    # at least three invariants
cat ProjectSettings/ProjectVersion.txt                                          # one pinned editor
python3 scripts/fingerprint.py . | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['unity'], d['packages']['source'], d['packages']['cinemachine'], d['input']['active_input_handler'])"
```

Exit when: the brief names dimension, projection, view, movement model and device; the lock
file resolves (`packages.source` reads `packages-lock.json`); the active input handler is the
one the brief chose; and `templates/GAMEPLAY_RECIPE.md` is filled as far as the numbers.

Skills: `unity-game-brief` for the brief and the look, `unity-new-project` for the project and
its packages, `codex-visual` when the look is locked with generated images.

## 2 · 3C prototype

Character, camera, controls — on untextured geometry, with placeholder capsules and squares.
The order inside the stage is fixed: controls, then character, then camera, then animation,
because each is tuned against the one before.

```bash
# Derived level numbers exist and the greybox obeys them (numbers from the recipe).
python3 scripts/level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 \
    --fall-multiplier 1.5 --gap 4 --height 2 --strict

# One journey per C, headless. Exit code and violations both matter.
"$UNITY" -batchmode -projectPath . -runTests -testPlatform PlayMode \
    -testFilter 'InputJourney|CharacterJourney|CameraJourney' \
    -testResults results.xml -logFile tests.log
python3 "$HARNESS/scripts/journey_report.py" --after "$JOURNEY_OUT/ledge-drop/timeline.jsonl" \
    --no-null cam --min pos.y:-1

# The jump the game performs is the jump the recipe states.
python3 scripts/jump_report.py "$JOURNEY_OUT/ledge-drop/timeline.jsonl" \
    --grounded-key grounded --apex 2.85 --air-time 0.718
```

`$HARNESS` is where the `unity-play-harness` skill sits; `$JOURNEY_OUT` is the directory the
recorder writes to.

Exit when: all three commands return 0 with a non-zero sample count; each journey has also been
seen to **fail** once, by breaking the thing it guards (coyote time to 0, the confiner removed);
and one person has played the greybox for five minutes and named nothing about movement.

Skills: `unity-input`, `unity-camera`, `unity-animation`, `unity-play-harness`; `unity-tilemap`
for a 2D greybox; `unity-3d-level` for a 3D greybox built to the numbers
(`unity-3d-level` → `reference/greybox.md`); `unity-3d-controller` for the 3D character and its
journeys (`Controller3DJourney` as the test filter); `unity-physics-3d` when a 3D contact does
not fire; `unity-debug` before believing any result file.

## 3 · Vertical slice

One level at final quality, one kind of opponent, one complete loop — start, play, win or
fail, and back to the start — with real art, sound and UI for exactly that much.

```bash
# The loop closes both ways: one journey reaches the win state, one reaches the fail state.
python3 "$HARNESS/scripts/journey_report.py" --after "$JOURNEY_OUT/slice-win/timeline.jsonl" \
    --monotonic state:Idle,Launched,Approach,AtGate --ready-before arrival
python3 "$HARNESS/scripts/journey_report.py" --after "$JOURNEY_OUT/slice-fail/timeline.jsonl" \
    --monotonic state:Idle,Launched,Approach,Caught

# Progress survives a restart: write, quit, relaunch, read.
"$UNITY" -batchmode -projectPath . -runTests -testPlatform EditMode -testFilter SaveRoundTrip \
    -testResults save.xml -logFile save.log
```

Then build for the target and run the slice there — the frame rate, the touch reach and the
load time of the Editor are not the device's.

Saving, briefly: the save is **one versioned document of
facts** — flags, counts, the room or cell the player is in — never a snapshot of scene objects;
it is written to a temporary file and moved over the old one so a crash cannot leave half a
file; and an EditMode test writes it, reads it back and compares, including one file from the
previous version.

Exit when: both journeys pass; the round-trip test passes; the build installs and the slice is
finished on the device by someone who did not make it.

Skills: `unity-game-ui` and the UI system it routes to; `unity-audio`; `unity-navigation` for an
opponent that paths; `unity-lighting` for the slice's final light in 3D (`unity-lighting` →
`reference/bake-setup.md`); `unity-rigged-character` or `unity-2d-sprites` for the character art;
`unity-android-release`, `unity-ios-build` or `unity-web-release` for the build;
`unity-device-testing` to run it.

## 4 · Production

The slice is the specification. Production is making the rest of the content to it, through
pipelines rather than by hand.

```bash
# Every level number is inside reach. One line per gap, "gap rise"; any failure stops the build.
while read -r gap rise; do
  python3 scripts/level_metrics.py --apex 3 --time-to-apex 0.4 --run-speed 8 \
      --fall-multiplier 1.5 --gap "$gap" --height "$rise" > /dev/null || exit 1
done < level-03.gaps

# Every level has a journey, and the whole set runs.
"$UNITY" -batchmode -projectPath . -runTests -testPlatform PlayMode -testFilter Journey \
    -testResults results.xml -logFile tests.log
grep -c '<test-case ' results.xml; grep -c 'result="Failed"' results.xml
```

Exit when: the content list in the brief is complete; every level passes its reach or
solvability check and its journey; and nobody has changed a controller number since the slice
without re-running the checks over every level.

Skills: `unity-2d-sprites`, `unity-sprite-atlas`, `unity-tilemap`, `unity-3d-models`,
`unity-rigged-character`, `blender-character-rig`, `codex-visual`, `comfyui-asset-generation`,
`unity-audio`, `unity-localization`, `unity-search` for finding what references what.

## 5 · Polish and optimise

Two different jobs that share a stage because both are judged against a number set earlier.

Feel: a complaint becomes a situation, a sampled quantity, a threshold and a before/after table
— `unity-play-harness` → `reference/complaint-to-test.md` — and the last step is a person
saying whether the new value is the feel they meant. That judgement is not automated.

Frame budget: measure on the device, change one thing, measure again.

```bash
python3 "$HARNESS/scripts/journey_report.py" \
    --before before/timeline.jsonl --after after/timeline.jsonl --max speed:12
```

Exit when: every open feel report has a before/after table and a yes from the person who filed
it; the counters named in the brief are inside budget on the slowest supported device; and the
3C journeys from stage 2 still pass unchanged.

Skills: `unity-profiling` for counters and comparisons, `unity-scene-optimisation` for the
change once a counter names the cost (LOD, occlusion, batching, culling distances, texture
memory), `unity-lighting` → `reference/shadows.md` for shadow cost and
`unity-lighting` → `reference/mobile-subset.md` for a phone, `unity-render-urp` for
post-processing on a budget, `unity-2d-pixel-perfect` for shimmer, `unity-debug` for reading what
a run actually did.

## 6 · Ship

Exit when: the signed artefact — not a development build — installs, starts, completes the
slice journey and survives a kill and relaunch on a real device, and the store-side
configuration it talks to is the production one.

Skills: `unity-android-release`, `unity-ios-build`, `unity-web-release`, `unity-device-testing`;
`unity-monetization`, `unity-iap`, `unity-ads-levelplay` where the game sells anything;
`unity-live-services` and `unity-ugs` where it talks to a backend.

---

## Three ways a stage is skipped without anyone deciding to

- **"We will tune the jump later."** Every level built before then encodes the untuned jump.
  Stage 2 exists so that later never arrives.
- **A slice with placeholder everything.** That is a larger prototype. The slice's whole job is
  to find out what final quality costs per minute of game.
- **Optimising in stage 3.** Before the slice is on the device there is no budget to be over.
  Measure there first; then decide.
