# PHASE 3A — an animation as one gridded sheet, step by step


`SKILL.md` PHASE 3S's stack, but the cells are **moments of one character**. The sheet decides the drawings,
**not where they sit**: frames are seated by silhouette afterwards, never centred per cell
(`slice_grid.py` never touches the sheet). No skeletons here.

1. **Shape the job** (`SKILL.md`, then `reference/job-shape.md`): idle 3–8, walk 6–12, attack 4–12 frames; 8 on a 3x3 as a half cycle
   plus `--reverse-loop` beat 16 half-dead cells → `reference/animation-sheets.md` §3d, §3a.
2. **Write the prompt:** `STYLE PREAMBLE` → the four locks → identity lock (colours as words
   *and* hexes) → time structure; a one-shot over 12+ frames is **staged** → same file, §1, §3.
3. **Anchors: order fixed, roles named in prose** — style, identity, family → same file, §2.
4. **Generate, key, then measure before you write anything:** the `generated_images` original,
   `key_unmix.py`, then `sheet_to_frames.py <keyed> … --report`. Empty cells, near-duplicates or
   a subject cut by the sheet edge → re-generate → `reference/animation-faults.md` §2.
5. **Write the frames — `--register` is required** (`ground` · `free` · `centroid` · `keep`; exit
   3 = a failed gate), then `audit_frames.py` and `frames_to_anim.py --onion --bg`: **one frame
   per cell on a contact sheet is not evidence about an animation** →
   `reference/animation-scripts.md` §1, §2.
6. **One cell wrong** → a new sheet or a local splice; **jitter, cut feet, a fringe, a boiling
   idle** (→ `breathe.py`) → not a re-generation → `reference/animation-faults.md` §3, §1a. **Pixel style** →
   post-process the whole sheet, then register → `reference/pixel-grid.md`.
7. **Outputs and the handoff:** frames + `frames.json` (`pivot_norm` = the pivot) + the keyed
   sheet (→ `anchors/sets/<action>.png` if the next animation must match) + previews →
   `reference/animation-scripts.md` §4.
