# Instrumental BGM — a bed with no voice in it

MiniMax Music 3 is a song model: left to choose, it sings, hums or chants. A background bed
sits under dialogue and sound effects, so a voice in it is a defect, and "instrumental" has to
be said in three places at once. Settings, components and post-processing:
`reference/minimax-music3.md`.

## The three places that decide it

| Where | Write | Why |
|---|---|---|
| Caption, **Vocal Details** | `Instrumental only. No vocals of any kind: no singing, no humming, no choir, no vocal chops, no spoken word, no whispers. The lead melody is carried by <instrument>.` | The exclusions are spelled out because a bare "instrumental" still hums. Naming the lead gives the melody somewhere to go other than a voice |
| **Lyrics** | Tags only, never empty: `[Intro]`, one `[Instrumental]` per section, `[Outro]` | An empty lyrics field leaves the choice to the model, and it chooses a voice about as often as not |
| The rest of the caption | No voice words, not even as texture | "Choir pad", "vocal chops", "chant", "sing-along", "anthemic" each invite one. Write the instrument instead: string pad, synth pad, brass stab |

Keep the lyrics to `[Intro]`, `[Instrumental]` and `[Outro]`. `[Verse]`, `[Pre-Chorus]` and
`[Chorus]` are sung sections, and `[Bridge]` and `[Solo]` add nothing a described section does
not.

## Caption skeleton

Three labelled sections, in this order:

```text
Global Metadata: <genre, subgenre>. <BPM> BPM, <key>. <mood, and how it moves: "a steady drive
from start to end, no build and no drop">. Background music for <where in the game>, looping
under <gameplay and sound effects | interface sounds>. <production character>, moderate dynamics.

Vocal Details: Instrumental only. No vocals of any kind: no singing, no humming, no choir, no
vocal chops, no spoken word, no whispers. The lead melody is carried by <lead instrument>.

Arrangement: <the instruments>. Intro: <what starts>. Section A: <the main theme, who plays
it>. Section B: <a second idea, who takes the lead>. Section A again: <what is added>.
Breakdown: <what drops out, for how long>. Section B again: <...>. Outro: <what remains>,
resolving so the end can loop back to the start.
```

What makes it a bed and not a song, all in Global Metadata:

- **Say where it plays** — "background music for the world map, looping under interface sounds".
- **Flatten the arc** — "steady from start to end, no build and no drop". A climax pulls
  attention off the game.
- **Moderate dynamics**, so one mixer level works for the whole loop.
- **An exact BPM and key** when beds will crossfade: give the set one key or a related pair.

## Length comes from the arrangement

`max_duration` is a ceiling; the model ends the track when its structure is done.

| Arrangement | Lyrics | Comes back at about |
|---|---|---|
| Intro, one main section, Outro | `[Intro]` `[Instrumental]` `[Outro]` | half a minute |
| Intro, A, B, A, Breakdown, B, Outro | `[Intro]`, five `[Instrumental]`, `[Outro]` | one to two minutes, and it varies by seed |

Adding `[Instrumental]` tags without describing more sections is unreliable: sometimes longer,
sometimes not. Set
`max_duration` above the length you want, and read the real duration with `ffprobe` before any
fade. A bed loops, so a short one that loops cleanly beats a long one that wanders; for variety,
generate the same caption on several seeds and rotate them.

## Three worked captions — the courier run

**Chase bed** (gameplay). Lyrics: `[Intro]`, three `[Instrumental]`, `[Outro]`.

```text
Global Metadata: Synthwave, retro electro. 128 BPM, A minor. Energetic and optimistic, a steady
drive from start to end with no dramatic drop. Background music for a three-lane courier runner
game, looping under gameplay and sound effects. Clean modern production, punchy and tight,
moderate dynamics.

Vocal Details: Instrumental only. No vocals of any kind: no singing, no humming, no choir, no
vocal chops, no spoken word, no whispers. The lead melody is carried by a bright arpeggiated
analog synth.

Arrangement: Four-on-the-floor kick with crisp claps and closed hi-hats, pulsing sidechained
analog bass, warm pad chords, bright arpeggiated synth lead. Intro: bass pulse and hi-hats, pad
fading in. Section A: full drums, the arpeggio lead states the theme. Section B: a square-wave
synth answers with a counter-melody over the same bass. Section A again: the theme returns with
an added octave. Outro: drums thin out, the arpeggio continues over the pad and resolves so the
end can loop back to the start.
```

**Menu bed.** Lyrics: `[Intro]`, five `[Instrumental]`, `[Outro]`.

```text
Global Metadata: Lo-fi hip-hop, chillhop. 78 BPM, D flat major. Relaxed and cosy throughout, no
build and no drop. Background music for a game menu screen, looping quietly under interface
sounds. Warm bedroom production: vinyl crackle, tape hiss, soft-clipped drums, low-passed mix.

Vocal Details: Instrumental only. No vocals of any kind: no singing, no humming, no choir, no
vocal chops, no spoken word, no whispers. The lead melody is carried by a warm Rhodes electric
piano, answered by a mellow jazz guitar.

Arrangement: Dusty boom-bap drums with a soft kick, lazy swung snare and brushed hi-hats, round
sub bass, Rhodes chords with slow chorus wobble, mellow jazz guitar licks, constant vinyl
crackle. Intro: crackle and solo Rhodes chords, drums slipping in. Section A: drums, bass and
Rhodes state the main theme. Section B: the guitar takes the lead with a new phrase while the
Rhodes comps. Section A again: the main theme returns with a soft counter-line on a muted
trumpet far back. Breakdown: drums drop away to crackle and floating Rhodes for four bars, then
the beat eases back in. Section B again: guitar and Rhodes trade phrases. Outro: elements drop
out one by one to crackle and a last Rhodes chord that leads back to the start.
```

**World-map bed.** Lyrics: `[Intro]`, five `[Instrumental]`, `[Outro]`.

```text
Global Metadata: Orchestral adventure score, cinematic. 110 BPM, D major. Heroic and hopeful, a
steady forward motion without a dramatic climax. Background music for the world map of a courier
runner game, looping under interface sounds. Concert-hall production, wide and clear, moderate
dynamics.

Vocal Details: Instrumental only. No vocals of any kind: no singing, no humming, no choir, no
vocal chops, no spoken word, no whispers. The lead melody is carried by French horns, doubled
by violins.

Arrangement: Staccato string ostinato, soaring French horn theme, playful flute and clarinet
countermelody, timpani and snare drum, harp glissandi, low brass pedal. Intro: string ostinato
and harp, horns entering softly. Section A: horns state the main theme over the ostinato.
Section B: woodwinds take a lighter second theme, pizzicato strings underneath. Section A again:
the main theme returns with full brass and timpani. Breakdown: the orchestra thins to harp and
solo clarinet for four bars, then the ostinato rebuilds. Section B again: strings carry the
second theme, horns answering. Outro: brass thins out, strings and harp carry the ostinato and
resolve so the end can loop back to the start.
```

## Run

Captions and lyrics have line breaks, so pass them as files: `--set NODE.INPUT=@path`.

```bash
python3 scripts/comfy_asset_client.py --workflow templates/minimax_music3_api.json \
  --output-dir out/bgm_menu_1 --keep-loaded \
  --set 4.caption=@captions/menu.txt --set 4.lyrics=@captions/menu_lyrics.txt \
  --set 4.max_duration=150 --set 4.seed=101 --set 7.seed=101
```

Change `4.seed` and `7.seed` together for another take; drop `--keep-loaded` on the last one.

## Acceptance — prove there is no voice

Generate two or three seeds per bed and screen every one:

```bash
python3 scripts/check_instrumental.py out/bgm_menu_*/*.flac      # exit 1 names the clips with a voice
```

It separates what a stem separator takes for a voice, then asks an audio tagger what that stem
sounds like — a flute or a synth lead the separator mistook reads as an instrument, a hum reads
as humming. It needs a Python with demucs, transformers, librosa and soundfile; when that is not
there, ask the user rather than set it up unasked, or listen to the intro and outro, where a hum
or a wordless "ooh" comes in.

| Result | Do |
|---|---|
| `VOCAL` on a caption that follows the three rules | another seed first; the caption is not the fault |
| `VOCAL` on most seeds | a voice word is still in the caption, or the lyrics hold a sung tag |
| `clean`, but short | add described sections to the Arrangement, one `[Instrumental]` each |
| `clean` | loudness, fades and delivery format: `reference/minimax-music3.md` |

A song with a voice is the opposite brief: Vocal Details describes the singer, and the lyrics
carry `[Verse]` and `[Chorus]` text.
