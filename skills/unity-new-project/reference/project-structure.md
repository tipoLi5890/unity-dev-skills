# Structure that survives growth

Moved out of SKILL.md §5: asmdef boundaries, the pure test lane, the input funnel, scenes, the art pipeline and generated assets.

## 5. Structure that survives growth

- **asmdef per module** (Input / Gameplay / UI / Integrations) — without
  them every script change recompiles everything, and layering violations
  are invisible. A native sensing package's Layer 0/1/2 split
  (capture → DSP → sensor, everything else `internal`) is the reference
  shape.
- **One assembly with `"noEngineReferences": true`** for scoring/state/decision logic buys a test
  lane that never opens Unity — and costs you engine serialization inside it. `JsonUtility` lives
  in UnityEngine, so it is unavailable there (and cannot parse dynamic JSON anyway: no
  dictionaries, unknown fields dropped). Adding an HTTP API, for example, means hand-writing a
  small JSON writer + parser inside that assembly while the `UnityWebRequest` client stays in the
  engine-referencing one. Decide the boundary knowing serialization sits on the wrong side of it.
  A ready-to-copy simulation / presenter / test skeleton already shaped this way — three asmdefs and
  the tests that run without a scene — lives in `unity-game-brief` resources.
- Write rule/decision classes as **plain C# with the clock and RNG seed injected** by the
  constructor, even when they live in an engine-referencing assembly. Then the only tests that
  cannot run under `dotnet test` are the ones touching `ScriptableObject`, `AssetDatabase`,
  `RectTransform`/`Canvas` or `JsonUtility` — which is what the boundary is *for*.
- **Run the pure assemblies' tests without the Editor**, with the compiler, runtime and NUnit the
  Editor already ships: `scripts/pure_tests.py run --tests <folder>` compiles each pure asmdef
  under its own name, excludes (and names) every test file that touches the engine, and exits
  0/2/3 in seconds. → `reference/pure-test-lane.md`
- **Single input funnel from day one**: gameplay depends on abstract actions, never on device
  specifics — touch, keyboard, gamepad and a sensing SDK all converge on one router (device
  details come from the sensing layer; the funnel is universal). The action asset and the struct
  gameplay reads: `unity-input`.
- Scenes: a bootstrap scene that loads content scenes additively beats one
  mega-scene — merge conflicts on a single scene file are unresolvable. The Boot scene and its
  services: `unity-scene-flow` → `reference/bootstrap.md`.
- Art pipeline: if assets are AI-generated, set up the art bible + grid
  workflow before mass production (`codex-visual`); 3D import/decimation
  discipline lives in `unity-3d-models`.
- **Assets a script generates are build output.** If a scaffolder recreates a ScriptableObject on
  every run, anything typed into the Inspector is silently lost at the next run — change the
  generator, rerun it, and keep a test pinning the values. Two traps that cost a debugging session
  each: `EditorSceneManager.NewScene` destroys ScriptableObjects that were never saved
  (`SaveAssets()` first, then re-`LoadAssetAtPath` after every scene change), and
  `EditorUtility.CopySerialized` wipes `m_Name` so `Resources.Load<T>(…).name` returns `""` →
  `reference/generated-assets.md`
