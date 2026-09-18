# Verdicts, and what counts as evidence

## Three outcomes, not two

| Exit | Means | Examples |
|---|---|---|
| **0** | Every step asserted and passed | — |
| **2** | A step's assertion failed **while the harness was provably healthy** | the state never reached `Running`; no `detached` line within 3 s of the node disappearing |
| **3** | The test could not be run | no device, screen dozing, APK missing, adb died, the human never acted within the window, licence error from the build |

A driver that returns 1 for everything teaches people to re-run until green. Decide per failure
which party it blames, and write that into the message: *"no Faulted within 3 s of unplug (native
state never went ERROR?)"* names a suspect; *"step 2 failed"* does not.

## A passing run is a claim about one build on one device

Quote it that way: device model and OS, artifact path and its build time, the lines that satisfied
each step with their timestamps. "Works on Android" is not something a single phone can say.

## Intermittent is a finding, not noise

"Passed yesterday, failed today, same build" on a hardware event almost always means **a race with
a window of a few milliseconds** — a poller reading a counter between the increment and the
enqueue, an IPC call between two writes. Do not re-run until it passes. Instead:

1. Write down exactly what differed between the passing and the failing run (cold start with vs
   without the device; first event vs second).
2. Look for the *stale* symptom: **the next event delivers two** — the lost one and the new one.
   That signature means the first was produced and never consumed.
3. Find the producer/consumer pair and check the order of "publish the data" and "bump the thing
   the consumer polls". Data first, signal last.
4. Confirm with the old build before fixing (trigger the next event, watch the stale one arrive),
   then re-run the failing scenario on the fixed build.

## Before a theory, a control

Each of these is one round trip and removes a whole family of explanations:

| Surprise | Control |
|---|---|
| Device A detects, device B does not | Swap their physical positions and repeat |
| Platform X counts, platform Y does not | Same stimulus, same seconds, both running; then compare the **raw measurement**, not the verdict |
| New build fails | Same steps on the previous artifact |
| Works interactively, fails unattended | Run the unattended driver with the human watching the screen |
| A number looks too good | Check what else feeds it — a reading pinned at its nominal value with no variance means you are measuring the **stimulus source**, not the effect |

## Classify by measurement, not by the script of the day

When a run has phases ("20 s still, then 10 swings"), do not slice the log by the clock or by what
the human was asked to do. Slice it by a measured quantity (a reading above/below a threshold, a state
line) and report how many samples fell in each class. People start late, stop early and improvise;
the measurement says what actually happened.

## Reading the first seconds

Averages, FFT windows and counters are empty at start. A probe's first one or two diag lines read
`0`/`False`. Conclude nothing from them; assert on a line that can only exist after the first full
window.

## A harness bug is fixed in the harness, the same day

Tapped forty times and the dialog stayed; the presence poll never saw the unplug; the watcher
reported an unplug at the second a build finished. Each is a defect in the driver — fix the script,
add the comment that says why, and re-run. Notes that live only in someone's head are paid for
again by the next person.

## Reporting

- What ran, on what, from which artifact.
- Per step: the asserted line, its timestamp, the measured latency.
- What was **not** run, and why.
- For a failure: which party is blamed, the control that was run, and the next smallest experiment.
