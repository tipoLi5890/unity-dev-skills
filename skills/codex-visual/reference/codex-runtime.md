# codex-runtime — how the call is made and how the file is obtained

`SKILL.md` routes; this file holds the mechanics, not what to draw. Flags move with the CLI: when
one errors, read `codex exec --help` before this file.

## 1. Always `codex exec` (non-interactive)

The Bash tool **cannot drive a TUI**; bare `codex "..."` hangs. Always `codex exec ...`.

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

`$CODEX_HOME` = `~/.codex`, and the directory name is the session id. `-C` moves the agent's shell
cwd, not the save path; a workspace copy appears only on the flat-vector detour (§6). Capture it
yourself:

```bash
# simplest: copy the newest, then verify it is a PNG
DEST=/abs/target.png
codex exec --sandbox workspace-write --skip-git-repo-check "$PROMPT" < /dev/null
cp "$(ls -t "$HOME/.codex/generated_images"/*/*.png | head -1)" "$DEST"
file "$DEST"
```

```bash
# sequential and exact: snapshot before, diff after
before=$(ls -1 "$HOME/.codex/generated_images"/*/*.png 2>/dev/null | sort)
codex exec --sandbox workspace-write --skip-git-repo-check "$PROMPT" -i "$MASTER" < /dev/null
NEW=$(comm -13 <(echo "$before") <(ls -1 "$HOME/.codex/generated_images"/*/*.png|sort) | xargs ls -t | head -1)
```

## 3. Parallel sets: a private `CODEX_HOME` per job

```bash
CH=<scratch>/codex-job-1                        # one private CODEX_HOME per job
mkdir -p "$CH"; ln -sf ~/.codex/auth.json "$CH/auth.json"; cp ~/.codex/config.toml "$CH/"
CODEX_HOME="$CH" codex exec … -C "$CH/out"      # then read "$CH/generated_images"
```

Each job gets its own `generated_images/`, so there is no race. With the grid method a whole set is
ONE call, so parallelize *across* sets, not within one — rarely needed. The copy inherits the
config's model pin, and codex writes its own session state into the directory; delete it when the
job is done.

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
colour in the art — as an **opaque** image, then key it out. Removal needs **Pillow and numpy**,
which system Python lacks; use the machine's existing venv at `$HOME/.codex/imagegen-venv` (absent →
stop and ask the user to create it with `python3 -m venv` + Pillow + numpy; never silently):

```bash
PY=$HOME/.codex/imagegen-venv/bin/python
"$PY" <skill>/scripts/key_unmix.py IN.png --out OUT.png --key-color '#ff00ff'       # art with an outline
"$PY" <skill>/scripts/key_unmix.py IN.png --out OUT.png --edge fill                 # effects: no outline
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
> (`reference/animation-sheets.md` §6).

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
> simpler keys that fail, with their numbers: `reference/animation-sheets.md` §4a.
> **A sheet that comes back RGBA was keyed by the agent** — reject it and ask for an opaque one.

The hex in the generation prompt and `--key-color` are **one fact written twice**: key magenta out
of a green-screen render and nothing is keyed (`key_unmix.py` exits 2 under 1% transparent;
`remove_chroma_key.py` succeeds on an opaque PNG). Both name the key colour `ART_DIRECTION.md`
records.

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
  fringe, tint, cut; exit 1) and `frames_to_anim.py --onion --bg` makes the two previews that show
  motion. Full usage: `reference/animation-sheets.md` §6.
- **Animation frames never go through `slice_grid.py`** — it centres every cell on its own bounding
  box, so a bat or a raised arm moves the body the other way.
- **`key_unmix.py`** keys both kinds of sheet (§5). **`sprite_ops.py`** is not a command: it holds
  the definitions the keyer, the slicer and the two gates share (core, rim, fringe, tint, slip), so
  none of them can disagree about a number. The scripts directory travels as a whole.

## 9. The single-asset call (PHASE 3)

Prompt = `STYLE PREAMBLE` verbatim ＋ the asset request (what/size/tiling), on a flat key colour the
subject lacks; the anchor holds the style:

```bash
DEST=<project asset dir>/<name>.png      # path per ART_DIRECTION.md
codex exec --sandbox workspace-write --skip-git-repo-check \
'$imagegen <STYLE PREAMBLE verbatim>. Subject: <description>, centered, <size>,
on a flat solid background in a key colour the subject lacks (#FF00FF, or the key
colour ART_DIRECTION.md records).' \
-i <repo>/ArtDirection/anchors/master.png < /dev/null      # prompt FIRST, -i LAST
cp "$(ls -t "$HOME/.codex/generated_images"/*/*.png | head -1)" "$DEST"   # then read its size
```

Then read its real size (§4) and key it (§5).
