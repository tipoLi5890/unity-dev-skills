# Migrating to SDK 9.x

SDK 9.0.0 broke two things at once: `LevelPlay.Init()` replaced `IronSource.Agent.init()`, and
per-instance ad-unit objects replaced the old static, placement-based ad calls. Anything written
against 8.x needs both.

Five situations, and they do not overlap much. Identify which one applies before touching code:

| | Situation |
|---|---|
| **A** | Upgrading the SDK itself to 9.x |
| **B** | Translating the initialization call |
| **C** | Translating the ad unit calls, per format |
| **D** | Android build that can no longer resolve `com.ironsource.sdk` |
| **E** | Coming from the Unity Ads `Advertisement Legacy` package |

The new ad-unit API needs SDK 8.4.0 as a floor, which 9.0.0+ satisfies by definition.

> **§C ends with a completeness checklist, and it is not optional.** Several 9.x requirements have no
> corresponding line in 8.x code, so a translation that handles every line present still ships an
> integration that cannot work.

## A — upgrading the SDK

> **The upgrade deletes folders, and deleting them discards settings and every installed adapter.**
> Inventory first, confirm, then delete. Never remove a folder without saying so beforehand.

1. **Write down the Developer Settings values** — app keys, app ids — from **Ads Mediation >
   Developer Settings**. The upgrade loses them. Wait for confirmation that they are saved.
2. **Write down the installed adapters**, from **Ads Mediation > Network Manager** or by listing the
   `IS*AdapterDependencies.xml` files under `Assets > LevelPlay > Editor`. The same set gets
   reinstalled afterwards.
3. **State exactly what will be deleted and why**, then get explicit agreement. Deleting Mobile
   Dependency Resolver is safe — the new package ships its own copy.

Then, depending on how the SDK is currently delivered. The deletions are file operations; **the
package or plugin step itself belongs to the publisher** — name it and hand it over.

**A1 — staying on `.unitypackage`.** Delete `Assets > LevelPlay` entirely, and
`Assets > Mobile Dependency Resolver` if it is there. The current
[Unity plugin](https://docs.unity.com/en-us/grow/levelplay/sdk/unity/package-integration) is then
downloaded and imported.

**A2 — staying on UPM.** Delete `Assets > LevelPlay` (or `Assets > IronSource`) entirely, and
`Assets > Mobile Dependency Resolver` if present. **Ads Mediation** is then updated from **Unity
Registry**.

**A3 — moving from `.unitypackage` to UPM.** Same deletions as A2, then a fresh install rather than
an update.

> **Changing package versions by editing files means editing `Packages/manifest.json` and nothing
> else.** Unity regenerates `packages-lock.json` from the manifest; a hand-edited lock file can leave
> the Editor unable to resolve anything.

### After the upgrade

1. Reinstall the adapters recorded in step 2 and re-enter the settings from step 1. The backup
   warning has done its job by now — do not repeat it.
2. **Only after A3**: remove `LEVELPLAY_DEPENDENCIES_INSTALLED` from **Project Settings > Player >
   Scripting Define Symbols**. Both distributions use this define, so removing it in any other
   situation breaks a working install. After A3 the define is stale — left in place it makes the UPM
   package skip its dependency check, and the UPM installer re-adds it once that check has run.
3. Read the console for deprecation warnings, then continue into §B and §C.
4. **§D applies only** if the project previously used a `.unitypackage` older than 7.9.0, or if the
   dependency XMLs under `Assets/LevelPlay/Editor` still name `android-sdk.is.com`. A fresh UPM
   install never needs it — do not raise it otherwise.

## B — the initialization call

### Namespace

```csharp
// Old (8.x): the classic IronSource classes (IronSource.Agent, IronSourceEvents, ...)
// live in the GLOBAL namespace — no using directive applies to them.
// The 8.x LevelPlay ad-unit classes (LevelPlayRewardedAd, ...) live in:
using com.unity3d.mediation;

// New
using Unity.Services.LevelPlay;
```

### The call

```csharp
// Old
IronSourceEvents.onSdkInitializationCompletedEvent += OnInitSuccess;
IronSource.Agent.setUserId("userId");
IronSource.Agent.validateIntegration();
IronSource.Agent.init(appKey);
```

```csharp
// New
LevelPlay.OnInitSuccess += OnInitSuccess;
LevelPlay.OnInitFailed += OnInitFailed;
LevelPlay.Init(appKey);              // basic
LevelPlay.Init(appKey, "userId");    // with user id
```

| Old | New |
|---|---|
| `void onSdkInitializationCompletedEvent()` | `void OnInitSuccess(LevelPlayConfiguration config)` |
| *(no failure callback existed)* | `void OnInitFailed(LevelPlayInitError error)` |

The failure callback is new, so there is no old line to translate into it — implement it anyway, or
a failed init is indistinguishable from an init that has not finished. `setUserId` folds into the
second `Init` argument. `validateIntegration()` has no direct replacement; the Test Suite took over
that role.

Before and after, complete:

```csharp
// Before
void Start()
{
    IronSourceEvents.onSdkInitializationCompletedEvent += SdkInitializationCompleted;
    IronSource.Agent.setUserId("user_123");
    IronSource.Agent.init(appKey);
}

void SdkInitializationCompleted()
{
    Debug.Log("IronSource initialized");
}
```

```csharp
// After
void Start()
{
    LevelPlay.OnInitSuccess += OnInitSuccess;
    LevelPlay.OnInitFailed += OnInitFailed;
    LevelPlay.Init(appKey, "user_123");
}

void OnInitSuccess(LevelPlayConfiguration config)
{
    Debug.Log("LevelPlay initialized");
    // ad objects get created here
}

void OnInitFailed(LevelPlayInitError error)
{
    Debug.LogError($"Init failed: {error.ErrorMessage}");
}

void OnDestroy()
{
    LevelPlay.OnInitSuccess -= OnInitSuccess;
    LevelPlay.OnInitFailed -= OnInitFailed;
}
```

## C — the ad unit calls

Static methods keyed on a format become instance objects keyed on an **ad unit id**, which comes from
the dashboard under **Setup > Ad Units**.

### C1 — rewarded

```csharp
// Old
IronSourceRewardedVideoEvents.onAdAvailableEvent += OnAdAvailable;
IronSourceRewardedVideoEvents.onAdUnavailableEvent += OnAdUnavailable;
IronSourceRewardedVideoEvents.onAdOpenedEvent += OnAdOpened;
IronSourceRewardedVideoEvents.onAdClosedEvent += OnAdClosed;
IronSourceRewardedVideoEvents.onAdRewardedEvent += OnAdRewarded;
IronSourceRewardedVideoEvents.onAdShowFailedEvent += OnAdShowFailed;
IronSourceRewardedVideoEvents.onAdClickedEvent += OnAdClicked;

if (IronSource.Agent.isRewardedVideoAvailable())
    IronSource.Agent.showRewardedVideo();
```

```csharp
// New
private LevelPlayRewardedAd rewardedAd;

// after OnInitSuccess
rewardedAd = new LevelPlayRewardedAd(adUnitId);
rewardedAd.OnAdLoaded += OnAdLoaded;
rewardedAd.OnAdLoadFailed += OnAdLoadFailed;
rewardedAd.OnAdDisplayed += OnAdDisplayed;
rewardedAd.OnAdDisplayFailed += OnAdDisplayFailed;
rewardedAd.OnAdRewarded += OnAdRewarded;
rewardedAd.OnAdClosed += OnAdClosed;
rewardedAd.OnAdClicked += OnAdClicked;         // optional
rewardedAd.OnAdInfoChanged += OnAdInfoChanged; // optional

// Do NOT add rewardedAd.LoadAd() here reflexively.
// The legacy SDK loaded rewarded video by itself; this API does not. Give the load an
// explicit trigger — a button handler, a scene entry, a gameplay beat:
//
//   public void OnPlayerReachesRewardedOpportunity() { rewardedAd.LoadAd(); }
//
// An always-ready preload (LoadAd() right after subscribing, and again in OnAdClosed) is
// legitimate — as a decision, not as a carry-over from behaviour the old SDK gave for free.

void ShowRewardedAd(string placementName = null)
{
    // IsAdReady() is the minimum. With dashboard placements in use, the capping check too:
    // showing into a capped placement fails.
    if (rewardedAd.IsAdReady() && !LevelPlayRewardedAd.IsPlacementCapped(placementName))
        rewardedAd.ShowAd(placementName);
}
```

Reward payload and the display-failure signature:

```csharp
void OnAdRewarded(LevelPlayAdInfo adInfo, LevelPlayReward reward)
{
    // Old: placement.GetRewardName(), placement.GetRewardAmount()
    Debug.Log($"Reward: {reward.Name} x {reward.Amount}");
    GrantReward(reward.Name, reward.Amount);
}

// The parameter types are LevelPlayAdInfo + LevelPlayAdError. LevelPlayAdDisplayInfoError
// existed in 8.x and was removed in 9.x — using it is a CS0246.
void OnAdDisplayFailed(LevelPlayAdInfo adInfo, LevelPlayAdError error)
{
    Debug.LogError($"Rewarded ad failed to display: {error.ErrorMessage}");
}
```

| Old | New |
|---|---|
| `IronSource.Agent.loadRewardedVideo()` | `rewardedAd.LoadAd()` |
| `IronSource.Agent.showRewardedVideo()` | `rewardedAd.ShowAd()` |
| `IronSource.Agent.isRewardedVideoAvailable()` | `rewardedAd.IsAdReady()` |
| `IronSource.Agent.isRewardedVideoPlacementCapped(name)` | `LevelPlayRewardedAd.IsPlacementCapped(name)` |
| `placement.GetRewardName()` | `reward.Name` |
| `placement.GetRewardAmount()` | `reward.Amount` |

### C2 — interstitial

```csharp
// Old
IronSourceInterstitialEvents.onAdReadyEvent += OnAdReady;
IronSourceInterstitialEvents.onAdLoadFailedEvent += OnAdLoadFailed;
IronSourceInterstitialEvents.onAdOpenedEvent += OnAdOpened;
IronSourceInterstitialEvents.onAdClosedEvent += OnAdClosed;
IronSourceInterstitialEvents.onAdShowFailedEvent += OnAdShowFailed;
IronSourceInterstitialEvents.onAdClickedEvent += OnAdClicked;

IronSource.Agent.loadInterstitial();
if (IronSource.Agent.isInterstitialReady())
    IronSource.Agent.showInterstitial();
```

```csharp
// New
private LevelPlayInterstitialAd interstitialAd;

// after OnInitSuccess
interstitialAd = new LevelPlayInterstitialAd(adUnitId);
interstitialAd.OnAdLoaded += OnAdLoaded;
interstitialAd.OnAdLoadFailed += OnAdLoadFailed;
interstitialAd.OnAdDisplayed += OnAdDisplayed;
interstitialAd.OnAdDisplayFailed += OnAdDisplayFailed;
interstitialAd.OnAdClicked += OnAdClicked;
interstitialAd.OnAdClosed += OnAdClosed;
interstitialAd.OnAdInfoChanged += OnAdInfoChanged;

interstitialAd.LoadAd();

void ShowInterstitialAd(string placementName = null)
{
    if (interstitialAd.IsAdReady() && !LevelPlayInterstitialAd.IsPlacementCapped(placementName))
        interstitialAd.ShowAd(placementName);
}

void OnDestroy()
{
    interstitialAd?.DestroyAd();
}
```

| Old | New |
|---|---|
| `IronSource.Agent.loadInterstitial()` | `interstitialAd.LoadAd()` |
| `IronSource.Agent.showInterstitial()` | `interstitialAd.ShowAd()` |
| `IronSource.Agent.isInterstitialReady()` | `interstitialAd.IsAdReady()` |
| `IronSource.Agent.isInterstitialPlacementCapped(name)` | `LevelPlayInterstitialAd.IsPlacementCapped(name)` |
| `onAdReadyEvent` | `OnAdLoaded` |
| `onAdOpenedEvent` | `OnAdDisplayed` |
| `onAdShowFailedEvent` | `OnAdDisplayFailed` |
| `onAdShowSucceededEvent` | *(gone)* |

Unlike rewarded, an interstitial preloads normally: load once, reload in `OnAdClosed`.

### C3 — banner

```csharp
// Old
IronSourceBannerEvents.onAdLoadedEvent += OnAdLoaded;
IronSourceBannerEvents.onAdLoadFailedEvent += OnAdLoadFailed;
IronSourceBannerEvents.onAdClickedEvent += OnAdClicked;
IronSourceBannerEvents.onAdScreenPresentedEvent += OnAdScreenPresented;
IronSourceBannerEvents.onAdScreenDismissedEvent += OnAdScreenDismissed;

IronSource.Agent.loadBanner(IronSourceBannerSize.BANNER, IronSourceBannerPosition.BOTTOM);
IronSource.Agent.destroyBanner();
```

```csharp
// New
private LevelPlayBannerAd bannerAd;

// after OnInitSuccess.
// The one-argument constructor already means BANNER size at BottomCenter — a legacy call
// that passed BANNER + BOTTOM needs no config object at all.
bannerAd = new LevelPlayBannerAd(adUnitId);

// Config.Builder is for anything other than those defaults:
// var config = new LevelPlayBannerAd.Config.Builder()
//     .SetSize(LevelPlayAdSize.LARGE)
//     .SetPosition(LevelPlayBannerPosition.TopCenter)
//     .SetRespectSafeArea(true)
//     .Build();
// bannerAd = new LevelPlayBannerAd(adUnitId, config);

bannerAd.OnAdLoaded += OnAdLoaded;
bannerAd.OnAdLoadFailed += OnAdLoadFailed;
bannerAd.OnAdDisplayed += OnAdDisplayed;
bannerAd.OnAdDisplayFailed += OnAdDisplayFailed;
bannerAd.OnAdClicked += OnAdClicked;
bannerAd.OnAdCollapsed += OnAdCollapsed;
bannerAd.OnAdExpanded += OnAdExpanded;
bannerAd.OnAdLeftApplication += OnAdLeftApplication;

bannerAd.LoadAd();
bannerAd.ShowAd();

bannerAd.HideAd();
bannerAd.PauseAutoRefresh();
bannerAd.ResumeAutoRefresh();

void OnDestroy()
{
    bannerAd?.DestroyAd();
}
```

> **`destroyBanner()` maps onto two different methods, and only the old code's intent decides
> which.** Meant to hide the banner for a while and bring it back? That is `HideAd()` — the instance
> stays alive and `ShowAd()` restores it with no reload. Meant to tear it down for good? That is
> `DestroyAd()`, and returning from it costs a new `LevelPlayBannerAd` plus a fresh `LoadAd()`. When
> the old code is ambiguous, `HideAd()` for visibility and `DestroyAd()` only in
> `OnDestroy()`/`OnDisable()` is the safe reading.

| Old (`IronSourceBannerSize`) | New (`LevelPlayAdSize`) | dp |
|---|---|---|
| `BANNER` | `LevelPlayAdSize.BANNER` | 320 × 50 |
| `LARGE` | `LevelPlayAdSize.LARGE` | 320 × 90 |
| `RECTANGLE` | `LevelPlayAdSize.MEDIUM_RECTANGLE` | 300 × 250 |
| `SMART` | `LevelPlayAdSize.CreateAdaptiveAdSize()` | adaptive |

Adaptive, which is what most `SMART` migrations want:

```csharp
// The 9.x constructor takes (adUnitId, Config) only — handing it a LevelPlayAdSize
// directly does not compile. Size goes through the builder:
var adaptiveConfig = new LevelPlayBannerAd.Config.Builder()
    .SetSize(LevelPlayAdSize.CreateAdaptiveAdSize())
    .Build();
bannerAd = new LevelPlayBannerAd(adUnitId, adaptiveConfig);
```

| Old | New |
|---|---|
| `IronSource.Agent.loadBanner(size, pos)` | `bannerAd.LoadAd()` — size and position move to the constructor |
| `IronSource.Agent.destroyBanner()` | `bannerAd.HideAd()` or `bannerAd.DestroyAd()` — see above |
| `IronSource.Agent.displayBanner()` | `bannerAd.ShowAd()` |
| `IronSource.Agent.hideBanner()` | `bannerAd.HideAd()` |
| `onAdScreenPresentedEvent` | `OnAdExpanded` |
| `onAdScreenDismissedEvent` | `OnAdCollapsed` |

### C4 — the impression handler

Subscription first, then the handler body.

```csharp
// Old
IronSourceEvents.onImpressionDataReadyEvent += ImpressionDataReadyEvent;
```

```csharp
// New — SDK 9.4.x and earlier: one global event, subscribed before LevelPlay.Init()
LevelPlay.OnImpressionDataReady += ImpressionDataReadyEvent;
```

```csharp
// New — SDK 9.5.0+: per ad instance, subscribed as each object is created.
// The global event survives here but is deprecated and warns.
rewardedAd.OnAdImpressionDataReady += ImpressionDataReadyEvent;
interstitialAd.OnAdImpressionDataReady += ImpressionDataReadyEvent;
bannerAd.OnAdImpressionDataReady += ImpressionDataReadyEvent;
```

> **`LevelPlay.OnImpressionDataReadyEvent` does not exist and never has.** The global member has no
> `Event` suffix. This is worth stating because the 8.x SDK's own deprecation message names the
> non-existent one — following that message costs a compile-fix cycle. Unsubscribe with the same
> names you subscribed with.

The handler keeps both of its log lines, with one property renamed:

```csharp
// Old
void ImpressionDataReadyEvent(IronSourceImpressionData impressionData)
{
    Debug.Log("ImpressionDataReadyEvent ToString(): " + impressionData.ToString());
    Debug.Log("ImpressionDataReadyEvent allData: " + impressionData.allData);
}
```

```csharp
// New
void ImpressionDataReadyEvent(LevelPlayImpressionData impressionData)
{
    Debug.Log("ImpressionDataReadyEvent ToString(): " + impressionData.ToString());
    // allData → AllData
    Debug.Log("ImpressionDataReadyEvent AllData: " + impressionData.AllData);
}
```

Dropping the second line looks tidy and quietly removes the raw payload dump that downstream
analytics code may be parsing. Forwarding to a platform: [`ilrd-api.md`](ilrd-api.md).

### C5 — completeness checklist

Run this against the migrated code, not against the old code. Each item is something 8.x had no line
for, which is exactly why a line-by-line port misses it.

- [ ] **Show paths check `IsAdReady()`, plus `IsPlacementCapped(placementName)` where dashboard
      placements are used.** The old code only checked availability. No placements in this game? Say
      so and move on.
- [ ] **A rewarded load trigger exists, and the publisher controls it.** The old SDK auto-loaded
      rewarded video, so there is no call to translate — one has to be **added**. Without it the ad
      is never ready. No auto-load in `OnInitSuccess` and no auto-reload in `OnAdClosed` unless the
      publisher chose a preload pattern deliberately; ask which they want.
- [ ] **Version members map one to one.** `IronSource.unityVersion()` → `LevelPlay.UnityVersion`,
      `IronSource.pluginVersion()` → `LevelPlay.PluginVersion`. Different values; do not swap them.
- [ ] **Logging preserved, not expanded.** Carry the old log lines across, renamed as needed. Do not
      invent new ones — a diff full of added logs hides the real changes.
- [ ] **The impression subscription uses the right name for the right version, and both handler log
      lines survive.** `onImpressionDataReadyEvent` → `LevelPlay.OnImpressionDataReady` (9.4.x and
      earlier) or per-instance `OnAdImpressionDataReady` (9.5.0+). `allData` → `AllData`. There is
      no `LevelPlay.OnImpressionDataReadyEvent` — the half-translated name compiles nowhere.
- [ ] **`destroyBanner()` resolved to hide or destroy** — see C3.
- [ ] **`IronSource.Agent.onApplicationPause(isPaused)` is deleted, not replaced.** It used to
      forward Unity's pause and resume to the native SDK; 9.x reads the app lifecycle itself, so
      there is nothing to call. `LevelPlay.OnApplicationPause` does not exist and will not compile,
      and `LevelPlay.SetPauseGame(bool)` is a different feature — it pauses the *game* while an ad is
      showing. If the Unity `OnApplicationPause` override contained only that call, delete the whole
      override and say why.
- [ ] **No invented members.** Every LevelPlay symbol in the migrated code appears either in this
      guide or in the installed package. A plausible name that does not exist costs a compile-fix
      round trip, and plausible names are exactly what this API invites.

After the code changes, ask for the Unity console and fix what appears. If the console is not
visible, do not stall on it: list the files changed, say what to look for, and continue.

## D — the Android repository moved

Android dependencies moved off `is.com` to Maven Central, with a June 30 2025 deadline. A project
still pointing at the old repository has a **failing Android build today**, with no code change to
explain it — which is why this reaches people as "the build broke and nothing changed".

Check whether it applies: open any dependency XML under `Assets > LevelPlay > Editor` (for example
`IronSourceSDKDependencies.xml`) and look for `https://android-sdk.is.com/` inside a `<repository>`
tag. Found → migrate. Not found → already migrated, and this section is noise.

```xml
<!-- Old shape — needs migration -->
<androidPackage spec="com.ironsource.sdk:mediationsdk:7.9.0">
  <repositories>
    <repository>https://android-sdk.is.com/</repository>
  </repositories>
</androidPackage>
```

```xml
<!-- Correct shape -->
<androidPackage spec="com.unity3d.ads-mediation:mediation-sdk:x.x.x">
</androidPackage>
```

**The SDK dependencies:** delete `IronSourceSDKDependencies.xml` and every `IS*AdapterDependencies.xml`
under `Assets > LevelPlay > Editor`, then reinstall the SDK and all required adapters through
**Ads Mediation > Network Manager**. Confirm the regenerated XMLs name `com.unity3d.ads-mediation`
and that no `is.com` reference remains anywhere.

**Ad Quality, if the project uses it:** delete `IronSourceAdQualityDependencies.xml`, obtain the
Maven Central version (Ad Quality 7.24.0 or later), place it in the same folder, and confirm it names
`com.unity3d.ads-mediation:adquality-sdk`.

Floors: LevelPlay Unity package 7.9.0+, and for Ad Quality the Maven Central version named above.

## E — coming from Unity Ads

For projects on the `Advertisement Legacy` package. Since 1 April 2026 a direct Unity Ads
integration may deliver reduced performance, which is the practical reason this migration exists.

**1. Install alongside.** Ads Mediation (`com.unity.services.levelplay`) goes in from **Unity
Registry**, with the Mobile Dependency Resolver prompt accepted — the publisher's step, not yours.
**Leave Advertisement Legacy in place** until the new integration is verified.

**2. Set up the dashboard.** Sign in at
[platform.ironsrc.com](https://platform.ironsrc.com/partners/identity/login), add the app, create the
ad units, and copy the App Key and ad unit ids.

**3. Replace initialization.**

```csharp
// Was
Advertisement.Initialize(_gameId, _testMode, this);
void OnInitializationComplete() { }
void OnInitializationFailed(UnityAdsInitializationError error, string message) { }
```

```csharp
// Now
using Unity.Services.LevelPlay;

LevelPlay.OnInitSuccess += OnInitSuccess;
LevelPlay.OnInitFailed += OnInitFailed;
LevelPlay.Init("YOUR_APP_KEY");   // App Key, not game id

void OnInitSuccess(LevelPlayConfiguration config)
{
    // ad objects get created here
}

void OnInitFailed(LevelPlayInitError error)
{
    Debug.LogError($"Init failed: {error.ErrorMessage}");
}
```

> **`LevelPlay.Init()` has no test-mode parameter.** If the old call passed `testMode`, say so out
> loud rather than dropping the flag quietly — the replacements are the Test Suite on a device build,
> or test mode switched on in the dashboard.

**4. Replace the ad code**, per format, using §C.

| Use case | Unity Ads | LevelPlay |
|---|---|---|
| Init identifier | `gameId` | `appKey` |
| Initialize | `Advertisement.Initialize()` | `LevelPlay.Init()` |
| Init success | `OnInitializationComplete()` | `LevelPlay.OnInitSuccess` |
| Init failed | `OnInitializationFailed()` | `LevelPlay.OnInitFailed` |
| Is initialized | `Advertisement.isInitialized` | *(no equivalent)* |
| Metadata | `Advertisement.SetMetaData()` | `LevelPlay.SetMetaData(key, value)` |
| Banner load | `Advertisement.Banner.Load()` | `bannerAd.LoadAd()` |
| Banner show | `Advertisement.Banner.Show()` | `bannerAd.ShowAd()` |
| Banner hide | `Advertisement.Banner.Hide()` | `bannerAd.HideAd()` |
| Load rewarded/interstitial | `Advertisement.Load(placementId, listener)` | `ad.LoadAd()` |
| Show rewarded/interstitial | `Advertisement.Show(placementId, listener)` | `ad.ShowAd()` |
| Loaded | `OnUnityAdsAdLoaded()` | `OnAdLoaded` on the instance |
| Load failed | `OnUnityAdsFailedToLoad()` | `OnAdLoadFailed` on the instance |
| Show started | `OnUnityAdsShowStart()` | `OnAdDisplayed` on the instance |
| Show completed | `OnUnityAdsShowComplete()` | `OnAdClosed` on the instance |
| Show failed | `OnUnityAdsShowFailure()` | `OnAdDisplayFailed` on the instance |
| Clicked | `OnUnityAdsShowClick()` | `OnAdClicked` on the instance |
| Plugin version | `Advertisement.version` | `LevelPlay.PluginVersion` |

Five structural differences behind that table: ad objects are instances rather than statics; the
identifier is an App Key rather than a game id; events are per instance rather than through a shared
listener interface; there is no test-mode argument; and banner size and position are constructor
arguments rather than separate calls.

**5. Remove the old package.** **Advertisement Legacy** comes out of **In Project** — again the
publisher's step — and only once every format has been verified working on device.

## Quick reference: 8.x → 9.x

### Initialization

| | Legacy | Current |
|---|---|---|
| Namespace | global (classic IronSource classes) / `com.unity3d.mediation` (8.x ad units) | `Unity.Services.LevelPlay` |
| Init | `IronSource.Agent.init(appKey)` | `LevelPlay.Init(appKey)` |
| User id | `IronSource.Agent.setUserId(id)` | `LevelPlay.Init(appKey, userId)` |
| Success | `onSdkInitializationCompletedEvent` | `LevelPlay.OnInitSuccess` |
| Failure | *(none)* | `LevelPlay.OnInitFailed` |
| Validate | `IronSource.Agent.validateIntegration()` | *(no equivalent — use the Test Suite, see C5)* |
| Test Suite | `IronSource.Agent.launchTestSuite()` | `LevelPlay.LaunchTestSuite()` |
| Unity version | `IronSource.unityVersion()` | `LevelPlay.UnityVersion` |
| Plugin version | `IronSource.pluginVersion()` | `LevelPlay.PluginVersion` |
| App pause | `IronSource.Agent.onApplicationPause(isPaused)` | *(removed — delete the call, see C5)* |

### Rewarded

| | Legacy | Current |
|---|---|---|
| Load | `IronSource.Agent.loadRewardedVideo()` | `rewardedAd.LoadAd()` |
| Show | `IronSource.Agent.showRewardedVideo()` | `rewardedAd.ShowAd()` |
| Ready | `IronSource.Agent.isRewardedVideoAvailable()` | `rewardedAd.IsAdReady()` |
| Capped | `IronSource.Agent.isRewardedVideoPlacementCapped(name)` | `LevelPlayRewardedAd.IsPlacementCapped(name)` |

### Interstitial

| | Legacy | Current |
|---|---|---|
| Load | `IronSource.Agent.loadInterstitial()` | `interstitialAd.LoadAd()` |
| Show | `IronSource.Agent.showInterstitial()` | `interstitialAd.ShowAd()` |
| Ready | `IronSource.Agent.isInterstitialReady()` | `interstitialAd.IsAdReady()` |
| Capped | `IronSource.Agent.isInterstitialPlacementCapped(name)` | `LevelPlayInterstitialAd.IsPlacementCapped(name)` |

### Banner

| | Legacy | Current |
|---|---|---|
| Load | `IronSource.Agent.loadBanner(size, pos)` | `bannerAd.LoadAd()` |
| Destroy | `IronSource.Agent.destroyBanner()` | `bannerAd.HideAd()` or `bannerAd.DestroyAd()` — C3 |
| Show | `IronSource.Agent.displayBanner()` | `bannerAd.ShowAd()` |
| Hide | `IronSource.Agent.hideBanner()` | `bannerAd.HideAd()` |

### Impression data

| | Legacy | Current |
|---|---|---|
| Event | `IronSourceEvents.onImpressionDataReadyEvent` | 9.4.x and earlier: `LevelPlay.OnImpressionDataReady`, before `Init()`. 9.5.0+: `OnAdImpressionDataReady` per instance |
| Payload | `IronSourceImpressionData` | `LevelPlayImpressionData` |
| Raw data | `impressionData.allData` | `impressionData.AllData` |
