# Troubleshooting and platform notes

## Errors and what they usually mean

The SDK's error-code page is the authority when a code disagrees with this table.

| Code | Name | Actual cause | What to change |
|---|---|---|---|
| `5041` | `VxErrorAlreadyInitialized` | `InitializeAsync()` ran twice — almost always a bootstrap on a scene that reloaded | `DontDestroyOnLoad` the bootstrap, or guard on `IsInitialized` |
| `20502` | `VxXmppServerErrorServiceUnavailable` | A ceiling: more than 10 non-positional channels for one user, or a 201st participant | Leave a channel before joining another; a positional channel past 200 needs the enterprise setting |
| — | login "does nothing" | `LoggedIn` was subscribed after `LoginAsync` returned, so the event had already fired | Subscribe between init and login |
| — | `ChannelJoined` never arrives | The join was awaited as though the await were the join | Bind `ChannelJoined` first; read the await as "request sent" |
| — | no audio either direction | Permission denied, the channel was joined `TextOnly`, or the input device is muted | Check the runtime permission, the `ChatCapability` used at join, and `IsInputDeviceMuted` — `UnmuteInputDevice()` if it is set |
| — | a whisper never arrives | Addressed by display name instead of `PlayerId`, or the recipient never subscribed to `DirectedMessageReceived` | Send to `AuthenticationService`'s `PlayerId` |

## Android

- `android.permission.RECORD_AUDIO` must be in the merged manifest **and** granted at runtime.
  The engine constant `UnityEngine.Android.Permission.Microphone` is that exact string, so there
  is one name, not two.
- The runtime request is not awaitable. Requesting on one line and joining on the next passes on
  a device that already had the grant and fails on a fresh install — gate the join on
  `HasUserAuthorizedPermission` or on the request callbacks.
- Bluetooth headsets route capture through SCO, and an underrun there sounds like a choppy
  microphone rather than a network problem. Test on a wired path first to place the fault.
- Shrinking with R8 strips classes the SDK reaches reflectively. Add the keep rules the package
  documents before shipping a minified build, or voice works in every build except the one you
  release. Verifying the merged manifest and the release build itself is `unity-android-release`.

## iOS

- The microphone usage description is a Player Setting, reachable from a build script as
  `PlayerSettings.iOS.microphoneUsageDescription`.
  Missing or empty, the OS terminates the app the moment it first touches the microphone — the
  first audio-capable join — so it presents as a crash on joining, not as a denied prompt. It is
  an App Review rejection as well.
- The system recording indicator is lit whenever Vivox is capturing. That is enforced by the OS
  and expected; players will ask about it, so it belongs in the settings copy.

## Web

The web build of the SDK is a subset. Audio taps, some codecs and parts of positional audio are
not there, so confirm a feature exists on that target before promising it. Browsers also require
a user gesture before capture, which means the first audio-capable join hangs off a button —
never off `Start`.

## Console

Console support ships as NDA-gated packages obtained from Unity directly. The public registry
package carries no console binaries, so a build that resolves fine on desktop will simply have
no voice there.

## When nothing obvious is wrong

Work down this ladder; each step rules out one silent failure.

1. **Order.** Core init, sign-in, Vivox init, login — in that order, with nothing between that
   could throw and be swallowed.
2. **Entry logging.** Log the first line of `LoggedIn`, `ChannelJoined` and
   `ChannelMessageReceived`. A handler that never enters was subscribed too late; that is a
   different bug from one that enters and does nothing.
3. **Capability.** Compare the `ChatCapability` the channel was joined with against what the
   code is trying to do. `TextOnly` will never carry voice, and nothing reports that.
4. **Permission.** Check the grant on the actual device, not in the Editor, where the desktop
   microphone is usually already authorised.
5. **Leaked subscriptions.** If it worked and then stopped after a scene change, audit
   `OnDestroy` unsubscribes before looking anywhere else.
6. **Address.** A directed message that vanishes is nearly always addressed to a display name.

If the ladder ends without a cause, the next step is a second device rather than more reading:
one client alone cannot distinguish "not transmitting" from "not receiving".
