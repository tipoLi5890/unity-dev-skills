# codex-runtime — how the call is made and how the file is obtained

`SKILL.md` routes; this file holds the mechanics, not what to draw. Flags move with the CLI: when
one errors, read `codex exec --help` before this file.

## 1. Always `codex exec` (non-interactive)

The Bash tool **cannot drive a TUI**; bare `codex "..."` hangs. Always `codex exec ...`.

**`scripts/codex_generate.py` is the call for a generation.** `codex exec` exits 0 when the agent
model is rejected and when the image tool never ran, so the script proves the result instead:

```bash
python3 <skill>/scripts/codex_generate.py --prompt-file prompt.txt --out "$DEST" \
    -i <repo>/ArtDirection/anchors/master.png        # [-m MODEL] [--no-probe] [--timeout 600]
                                                     # [--expect-size 1672x941] [--shared-home]
                                                     # [--job-log PATH]
```

It probes the model with a one-word prompt (`--no-probe` once it has passed in a batch), runs from
a scratch directory under a private, temporary `CODEX_HOME` (§3), copies the **original** out of
its own session's `generated_images` folder (§2, §4), and prints its real `size` and whether it
carries `alpha` (an RGBA render was keyed by the agent — ask again for an opaque one). **Exit 2** =
`codex` missing, **3** = the model was rejected (pass another `-m`; a slug that worked yesterday
can be refused today), **4** = the call ran and made no image, **5** = it made more than one: all
are written (`DEST`, then `<stem>.2.png`, `<stem>.3.png`, … in render order) and listed under
`images`, and none is chosen — look at them, **6** = `--expect-size WxH` did not match (±1 px by
default, because one 16:9 ask has come back both 1672x940 and 1672x941; the file is written so
it can be looked at). 5 wins over 6.

Every object it prints also pins the call for skill `art-asset-registry`: `model` (the `-m`
value, `null` for the config's) and `record` (the call's partial ledger record — tool, params,
inputs, files and a verdict: `green` on exit 0, `failed` on 4, 5 and 6, `harness` on 2 and 3);
once the prompt has been read, `prompt_sha256` (of the prompt file's bytes, or of `--prompt` as
given; the object carries the hash, not the text) and `inputs` (each `-i` with its `sha256`). A
written image adds `out_sha256`. `--job-log PATH` appends that object as one JSON line with `ts`
and `exit_code` (this script's; `exit` on exit 4 is codex's own); should an `ERROR` line in
`detail` quote the prompt, the log line has `<prompt>` in its place, and any URL (an endpoint
with its query string) reads `<url>` there; stdout keeps both. The rules below are what it
does, and what a call made by hand has to do.

- **Generation must be allowed to write:** `--sandbox workspace-write --skip-git-repo-check`. The
  `exec` default is read-only and **silently blocks the save**.
- **`< /dev/null`** — from a non-TTY tool `codex exec` otherwise waits on stdin.
- Bash `timeout: 600000` (generation is slow), **absolute paths**, and a **single-quoted prompt**
  so `$imagegen` is not shell-expanded.
- **`-i` is variadic → prompt FIRST, `-i` LAST.** `codex exec -i img "prompt"` swallows the prompt
  as another image ("No prompt provided via stdin"). Correct: `codex exec "prompt" -i img`
  (analysis) and `codex exec --sandbox … '$imagegen …' -i anchor.png` (generation).
- **Analysis is read-only** — no `--sandbox` needed.
- **Don't generate trivial shapes / flat icons** — the imagegen skill code-draws those instead of
  using the model (a "blue circle" returns a procedural PNG). Use it for real raster art.
- **Write the generation prompt in English** — tighter control over layout, cell-to-cell uniformity
  and glyph placement. A project's `STYLE PREAMBLE` may stay in its authored language.
- **Auth:** the built-in tool needs no `OPENAI_API_KEY` — it uses the ChatGPT login (`codex login
  status`; `codex doctor` diagnoses install and auth).
- **A pinned model slug that errors** — `-m` in a saved recipe, or `model =` in
  `~/.codex/config.toml` — is the classic sudden failure. Pass `-m` explicitly and check what this
  build accepts with `codex exec --help`.

If codex is missing: **stop and ask the user** to install it (`npm install -g @openai/codex` or
`brew install codex`, then `codex login`). Never auto-install.

## 2. Where the file lands — `-C` does NOT isolate it

The built-in tool saves **only** to

```text
$CODEX_HOME/generated_images/<session-id>/exec-<uuid>.png
```

`$CODEX_HOME` = `~/.codex`, and the directory name is the session id — the one `codex exec` prints
in its header as `session id: …` (the folder and the session's rollout file carry the same id).
`-C` moves the agent's shell cwd, not the save path. The image tool also leaves a copy under
`output/` in the working directory — run from a scratch directory, never the project root — and a
workspace copy appears on the flat-vector detour (§6).

**Never take "the newest PNG".** Every codex session on the machine writes under the same
`generated_images/`, so the newest file is whatever any session rendered last, and a before/after
diff of the whole folder still collects a concurrent job's render. In one project a storyboard
keyframe came back as another job's pixel-art character (once; the size was the giveaway), and a
call that rendered twice was silently resolved to one of the two (8 of 35 concept screens, all
in the first two rounds). `codex_generate.py` does the capture by session; by hand:

```bash
DEST=/abs/target.png; LOG=$(mktemp)
codex exec --sandbox workspace-write --skip-git-repo-check "$PROMPT" -i "$MASTER" < /dev/null > "$LOG" 2>&1
SID=$(sed -n 's/^session id: *//p' "$LOG" | head -1)
set -- "${CODEX_HOME:-$HOME/.codex}/generated_images/$SID"/*.png
if [ -n "$SID" ] && [ "$#" -eq 1 ] && [ -f "$1" ]; then cp "$1" "$DEST"; file "$DEST"
else echo "expected one image in session '$SID', got: $*"; fi   # two: look at both, choose
```

## 3. A private `CODEX_HOME` per call — the script's default

```bash
CH=$(mktemp -d)                                 # one private CODEX_HOME per call or job
ln -s ~/.codex/auth.json "$CH/auth.json"; cp ~/.codex/config.toml "$CH/"
CODEX_HOME="$CH" codex exec …                   # then read "$CH/generated_images"; rm -rf "$CH"
```

Each call gets its own `generated_images/`, so nothing another session renders can be collected,
and parallel jobs cannot race. `codex_generate.py` does exactly this on every call and removes the
directory afterwards. Codex fills a fresh home on start (its bundled skills, `$imagegen` included,
and its own state); one real generation (with its probe) and one separate probe ran this way, and
the user's `generated_images/` and `auth.json` were untouched. The copy inherits the config's
model pin.

- **The login is shared through the link.** Should codex ever replace the link with a file (a
  token refresh written by rename), the fresh login would exist only in the private home: the
  script checks the link after every call and, if it was replaced, keeps the directory, sets
  `auth_link_replaced` and says so on stderr. Not observed so far.
- **No `auth.json`** (a keyring or API-key login): the script runs under the shared home and says
  so under `isolation_skipped`.
- **`--shared-home`** runs under the real `CODEX_HOME`. Only the call's own session folder counts
  then; when no `session id:` line can be read, only session folders that did not exist before the
  call — a job started meanwhile can still land there, which is why it is not the default.
  `--keep-home` keeps the private home for debugging.

With the grid method a whole set is ONE call, so parallelize *across* sets, not within one —
rarely needed.

## 4. Take the original, never the agent's copy

The agent resizes its own deliverable to the size the prose named (`sips`), so the file it hands
back can be an interpolation of the real render: an announced "2048x2048 sheet" can be a LANCZOS
upscale of a 1254 px original. Always take the `generated_images` original and
read its size:

```bash
"$HOME/.codex/imagegen-venv/bin/python" -c 'from PIL import Image;print(Image.open("'"$DEST"'").size)'
```

## 5. Transparency is a chroma key — with four traps

The built-in tool has **no native transparency** (`reference/image-model.md` §4). Generate on a
**flat key colour absent from the subject** — magenta `#FF00FF` for a green-and-gold palette, NOT a
colour in the art; `pick_key.py` chooses it (below) — as an **opaque** image, then key it out. Removal needs **Pillow and numpy**,
which system Python lacks; use the machine's existing venv at `$HOME/.codex/imagegen-venv` (absent →
stop and ask the user to create it with `python3 -m venv` + Pillow + numpy; never silently):

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
"$PY" <skill>/scripts/key_unmix.py IN.png --out OUT.png --key-color '#ff00ff'       # art with an outline
"$PY" <skill>/scripts/key_unmix.py IN.png --out OUT.png --edge fill                 # effects: no outline
# a field painted off the key (video frames, a dim render): name the hex, un-mix by tint
"$PY" <skill>/scripts/key_unmix.py IN.png --out OUT.png --key-color '#00ff00' --edge tint
# already keyed and shipped (trimmed, 9-sliced, retouched): repair the rim without re-slicing
"$PY" <skill>/scripts/key_unmix.py --defringe <asset dir> --in-place
```

It prints `transparent_pct`, and `fringe_pct` / `tint_pct` for a binary key and for its own result,
and exits non-zero when the rim is still key-coloured or almost nothing was keyed. The keyer codex
bundles — `remove_chroma_key.py --key-color '#ff00ff' --tolerance 40 --despill --force`, or
`--auto-key corners` — stays the fallback for a venv without numpy, and is what Trap 4 measures.

> **Trap 1 — the painted key varies per sample, and the tolerance is per channel.** A render can
> paint its `#00ff00` field as `(2,250,15)`: the default `--tolerance 12` then keys **0.71%** of the
> canvas and reports success, while `--auto-key corners`, or `--tolerance 40`, keys ~43.6%.
> **Verify the transparent fraction** before slicing — `key_unmix.py` prints it as
> `transparent_pct`, beside `painted_field … off_by N` (how far the sheet's border is from the key
> you named); its field distance is 60, because a painted `#FF00FF` strays up to ~45 at the corners.

> **Trap 2 — `--soft-matte` eats a subject that shares the key's dominant channel.** A leaf-green
> fill `(93,169,106)` against a `#00ff00` key comes back at **alpha 147/255**, with 98.3% of the
> partial pixels in the interior, not on the rim; without `--soft-matte`, alpha 255.
> Key a hue the palette lacks, and never soft-matte GIF-bound frames —
> a soft edge becomes a halo.

> **Trap 3 — the keyed file keeps one or two pixels at alpha ~20 in a canvas corner.** Not
> visible, not in the subject, and enough to drag any `alpha > 16` bounding box to the canvas edge:
> a single asset normalised from such a file ships scaled down and pushed to the opposite side
> (78% asked, 58–68% delivered, up to 14% of the canvas off-centre), and looks like the model
> placed it badly. The set scripts now isolate the subject before measuring and report the strays
> they clear; `sheet_to_frames.py --drop-strays` does the same for an animation sheet. Read the
> `strays` column, and never trust a bbox you have not gated with `audit_set.py`. A **binary** key
> leaves the same speck at alpha 255, where `--drop-strays` cannot see it
> (`reference/animation-scripts.md` §2).

> **Trap 4 — a binary key leaves the key ON the subject, and no importer setting removes it.** The
> renderer paints the anti-aliased rim as a mix of subject and key: field `(247,2,243)`, outline
> `(7,1,8)`, and the pixel between them `(118,8,121)`. A tolerance keeps that pixel opaque and
> purple. Over 25 sheets a binary key left 25–40% of the rim (visible pixels within 2 px of
> transparency) within 150 RGB of the key — `fringe` — and 43–60% of it measurably mixed with the
> key — `tint`; `--despill` left 20–27% on five static sheets, and 5–52% / 26–84% per asset once sliced.
> Unity's *Alpha Is Transparency* repairs the colour under **transparent** pixels; these are
> **opaque**. `key_unmix.py` works in the 2 px boundary band only — alpha along the key→outline
> line, the key un-mixed out, then a choke — and reads 0.0–0.2% / 0.0–0.3% on the same sheets with
> the interior untouched. Its rim alpha is soft (0.35–1) but its colour is clean, which is the
> difference from Trap 2: a GIF's 1-bit cut lands on un-mixed pixels, so there is no halo. The two
> simpler keys that fail, with their numbers: `reference/animation-faults.md` §1a.
> **A sheet that comes back RGBA was keyed by the agent** — reject it and ask for an opaque one.

The hex in the generation prompt and `--key-color` are **one fact written twice**: key magenta out
of a green-screen render and nothing is keyed (`key_unmix.py` exits 2 under 1% transparent;
`remove_chroma_key.py` succeeds on an opaque PNG). Both name the key colour `ART_DIRECTION.md`
records — per character, the one `pick_key.py` chose.

### Choose the key before generating — `pick_key.py`

The key is a property of the **subject**, so pick it from the base still (the anchor, the
character's approved pose) before the first sheet or clip is made on it:

```bash
"$PY" <skill>/scripts/pick_key.py /abs/ArtDirection/anchors/sets/runner_base.png > /abs/keys/runner.json
```

It finds the subject (the image shrunk to 256 px with NEAREST, the border field flood-filled
away, the anti-aliased rim and one-pixel specks dropped) and scores four candidates — magenta
`#FF00FF`, green `#00FF00`, cyan `#00FFFF`, blue `#004DFF`. A candidate is **eligible** when the
subject's nearest pixel is farther from it than `--min-distance` (96): the radius `--edge tint`
erases around the key, so an eligible key cannot take a pixel of the art with it. Among the
eligible ones the highest (1st-percentile distance, nearest distance) wins, ties to magenta. The
JSON names the pick (`hex`), and for every candidate its distances, its nearest subject pixel and
the bbox of the subject pixels inside its radius.

**Exit 1 = no key clears the radius**: the art carries every key's hue somewhere (a green visor
on the runner, a pink sash on the sentry). stderr names, for the best-scoring key, the pixel and
the bbox that would be erased. Recolour that feature in the base and pick again, or accept losing
it — never key on a colour the subject contains. A transparent base reads `mode transparent`; a
base with no flat field reads `heterogeneous` and warns that its distances may count background.

### `--edge tint` — when the field is not the colour you named

`outline` and `fill` assume the field is the key within 60 RGB and the rim is the key mixed with
one neighbour. **`--edge tint`** is for the field that is painted off the key — video frames, a
renderer that paints `#00FF00` as `(3,240,2)` or `#FF00FF` as `(216,46,147)` — and for a rim that
mixes the key with fills of every colour. What its thresholds mean:

- **`--lo` 96 — two erase balls.** Every pixel within 96 of the named key goes, wherever it sits.
  A second ball of the same radius sits on the colour the border was actually painted (read from
  the corners and the 1 px border); it only takes pixels carrying the key's hue signature and what
  is 8-connected to them inside the ball. A hot-pink fill inside the subject, within 96 of a dim
  painted magenta, survives; a subject patch with the key's own hue does not — which is what
  `pick_key.py` prevents.
- **tint < 18 is subject**, never touched. `tint = mean(key channels) − mean(other channels)`; a
  pixel's key share is `k = min(tint / key_tint, 1)`, its colour becomes `(rgb − k·painted)/(1−k)`
  and its alpha `1 − k`.
- **Key-tinted material keeps its hue.** A teal jacket on green has a tint of its own (about
  50), so un-mixing its rim against zero would take green the jacket owns and leave it blue.
  When the material just inside the rim (past ring 4) has tint ≥ 18, the rim is un-mixed
  against it instead: `k = (tint − base)/(key_tint − base)`. The run prints the pixels this
  touched as `baseline_px`. A neutral subject (base under 18) keys exactly as above.
- **`--band` 4 — rings un-mixed.** Only pixels 1–4 rings from the cut are un-mixed; one still
  within 180 of the key (an in-band blend) only in rings 1–2. No choke.
- **`--despill`** (default on; `--no-despill` off) recolours small trapped spill: 8-connected
  tinted clusters of at most max(32, 0.5% of the subject) px, one pixel tinted past 40, get the key
  taken out of their colour and keep their alpha. A larger key-tinted region is the art's own
  colour and stays.

**Name the key hex in tint mode.** `--key-color auto` takes the border median as the declared
key, and a dim painted field then shifts the channel split the tint axis is read from. The run
prints `painted_key (r,g,b) off_by X key_tint Y` and the same `fringe_pct` / `tint_pct` lines and
exit codes as the other modes. Generated sheets stay on `outline` / `fill`, the default.

## 6. The flat-vector detour

For strict-flat icons codex may judge the raster model "keeps adding gradients" and instead
hand-author an SVG → render a PNG into the `-C` workspace. That output is perfectly consistent
(procedural) — keep it; it is just why `-C` sometimes holds a file and sometimes doesn't.

## 7. Recipe — analyze / recognize images (no style needed)

```bash
codex exec "說明錯誤訊息並建議修法（5 點以內）" -i /abs/screenshot.png
codex exec "比較這兩張設計稿的差異" -i a.png b.png     # prompt FIRST; -i is variadic and eats a trailing prompt
codex exec "萃取 6-8 個主要 hex 色碼並標用途；再用 6-8 個關鍵字描述風格、光影、造型語言。" \
  -i <repo>/ArtDirection/anchors/master.png            # PHASE 2 ground truth (strongest -m)
codex exec "這些應符合 ART_DIRECTION 的配色與風格；找出不一致並說明修法" \
  -i a.png b.png /…/anchors/master.png                 # PHASE 4 audit
```

Relay Codex's stdout back to the user in your own words.

## 8. The set and animation scripts

- **Set scripts** — `slice_grid.py` · `normalize_set.py` · `audit_set.py`. Both normalisers
  isolate the **subject** (pixels at alpha ≥ 96, grown through every connected pixel above
  `--alpha-thr`; a keyer's stray speck never joins and is cleared) and scale and centre its
  **core** (alpha > 40, so a glow's outer haze does not steer placement); the paste is mask-free
  (a masked paste onto transparency squares soft alpha). `--raw-bbox` places by a plain alpha bbox
  with no subject isolation, for reproducing a set normalised that way. `slice_grid.py` cuts on the **found gutters** (the emptiest
  row/column within a third of a cell of each equal split; `--gutters nominal` for the exact
  split), reports haze-only cells as EMPTY and warns when a subject touches its cell edge —
  re-generate with wider gutters. `normalize_set.py` **REQUIRES** `--content-frac`,
  `--match-anchor`, `--recenter` (translate a shipped set onto its own canvas centre, no rescale)
  or `--report`. Use ONE project-wide `--canvas` / `--content-frac` per asset class;
  `--no-normalize` keeps the relative sizes of a deliberately mixed set, `--fit height` gives
  characters a shared ground line, `--canvas-h` a non-square asset. Both end on a post-normalize
  CV line and a max centre offset; a normalised set reads near 0% and ≤ 0.5 px.
  **`audit_set.py <files> --expect-frac F [--fit …] [--symmetry]`** is the gate on what shipped:
  one line per asset (canvas, core, centre offset, fill against F, strays; with `--symmetry`
  mirror IoU, tilt and rim level for upright objects), the set's width/height spread, exit 1 on a
  centre offset over 2 px, a fill more than 0.02 off, or — with `--symmetry` — IoU below 0.92,
  tilt over 8 px, a rim more than 6 px off level. With `--key-color` it also reads each asset's
  rim (`fringe` ≤ 0.5%, `tint` ≤ 2%, §5 Trap 4). Run it before a set is registered and on any
  set someone says "looks a bit off".
- **Animation scripts** — `sheet_to_frames.py` · `audit_frames.py` · `frames_to_anim.py`. The
  acceptance gate is `sheet_to_frames.py --report` on the keyed sheet: empty cells, near-duplicates,
  cut subjects and the rim, with nothing written and exit 3 on a hard fault. Writing needs
  `--register ground | free | centroid | keep` — where a frame sits is decided by silhouette, not
  by the cell the model drew it in. `audit_frames.py` re-reads the written PNGs (feet, slip,
  fringe, tint, cut, key residue, sparse frames; exit 1) and `frames_to_anim.py --onion --bg` makes
  the two previews that show motion. `breathe.py` makes an idle loop from one still pose, with no
  sheet. Full usage: `reference/animation-scripts.md` §2.
- **Animation frames never go through `slice_grid.py`** — it centres every cell on its own bounding
  box, so a bat or a raised arm moves the body the other way.
- **3D source scripts** — `turnaround_to_views.py` · `audit_3d_source.py`: one scale for four
  views, and the gate on an image before a conversion (`reference/image-to-3d-input.md` §5, §8).
- **Pixel scripts** — `pixel_snap.py` · `audit_pixel.py`, with `sheet_to_frames.py --pixelate N
  --pixel-method snap` for animation sheets. `pixel_snap.py` is the last step of the static path:
  it snaps images already on their final canvas to a fixed cell count and one palette, and writes
  each cell as an F px block. `audit_pixel.py` is the gate on either kind — block size, canvas,
  lattice phase, binary alpha, colour count, palette; exit 1 on a failed gate, 2 when it had
  nothing to check against. Full usage: `reference/pixel-grid.md`.
- **`key_unmix.py`** keys both kinds of sheet, and `--edge tint` a field painted off the key;
  **`pick_key.py`** chooses the key before generating (§5). **`sprite_ops.py`** is not a command: it holds
  the definitions the keyer, the slicer and the two gates share (core, rim, fringe, tint, slip), so
  none of them can disagree about a number. **`pixel_ops.py`** is the same kind of shared module
  for the pixel scripts — the cell fit, the colour recovery, the palette and the lattice read-back —
  and has no command of its own beyond `--selftest`. The scripts directory travels as a whole.

## 9. The single-asset call (PHASE 3)

Prompt = `STYLE PREAMBLE` verbatim ＋ the asset request (what/size/tiling), on a flat key colour the
subject lacks; the anchor holds the style:

```bash
DEST=<project asset dir>/<name>.png      # path per ART_DIRECTION.md
cat > <scratch>/prompt.txt <<'EOF'
$imagegen <STYLE PREAMBLE verbatim>. Subject: <description>, centered, <size>,
on a flat solid background in a key colour the subject lacks (#FF00FF, or the key
colour ART_DIRECTION.md records).
EOF
python3 <skill>/scripts/codex_generate.py --prompt-file <scratch>/prompt.txt --out "$DEST" \
    -i <repo>/ArtDirection/anchors/master.png --job-log <scratch>/jobs.jsonl \
    --expect-size 1254x1254                                            # square: image-model.md §3
```

Exit 0 is one render of the expected size; after 5 or 6, open the files before deciding anything
(§1). By hand, the capture is §2's session recipe. Then key it (§5). The printed object is what
skill `art-asset-registry` turns into a ledger record (its `ingest` command); it refuses the
output of an exit 5, since none of the images was chosen.
