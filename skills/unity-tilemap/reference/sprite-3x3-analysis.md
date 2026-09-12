# Reading a tile's shape out of its own pixels

> The thresholds below are starting points; read the emitted patterns before applying them.

A terrain sprite already knows which rule it belongs to. A top-edge tile is solid along its
bottom and empty along its top; a corner is solid on two sides. Segmenting the sprite into a
3 × 3 grid and comparing each cell to the centre recovers that shape as a pattern string, which
is exactly the input a `TilingRule` needs.

This is a heuristic over pixels, not a parse of authored metadata. It is right often enough to
save an afternoon of hand-authoring and wrong often enough that the output has to be read before
it is applied.

## Algorithm

1. Take the sprite's `rect` — its region inside the texture, in pixels — and divide width and
   height by three. Integer division: a sprite whose dimensions are not multiples of three loses
   up to two pixels off the top and right edge, which does not matter at these thresholds.
2. **Centre cell first.** Count colours across the centre cell and take the most frequent one.
   That colour is the definition of "solid" for this sprite, so it is derived per sprite rather
   than configured — two tiles from different terrains each analyse against their own material.
3. **For each of the other eight cells**, count how many of its pixels match that colour within
   the tolerance, and divide by the cell's pixel count.
4. Share at or above the **match threshold** → `.`; below → `X`. The centre is always `*`.
5. Emit `T T T / L * R / B B B`, rows top to bottom.

## The Y flip

Texture coordinates put y = 0 at the **bottom**; the pattern string reads top-down. The row being
sampled is therefore `(2 - row)`, not `row`:

```csharp
int startY = (int)rect.y + (2 - row) * cellHeight;
```

Drop the flip and every pattern comes out mirrored vertically. It does not throw and it does not
look obviously wrong — the rule tile simply paints top edges along the bottom of every landmass,
which reads as "the autotiling is inverted" long after the analysis step is out of mind.

## The two knobs

| Knob | Typical values | What moving it does |
|---|---|---|
| Match threshold | `0.5`, `0.75`, `0.9` | Share of a cell's pixels that must match the centre colour. `0.5` tolerates cells that are half transition; `0.75` is the working default; `0.9` suits flat-colour tiles and rejects anything with a border |
| Colour tolerance | per-channel RGB distance, e.g. `0.04` | How far a pixel may sit from the centre colour and still count. Tight for a limited palette; looser for dithering, gradients or a lightly noised texture |

> **Raise the threshold before loosening the tolerance.** A loose tolerance makes every pixel
> match and every sprite reports the fully-surrounded pattern — a failure that reads as "the
> analysis did nothing" rather than as a bad number. A threshold that is too high fails the
> other way, with everything reporting the empty pattern, which is at least obviously wrong.

## Reading the output before trusting it

Log the pattern beside the sprite name for every sprite and look at the list. Three signatures,
each with one cause:

| What the list shows | Cause |
|---|---|
| Every sprite reports `. . . / . * . / . . .` | Tolerance too loose, or the sprite is a solid fill with no edge |
| Every sprite reports `X X X / X * X / X X X` | Threshold too high, or the centre colour is transparent while the edges are not |
| Patterns are vertically mirrored | The Y flip |
| Half the sprites report patterns not in the known table | The sheet contains decorations, variants or props alongside the terrain — filter them out of the input rather than loosening the pattern filter |

## The texture has to be readable

`GetPixel` on an imported texture requires **Read/Write Enabled** on its importer. It is off by
default, and turning it on doubles the texture's memory because a CPU-side copy is kept. Turn it
on for the analysis, run it, turn it off, and reimport — the rule tile asset holds sprite
references, not pixels, so nothing downstream needs the flag.

An Editor-only alternative that avoids the flag entirely is to read from the source file through
`AssetDatabase` and decode it into a temporary readable texture. Either way, the analysis runs
once at authoring time and its result is serialised into the rule tile; nothing about this
belongs in a build.

## Transparency

Transparent pixels are a colour like any other to this algorithm — both halves of it, the
majority-colour histogram that elects the centre's colour and the per-pixel comparison against
it, key on RGB only and ignore alpha. Keeping the two consistent matters: a histogram that
included alpha would split a fill varying only in alpha across several buckets and could
elect a minority RGB as the centre colour, after which every cell scores against the wrong
target.

Ignoring alpha works for terrain sprites whose empty side is fully transparent, because a
transparent region's RGB rarely matches the material's.
It fails on art where the transparent pixels carry the same RGB as the fill and differ only in
alpha: every cell then matches and every sprite reports fully surrounded. If a tile set behaves
that way, extend the comparison to alpha; it is two lines and it is the correct fix, not a
tolerance change.

## Where this ends

The pattern is a hypothesis about one sprite. Turning a set of hypotheses into a rule tile —
filtering to the known patterns, deduplicating, ordering by specificity and picking the default
sprite — is `SKILL.md` §6, and the tables are in
[`rule-tile-patterns.md`](rule-tile-patterns.md).
