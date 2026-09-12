# Reviewing a UI with multiple agents

A structured critique finds things a single pass will not, but only if it is aimed. Unaimed, it
produces a generic UX lecture. Aimed, its adversarial pass thins the findings to the ones that
hold, and its synthesis can overturn one of its own reviewers' central recommendations.

**Only run this when the user has explicitly asked for multi-agent orchestration.**

## Shape

```
Critique   4 lenses in parallel, high-capability model
             UI-visual · UI-implementation · UX-flow · UX-ergonomics
Challenge  cross-assigned: each lens's findings are attacked by a DIFFERENT lens
Synthesis  dedupe, resolve the UI-vs-UX conflicts, rank by impact ÷ effort
```

Cross-assignment matters: nobody grades their own work, and every finding is read by someone with a
different bias.

## The brief does the work

Give every agent the same brief, and put four things in it:

1. **The constraint that changes everything.** Here: the player *plays at 2–3 m from a propped-up
   tablet*, so legibility at distance beats thumb ergonomics, and any screen whose primary action
   the game's own inputs cannot reach is broken — so name those inputs in the brief (here, a
   gamepad, with three controls bound). Without this the critique regresses to generic mobile
   advice.
2. **The deliberate architecture**, marked as deliberate. "The UI is IMGUI with no Canvas; this is
   intentional and survives the scene reload a retry triggers. Do not propose porting it unless you
   can show something genuinely impossible otherwise."
3. **The real artefacts** — absolute paths to sources *and* to screenshots. Agents that can read
   images will measure pixel relationships; agents given only prose will speculate.
4. **What a good finding looks like**: names the file:line or the screenshot, cites evidence
   actually observed, states the consequence for a real player, proposes a fix implementable inside
   the constraints. Tell them to reject their own platitudes.

Force structured output with a schema (`severity`, `where`, `evidence`, `consequence`, `fix`,
`effort`) so synthesis operates on data rather than prose.

## Make the challenge phase actually adversarial

Default the challenger to **refute**:

> "refuted" — factually wrong about this build, OR the fix would make things worse, OR it is a
> platitude. "overstated" — something real, but the severity is inflated; give the honest version.
> "confirmed" — only when you verified it yourself. If you cannot verify it from the code or the
> image, refute it.

Expect mostly `confirmed` and `overstated` with `corrected_fix` filled in. Zero refutations does not
mean the phase was useless — check the verdict distribution before saying so. (The corrections can
be substantive: one proposed fix would have created a new colour collision.)

## Synthesis earns its place on the conflicts

The one thing only synthesis can do is arbitrate where UI wants restraint and UX wants prominence.
Ask for the call **and the reasoning**, and require it to name only real conflicts.

Examples of real conflicts:

- *Distance boost vs. a disciplined scale* → do the fit-to-width extraction **first**, then the
  scale, then the boost, and make the boost role-based. Applying the multiplier first would ship
  overflowing buttons.
- *Bigger type vs. less type on a prompt* → cut the words. At a size that survives 2 m the sentence
  spans the frame — and it was factually wrong anyway.
- *A result screen offering more actions than the game binds* → the third action is provably
  unreachable, so two of the three bound controls would do the same thing. Ship two and print
  exactly that.

## Then verify the plan yourself

The panel is a source of hypotheses, not of truth. Before implementing, check its factual claims —
they will be specific enough to check, and that is the point of demanding `file:line`. And when a
recommendation turns out wrong in practice, say so with the evidence: a blanket type multiplier
implemented exactly as specified, screenshotted, and reverted because it bursts the layout — which
the synthesis itself warns about, in a paragraph the implementation missed.
