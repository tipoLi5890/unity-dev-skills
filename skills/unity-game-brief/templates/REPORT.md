# REPORT.md — the shape of every hand-back

<!-- Not a document to keep. This is the five-line shape of what the agent says when it hands
     work back to the human: numbers, one screenshot, one question. Anything longer is asking
     the human to do the reading that the agent was supposed to do. Copy the block, fill it,
     paste it; delete the file once the shape is habit. -->

```
Numbers:    <the number, its unit, over what sample, and the invariant it was checked against>
Invariant:  <INV-n held | INV-n broke: expected X, got Y>
Screenshot: <path> <the state logged next to it>
Changed:    <one line: what value or file moved, from what to what>
Question:   <one fork for the human, with the default you will take if nobody answers>
```

## Worked example

```
Numbers:    launch -> gate 27.72 s median, 27.73 s worst over seeds 1-5 (INV-3: 20-40 s, held).
Invariant:  INV-5 held over seeds 1-1000 — no row blocks all three lanes.
Screenshot: Shots/03_gate.png state=AtGate lane=1 pickups=4.
Changed:    LaunchSpeed 4.0 -> 4.4 in RunConfig.Courier().
Question:   arrival feels abrupt — keep the pass-through, or hold 0.3 s at the gate?
            Default: hold.
```

## The four rules the shape enforces

1. **A number, or it did not happen.** "Feels better" is the human's line, not the agent's. The
   agent reports what it measured and over what sample.
2. **One screenshot, with its state logged next to it.** A capture with no state line is a
   photograph of an unknown moment. More than one screenshot means the agent has not decided
   which one matters.
3. **One question.** Three questions is an unfinished proposal handed back as homework. Pick the
   fork that most changes what gets built next.
4. **A default for the question.** The human may be asleep. Work continues along the default,
   and the default is stated so that reversing it is one line, not a rewrite.
