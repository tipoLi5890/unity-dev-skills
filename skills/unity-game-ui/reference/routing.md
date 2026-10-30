# Routing a UI request: fingerprint, ladder, request shape

> Part of the `unity-game-ui` skill. The detail behind SKILL.md §0: how to tell the UI system from
> the files, the default when nothing tells you, and how much a request is asking for.

## Fingerprint the project

**No explicit signal — fingerprint the project.** Scan assets and scripts, **not
`Packages/manifest.json`**: uGUI and UI Toolkit are both built into Unity 6, so the manifest
cannot tell them apart.

```bash
# Quote every --include pattern: unquoted, zsh expands it against the CWD and
# grep never sees the flag — zsh fails with "no matches found".
find Assets \( -name '*.uxml' -o -name '*.uss' \) | head            # → UI Toolkit
grep -rl 'UIDocument\|CreateGUI' Assets --include='*.cs' | head     # → UI Toolkit
grep -rl 'RectTransform' Assets --include='*.unity' --include='*.prefab' | head   # → uGUI
grep -rl 'void OnGUI' Assets --include='*.cs' | head                # → IMGUI
```

Read the result as a whole: all four empty on a project that clearly has UI means you are
looking at the wrong directory, not that the project has no UI system.

**There is no automated Figma import in this toolchain** — no importer, no service call, nothing
to enable. The conversion people have seen exists only inside Unity's own in-Editor assistant, and
there is no client-side equivalent to call, so promising one costs a round trip and produces
nothing. A design link is therefore a reading task: ask for a description or a screenshot of the
screen and build it with the system the routing lands on.

## The default ladder

1. Existing project → follow whatever it already uses. Consistency beats preference.
2. New runtime UI, no preference stated → **uGUI**.
3. Mobile, or a stated performance constraint → lean **uGUI**.
4. New *editor* UI → **UI Toolkit**; IMGUI only if the project is already all-IMGUI.
5. Mixed project → match the closest existing UI of the same kind (runtime vs editor).

**Then hand off.** uGUI → `unity-ui-ugui`. UI Toolkit → `unity-ui-toolkit`. Runtime `OnGUI`
stays here. This skill does not duplicate the other two.

## Decide what kind of answer the request wants

Routing says *which* skill. This says *how much*. Three request shapes, and the output of each is
different:

| Shape | The request sounds like | What comes back |
|---|---|---|
| Understand | "what does this button do", "how is this screen laid out", "how many panels are in here" | An explanation of the components, the hierarchy and the events. **No file changes at all.** |
| Edit | "make the gate label amber", "move the hazard pip left", "this panel is too tall" | A change to exactly what was named, and nothing adjacent. |
| Generate | "build a pause screen", "make a lane-select menu" | Only the files that screen needs. |

Three phrasings read as more than they are, and all three mean *visuals*:

- **"proper buttons"** — styled buttons, not a button controller.
- **"working UI"** — markup and layout that render correctly, not wired behaviour.
- **"a menu screen"** — the arrangement of the screen, not the navigation between screens.

> **Do not add scripts unless the request asks for behaviour.** A `MonoBehaviour` nobody asked for
> is a file to review, a reference to wire, and a second owner of the layout. The signal is
> explicit — "with code", "make it functional", "hook up the logic", a named callback — and in its
> absence the honest move is to build the visuals and say plainly that nothing is wired yet.

Both system skills inherit this rather than restating it.
