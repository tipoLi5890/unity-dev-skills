# The branches: what differs per control style

> Part of the `unity-input` skill (SKILL.md §2). The funnel is the same in every branch; what changes
> is which bindings exist and how `aim` and `move` are produced.

| Branch | What is different | Read |
|---|---|---|
| Keyboard and gamepad (lane run, side run, gate room) | Nothing — the template as shipped. Both schemes are live at once; `ActiveScheme` says which was used last | `reference/action-asset.md` |
| Touch and on-screen controls (mobile casual) | An on-screen stick **is** a gamepad to the action system, so `Touch` shares the gamepad bindings; taps and swipes are a separate gesture layer | `reference/touch-and-on-screen.md` |
| Pointer aim (twin-stick depot) | `Aim` is PassThrough over a stick and a pointer position; the reader resolves it to a direction on the play plane | `reference/pointer-and-aim.md` |
| Click-to-move | A world click is not a UI click; the pointer becomes a destination, not a direction | `reference/pointer-and-aim.md` |
| A timing press graded in milliseconds on a device with latency and coarse timestamps (strike timing, rhythm) | The press carries the device's own timestamp, converted to match time across pauses, plus the tick it arrived; windows no narrower than one timestamp quantum; the ideal press placed ahead of contact by the capture latency | `reference/timing-press.md` |
| Grid step with key repeat (sorting yard) | A held direction becomes steps: one at once, 0.25 s, then every 0.10 s — `StepRepeater` in `resources/RunInput.cs`, not the OS key repeat and not a Hold interaction | `reference/reading-input.md` |
