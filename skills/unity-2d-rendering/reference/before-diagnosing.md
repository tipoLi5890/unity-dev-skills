# Before diagnosing — the two reports, and how the turn ends

`SKILL.md` §0 in full: every later section depends on what these two reports say.


Work on a live Editor, not on files — `unity-debug` → `reference/editor-control.md`. Two
reports come first, because every later section depends on what they say.

1. **`Renderer2DSetup.Report()`** — the pipeline asset in force for the current quality level,
   its renderer list, which renderer is the default, and the sort mode and axis on each 2D
   Renderer. Three outcomes:
   - `pipeline` is `built-in`: there is no `Light2D`, and the sort axis lives on the camera
     and under Project Settings → Graphics.
   - URP with `renderer2DInForce` false: sprites sort by the camera's own axis and lights do
     nothing. The create command in the same file adds a 2D Renderer after reporting.
   - URP with a 2D Renderer in force: the renderer asset's Transparency Sort Mode and Axis are
     the only ones read. A value under Project Settings or on the camera is ignored.
   A URP asset can sit in the project and be assigned nowhere: `unity-render-urp` →
   `reference/resolve-active-pipeline.md`.
2. **`SortingAudit.Json()`** — every renderer in the open scenes with its four keys, its
   `SortingGroup`, its sort point, whether its material is lit, and the pairs that tie.

Then two rules for how the turn ends:

- **Answer from the frame.** The Frame Debugger (Window → Analysis → Frame Debugger) shows the
  order things were drawn in; a later event is on top. Where the audit and the frame disagree,
  the frame is right.
- **Change the key that decided, and only that one.** Raising Order in Layer on an object whose
  sorting layer already lost changes nothing and leaves a wrong number behind for the next
  person. Record and restore any setting changed while probing.
