# The pure test lane: rules tests in seconds, with no Editor

> Part of the `unity-new-project` skill. Script: `scripts/pure_tests.py`.

§5 of the skill puts scoring, state and decision logic in assemblies with
`"noEngineReferences": true`. That buys a test lane that never opens Unity, and this page is how to
run it. In a tennis game whose whole simulation (ball physics, shot solver, rules, bots, replay)
lived in three pure assemblies, the rules tests (64, later 68) ran in a few seconds on a quiet machine, against
minutes for an Editor leg that has to queue for a lane. Agents ran them after every change to the
simulation, and no Editor was needed until the presentation changed.

## What the runner does

```bash
python3 scripts/pure_tests.py plan --project . --tests Assets/Tests/Rules   # what compiles, what is excluded
python3 scripts/pure_tests.py run  --project . --tests Assets/Tests/Rules [--filter Solver]
python3 scripts/pure_tests.py selftest [--e2e <a project whose Editor and Library exist>]
```

1. **Finds the tools inside the installed Editor**, from the version in `ProjectVersion.txt`: the
   .NET runtime it ships (`Scripting/NetCoreRuntime/dotnet`), its Roslyn compiler
   (`Scripting/DotNetSdkRoslyn/csc.dll`), and Unity's own NUnit build from the project's
   `Library/PackageCache/com.unity.ext.nunit@*/net40/unity-custom/`. Nothing is downloaded, and an
   Editor upgrade moves the tools with the project.
2. **Compiles each pure asmdef as its own assembly, under its asmdef name**, in dependency order,
   from its folder minus any subtree holding another asmdef (Unity's rule). One merged assembly
   would let a test see `internal` members the Editor refuses; separate ones keep
   `InternalsVisibleTo` honest. A pure asmdef that references an engine one is refused (exit 3).
3. **Compiles only the test files that are pure**, and prints every exclusion with its reason: the
   code names `UnityEngine` or `UnityEditor`, has a `using` for a namespace no pure assembly
   declares, matches `--exclude`, or uses a type declared in an excluded file (a shared fixture).
   Comments are stripped first, so a sentence about UnityEngine does not exclude a file.
4. **Runs them with NUnit's own runner** (`NUnitTestAssemblyRunner`), the API Unity's test
   framework drives, so `[TestCase]`, `[Values]` and `[TestCaseSource]` expand as they do in the
   Editor. The working directory is the project root, as in the Editor.
5. **Counts every leaf result, and a suite that failed with no failing leaf counts as a failure**
   (a fixture set-up or a `TestCaseSource` that threw). Exit 0 green, 2 a failed or inconclusive
   test, 3 a harness failure, including **zero tests run**: a filter that matches nothing is not
   green.

## What it is not

- **Not the verdict.** The Editor leg (`unity-debug` → `reference/cli-harness.md`) still runs every
  test, including the excluded ones. The pure lane is the fast loop in between.
- **Not Mono.** CoreCLR's maths library can differ from the Editor's in the last bits. A test with a
  tolerance tighter than that belongs to the Editor leg.
- **Not load-proof.** A timing assertion inside a pure test is as exposed to a busy machine as any
  other. Running this lane against the tennis simulation with the machine's load average at about 36
  (several agents, Blender and Editors running), a "the solver takes under 3 ms" test measured
  6.6 to 9.8 ms and failed, and the whole run took 48 to 100 s instead of seconds. Read
  `uptime` before believing a red timing test (`unity-debug` → `reference/parallel-runs.md`).
- **Not a workaround for a compile error.** A pure file that does not compile is a harness failure;
  never exclude it to get a green run.

## Test conventions that keep the lane useful

- A test that needs the repo root (to read a data file) finds it by walking up from the working
  directory to `ProjectSettings/ProjectVersion.txt`, or reads an environment variable that the
  runner passes with `--env NAME=path`. It never hard-codes a path.
- Keep fixtures that touch the engine in their own files, so the exclusion closure removes only
  them and not every test that shares a helper.
- Name the pure test asmdef's folder and pass it with `--tests`; the test assembly keeps that
  asmdef's name, so `InternalsVisibleTo("<Game>.Rules.Tests")` works in both legs.
