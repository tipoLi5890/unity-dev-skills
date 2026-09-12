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

## 5. Transparency is a chroma key — with two traps

The built-in tool has **no native transparency** (`reference/image-model.md` §4). Generate on a
**flat key colour absent from the subject** — magenta `#FF00FF` for a green-and-gold palette, NOT a
colour in the art — then key it out. Removal needs **Pillow**, which system Python lacks; use the
machine's existing venv at `$HOME/.codex/imagegen-venv` (absent → stop and ask the user to create it
with `python3 -m venv` + Pillow; never silently):

```bash
"$HOME/.codex/imagegen-venv/bin/python" \
  "$HOME/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py" \
  --input IN.png --out OUT.png --key-color '#ff00ff' --tolerance 40 --despill --force
# or let it read the field: --auto-key corners  (instead of --key-color/--tolerance)
```

> **Trap 1 — the painted key varies per sample, and the tolerance is per channel.** A render can
> paint its `#00ff00` field as `(2,250,15)`: the default `--tolerance 12` then keys **0.71%** of the
> canvas and reports success, while `--auto-key corners`, or `--tolerance 40`, keys ~43.6%.
> **Verify the transparent fraction** before slicing —
> `sheet_to_frames.py --report` prints it as `transparent_pct`.

> **Trap 2 — `--soft-matte` eats a subject that shares the key's dominant channel.** A leaf-green
> fill `(93,169,106)` against a `#00ff00` key comes back at **alpha 147/255**, with 98.3% of the
> partial pixels in the interior, not on the rim; without `--soft-matte`, alpha 255.
> Key a hue the palette lacks, and never soft-matte GIF-bound frames —
> a soft edge becomes a halo.

The hex in the generation prompt and `--key-color` are **one fact written twice**: key magenta out
of a green-screen render and the command succeeds on an opaque PNG. Both name the key colour
`ART_DIRECTION.md` records.

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

- **Set scripts** — `slice_grid.py` · `normalize_set.py`. `normalize_set.py` **REQUIRES**
  `--content-frac` or `--match-anchor` (a bare invocation errors). `slice_grid.py --report` warns
  when a cell's content touches its edge — raise `--inset-frac` or the prompt's gutters and
  re-generate. Use ONE project-wide `--canvas` / `--content-frac` per asset class;
  `--no-normalize` keeps the relative sizes of a deliberately mixed set, and `--fit height` gives
  characters a shared ground line. Both scripts end on a post-normalize CV line; a normalised set
  reads near 0%.
- **Animation scripts** — `sheet_to_frames.py` · `frames_to_anim.py`. The acceptance gate is
  `sheet_to_frames.py --report`: drift, near-duplicates and bleed, with nothing written. Full
  usage: `reference/animation-sheets.md` §6.
- **Animation frames never go through `slice_grid.py`** — it re-centres every cell and erases the
  arc.

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
