# Editor yes, build no: the first frames and the physics step

Part of the `unity-physics-3d` skill. SKILL.md §6 states the rules; this file holds the two that
need the detail.

- **The first frames of a player are not the first frames of the Editor.** The Editor has been
  stepping PhysX since the domain reloaded; a fresh player has not, so anything that spawns in
  `Awake` and expects a resolved contact before the first `FixedUpdate` can behave differently in a
  build. Two ways out, cheapest first: hold the collider (or the object) disabled for one frame from
  a coroutine in `Start`, or take ownership of the step —
  `Physics.simulationMode = SimulationMode.Script`, then call
  `Physics.Simulate(Time.fixedDeltaTime)` yourself once the scene is assembled, and set the mode
  back. `SimulationMode` is `FixedUpdate, Update, Script`, `Physics.simulationMode` reads
  `FixedUpdate` by default, and `Physics.Simulate` is present. Older code sets
  `Physics.autoSimulation = false` for the same effect; that property still exists and still works,
  carrying `[Obsolete("Physics.autoSimulation has been replaced by Physics.simulationMode")]` as a
  **warning, not an error**, so it compiles and nobody notices. Treat the ordering symptom itself
  as the hypothesis to test with the one-frame delay, not as a diagnosis.
- **Set Fixed Timestep deliberately, per platform.** `Project Settings → Time → Fixed Timestep` is
  the physics step, and a project that never touched it ships whatever the default is —
  `Time.fixedDeltaTime = 0.02`, i.e. 50 Hz. A build running at a different step than the Editor gets
  different tunnelling, different force integration and different contact counts from the identical
  scene, which is exactly the shape of "it works in the editor". Write the number down in the
  project settings rather than inheriting it, and change it knowingly: halving the step doubles the
  physics cost.
