# Which source decides

Moved out of SKILL.md: the checks to run before writing Vivox code, and which source wins on a mismatch.

## Before you start: which source decides

- **Is the package there?** Without it the types do not exist:
  `System.Type.GetType("Unity.Services.Vivox.VivoxService, Unity.Services.Vivox")` is **null**.
- **Two platform facts need no credentials.** `UnityEngine.Android.Permission.Microphone` reads
  `android.permission.RECORD_AUDIO`. The iOS plist entry is a Player Setting, not a hand-edited
  file: `PlayerSettings.iOS.microphoneUsageDescription` is a static `String` property, so CI can
  assert on it.
- **Everything else needs a UGS project with Vivox credentials, a microphone and a second device
  to run.** Error codes, ceilings, event ordering and history retention come from the SDK's
  documentation. On a mismatch, the installed package decides a **signature** (the compiler reads
  it); the Vivox documentation decides **what the service does** and **what an error code
  means**. A curated index of them is at `https://docs.unity.com/en-us/vivox-unity/llms.txt` —
  fetch it to find which page covers a topic, then read the page. Cite the page, not the
  index: the index finds sources, it is not one.
