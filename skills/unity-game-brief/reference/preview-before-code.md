# Preview before code

What to make, in order, so a person can see the game and an agent can read its intent before the
first gameplay script exists. Each artefact answers one question; each is made from a file that can
be run again, so a changed rule is a re-run, not a redraw.

> **A polished image is not proof of gameplay.** A preview communicates intent and timing. Whether
> the game is fun is settled by the greybox playable at the end of this list, and by nothing above it.

## The order

| # | Artefact | Answers | Made with |
|---|---|---|---|
| 1 | **Flow diagram** — the overall flow (boot → title → run → result → again) and the story flow (beats) | What screens and moments exist, and what leads to what | A plain node list or diagram in the project; each node gets an id |
| 2 | **Key art** — the locked anchor image | What it looks like at its best | §2 of the skill; `codex-visual` generates |
| 3 | **Screen mockups at the target resolution** — one per flow node that has a screen | What the player sees, at the size they see it | `codex-visual` (game screens, not posters); grouped with `codex-visual` → `reference/overview-sheets.md` |
| 4 | **Layout and keyframes** — where things stand in a moment, then generated stills that keep one camera | Whether the shots agree with each other | `comfyui-asset-generation` → `reference/h3-keyframe-segments.md` (`layout_map.py`, `camera_gate.py`) |
| 5 | **Timed animatic / simulated gameplay preview** — sprites moved by the game's own rules, with every sound logged | How long things take, and whether the rhythm reads | `scripts/preview_compose.py`, joined by `scripts/preview_reel.py` |
| 6 | **Greybox playable** — the first interaction | Whether it feels right in the hand | §5 of the skill |

Do not skip ahead. A preview made before the mockups invents a look; mockups made before the flow
invent screens nobody needs. Steps 1–5 together should take less time than step 6.

## The timings are written down

The preview is worth making only because its numbers are. Write the rules as constants in one
block (lane width, run speed, the gate's open window, pickup spacing), generate the timeline from
them, and copy the same constants into the brief. When the first build runs, the invariants are
checked against these numbers — the preview stops being a picture and becomes the first spec of
timing. A timeline keyed by hand ("the runner looks about here at 2 s") is a drawing, and nothing
can be checked against it.

`scripts/examples/courier_run_preview.py` is the worked case: placeholder shapes for the Runner, the
three lanes, the gate, the sentry and the pickups; every position derived from the constants block;
a `gate_pass` or `gate_hit` event when the Runner reaches a gate, and a `pickup` event for each pickup
in the Runner's lane. Its selftest checks the frame count against fps × duration, the encoded
duration within one frame, one event per rule trigger (and the count worked by hand from the
constants), and that two runs give the same events and the same frame hashes.

## The compositor in one paragraph

`preview_compose.py TIMELINE.json --out preview.mp4 [--sfx-dir DIR]`. The timeline lists sprites
(`assets`), layers with keys (`t`, `x`, `y`, `scale`, `alpha`, `rot`, `frame`) and one ease each
(`linear`, `in_out`, `out`, `step`), timed text, and events (`t`, `sfx`, `vol`). Each frame is
composited in `z` order and piped to ffmpeg; next to the video it writes `preview.events.json`
(every event with its frame, and one hash over all frames) and `preview.contact.png` (eight frames
with their times and the title-safe frame). With `--sfx-dir` the events are mixed and normalised to
−16 LUFS. The full schema is the script's docstring. Its text uses Pillow's built-in face, which
draws Latin letters, digits and ASCII punctuation only: write on-screen text in those (a `—` or
CJK text comes out as boxes), and put other languages on the reel's cards, which take a `font`.

`preview_reel.py REEL.json --out reel.mp4` puts title cards in front of clips, lays one music bed
under them, places each clip's events again at the clip's start, normalises the whole, and writes
`reel.timeline.json` with every card, clip and event in reel time and the integrated loudness it reads back.
Both list under `sfx_missing` every event name no sound file matched: a silent reel with `ok` is
not a finished one.

## Sprites for a preview

- **Placeholders first.** Coloured shapes with the right sizes and the locked palette roles answer
  the timing question as well as finished art, and change in seconds.
- **Generated sprites second**, cut out on transparency, one file per state or a horizontal strip
  with `frames`; a rigged character's preview-track clips rendered to frames work the same way.
- **Sizes in game units.** Pick pixels per metre once (the constants block) and draw every sprite at
  that scale; a sprite that is the wrong size makes a wrong timing look right.

## What each preview is checked against

| Artefact | The person says yes to | Recorded |
|---|---|---|
| Flow diagram | The list of nodes and arrows | Each node's status: `planned`, `mocked` (a mockup exists), `approved` |
| Mockup | One screen, at the target resolution | The mockup in the ledger with a `flow-node` link to `flow:<node>` |
| Preview | The rhythm: the gate window, the gap between pickups | The clip with a `beat` link to `beat:<id>`, and its events file |
| Reel | The whole sequence, watched once | The reel and its timeline file |

The ledger words are in `art-asset-registry` → `reference/ledger-schema.md` (rels `flow-node`,
`beat`). A node's status lives in the flow document; nothing validates it.

## When the preview and the build disagree

The build is right about feel; the preview is right about what was intended. When a playtest says
the gate window is too short, change the constant, re-run the preview, and show both — the number
that changed is the conversation, not the video.
