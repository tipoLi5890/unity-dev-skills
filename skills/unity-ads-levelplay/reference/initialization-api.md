# Initialization API

Nothing loads before `LevelPlay.Init()` succeeds, so this is the step whose mistakes look like
every other kind of failure. Four rules hold regardless of where the code ends up:

- **Subscribe `OnInitSuccess` and `OnInitFailed` before calling `Init()`.**
- **Call `Init()` as early as the first scene allows**, so ads have time to load before they are
  wanted.
- **Initialize exactly once** — `DontDestroyOnLoad` on the holder, not a fresh call per scene.
- **Create ad objects inside `OnInitSuccess`**, never earlier.

## Where the code lives — four shapes

Which one to use is the publisher's decision, not a default. Present all four; the code is the same
`Init` call in each.

### 1. A dedicated script

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class LevelPlayInitializer : MonoBehaviour
{
    [SerializeField] private string appKey;

    void Awake()
    {
        // Survive scene loads so the SDK is initialized once per process
        DontDestroyOnLoad(gameObject);
    }

    void Start()
    {
        LevelPlay.OnInitSuccess += OnInitSuccess;
        LevelPlay.OnInitFailed += OnInitFailed;

        LevelPlay.Init(appKey);
    }

    private void OnInitSuccess(LevelPlayConfiguration config)
    {
        Debug.Log("LevelPlay SDK initialized successfully");
        // Ad objects are created from here
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

`Assets/Scripts/LevelPlayInitializer.cs` is a reasonable home. Then: attach it to a GameObject in the
first scene, and paste the App Key into the Inspector field.

**If ATT was set up for iOS, use the coroutine variant from [`ios-setup.md`](ios-setup.md) instead of
this template** — it already carries `DontDestroyOnLoad` and the `IEnumerator Start()` that waits for
the prompt.

### 2. Folded into an existing manager

Add the namespace, three lines to the existing `Start()`, the two callbacks, and the unsubscribes:

```csharp
using Unity.Services.LevelPlay;
```

```csharp
void Start()
{
    LevelPlay.OnInitSuccess += OnInitSuccess;
    LevelPlay.OnInitFailed += OnInitFailed;
    LevelPlay.Init("YOUR_APP_KEY_HERE");

    // ... whatever this Start() already did
}
```

```csharp
private void OnInitSuccess(LevelPlayConfiguration config)
{
    Debug.Log("LevelPlay SDK initialized successfully");
}

private void OnInitFailed(LevelPlayInitError error)
{
    Debug.LogError($"LevelPlay initialization failed: {error.ErrorMessage}");
}
```

```csharp
void OnDestroy()
{
    LevelPlay.OnInitSuccess -= OnInitSuccess;
    LevelPlay.OnInitFailed -= OnInitFailed;
}
```

Two things to check before testing. The placeholder has to be replaced with the real alphanumeric App
Key — a literal `"YOUR_APP_KEY_HERE"` reaching a build is a common and entirely silent failure. And
if the host script does not already persist across scenes, add `DontDestroyOnLoad(gameObject)` to its
`Awake()`, or a scene load re-runs `Init()`.

### 3. Its own script, referenced by the manager

Create the class from shape 1, **attach the component in the Editor** to a dedicated persistent
GameObject, set the App Key on that component, and let the manager hold a reference:

```csharp
using UnityEngine;

public class GameManager : MonoBehaviour
{
    // Assigned in the Inspector. The App Key lives on the initializer component,
    // not here, so ad credentials stay in one place.
    [SerializeField] private LevelPlayInitializer levelPlayInitializer;

    void Awake()
    {
        // The initializer initializes itself in its own Start();
        // this reference exists only so the manager can coordinate with it.
    }
}
```

> **Why not `AddComponent<LevelPlayInitializer>()` at runtime?** The App Key comes from a
> `[SerializeField]`, and a component created at runtime never receives a serialized Inspector value.
> The key would be empty and initialization would fail with a message about the key rather than about
> the component. Attaching in the Editor is what makes the field fillable.

Since `Awake()` calls `DontDestroyOnLoad(gameObject)`, put the initializer on an ads-specific
GameObject rather than on the manager — unless the manager is meant to persist too.

### 4. Just the code

Hand over the complete class from shape 1 as a snippet, with no file creation and no Inspector
walkthrough, plus the one-line instruction: save it as `LevelPlayInitializer.cs`, attach it to a
persistent GameObject in the first scene, set the App Key field in the Inspector.

## Impression-revenue wiring at init time — version dependent

**SDK 9.5.0+: add nothing here.** Impression data arrives per ad instance through
`OnAdImpressionDataReady`, subscribed when each ad object is created. The global
`LevelPlay.OnImpressionDataReady` still exists but is deprecated on this branch and raises a compiler
warning.

**SDK 9.4.x and earlier:** the global event is the only route, and it has to be subscribed **before**
`Init()` or early impressions are lost. Inside `Start()`, above `LevelPlay.Init(appKey)`:

```csharp
// SDK 9.4.x and earlier. Must precede LevelPlay.Init(). Fires on a BACKGROUND thread —
// see ilrd-api.md before doing anything but logging in the handler.
LevelPlay.OnImpressionDataReady += OnImpressionDataReady;
```

```csharp
private void OnImpressionDataReady(LevelPlayImpressionData impressionData)
{
    Debug.Log($"ILRD: {impressionData.AdNetwork} / {impressionData.AdFormat} / ${impressionData.Revenue}");
}
```

```csharp
LevelPlay.OnImpressionDataReady -= OnImpressionDataReady;   // in OnDestroy()
```

On the iOS coroutine initializer there is no `Init` inside `Start()` at all, so the subscription goes
into `InitializeLevelPlay()` immediately above `LevelPlay.Init(appKey)`. Shapes 2 and 3 take the same
wiring in whichever file owns the `Init` call — for shape 3 that is the initializer, with no change
to the manager.

Confirming the log line fires needs a device build: mock ads generate no impression data.

## API reference

### `LevelPlay.Init(string appKey, string userId = null)`

```csharp
LevelPlay.Init("your_app_key");
LevelPlay.Init("your_app_key", "user_12345");
```

`appKey` from the dashboard. The optional `userId` is your own identifier, and it is what
server-to-server reward verification and user-level analytics key on. Callbacks must already be
subscribed. Constraints on the id: alphanumeric, up to 64 characters, unique per player.

### `LevelPlay.SetSegment(LevelPlaySegment segment)`

Attaches user-segment data for targeting and reporting. Callable before or after `Init()`, and worth
re-sending when a player crosses a milestone — a level, a first purchase.

```csharp
var segment = new LevelPlaySegment();
segment.SegmentName = "high_spenders";
segment.Level = 25;
segment.UserCreationDate = 1609459200000;   // Unix ms
segment.IapTotal = 49.99;
segment.IsPaying = 1;                        // 0 or 1

segment.SetCustom("vip_tier", "gold");
segment.SetCustom("gameplay_hours", "150");

LevelPlay.SetSegment(segment);
```

| Member | Type | Meaning |
|---|---|---|
| `SegmentName` | string | Segment label |
| `Level` | int | Current level |
| `UserCreationDate` | long | Account creation, Unix ms |
| `IapTotal` | double | Lifetime IAP spend |
| `IsPaying` | int | 0 or 1 |
| `SetCustom(key, value)` | method | Custom pair — **maximum 5** |

### `LevelPlay.SetDynamicUserId(string userId)`

Returns `bool`. A user id that can change mid-session, used specifically for server-side rewarded
verification — distinct from the `userId` passed to `Init()`. Set it before showing a rewarded ad
that needs verification; the typical trigger is a guest player signing in.

```csharp
bool success = LevelPlay.SetDynamicUserId("user_67890");
```

### `LevelPlay.SetMetaData(string key, params string[] values)`

Two uses worth knowing:

```csharp
// Server-to-server rewarded callback parameters (SDK 8.11.0+)
LevelPlay.SetMetaData("LevelPlay_Rewarded_Server_Params", new [] { "key1=value1", "key2=value2" });
```

```csharp
// Test Suite — must precede Init()
LevelPlay.SetMetaData("is_test_suite", "enable");
LevelPlay.Init(appKey);
```

### `LevelPlay.SetPauseGame(bool pause)`

iOS only (SDK 8.5.0+). Pauses game activity — but not ad callbacks — while a rewarded or interstitial
ad is on screen; resumes on close. Once per session, either side of `Init()`.

### `LevelPlay.LaunchTestSuite()`

Opens the on-device test overlay. Requires `SetMetaData("is_test_suite", "enable")` before `Init()`
and a successful initialization, and does nothing in the Editor. Guard it so it cannot ship:

```csharp
void OnInitSuccess(LevelPlayConfiguration config)
{
    #if UNITY_EDITOR || DEVELOPMENT_BUILD
    LevelPlay.LaunchTestSuite();
    #endif
}
```

### `LevelPlay.SetAdaptersDebug(bool enabled)`

Verbose adapter logging. The right tool when one specific network is not filling and nothing in your
own logs explains it. Either side of `Init()`; keep it out of release builds.

### `LevelPlay.SetNetworkData(string networkKey, string networkData)`

Passes an adapter-specific string to one network. Call before `Init()`. Consult that network's
adapter documentation for what it accepts — a standard integration does not need this.

```csharp
LevelPlay.SetNetworkData("UnityAds", "customValue");
```

### Events

`LevelPlay.OnInitSuccess` — `event Action<LevelPlayConfiguration>`.

```csharp
LevelPlay.OnInitSuccess += (config) =>
{
    Debug.Log("SDK ready");
    Debug.Log($"Unity Version: {LevelPlay.UnityVersion}");
    Debug.Log($"Plugin Version: {LevelPlay.PluginVersion}");
};
```

`UnityVersion` and `PluginVersion` are static members of `LevelPlay`, **not** properties of the
`LevelPlayConfiguration` you are handed — a natural-looking guess that does not compile.

`LevelPlay.OnInitFailed` — `event Action<LevelPlayInitError>`, carrying `ErrorCode` and
`ErrorMessage`.

```csharp
LevelPlay.OnInitFailed += (error) =>
{
    Debug.LogError($"Init failed: Code {error.ErrorCode}, Message: {error.ErrorMessage}");
};
```

A retry on failure is reasonable — `Invoke(nameof(RetryInitialization), 5f)` calling `Init(appKey)`
again — as long as it is bounded. An App Key that is wrong will not become right.

## Timing

Early, in the first scene, is the default and the recommendation: loads start sooner, so an ad is
ready when the game first wants one.

Deferring is legitimate in exactly one shape — when something must be *known* before `Init()` runs.
A consent answer is the honest case:

```csharp
IEnumerator InitializeAfterOnboarding()
{
    yield return new WaitUntil(() => HasCompletedOnboarding());

    LevelPlay.OnInitSuccess += OnInitSuccess;
    LevelPlay.OnInitFailed += OnInitFailed;
    LevelPlay.Init(appKey);
}
```

The cost is that ads are not ready as early. Deferring merely to shorten app start trades a real
monetisation window for a launch metric.

## Coming from `IronSource.Agent`

```csharp
// Was
IronSource.Agent.validateIntegration();
IronSource.Agent.init(appKey);
```

```csharp
// Now
LevelPlay.OnInitSuccess += OnInitSuccess;
LevelPlay.OnInitFailed += OnInitFailed;
LevelPlay.Init(appKey);
```

Three differences that matter: there is now a failure callback, subscription must precede `Init()`,
and ad objects are created explicitly rather than the SDK loading in the background on its own.
Integration validation moved from `validateIntegration()` to the Test Suite. Full migration —
per-format API mapping, the completeness checklist, Unity Ads, Maven Central — is
[`migration-sdk-9.md`](migration-sdk-9.md).

## Error codes

> Code **508** arrives as a `LevelPlayInitError` through `OnInitFailed`; it is mediation-level, not
> per-ad, which is why its ad-format column is empty. Everything else below reaches you as a
> `LevelPlayAdError` in a load- or show-failure callback.

| Code | Ad formats | Meaning |
|---|---|---|
| **508** | — | Mediation or network init failure; Demand Only API called in non-Demand-Only mode, or the reverse |
| **509** | Interstitial, Rewarded | Show failed: no ads to show |
| **510** | Interstitial, Rewarded, Banner | Load failed: server response failed |
| **520** | Interstitial, Rewarded | Show failed: no internet, with `ShouldTrackNetworkState` enabled |
| **524** | Interstitial, Rewarded | Show failed: placement at its pace or capping limit |
| **526** | Interstitial, Rewarded | Show failed: ad unit at its daily cap for the session |
| **604** | Banner | Load failed: placement capped |
| **605** | Banner | Unexpected exception while loading the banner |
| **606** | Banner | No banner fill on any network, first load |
| **1007** | Interstitial, Rewarded | Auction failed: request lacked required information |
| **1022** | Rewarded | Show failed: another rewarded ad is already showing |
| **1023** | Rewarded | Show failed: no available ads |
| **1035** | Interstitial | Empty waterfall |
| **1036** | Interstitial | Show failed: another interstitial is already showing |
| **1037** | Interstitial | Load failed: another interstitial load is in flight |

Branch on the code, not the message:

```csharp
private void OnAdLoadFailed(LevelPlayAdError error)
{
    Debug.LogWarning($"Ad load failed: Code {error.ErrorCode}, Message: {error.ErrorMessage}");

    if (error.ErrorCode == 510)
    {
        // Server response failed — retry with backoff
    }
    else if (error.ErrorCode == 520)
    {
        // Offline — wait for connectivity rather than retrying on a timer
    }
}
```

`1036` and `1037` are your own code calling twice, not the network's fault — see
[`interstitial-api.md`](interstitial-api.md).

## Checks worth running

- Initialization logs success, and `OnInitSuccess` actually fires.
- Ad objects are constructed after it, not beside it.
- `OnInitFailed` is implemented and its message is visible.
- The user id, if used, arrives as the second argument to `Init` and is non-empty.
- Init happens in the first scene, and only once across a scene change.

## App Key, ad unit ids and AdMob keys

From the LevelPlay dashboard at <https://platform.ironsrc.com/>:

| Item | Where | Needed by |
|---|---|---|
| **App Key** | **Apps** → your app → the alphanumeric string under the title | SKILL.md §7 |
| **Ad unit ids** | **Ad units** → your app → one id per format | SKILL.md §9 |

If the app and its ad units do not exist yet, create them first — Unity's
[add-app](https://docs.unity.com/en-us/grow/levelplay/platform/get-started/add-app) and
[ad-units](https://docs.unity.com/en-us/grow/levelplay/platform/get-started/ad-units) pages are the
authority. The App Key is needed before initialization; ad unit ids can wait until the formats are
chosen.

**AdMob as a mediated network needs its own keys**, entered under **Ads Mediation > Developer
Settings > LevelPlay Mediation Settings** as an Android app key and an iOS app key. Only relevant if
AdMob is one of the installed adapters. No **Ads Mediation** menu at all means the package is not
installed (SKILL.md §3) or the Editor needs a restart.
