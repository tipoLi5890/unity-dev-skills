# Haptics — gamepad motors with an end time, and what a phone's engine call can do

> Part of the `unity-game-feel` skill. Gamepad rumble through the Input System, a helper that
> always turns the motors off, stopping on pause, focus loss and quit; and the one vibration call
> the engine gives a phone, with its limits.

## 1. Gamepad rumble is a level, not a pulse

`Gamepad.SetMotorSpeeds(low, high)` sets two motor speeds (0..1) and leaves them there. There is
no duration argument: a rumble started on a hit runs until something sets it back to zero. The
bugs follow from that — a controller that keeps buzzing in the pause menu, after the game quits
in the Editor, or after the scene that started it unloaded.

| Motor | Feels like | Use |
|---|---|---|
| low (`lowFrequency`, left, heavy) | A thud | Landings, hits taken, the fail |
| high (`highFrequency`, right, light) | A buzz | Pickups, a launch charging, hits given |

`Feedback` rows carry `low`, `high` and `ms`, and raise `Feedback.HapticRequested(low, high,
seconds)` after multiplying by `FeelSettings.haptics`. `Feedback.cs` compiles without the Input
System; the side that owns the device subscribes.

## 2. The helper — every rumble has an end

```csharp
// RumbleChannel.cs — turns Feedback.HapticRequested into gamepad motor speeds that always stop.
// Drop into a Runtime assembly that references Unity.InputSystem, one per game, in the boot scene.
// REQUIRES com.unity.inputsystem
using UnityEngine;
using UnityEngine.InputSystem;

public sealed class RumbleChannel : MonoBehaviour
{
    [Tooltip("Longest rumble, seconds. A longer request is clamped.")]
    public float maxSeconds = 0.5f;

    Gamepad _pad;
    float _until, _low, _high;
    bool _paused;

    void OnEnable()  => Feedback.HapticRequested += Rumble;
    void OnDisable() { Feedback.HapticRequested -= Rumble; Stop(); }
    void OnApplicationQuit() => Stop();
    void OnApplicationFocus(bool focused) { if (!focused) Stop(); }

    public void Rumble(float low, float high, float seconds)
    {
        if (_paused) return;
        Gamepad pad = Gamepad.current;                   // the pad the player last touched
        if (pad == null) return;
        if (_pad != null && _pad != pad) _pad.ResetHaptics();
        _pad = pad;
        // Overlap takes the stronger of each motor and the later end: two hits are one rumble.
        bool live = Time.unscaledTime < _until;
        _low = live ? Mathf.Max(_low, low) : low;
        _high = live ? Mathf.Max(_high, high) : high;
        _until = Mathf.Max(_until, Time.unscaledTime + Mathf.Min(seconds, maxSeconds));
        pad.SetMotorSpeeds(Mathf.Clamp01(_low), Mathf.Clamp01(_high));
    }

    /// <summary>Pause: motors stop and new requests are refused until resumed.</summary>
    public void SetPaused(bool paused) { _paused = paused; if (paused) Stop(); }

    void Update()
    {
        // Unscaled: a rumble timed on scaled time never ends inside a hit stop or a pause.
        if (_pad != null && Time.unscaledTime >= _until) Stop();
    }

    void Stop()
    {
        if (_pad != null) _pad.ResetHaptics();
        _pad = null;
        _until = 0f;
        _low = _high = 0f;
    }
}
```

A gamepad stores the speeds it was last given. `PauseHaptics()` sends zero to the motors and
keeps the stored speeds; `ResumeHaptics()` sends them again — so a rumble paused at a menu comes
back at full strength after it, long past its end, unless something cleared it. `ResetHaptics()`
zeroes the stored speeds and the motors together. The helper stops with `ResetHaptics` so no
path leaves a stored speed behind for a later resume to replay.

**On pause** — wire the helper to the game's pause the same way the hit stop owner is wired
(`reference/hit-stop-and-time.md` §4): `SetPaused(true)` on entering the paused phase,
`SetPaused(false)` on leaving. The pause state machine itself is `unity-scene-flow` →
`reference/game-state-and-pause.md`. Without a helper, `InputSystem.PauseHaptics()` and
`InputSystem.ResumeHaptics()` pause and resume every device at once, and
`InputSystem.ResetHaptics()` stops every device.

**On quit and on leaving play mode** — `OnApplicationQuit` and `OnDisable` both stop. In the
Editor, a pad still buzzing after Play is pressed off means a rumble was started by something
other than the helper; grep for it:

```bash
grep -rn "SetMotorSpeeds" Assets --include='*.cs'      # every hit outside RumbleChannel is a second owner
```

**Several players** — `Gamepad.current` is the last pad used. In local multiplayer each player
has a device: hold that player's `Gamepad` (from its `PlayerInput.devices` or the reader that
owns its actions) instead of `current`, and give each player its own helper.

## 3. Numbers

| Event | low / high | ms |
|---|---|---|
| land | 0.3 / 0 | 60 |
| hit taken | 0.6 / 0.3 | 120 |
| launch | 0.5 / 0.5 | 150 |
| fail | 1 / 1 | 250 |

Keep a rumble at 50 ms or more: a motor needs that long to spin up enough to be felt. Over 300 ms a rumble stops reading as
an event and becomes noise; the helper clamps at `maxSeconds` 0.5. The `haptics` setting (0..1)
scales both motors and 0 turns rumble off — every game with rumble offers it.

Motors and their response differ between pads; a value that thuds on one buzzes on another. Tune
on the pads the game ships for, with a person holding them — a test cannot feel a motor.

## 4. Phones — what the engine gives

`Handheld.Vibrate()` is the engine's only vibration call. It takes no argument: no duration, no
strength, no pattern. The platform decides how long it lasts: a fixed system vibration on each
platform. It is right for a fail, and too long and too
coarse for a pickup or a hit.

```csharp
#if UNITY_ANDROID || UNITY_IOS
    if (FeelSettings.haptics > 0f) Handheld.Vibrate();
#endif
```

- On Android the build needs the `VIBRATE` permission; Unity adds it to the manifest when a
  script calls `Handheld.Vibrate`. Check the merged manifest in the build if vibration is silent.
- Short pulses, intensity and patterns are platform features the engine does not wrap: Android's
  `Vibrator` and `VibrationEffect`, iOS Core Haptics. They are reached through a native plugin
  (or, on Android, Unity's JNI bridge, `AndroidJavaObject`). Treat that as a platform plugin with
  its own build and test pass, not as a call.
- A phone game whose only feedback is vibration has none for players who switch it off: every
  haptic cell in the table sits beside a sound or a flash.

## 5. Testing

The journey cannot feel a motor. What it can prove, with a subscriber of its own on
`Feedback.HapticRequested`, is that a row asked for the right numbers and that the `haptics`
setting at 0 asks for nothing. Whether the motors stop on pause and on quit, and whether the
phone buzzes at all, is checked on hardware: a gamepad at the desk, and a phone through
`unity-device-testing` — its driver runs the build on the device and a person reports what they
felt as one step of the run (`unity-device-testing` → `reference/human-in-the-loop.md`).
