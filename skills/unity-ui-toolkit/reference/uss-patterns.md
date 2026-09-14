# USS patterns: tokens, states, wrapping and selector cost

> Part of the `unity-ui-toolkit` skill. Read when the markup is already right and the styling is
> the work: a value repeated across twenty rules, hover/press/disabled states from one texture, a
> label that refuses to wrap, a panel background that smears when it stretches, or a rule that
> quietly loses to another rule. Properties that do not exist in USS at all are §1 of the skill.

## Two properties that are neither missing nor ordinary

§1 of the skill lists what USS does not have. These two are in neither column, and both cost a
round trip when assumed either way.

> **`filter` does exist.** A common belief is that USS lacks it; it is wrong. Check what it
> actually does on your version before using it; "it exists" is not "it behaves like the CSS one".

**`transition-property` also exists.** The restriction is on its **values**: naming a specific
property is ignored. Use `none` / `initial` / `inherit`, or leave it out and let the other
`transition-*` properties do the work.

## Custom properties: name the value once

A custom property is any property whose name starts with `--`. Declare the set on `:root` and
read it back with `var()`; the values inherit down the tree, so a child rule reads the same token
without re-declaring it.

```uss
:root {
  --space-1: 6px;
  --space-2: 12px;
  --space-3: 20px;
  --lane-width: 96px;
  --surface: rgb(22, 24, 28);
  --surface-raised: rgb(34, 37, 43);
  --text: rgb(238, 240, 244);
  --hazard: rgb(214, 84, 58);
}

.hud-panel {
  padding: var(--space-2);
  background-color: var(--surface);
  color: var(--text);
}

.hazard-pip {
  width: var(--space-3);
  background-color: var(--hazard);
}
```

Three things this buys, and one thing to watch:

- **Retuning the courier HUD for a tablet read at 2–3 m is an edit to `:root`**, not a sweep
  through every rule. Spacing and type sizes are the ones that move together.
- **A token names a role, not a colour.** `--hazard` survives the day the hue changes;
  `--orange` becomes a lie. The same argument as `unity-game-ui`'s "one palette entry, one
  meaning".
- **A token can hold any value a property accepts** — a length, a colour, a keyword.
- **`:root` is the root of the tree the stylesheet is applied to**, not "the whole game". A
  stylesheet attached to a nested `VisualTreeAsset` resolves `:root` against *that* tree's root,
  so tokens declared in a parent document are visible only through inheritance. If a token reads
  as empty in a nested panel, that is the reason before it is a typo.

## One texture, four states

Shipping `gate-button.png`, `gate-button-hover.png`, `gate-button-pressed.png` and
`gate-button-disabled.png` costs four import slots, four places to update, and four chances for
one of them to drift. Ship one texture and tint it per state:

```uss
.gate-button {
  background-image: url("project://database/Assets/UI/Textures/gate-button.png");
  transition-duration: 0.12s;
}

.gate-button:hover    { -unity-background-image-tint-color: rgba(255, 246, 222, 0.22); }
.gate-button:active   { -unity-background-image-tint-color: rgba(18, 20, 26, 0.28); }
.gate-button:disabled { -unity-background-image-tint-color: rgba(140, 140, 140, 0.55); }
```

`-unity-background-image-tint-color` multiplies into the background image only — it does not
touch text, borders or child elements, which is what makes it safe to drive from a pseudo-state.

Two traps travel with this:

- **The transition lives on `.gate-button`, not on `:hover`.** On the state the property only
  exists while hovering, so it animates in and snaps back out. This is §2 of the skill and it is
  the single most common USS mistake.
- **A tint is not a contrast fix.** A 22% warm-white wash over a mid-grey plate moves luminance
  contrast by a fraction of a stop; at 2–3 m that reads as "nothing happened". Aim for a
  luminance separation you can measure between the two states, and add a second channel (a
  border, an offset) when the hue is doing the work alone:
  `unity-game-ui` → `reference/colour-and-contrast.md`.

## A label does not wrap until you say so

The default is to keep the line intact and let it overflow its box, so a hazard-warning string
that fits on the authoring monitor becomes one clipped line on a narrower panel:

```uss
.hazard-caption {
  white-space: normal;   /* wrap at the box edge */
  overflow: visible;     /* do not clip what the box cannot hold */
}
```

`white-space: nowrap` is the other value and is what you want on a single-line counter where a
second line would push the layout around. **Confirm the default on your version** by setting a
long string on a fixed-width label and looking at it — the value the inspector reports is the
computed one, and that is the answer.

Wrapping interacts with flex: a label inside a `flex-direction: row` parent is sized by the row
before it is wrapped, so a caption that still will not wrap usually has a parent that gave it
infinite width. Give the label `flex-shrink: 1` (or the row a bounded width) and the wrap
appears.

## 9-slice: one panel texture at every size

A gate panel, a sentry callout and an inventory slot are the same bordered plate at three sizes.
Stretching one texture across all three rounds the corners differently in each. Slicing does not:

```uss
.plate {
  background-image: url("project://database/Assets/UI/Textures/plate.png");
  -unity-slice-left: 14;
  -unity-slice-right: 14;
  -unity-slice-top: 10;
  -unity-slice-bottom: 18;
  -unity-slice-scale: 1;
}
```

- The four `-unity-slice-*` values are **source-texture pixels**, measured inward from each edge.
  They mark the border regions that must not stretch; everything inside them is what stretches.
- **Each edge takes its own number, matching that edge's artwork.** The plate above has a heavier
  lip along the bottom than along the top, so its bottom inset is the larger one. Four equal
  values are a special case, not the rule.
- `-unity-slice-scale` multiplies the drawn size of those border regions. Leave it at `1` unless
  the UI is scaled up as a whole and the borders come out too thin.
- **The slice values have to fall inside the texture.** Left plus right greater than the texture
  width leaves no middle to stretch, and the result is a plate that looks corrupted rather than
  an error.
- A slice value of `0` on one edge is legitimate — a bar that stretches horizontally and is fixed
  vertically wants `left`/`right` set and `top`/`bottom` at `0`.

Whether a newer version also offers a tiled (rather than stretched) slice mode is worth
**confirming on your version** before assuming the middle region repeats.

## Selector cost: `>` beats a space

Style resolution walks ancestors for every element. A descendant selector (`.a .b`) has to walk
the whole chain to the root before it can rule itself out; a child selector (`.a > .b`) checks
one parent and stops.

```uss
/* cheaper — one parent check per link */
.hud > .lane-row > .lane-label { }

/* dearer — walks every ancestor */
.hud .lane-row .lane-label { }
```

On a three-lane HUD the difference is noise. On an inventory or a scrolling run log where the
same rules apply to hundreds of elements it is not, and it compounds with the other costs in §7
of the skill — hierarchy size first, `:hover` on a many-child parent second, class count third.

The cheapest selector of all is one class, matched directly. Prefer adding a class to reaching
for a deeper path: `.lane-label` beats `.hud > .lane-row > .lane-label` on both cost and
readability, and it survives someone inserting a wrapper element.

## Specificity, and how a rule loses

When two rules set the same property on the same element, the more specific one wins — and
"specific" is counted, not judged. Roughly, from weakest to strongest:

| Form | Example | Beats |
|---|---|---|
| Type selector | `Label` | nothing above it |
| One class | `.lane-label` | type selectors |
| Class plus pseudo-state | `.lane-label:hover` | one class |
| Two classes, or a descendant path | `.hud .lane-label` | one class |
| Name selector | `#laneLabel` | classes |
| Inline `style=` in UXML | — | everything, and cannot be overridden |

Equal specificity is settled by order: the later rule wins, and a later *stylesheet* on the
element wins over an earlier one.

So when a style "does nothing", walk this ladder before doubting the property:

1. **Does the property exist?** §1 of the skill — an unsupported property is ignored silently,
   and that failure looks identical to this one.
2. **Is a more specific rule setting it?** Search the stylesheet for the property name, not for
   the selector you wrote.
3. **Is it set inline?** `style="…"` in UXML outranks every stylesheet and is why the skill bans
   it outright.
4. **Is it set from C#?** `element.style.x = …` writes the same inline layer as `style="…"` and
   wins for the same reason. A one-off C# style write in a setup method is the usual cause of
   "the USS rule only applies until the screen opens".
5. **Is the element the one you think it is?** A class on the wrapper and a rule aimed at the
   child is the other half of this.

Never define the same selector twice in one stylesheet. The second definition wins, the first
looks live, and the next person edits the wrong one.

## Checks

- Read the computed value back rather than trusting the rule: a property that does not exist and
  a property that lost to a more specific rule both leave the Console clean.
- Look at the screen at two window sizes. A 9-slice with bad slice values only misbehaves once
  the element stretches.
- Hover, press and disable anything interactive, and check the tint actually separates the states
  at the real viewing distance rather than on the authoring monitor.
- Set a deliberately long string into every label that takes runtime text. Clipping is the
  symptom `white-space` exists to prevent, and an authoring-time placeholder never triggers it.
