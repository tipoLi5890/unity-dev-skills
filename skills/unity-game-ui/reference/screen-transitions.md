# Screen transitions: visibility is not a lifecycle

Fades are the cheapest way to make a menu flow feel finished. They are also the change most likely
to break logic that has nothing to do with rendering, because a lot of UI code quietly uses
"am I on screen?" as its stop condition.

---

## The bug an exit fade introduces

Change screen transitions so `Hide()` **fades out over 0.12 s** instead of deactivating the object
immediately, and take a screen — a pre-round countdown — that guards its per-frame work with the
obvious line:

```csharp
void Update()
{
    if (!Visible) return;          // was exactly true before Hide() became a fade
    ...
    if (_t <= 0f) done?.Invoke();  // start the round
}
```

`Visible` now stays true for the length of the fade, so `done` fires **every frame** of it. Each
call starts another round, so the recorded session for a single round holds **duplicate pickups**,
which surface on the results screen as an implausible score line — a pickup count far larger than
the number of things the run actually showed the player. Nothing looks wrong on screen; the
transition animates perfectly.

The general shape: **visibility is a rendering property, and it is being used as a state
machine.** The two agree exactly as long as hiding is instantaneous.

---

## Fix it in three places, not one

1. **Latch the one-shot, and clear the latch *before* invoking the callback.** Clearing after the
   call still lets a re-entrant caller through.

   ```csharp
   bool _running;
   ...
   if (_t <= 0f && _running) { _running = false; done?.Invoke(); }
   ```

2. **Guard the thing being started, too.** The screen is not the only possible source of a double
   start — a touch button, a keyboard input and an Android back press can all reach the same entry
   point:

   ```csharp
   public void Begin()
   {
       if (IsRunning) return;
       ...
   }
   ```

3. **Assert the invariant in a test.** "Fires exactly once" is a property to check, not to read.
   A play-mode smoke test that drives one round and asserts exactly one pickup was recorded catches
   the whole class, including the next transition someone lengthens.

Then **audit every early-out of this shape** the day you add a fade — this is a grep, and it is
short:

```bash
grep -rn '!Visible\|!activeSelf\|!isActiveAndEnabled\|alpha *[<=]' Assets --include='*.cs'
```

Each hit is a question: does this mean "do not draw" (fine) or "do not run" (now wrong)? Anything
in the second group needs its own explicit flag.

**Corollary:** during an exit fade two screens are alive at once, so input can reach both. Route
input from the flow state machine — the thing that knows which screen is *current* — rather than
from whichever object happens to be enabled.

---

## Starting values

A starting point, not a law — authored taste, so tune them to the game:

| | |
|---|---|
| Enter | 0.22 s fade in + 24 px positional offset |
| Direction | forward navigation floats **up**, going back sinks **down** |
| Exit | 0.12 s fade out |
| Deliberately absent | scale-in, bounce, blur |

The direction carries meaning for free: a player who cannot read the header still sees whether they
went deeper or came back. Keeping scale and bounce out is a legibility decision — motion that
changes an element's size fights the pixel grid (see `layout-math.md` §3, "breathe with light, not
with geometry") and buys nothing at distance.

**Budget the audit with the feature.** The exit fade is what makes the flow feel considered, and it
is also what turned "hidden" into "still running". Adding one is a two-part job: the animation, and
the pass over everything that used visibility as a lifecycle.
