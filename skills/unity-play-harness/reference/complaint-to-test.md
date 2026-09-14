# Turning a feel report into a repeatable test

> Part of the `unity-play-harness` skill. The method that converts "it comes in too fast" into a
> situation, a sampled quantity, a threshold and a before/after table — and says which part of
> the judgement stays with the person who filed it.

A feel report is not vague. It is *specific about an experience* and silent about the mechanism,
which is exactly the right division of labour: the person feels, the harness measures. What goes
wrong is answering it with a guess and a code change, because then neither side can tell whether
anything improved.

Five questions, in order. Each one has a wrong answer that is worth naming.

## a · Which situation, with which parameters?

The complaint happened somewhere. Name the moment as a situation id, and the variation as
parameters — `approach-gate` with `angle=80`, `hazard-lane` with `cold=true`.

If no existing situation covers it, **add one before changing any game code.** A complaint that
cannot be entered on demand cannot be confirmed fixed; it can only be declared fixed.
→ `reference/situations.md`

Wrong answer: "it happens sometimes during a run". That is a situation that has not been found
yet, not a bug that is intermittent.

## b · What quantity would have been different?

Turn the feeling into something in the probe line. "Too fast" is `speed`. "Disappears" is
`ready.laneMesh` and `ready.laneCollider`. "Inconsistent" is `custom.lodLevel` at two distances.
"Sluggish" is time-to-threshold: the sample index where `speed` first exceeds a value.

If nothing in the line could have been different, the probe is missing a key — add it with
`GameProbe.Register` and re-run. → `reference/probe-contract.md`

Wrong answer: sampling twenty quantities in case one of them moves. A timeline nobody reads
proves nothing, and the report then has twenty columns and no claim.

## c · What is the threshold, and where does it come from?

A number with no source is a number invented to make the test pass. Thresholds come from, in
descending order of trust:

1. **A stated design constraint** — the budget written down when the feature was specified. That
   is what `unity-game-brief` produces, and the invariant should quote its identifier.
2. **The measured behaviour of the version people liked**, recorded as a timeline before the
   change that broke it. This is the argument for keeping one.
3. **A value agreed in this conversation**, written into the test with the sentence that agreed
   it, so the next person reads the reason rather than the constant.

Wrong answer: the value the current build happens to produce, rounded up.

## d · The before/after table

Record the journey, change one thing, record it again, and put the two next to each other. One
change at a time — two changes and a moved number attribute to whichever one you already
believed. → `reference/timeline-format.md`

## e · What stays with the human?

Everything about whether the new value is the *right* value. The harness proves the number moved
where it was aimed and that nothing else moved with it. It cannot prove the game feels better,
and a report that claims it does is claiming something it did not measure.

So the message back ends with a question, not a conclusion.

---

## Three worked rows

**"Coming in sideways it still hits the gate too fast."**

| | |
|---|---|
| Situation | `approach-gate`, `angle=80` — the sideways entry, made repeatable |
| Sample | `speed`, `custom.gateDist`, `custom.lane`, every frame |
| Invariant | `speed` where `gateDist < 2` stays under the gate's stated maximum entry speed |
| Test | `JourneyAsserts.Never(samples, s => s.Number("gateDist") < 2f && s.speed > 12f, "entry-speed")` |
| Report | `--max 'speed:12@gateDist<2'` with `--before`, two rows: median and worst |
| Human | Whether the slower arrival still reads as an arrival rather than a stop |

**"The lane disappears while it loads."**

| | |
|---|---|
| Situation | `hazard-lane`, `cold=true` — forces the streamer to drop and rebuild the section |
| Sample | `ready.laneMesh`, `ready.laneCollider`, `allReady`, `counts.hazards`, every frame |
| Invariant | The two members are never in disagreement, and `allReady` holds before `arrival` |
| Test | `JourneyAsserts.ReadyBefore(samples, "arrival", s => s.Number("gateDist") < 20f)` |
| Report | `--together laneMesh,laneCollider --ready-before arrival` |
| Human | Nothing, unless the fix delays the whole moment — then whether the wait is acceptable |

This is the one that most often turns out to be a readiness-set bug rather than a rendering bug:
the mesh became visible one pass before its collider existed, so for two frames the runner is
drawn on a lane it can fall through. **Both members flipping in the same sample is the fix**, and
`--together` is how it stays fixed. → `reference/situations.md`

**"The gate looks inconsistent close up and far away."**

| | |
|---|---|
| Situation | `approach-gate` twice, `distance=40` and `distance=4` |
| Sample | `custom.lodLevel`, `custom.gateDist`, plus a milestone screenshot at each distance |
| Invariant | Only that the level actually changed between the two runs — the rest is a judgement |
| Test | A journey per distance; assert the two `lodLevel` values differ, and capture both PNGs |
| Report | The two images side by side, each labelled with its distance and level |
| Human | **The whole verdict.** Two silhouettes reading as the same object at 2–3 m from a propped-up tablet is not something a number decides |

Note what the third row does not do: it does not invent a contrast or edge-energy threshold and
declare the complaint resolved. It makes the comparison cheap and honest, and hands it over.
→ `unity-debug` → `reference/visual-checks.md`

## Closing the loop

1. **Re-run the same journey, same situation, same parameters.** A different situation produces a
   different number and answers a question nobody asked.
2. **Put the two tables side by side** and say which invariant now holds that did not before.
3. **Attach the milestone screenshots**, the same milestone from both runs.
4. **Ask them to play it again** — naming the one thing you changed and the one thing you did not.

```
Entry speed at the gate, approach-gate angle=80, 74 samples:
  median 11.4 → 9.6, worst 13.4 → 11.6, budget 12 (was exceeded on 3 frames, now 0)
Screenshots: journeys/approach-gate/01_arrival.png, before and after.
Changed: gate braking starts 0.4 units earlier. Nothing else.
Does the arrival still feel like an arrival, or does it now read as a stop?
```

That last line is not politeness. The number moved because it was aimed at; whether the game is
better is a different claim, and the person who filed the report is the only instrument for it.
