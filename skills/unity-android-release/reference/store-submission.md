# Between a signed artifact and a live listing

## APK or AAB

- **AAB** for Play. It is what the store takes, and Play generates per-device APKs from it.
- **APK** for direct distribution and for testing — an AAB cannot be installed on a device, so
  the artifact you verify by playing is always an APK.

Build the APK first even when the AAB is the goal: it is the only one you can install, and
"it built" is not "it runs".

## Symbols, kept with the artifact that produced them

An IL2CPP crash stack without symbols is a list of addresses. Symbolication needs the symbols from
**that exact build** — a rebuild, even from the same commit, will not match.

Enable `Create Symbols.zip` in Player Settings before the first artifact you hand out, and archive
it beside the artifact. This is only ever discovered to be missing at the moment you receive your
first crash report, which is exactly when it is too late to add.

## The Data Safety form is answered from the merged manifest

Not from memory, and not from your own `AndroidManifest.xml`. Read the permissions out of the
artifact (`artifact-verification.md`) and answer from that list. A permission a plugin brought in is
still a declaration you are signing.

Watch for the ones that draw scrutiny — `RECORD_AUDIO`, anything `FOREGROUND_SERVICE_*`, location,
and any permission that arrived without you asking for it. Have a one-line justification ready for
each before you open the form, and be able to point at the feature that needs it.

## 16 KB page size is a store requirement, and your plugins decide whether you meet it

Play requires 16 KB page-size compatibility for new apps, and from Android 15 an app with
`targetSdk >= 35` cannot load a 4 KB-aligned native library on a 16 KB-page device. A project that
ships someone else's `.so` therefore has a `targetSdk` ceiling set by that library, not by its own
readiness — check it before you promise a submission date, because the fix is upstream and the
symptom appears only on some hardware. The check and the pin are in
`player-settings-android.md`.

Confirm the exact date and policy wording in Play Console Help before you plan around a deadline.

## The new-app gate — check whether it applies to you

Confirm the current rules in Play Console Help:

- Applies to apps published from a **personal** Play Console account **created on or after
  2023-11-13**. Accounts registered as a legal business entity are **exempt entirely** — so the
  first question is which kind of account you have, not how many testers you can find.
- The bar is **12 testers opted in continuously for 14 days**.
- Since 2026 Google also checks the testers genuinely **used** the app — real accounts on
  independent devices with natural usage across the window, not a batch of dormant opt-ins.

It is a calendar dependency, not a task. Start recruiting when the **first installable APK exists**,
not when the store page is ready — the 14 days cannot be compressed.

## Size

Texture compression is the lever — ASTC on modern targets. Read the build report for the top asset
offenders rather than guessing; in a Unity game the answer is almost always textures and audio, and
almost never code.

Strip Development Build flags for anything handed to a human. A profiler socket and a watermark
read as a broken build to everyone who is not the person who made it.

## Reproducibility, before you need it

A `file:` UPM dependency pins a package to one machine's filesystem:

```json
"com.example.plugin": "file:/Users/you/dev/plugin/unity-package"
```

That builds only on your machine. It is fine while a plugin is being co-developed and a problem the
moment CI, a second machine or a colleague is involved — move it to a git URL pinned to an
annotated tag before that day, not during it. Have the build script warn on `file:` for release
builds so the debt is visible each time.
