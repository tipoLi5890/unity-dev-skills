# Drawing a picture to cut into layers

A 2D character or scene that will be split into layers (a PSB for Unity 2D Animation, a PSD for
Live2D Cubism, parallax strips) is drawn for the cut, not only for the look. The cut and the
fills are `comfyui-asset-generation` → `reference/layered-2d.md`; this page is the brief.

## A character

Choose the view by what the game shows:

- **Front:** a portrait, dialogue busts, a top-down game.
- **Side:** a side-scroller. A front view running in place reads weakly.

When the game needs both, draw both as separate pictures with the same anchor and canvas.

Every picture follows these rules:

- **One character, whole, centred.** It fills about 85 % of the height on a 2:3 portrait canvas
  (1024 × 1536).
- **A flat key background** (`#FF00FF` unless the palette is magenta: `reference/codex-runtime.md`
  §5). No ground plane, no cast or contact shadow, no text.
- **Limbs apart:**
  - Clear background between each arm and the body below the armpit, and between the legs below
    the crotch.
  - The split finds the arms as islands of their own below the armpit, so an arm drawn against
    the body cannot be cut from it.
- **Nothing crossing:** no arm across the chest, no scarf or long hair over a joint. A bag sits
  on the hip, away from the hands.
- **A held prop** (a pole, a spear, a shield) is cut as a layer of its own with `layer_split.py
  fills --props`, so it may cross the body. Its arm must still stand clear:
  - Hold it out in front, the arm stretched forward at chest height. A prop held low at the hip
    pulls the arm onto the body, and asking for a gap does not undo that.
  - A shield goes on the far arm, behind the body's far side; the split fills the far arm behind it.
  - The whole prop inside the frame.
- **Neutral face:** eyes open, mouth closed, looking along the view. The blink and talk frames
  are edits of this one.
- **Even lighting:** flat or two-tone shading and the same outline weight all round. The split
  draws the outline back on a shoulder from the source's own outline colour.

By view:

- **Front:**
  - Strictly front-facing and symmetric.
  - Arms straight, about 30° out from the body, open hands.
  - Legs apart, with a gap from the crotch down.
- **Side:**
  - A strict profile, facing the direction the game runs.
  - The near arm swung about 30° forward and the far arm 30° back, both clear of the chest and
    back.
  - An open stride: the near leg forward, the far leg back, a gap below the shorts.
  - One eye shows.

The courier-run runner's side brief, after the project's style preamble and with the front
picture as `-i` Picture 1:

```text
Subject: ONE character, the same bike courier as Picture 1, drawn in a strict SIDE VIEW, full
profile, facing RIGHT. Neutral rig pose for cutting into layers: the near arm straight and swung
about 30 degrees FORWARD with clear empty space between it and the chest, the far arm straight and
swung about 30 degrees BACKWARD with clear empty space between it and the back, open relaxed hands;
legs in an open stride, the near leg forward and the far leg back, a clear gap between the legs
below the shorts, both feet flat. Face in profile: one eye visible and open, calm neutral
expression, mouth closed. Nothing held; the bag sits on the far hip behind the body. Whole
character in frame, nothing cropped, centered, filling about 85% of the image height. Portrait
image. No cast or contact shadow, no ground plane, no text. Flat solid #FF00FF background.
```

A courier-run street guard (an enemy, facing the runner), with the same preamble and the runner
as Picture 1:

```text
Subject: ONE enemy character, a city street guard, drawn in a strict SIDE VIEW, full profile,
facing LEFT. His NEAR arm is stretched FORWARD to the left, almost straight, at chest height, with
clear empty background between the whole arm and the jacket below the armpit; that hand grips a
long wooden guard pole near its middle, the pole running from its front end raised ahead of the
hand back through the hand and diagonally down ACROSS the front of his jacket and hips, the back
end low behind his legs. His FAR arm carries a round riot shield strapped to the forearm, behind
the body's far side. Legs in an open stride, a clear gap between them. One eye visible and open,
mouth closed. Whole character, pole and shield in frame. Flat solid #FF00FF background.
```

**Several renders:** a call can return more than one image (`codex_generate.py` exits 5). Pick
the one whose arms stand clearest of the body.

**Key it:** use `key_unmix.py --edge tint`. The fills step pads every edit to a square itself,
so draw at 2:3.

## A scene

Qwen-Image-Layered splits a scene by depth. Draw the depths so that they separate:

- **Bands that do not interleave:**
  1. the sky;
  2. a far silhouette, such as a skyline;
  3. the middle distance, such as shopfronts;
  4. the ground;
  5. two or three near props in front.
- **Seen straight from the side,** wide landscape (16:9).
- **Props apart:** each near prop stands alone, partly covering the band behind it, never two
  touching. Each prop becomes a sprite of its own, placed by the level, so the strips never
  repeat a prop beside its own copy.
- **No people, vehicles or lettered signs.** They would land in a strip and repeat with it.
- **Even light,** with no cast shadow across bands. A shadow belongs to no single layer.

The scene's layered-model prompt describes the whole picture, band by band, in the brief's words.
