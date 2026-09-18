# When a step needs a person

Plugging, unplugging, waving, walking away, tapping a system sheet — a script cannot do these, and
a person doing them is the least reliable instrument in the run. The method is to make the human's
part **small, single, and verified**.

## Arm first, ask second

Start the watcher **before** sending the instruction. The human acts the moment they read it; a
watcher started afterwards misses the edge and then waits forever on a state that already changed.

```bash
nohup Tools/device-acceptance.sh -s "$SERIAL" --apk "$APK" --wait > run.log 2>&1 &
# only now:  "Unplug the charger, wait five seconds, plug it back in. Tell me when done."
```

`--wait` replaces "press Enter when done" with a poll on the device for the physical change (the
charger line flips; the app's own event line appears). That gives two things an Enter key cannot: the run
is **unattended**, and the step's clock starts at the **real** event, so "detected within 3 s"
still means something.

## One instruction, one observable

| Ask like this | Not like this |
|---|---|
| "Unplug the charger. Tell me when it's out." | "Unplug it, restart the app, and plug it back when it says waiting" |
| "Press the big button at the bottom once." | "Switch to built-in mode" |
| "Hold the controller 30 cm from both phones, still, 20 s; then press **A** 10 times, one per second." | "Do the input test" |

Each instruction names **what to touch, how many times, and for how long**. Anything the human must
decide is a variable you did not control.

**Never take "done" as the observation.** After every report, read the device: did the node
disappear, did `mode -> builtin` appear, how many `state` lines arrived? People press the button on
the wrong phone, press it twice, plug in a second too early, or answer about the previous request.
When the log disagrees with the report, the log wins — say what it shows and ask again.

## Batch the physical work

Every ask costs a human round trip; every build costs minutes. Spend the human's turns carefully:

- Do everything that needs no hands first (install, cold start, background/resume via `input
  keyevent`), then ask once for the physical sequence.
- Fold scenarios together when one action serves two checks: *unplug → (driver cold-starts the app
  with nothing attached) → replug* covers "unplug is detected", "cold start without the device" and
  "attach is detected" with one human action.
- When a build is cooking, give the human a useful parallel task (a control run on the other
  device) instead of waiting in silence.
- If the driver can do it, the driver does it: tap Android dialogs and mode buttons by coordinate;
  keep human taps for iOS.

## Two devices at once

Side by side, same stimulus, same seconds — and then **do not trust the symmetry**:

- One of the two is always a little closer, a little more on-axis. A 5 dB difference between two
  identical sensors is position until a **swap** says otherwise. Swap and repeat before writing a
  platform difference down.
- Give the human one instruction that covers both ("both phones, do not touch the buttons"). The
  commonest protocol error is a stray tap on the device that was supposed to stay put — which the
  log shows as a `mode ->` line nobody asked for.
- Clear both logs at the same moment and record wall-clock time on both; iOS Unity lines carry no
  timestamp, so interleave on the app's own counter or on native lines.

## What to tell the human about the screen

Say what they should see when it worked ("the button text changes to …", "a line `switching to …`
appears"). Then they can tell *you* it did not happen, before you spend a round trip discovering it
from the log.

## When the human's environment is the blocker

Licence expired, device locked, accessory missing, cable in the wrong phone: report it as a harness
stop (exit 3) with the one action that unblocks it. Do not accept terms, sign in, or change account
state on the human's behalf.
