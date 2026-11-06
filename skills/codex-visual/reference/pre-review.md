# pre-review — the agent reads the sheet first, a person reads what it flagged

Several stages of a character end with a person looking at pictures: the views, the 8-view mesh
sheet, the painted turntable, the assembly compare, the game-mesh side-by-side, the markers and
pose renders, the retarget stills, the Unity screenshot. Before the person looks, the agent
running these skills reads the same sheet and answers a fixed list of yes/no defect questions.
`scripts/prereview.py` composes the sheets, records the answers as `review/1`
(`schemas/review-1.json` in the plugin repo) and names the items a person must look at. The
agent reads the images in its own session: no API call, no model download.

A pre-review never approves anything. The person still approves with
`registry.py status ID approved` (`art-asset-registry`).

## 1. Why it is built this way

- **A fixed checklist of binary defect questions.** Each question asks whether something is
  wrong, so `defect` always means a fault and `clear` means it is not there. Open questions
  ("does it look good?") drift from one run to the next.
- **A few views are enough.** Six views of an object find most visible defects; the stage sheets
  already have that many.
- **A picture-reading model is a weaker judge than a trained person.** So the result is a
  pre-review that narrows what the person reads, never a gate.
- **Position bias is real.** A judge reads some cells of a grid more carefully than others. Each
  checklist is answered twice: on sheet a (the spec's cell order) and on sheet b (the same cells
  shuffled, labels moving with their images). Two passes that disagree are flagged. A sequence
  (S8's stills, A2's frames) is reversed on sheet b instead, so each frame keeps its neighbours and
  a one-frame pop or a loop seam can still be read.

## 2. The flow

```bash
python3 <skill>/scripts/prereview.py list --stage S3              # the checklist, before looking
python3 <skill>/scripts/prereview.py list --json                  # every stage, as JSON
python3 <skill>/scripts/prereview.py new --stage S3 --spec ArtDirection/qa/runner_qa.json \
    --subject out/runner_r03/runner.glb --out ArtDirection/review/runner_r03_s3 \
    --require out/runner_r03/inspect.json \
    --reviewer claude --model NAME
python3 <skill>/scripts/prereview.py new --stage S3 --spec ArtDirection/qa/runner_qa.json \
    --subject out/runner_r03/runner.glb --out ArtDirection/review/runner_r03_s3 --force  # over an old draft
# look at ArtDirection/review/runner_r03_s3.a.png only; answer every item (pass a)
python3 <skill>/scripts/prereview.py answer ArtDirection/review/runner_r03_s3.review.json --pass a \
    --from pass_a.json                                            # {id: {answer, view, note}}
# then look at ArtDirection/review/runner_r03_s3.b.png only; answer every item again (pass b)
python3 <skill>/scripts/prereview.py answer ArtDirection/review/runner_r03_s3.review.json --pass b \
    --id s3.hole --answer defect --view left --note "a gap under the left arm"
python3 <skill>/scripts/prereview.py check ArtDirection/review/runner_r03_s3.review.json
python3 <skill>/scripts/prereview.py --selftest
```

1. **`new`** reads a `contact_sheet.py` spec with `items` (one sheet; a `sheets` spec is refused:
   pre-review each sheet from its own spec). It writes `NAME.a.png` in the spec's order,
   `NAME.b.png` with `contact_sheet.py --order` (the seed is taken from the subject's sha256, so
   the same subject always gives the same b; S8 and A2 reverse the spec instead, `seed` null), and `NAME.review.json`, a draft: the stage's
   checklist copied in, no answers. `--subject` is the file the sheet shows (the GLB, the painted
   GLB, the rig's `.blend`); its sha256 pins the review to those bytes. `--require` refuses as on
   `contact_sheet.py`: nothing is written while a numeric check fails. An existing review is kept
   unless `--force` is given. `--reviewer` (default `claude`) and `--model` name who answered.
2. **`answer`**, pass a: look at sheet a, and only sheet a. Answer every item.
3. **`answer`**, pass b: a fresh look at sheet b. Do not reread pass a's answers first.
4. **`check`** validates the review, needs every item answered in both passes, refuses a sheet or
   a subject whose bytes changed since the draft, writes `flagged` and `verdict` back and prints
   the flagged items with each pass's view and note.
5. **The person** reads the flagged items on the sheets, decides, and approves or rejects in the
   registry. Record the review first, so the approval can name it:

```bash
python3 registry.py ingest --json ArtDirection/review/runner_r03_s3.review.json --write
python3 registry.py status artdirection/models/runner/runner approved --approver lead \
    --evidence artdirection/review/runner-r03-s3-review
```

`ingest` refuses a draft and never changes a status. `registry.py check` warns `review-flagged`
when an asset is approved while its latest pre-review of the same bytes flagged items.

## 3. Answering

One answer per item and pass: `{"answer": "defect" | "clear" | "unsure", "view": label or null,
"note": "short text"}`.

- **`defect`**: the sheet shows the fault. `view` is the label of the cell it is in.
- **`clear`**: the sheet shows the place the question is about, and the fault is not there.
- **`unsure`**: the sheet cannot settle it (too small, hidden, cropped). Never guess `clear`.
- **`note`**: what and where, in a few words, for the person ("left elbow pinched"). Empty when
  clear.
- Judge from the pixels on that sheet alone: not from the gate numbers, not from an earlier
  review, not from what the stage is supposed to produce.

Two ways to record, both validated by `check`:

| Way | When |
|---|---|
| `answer --pass a --from FILE` (or `-` for stdin): `{id: {answer, view, note}}` | a whole pass at once: the least typing, every id and label checked on entry |
| `answer --pass b --id ID --answer A [--view L] [--note N]` | one item, or a correction |
| edit `answers.a` / `answers.b` in `NAME.review.json` by hand | accepted; `check` refuses anything malformed (exit 3) |

An id not on the checklist, an answer outside the three, or a view that is not a cell label exits
1. Any answer puts the review back to `draft` until `check` runs again.

## 4. What `check` decides

An item is flagged when either pass says `defect` or `unsure`, or the two passes disagree.

| Exit | Verdict | Means |
|---|---|---|
| 0 | `clear` | no item flagged; the person still approves |
| 2 | `flagged` | a person looks at the printed items first |
| 3 | — | malformed, an item unanswered, or a sheet or the subject changed since the draft (make a new draft) |
| 1 | — | usage |

## 5. The stages

`prereview.py list` prints every checklist; `--stage` picks one, `--json` prints JSON. The
checklists live only in the script.

| Stage | The sheet | Labels its questions name |
|---|---|---|
| S1 | the three-quarter image and FRONT, LEFT, BACK, RIGHT | `front`, `left`, `back`, `right` |
| S3 | the 8-view mesh QA sheet (`reference/review-sheets.md`) | `front`, `left`, `back`, `right`, `top`, `clay`, `occlusion`, `uv_atlas` |
| S3b | `turntable.png` from `mesh-texture-paint` | the yaws |
| S3c | `compare.png` from `blender-character-rig` part assembly | the four columns |
| S5 | the game-mesh side-by-side, clay and textured | front, side, back, game camera |
| S6 | `markers_front.png`, `markers_side.png`, then the `deform_gate.py --render` poses | `markers_front`, `markers_side`, the pose names |
| S8 | one clip's rest and wrist stills, beside the source | `rest`, the frames |
| S12 | the Unity screenshot under the game camera | — |
| A2 | a 2D clip's frames in order, after the approved still (`codex-visual` PHASE 3A; run `audit_identity.py` first) | `still`, `first`, `last`, the frame labels |

Label the cells with those names where they apply: a `view` must be one of the sheet's labels.
A stage with two kinds of picture (S6) is one sheet of both, or two reviews.

## 6. What pre-review cannot do

- **Approve.** Only a person does, in the registry.
- **Measure.** A sheet shows; the numbers live in the gates, and `--require` keeps a failing gate
  from reaching a sheet at all.
- **See what the sheet does not show.** Motion, a pose that was not rendered, the far side of a
  view, a defect smaller than a cell's pixels: `unsure` at best, usually nothing.
- **Replace the stage's own reading.** The stage's reference file says what a person checks; the
  checklist is a short list of the common faults, not the whole of it.
- **Stay valid after a change.** A new render, a remeshed GLB or a repainted texture needs a new
  draft; `check` refuses the old one.
