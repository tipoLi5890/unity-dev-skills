# Spring chains — the hood, bag, hem, shorts and hair of a fused shell

> Part of the `character-autorig` skill. `scripts/secondary_chains.py` adds the chains;
> `autorig.py secondary` runs it as the last stage; the springs themselves run in Unity
> (`unity-rigged-character` → `reference/secondary-motion.md`). Gates: `reference/gates.md`.

An image-to-3D character is one shell, so a hood or a hem is not a separate cloth mesh. The script
finds each loose region on the bound mesh, adds a short chain of plain bones named `cc_*` under the
contract bone it hangs from (and an unweighted tip bone, since Unity imports no bone tails), and
moves a share of the existing skin weights onto the chain inside that region only. Auto-Rig Pro's
exporter keeps every `cc_*` bone as a deform custom bone with its name and parent, so the bind and
any weight repair stay as they are: no Match to Rig, no rebind. An Auto-Rig Pro limb (tail, kilt,
ears) would need both, which re-solves the whole body.

## The stage

`autorig.py all` runs it after the deformation gate passes, on the rig to take on (the passing
repair's `repair/aN/NAME_arp.blend`, else `rig/NAME_arp.blend`), with the contract report as the
role map. It writes `secondary/`: `NAME_sec.blend`, `NAME.fbx` (the `brt_arp` export),
`NAME.skeleton.json`, `NAME.secondary.json` (secondary/1, the hand-off to Unity),
`NAME.secondary.gate.json`, `pics/` (before, regions, a swing), then `NAME.contract.json` and
`NAME.deform.json` from the contract and deformation gates run again on that export. Both readings
equal the ones without the chains outside the chain regions: the deformation gate reads each bone
the chains hang from as if they were not there (`reference/gates.md`). `--no-secondary` skips the
stage; `autorig.py secondary OUT` runs it alone; `--secondary-markers FILE` passes manual chains.

A body with nothing loose gets an empty chain list, no bone and no new export: the files to take
on stay the rig's own.

**A separate hair object** (a character in parts: `autorig.py all --hair`, whose `parts_bind` step
leaves an object `Hair`, marked `parts_hair`, bound rigidly to Head). The body is then never
searched for hair: its head is a bald scalp. By default the hair stays rigid on Head, and the gate
report's `detect.hair_object` says so. `--hair-chains` (on `autorig.py` too) runs the hair kind on
that object instead: the head centre comes from the body's head skin and the hair together, the
thresholds from the body's height, and the spikes' chains are weighted on the hair object only (Head
gives the share). A spike too small to give each bone 50 vertices is left rigid
(`detect.dropped_small`). Each gate covers both meshes: a chain's weight on the other mesh counts
as a leak, and the export check matches each re-imported mesh to its source. `--hair-mesh NAME`
names another object; `--hair-mesh none` ignores it.

## Kinds and defaults

Parameters per 1/60 s (stiffness, drag), gravity as a multiple of world gravity, the particle
radius as a fraction of the height H.

| kind | Found as | Chains | Hangs from | stiffness / drag / gravity / max° | radius | Colliders |
|---|---|---|---|---|---|---|
| `hood` | a bulge ≥ 0.04 H off the opened back profile, centred above UpperChest, ≥ 0.12 H across | 1 × 2 bones | Neck or UpperChest | 0.35 / 0.35 / 0.6 / 40 | 0.023 H | Chest, UpperChest, Back |
| `bag` | the same, centred between Hips − 0.08 H and UpperChest, ≥ 0.08 H across | 1 × 1 bone | Spine, Hips or Chest | 0.25 / 0.45 / 1.0 / 30 | 0.034 H | Hips, Spine, both thighs |
| `bag` on a hip (`bagL`, `bagR`) | the back rule turned 90°: ≥ 0.04 H out of the opened lateral profile (hips, spine, chest and that thigh; never an arm), centred between Hips − 0.08 H and UpperChest, ≥ 0.08 H deep, ≤ 0.25 H tall | 1 × 1 bone per side | Hips or Spine | as `bag` | 0.034 H | Hips, Spine, Chest, that thigh |
| `hem` | horizontal skin within Hips ± 0.06 H with a lip: the skin 0.012 H above the edge ≥ 0.004 H further out than below, in ≥ 4 of six sectors | 4–6 × 1 | Hips or Spine | 0.55 / 0.40 / 0.3 / 25 | 0.011 H | both thighs, Hips |
| `hem`, `--skirt` | the skirt route's hem (`arp_markers --body skirt`), wherever it hangs: the skirt's own skin in six sectors, a sector live with ≥ 30 vertices within 0.03 H of the hem | 4–6 × 2 | the thigh it covers (else Hips) | as `hem` | 0.011 H | both thighs, Hips |
| `shorts_hem` | per leg, a drop of the thigh's skin radius by ≥ 1.35 × and ≥ 0.01 H, on both legs within 0.03 H | 3 per leg × 1 | UpperLeg | 0.65 / 0.40 / 0.2 / 20 | 0.009 H | both thighs, its own included |
| `hair` | head skin outside the face cone, the farthest fifth clustered by direction; a cluster is a spike when ≥ 0.12 of its skin faces sideways, no one axis holds > 0.72 of those sides' normals, and ≥ 0.24 of its skin on the outer envelope (within 1 % of the farthest in its direction, share-weighted) faces sideways (|normal · radial| < 0.6) | ≤ 6 × 1–2 | Head | 0.75 / 0.30 / 0.1 / 20 | 0.006 H | Head |
| `strap` | never detected (fixed at both ends): a marker chain only | 1 × 1, stiff | UpperChest or Chest | 0.85 / 0.50 / 0.3 / 10 | 0.006 H | Chest, UpperChest |

The thresholds are what separate clothing from anatomy: the selftest's smooth body (buttocks, a
tapering thigh, an oval skull) gets no chain, the test shell gets every kind but the hood. Each
vertex belongs to one region (bag, hood, hair, hem, shorts hem, strap in that order).

**Look-alikes** (each rule has a counterexample in the selftest, found with the rule off). A back
component spanning more than 180° round the spine line wraps the body: a belt read against a coat
whose back is vented (the opened profile drops to the front skin there) is no bag. A hood narrower
than 0.12 H, or a bag narrower than 0.08 H, is a hank of hair, a hair tie or a strap. A hair cluster
whose sideways skin faces one way is a plate, a cap's brim or a visor; one whose outer skin, seen from
the head centre, is a smooth dome is a crown, a cap's or a helmet's, rigid on Head: its side-facing skin
(the rim, the hair under it) is hidden (`detect.hair_rejected`, `why: crown`; `detect.hair_outer_sides`).
A side bulge taller than 0.25 H is a cape's or a long coat's edge, one shallower than 0.08 H front to back a
strap (`detect.side_bag.rejected`); a bag set back behind the hip's widest point stands out of neither
profile and takes a marker chain. A
shorts drop on one leg alone, or at heights more than 0.03 H apart, is a skirt's or a coat's hem:
no shorts chain (`detect.shorts.unpaired`). Everything rejected is listed in `detect.back.rejected`;
a narrow one behind the head is the place for a ponytail marker.

**A long coat or skirt** (`autorig.py` passes `--skirt rig/NAME.markers.json` on the skirt route).
The jacket hem's search (Hips ± 0.06 H) never reaches a knee-length hem, and a chain hung from Hips
can take only Hips' share of a skirt the thighs hold (0.17–0.34 on a greatcoat). Here each sector's
chain runs from the hip down the skirt's surface to the markers' hem, hangs from the bone holding
most of its skin (the thigh it covers, after the skirt bind) and takes its share from that bone
first: 0.6 at the hem (`SKIRT_SHARE`), fading to 0 within 0.04 H of the legs' own skin (a skirt
joined to them). The six blend round one ring and share its skin; where a vertex would hold more
than four weights, chains merge only with chains on the same bone, then that bone's remainder goes
into its own chain, so a pose moves the skirt as the bind did and the Blender gates read the same.
No shorts hem is searched under a skirt. **A cape** reaches the hem only behind: with both back
sectors live and neither front one it is chained on its live sectors, each half hung from the thigh it
hangs behind (one parent for both tears it in a squat). A back bulge with at least half its skin in the
skirt's region is the coat's or the cape's own drape, never a bag (`detect.back.rejected`).

**Weights.** A chain's share ramps from 0 at its root to its maximum along it, feathered at the
region border and blended between neighbours of a ring (a jacket's hem, a skirt's hem, each leg's
shorts): a ring's chains share its skin, so no sector loses its blend to the one before it. It is taken from the chain's parent first,
then from the region's other source bones in proportion; limb bones never give to a torso chain.
Every vertex keeps at most 4 weights summing to 1. Outside the regions nothing changes. The bag's
share fades smoothly from 0.012 H outside its bulge to 0.04 H inside it: on a fused shell the bag's
bottom meets the jacket at one edge, and a full share against none there stretches that edge
several times over when the bag swings; the fade spreads it over a band.

**Colliders.** Capsules between bone origins (Hips across the thighs, Spine, Chest, UpperChest,
both thighs inset 0.1, both shins) and a Head sphere, radii from the skin around them. Each kind
tests its group; a collider that holds a chain joint below the root at rest is shrunk until it
does not, or dropped from that chain's list when that would take it under half its radius. A
collider is shared, so a shorts hem's own thigh shrinking also tightens the bag's and the hem's
test. A hood's tip rests on the back, inside the torso capsules, so those drop from its list
(`colliders.dropped`); it gets a `Back` sphere instead (`colliders.added`): radius 0.5 H on
UpperChest, its centre in front of the chain, its surface just under the rest joints by the particle
radius and 2 mm. It never starts in penetration, and the hood cannot sink into the back further than
it rests.

## Manual chains — the markers file

`--markers FILE` (or `autorig.py --secondary-markers FILE`) places chains by hand and skips
detected ones by name. Marker chains of a kind replace that kind's detection, so list every chain
of it to keep (the gate report's `chains` holds the detected joints to copy). Points in the body
frame (metres, +Z up, facing −Y, +X the character's left), root to tip; the last point is the tip
bone's head.

```json
{
  "chains": [
    {"kind": "hood", "name": "hood", "joints": [[0, 0.12, 1.47], [0.01, 0.14, 1.37], [0.01, 0.1, 1.26]],
     "region_radius": 0.08},
    {"kind": "strap", "name": "strap1", "joints": [[0.09, -0.12, 1.42], [-0.1, -0.15, 1.08]],
     "region_radius": 0.03}
  ],
  "skip": ["hemBR", "shortsRB"]
}
```

A marker chain's region is the allowed skin (its kind's body parts, not yet taken) within
`region_radius` (default 0.03 H) of its polyline. **A ponytail** is a `hair` marker chain from the
tie down the hank: its region may take the head's and the torso's skin (a ponytail on a fused shell
is bound to Neck, UpperChest, even a Shoulder), its share comes from those bones, and it hangs from
Head, so it turns with the head (a `hood` marker on UpperChest does not); one that hangs below the
neck gets the `Back` sphere beside the Head one. Keep `region_radius` to the hank's own width, or
the coat under it swings too. **The strap's stiff mid-sag:** a strap is fixed
at the shoulder and the hip, so its one bone gets a share that peaks mid-span and fades to zero at
both ends (sin² along it): the middle sags and settles, the ends ride the chest. `side` (`x`, `l`,
`r`) names the bones' suffix; a shorts marker's thigh is the side its first joint is on.

## Clips and the chain bones

`blender-retarget`'s `arp.retarget` keys only the controls its map names (and the IK/FK
switches): no `cc_` bone gets a curve. Auto-Rig Pro's FBX export then bakes the active action onto
every exported bone, the `cc_` bones included, as curves holding their rest values. In Unity such a
clip writes each chain bone to rest every frame; a `humanoid-motion` clip never writes them. The
spring runtime handles both (`unity-rigged-character` → `reference/secondary-motion.md`, the animated pose).

## Checks

`blender -b --factory-startup -P scripts/secondary_chains.py -- --selftest` builds a test shell
(jacket with a hem lip, a back bag, shorts over thinner legs, a head with spikes) and the smooth
body, and checks: every kind but the hood found, every gate green, each shorts hem testing both
thighs, `--require hood` failing, a strap marker's mid-span share, an empty chain list on the
smooth body, a rig that already has chains refused, and the spikes as a separate hair object: rigid
by default, chained on that object with `--hair-chains`, `--require hair` failing without it; the
look-alikes (a hank down the back, a flat brim, a smooth cap over the spikes, a tall flap at the side,
shorts on one leg, a band wrapping the body) caught by their rules, a pouch on the hip found as a side bag
with every gate green, and a ponytail marker hung from Head with a Back sphere. Its secondary/1 and gate/1 samples go to
`tools/check-contracts.py`.
