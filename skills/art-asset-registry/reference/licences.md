# Licences and the sales territory

Some models may be used commercially only outside certain countries. An asset made with one
carries that limit, and so does everything made from it: a clip solved from a generated video, a
mesh rigged from it. The ledger records the limit on the asset that brought it in, and `check`
follows `parent` and `depends-on` links to find it again downstream. Where the game is sold is
written once, in `ART_DIRECTION.md`.

## The `licence` object

```json
"licence": {"source": "minimax-h3-local", "id": "runner-run-take-2",
            "territory": {"excludes": ["US", "EU", "UK", "KR"]}}
```

| Key | Req. | Meaning |
|---|---|---|
| `source` | Y | a slug naming the licence the asset was made under; the known ones are below |
| `id` | N | which use of it: a job, a take, an order or a pack, so the terms can be found again |
| `territory` | Y | `"worldwide"`, or `{"excludes": [codes]}` with at least one code |

A code is ISO 3166-1 alpha-2 (`US`, `GB`, `KR`, `JP`), or `EU` for every EU member state. `UK` is
read as `GB` and `EL` as `GR`, since licences write them that way. `licence` is not `license`:
`license` is the string a purchased or third-party file already carries (`purchased:<pack>`,
`cc0`); `licence` says where the asset may be sold. A record may carry both.

Record `licence` on the asset where a model, a service or footage entered the project, and on
anything recorded from a producer that knows its model. A downstream asset made only by the
project's own tools needs none: its `parent` or `depends-on` link carries the limit to it. A
revision recorded without `licence` keeps the previous one.

## The sales territory: one line in `ART_DIRECTION.md`

`check` reads `ART_DIRECTION.md` at the project root (`--root`), the first line outside a code
fence that reads:

```markdown
Sales territory: worldwide
Sales territory: JP, TW, EU
Sales territory: undecided
```

The key is case-insensitive and may be bold or a list item (`- **Sales territory:** JP, TW`).
The value is `worldwide`, a list of codes separated by commas or spaces, or `undecided`.

| Declared | An approved asset whose licence, or an upstream one, excludes a code |
|---|---|
| `worldwide` | ERROR `territory-excluded`: any exclusion blocks it |
| a list of codes | ERROR `territory-excluded` when the exclusions meet the list (`EU` meets `DE`, `DE` meets `EU`, `UK` meets `GB`) |
| `undecided`, or no line, or no file | WARN `territory-undeclared` naming the licence and what it excludes |
| a word that is no code (`Narnia`, `USA`) | WARN `territory-unknown` for the word; the other codes are still checked |

The ERROR applies to approved records only: `approved` is the version the game loads, the ship
status. `status ID approved` and `record --status approved` refuse the same asset (exit 2). A
candidate is never refused for its territory, so work goes on while the territory is undecided.
The message names the chain, e.g. `licence minimax-h3-local via artdirection/clips/runner-run ->
artdirection/motion/runner-run-h3 excludes EU, GB, KR, US`.

To answer "can this ship there?" before deciding, write the candidate line in `ART_DIRECTION.md`,
run `check`, and put the line back.

## Known sources

| `licence.source` | What | `territory` |
|---|---|---|
| `minimax-h3-local` | MiniMax H3 video generated on local open weights under the H3 community licence | `{"excludes": ["US", "EU", "UK", "KR"]}` |
| `fal-h3` | H3 or H3 Max run on fal, under fal's terms | `"worldwide"` |
| `phone-footage` | footage the team shot itself, of performers who agreed to it | `"worldwide"` |
| `auto-rig-pro` | a rig or weights made with Auto-Rig Pro | `"worldwide"` |
| `hy-motion` | HY-Motion text-to-motion | `{"excludes": ["EU", "UK", "KR"]}` |

Before a source here is relied on for a shipped asset, confirm its current licence text still says
the same; if it changed, record the new `territory` on a new revision and run `check`. A source
not in the table: read its licence, write the exclusions it names, and add a row here. Footage of
a person needs that person's written release before it is recorded `worldwide`; without one,
record it as a candidate and do not approve it.

## Worked example: the courier run

The runner's run comes from `humanoid-motion`'s two cameras: a front and a side view of the runner
become a two-view video on local H3 (`licence` `minimax-h3-local`), and the clip is solved from it
onto the contract skeleton (a `depends-on` link to the video, no `licence` of its own). With
`Sales territory: undecided`, `check` warns once per approved clip. When the publisher settles on
`Sales territory: JP, TW`, the warnings go and nothing fails. If it becomes `worldwide`, `check`
fails every clip whose chain reaches the H3 video: regenerate those videos on fal (`fal-h3`,
`worldwide`) from the same reference and prompt, record the new clips, approve them, and
supersede the old ones.
