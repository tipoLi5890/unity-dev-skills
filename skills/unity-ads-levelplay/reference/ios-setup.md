# iOS setup

iOS adds three requirements on top of the shared integration: SKAdNetwork identifiers in
`Info.plist`, an App Tracking Transparency prompt resolved before `LevelPlay.Init()`, and a privacy
manifest that matches what the SDK actually collects. The first is largely automatic. The second is
the one that takes real code.

For the currently supported Unity, iOS deployment target and Xcode versions, read Unity's
[iOS SDK integration guide](https://docs.unity.com/en-us/grow/levelplay/sdk/ios/sdk-integration) —
those move faster than any skill file.

## SKAdNetwork

Apple's privacy-preserving attribution framework. The package writes the required identifiers into
`Info.plist` during the build, so this is a verification step rather than a task:

1. Build for iOS.
2. Open the generated Xcode project.
3. Find the `SKAdNetworkItems` array in `Info.plist`.
4. Confirm it holds many entries of the form `xxxx1234abc.skadnetwork`.

```xml
<key>SKAdNetworkItems</key>
<array>
    <dict>
        <key>SKAdNetworkIdentifier</key>
        <string>cstr6suwn9.skadnetwork</string>
    </dict>
    <dict>
        <key>SKAdNetworkIdentifier</key>
        <string>4fzdc2evr5.skadnetwork</string>
    </dict>
    <!-- many more -->
</array>
```

Empty or missing, in order of likelihood: the package is out of date, another post-process build
script is fighting over the plist, or someone has been editing `Info.plist` by hand. Let the package
own this array.

## App Tracking Transparency

Apple requires authorization before an app accesses the advertising identifier on iOS 14.5+. The
request has to **complete** before `LevelPlay.Init()` — not be fired alongside it. It is a platform
requirement first; the effect on personalised ads and fill rate is a consequence, not the reason.

Three pieces: a post-build script that writes the usage description, a native plugin that raises the
prompt, and a coroutine initializer that waits for the answer.

### 1. The usage description

Apple shows this string inside the system dialog, and reviews it. Write it through a post-build
script rather than Player Settings — the **User Tracking Usage Description** field is not present in
Unity 6, so the script is the approach that holds across versions.

`Assets/Editor/AdsIosPostBuild.cs`:

```csharp
using UnityEngine;
using UnityEditor;
using UnityEditor.Callbacks;

#if UNITY_IOS
using UnityEditor.iOS.Xcode;
using System.IO;
#endif

public class AdsIosPostBuild
{
#if UNITY_IOS
    [PostProcessBuild(999)]
    public static void OnPostProcessBuild(BuildTarget target, string buildPath)
    {
        if (target != BuildTarget.iOS) return;

        var plistPath = Path.Combine(buildPath, "Info.plist");
        var plist = new PlistDocument();
        plist.ReadFromFile(plistPath);

        plist.root.SetString(
            "NSUserTrackingUsageDescription",
            "We use tracking to show you relevant ads and support free gameplay."
        );

        plist.WriteToFile(plistPath);
        Debug.Log("AdsIosPostBuild: NSUserTrackingUsageDescription written to Info.plist");
    }
#endif
}
```

Rewrite the string for the actual app. A vague one is a rejection risk, and the placeholder above is
a placeholder.

### 2. The native plugin

`Assets/Plugins/iOS/ATTRequester.mm`:

```objc
#import <AppTrackingTransparency/AppTrackingTransparency.h>

typedef void (*ATTCallback)(int status);

extern "C"
{
    // Current status, without prompting:
    // 0 = Not Determined, 1 = Restricted, 2 = Denied, 3 = Authorized
    int _ATT_GetStatus()
    {
        if (@available(iOS 14, *))
        {
            return (int)[ATTrackingManager trackingAuthorizationStatus];
        }
        return 3; // Pre-iOS 14: nothing to ask, treat as authorized
    }

    // Raise the prompt, then hand the resulting status back on the main queue.
    void _ATT_RequestPermission(ATTCallback callback)
    {
        if (@available(iOS 14, *))
        {
            [ATTrackingManager requestTrackingAuthorizationWithCompletionHandler:^(ATTrackingManagerAuthorizationStatus status)
            {
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (callback) callback((int)status);
                });
            }];
        }
        else
        {
            if (callback) callback(3);
        }
    }
}
```

The `dispatch_async` onto the main queue is load-bearing: it is what makes the callback safe to
cross back into managed code under IL2CPP.

### 3. The initializer that waits

This **replaces** the plain initializer, it does not sit beside it. `Start()` becomes a coroutine and
`Init()` moves into its own method:

```csharp
using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;
using Unity.Services.LevelPlay;

public class LevelPlayInitializer : MonoBehaviour
{
    [SerializeField] private string appKey;

#if UNITY_IOS && !UNITY_EDITOR
    private delegate void ATTCallbackDelegate(int status);

    [DllImport("__Internal")] private static extern int _ATT_GetStatus();
    [DllImport("__Internal")] private static extern void _ATT_RequestPermission(ATTCallbackDelegate callback);

    private const int ATT_NOT_DETERMINED = 0;
    private static bool _attDone = false;

    [AOT.MonoPInvokeCallback(typeof(ATTCallbackDelegate))]
    private static void OnATTCallback(int status)
    {
        Debug.Log($"ATT: player responded — status {status}");
        _attDone = true;
    }

    private IEnumerator RequestATT()
    {
        // Already answered on a previous launch: do not prompt again.
        if (_ATT_GetStatus() != ATT_NOT_DETERMINED)
        {
            Debug.Log($"ATT: already determined (status {_ATT_GetStatus()})");
            yield break;
        }

        _attDone = false;
        _ATT_RequestPermission(OnATTCallback);
        yield return new WaitUntil(() => _attDone);
    }
#endif

    void Awake()
    {
        DontDestroyOnLoad(gameObject);
    }

    IEnumerator Start()
    {
#if UNITY_IOS && !UNITY_EDITOR
        yield return RequestATT();
#else
        yield return null;   // Editor and Android: no ATT
#endif
        InitializeLevelPlay();
    }

    private void InitializeLevelPlay()
    {
        // Privacy settings and, on SDK 9.4.x, the global ILRD subscription go here — before Init.
        LevelPlay.OnInitSuccess += OnInitSuccess;
        LevelPlay.OnInitFailed += OnInitFailed;
        LevelPlay.Init(appKey);
    }

    private void OnInitSuccess(LevelPlayConfiguration config)
    {
        Debug.Log("LevelPlay SDK initialized successfully");
    }

    private void OnInitFailed(LevelPlayInitError error)
    {
        Debug.LogError($"LevelPlay initialization failed: {error.ErrorMessage}");
    }

    void OnDestroy()
    {
        LevelPlay.OnInitSuccess -= OnInitSuccess;
        LevelPlay.OnInitFailed -= OnInitFailed;
    }
}
```

Four details that are each a device-only failure if dropped:

- **`[AOT.MonoPInvokeCallback]`** — without it the native callback crashes under IL2CPP. It compiles
  fine.
- **`[DllImport("__Internal")]`** is how the managed side reaches the `.mm` functions.
- **`_ATT_GetStatus()` first** — re-prompting someone who already answered is not possible anyway,
  and the check keeps the coroutine from waiting for a dialog that will never appear.
- **`#if UNITY_IOS && !UNITY_EDITOR`** — the plugin does not exist in the Editor or on Android.

Because `Init` now lives in `InitializeLevelPlay()`, anything documented as "before `Init()`" moves
there too: privacy calls, and on SDK 9.4.x the `LevelPlay.SetMetaData("is_test_suite", ...)` line and
the global ILRD subscription.

## Privacy manifest, iOS 17+

The SDK ships its own `PrivacyInfo.xcprivacy`, which typically declares device identifiers (IDFA),
usage data, tracking, and the required-reason APIs it uses (user defaults, file timestamp, system
boot time, disk space). What matters is that **the app's own declarations do not contradict it** —
check the Xcode project for a privacy manifest, confirm it covers the SDK's data types, and make the
App Store Connect answers match. That App Store half is `unity-monetization`.

## Xcode

Frameworks the SDK needs, normally added for you — verify under **Signing & Capabilities** if
linking fails:

- `AdSupport.framework` — IDFA
- `AppTrackingTransparency.framework` — ATT, iOS 14+
- `StoreKit.framework` — SKAdNetwork

`Other Linker Flags` should contain `-ObjC` (Unity adds it). If the Xcode in use still exposes
**Enable Bitcode**, set it to No; recent versions no longer offer it for iOS targets. For the
deployment target, take whatever Unity's
[iOS SDK integration guide](https://docs.unity.com/en-us/grow/levelplay/sdk/ios/sdk-integration)
currently states — the same page linked at the top of this file.

### App Transport Security

Some ad creatives are still served over HTTP, so without an ATS exception a fraction of ads silently
fail to render. Two ways, in decreasing order of bluntness:

```xml
<!-- Blanket allowance — simplest, weakest -->
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
</dict>
```

```xml
<!-- Per-domain exceptions — more work, narrower blast radius -->
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSExceptionDomains</key>
    <dict>
        <key>ironsrc.com</key>
        <dict>
            <key>NSIncludesSubdomains</key>
            <true/>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
    </dict>
</dict>
```

The per-domain form needs one entry per network in the waterfall, which is why the blanket form
persists in practice. Decide deliberately. Apply it in a post-process build step so it survives the
next Unity export.

## Testing on device

Simulators are not adequate here — use hardware. To re-test the prompt, ATT status is reset by
**Settings > General > Transfer or Reset iPhone > Reset > Reset Location & Privacy**; current status
is visible under **Settings > Privacy & Security > Tracking**.

Test all three ATT outcomes: authorized, denied, and restricted at the device level. Watch the Xcode
console for the initialization result.

## The iOS failures worth recognising

**ATT prompt never appears.** Either `NSUserTrackingUsageDescription` is missing (check the console
for the post-build log line), or the status is already determined on that device, or you are on a
simulator.

**Ads get worse after a denial.** Working as designed. Personalised inventory drops out;
non-personalised ads still serve at a lower rate. Continue initializing, never gate features on the
answer, and do not re-prompt.

**Submission rejected on privacy grounds.** Usually a mismatch between the App Store declarations
and what the linked SDKs collect, or a tracking description Apple found too vague. The declaration
describes the shipped binary, not the intent — a build containing an ad SDK declares what that SDK
brings even if ads are switched off in config.

## Before submitting

- ATT complete: post-build script, native plugin, coroutine initializer, and the description string
  rewritten for this app.
- SKAdNetwork array present in the built `Info.plist`.
- Privacy manifest checked against the SDK's declarations; App Store Connect answers match.
- ATS configured deliberately.
- Tested on hardware, in both the granted and denied states.
- Nothing in the app tracks a player who denied.

Apple's references: [App Tracking Transparency](https://developer.apple.com/documentation/apptrackingtransparency),
[SKAdNetwork](https://developer.apple.com/documentation/storekit/skadnetwork),
[user privacy and data use](https://developer.apple.com/app-store/user-privacy-and-data-use/).
