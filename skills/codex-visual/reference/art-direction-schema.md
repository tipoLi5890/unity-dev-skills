# `/ART_DIRECTION.md` — the sections the file must contain

The project's art bible, written in PHASE 2 of `SKILL.md`. PHASE 2 fills `Status: LOCKED`, version,
**dimensionality**, **style family**, **engine/approach**, palette, mood, **pixel spec if pixel**
(grid px, palette size, view angle, frame counts, outline), **asset-format conventions**, the
verbatim **STYLE PREAMBLE**, anchor path(s), do/don't.

- **Status / Version / Last updated**, **Scenario / IP brief**
- **Dimensionality / render target** (2D / 2.5D / 3D), **Style family** (from the board/refs)
- **Generation engine / approach** (which engine above; + any post-process; + pinned agent model,
  if the project pins one)
- **Asset-template formats** this project needs
- **Palette** — `role | hex | usage` (extracted from the anchor)
- **Pixel spec** — *only if style = pixel* (grid px, palette size, view angle, frame counts, outline)
- **Mood / keywords**; **Anchors** — path(s) to canonical reference image(s)
- **STYLE PREAMBLE (inject verbatim)** — exact text prepended to every prompt
- **Per-asset conventions** — sizes/format/transparency/tiling per type
- **Set / sheet conventions** — which asset groups are one grid sheet (grid size, cell count,
  chroma key, canvas/content-frac), where per-set anchors live
- **Animation conventions** — one row per action: frame count · grid · cell px · fps · loop or
  one-shot (and whether the loop is authored as a half cycle for `--reverse-loop`) · frame canvas
  and pivot · in-cell safe margin · key colour · preview formats · naming stem. E.g. `idle | 8 |
  3x3 | 418 px | 10 fps | loop, half cycle | 512² bottom-centre | 13 px | #FF00FF | GIF+APNG |
  hero_idle`. Frame counts here override anything a per-asset row says
- **Do / Don't**, **Changelog**
