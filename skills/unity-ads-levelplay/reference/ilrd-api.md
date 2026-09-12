# Impression-level revenue

Per-impression revenue data, delivered as each ad is shown, for forwarding to an analytics or
attribution platform — Firebase, AppsFlyer, Adjust, Singular, or a backend of your own. Present from
SDK 7.0.3 onward, and it covers all three formats.

Two properties of this callback shape everything else:

> **Where you subscribe depends on the resolved SDK version**, and the two branches are wired in
> different files.

> **It runs on a background thread.** Not the Unity main thread. Touching a Unity object from inside
> it is a crash, not a warning.

## The fork

| SDK version | Event | Where |
|---|---|---|
| **9.5.0+** | `OnAdImpressionDataReady` on each ad object (`LevelPlayRewardedAd`, `LevelPlayInterstitialAd`, `LevelPlayBannerAd`) | Subscribe as each ad is created |
| **9.4.x and earlier** | `LevelPlay.OnImpressionDataReady`, one static event | Subscribe once, **before** `LevelPlay.Init()` |

On 9.5.0+ the global event has not disappeared, but it is deprecated and raises a compiler warning —
the per-instance event is the supported route there. Read the version from
`Packages/packages-lock.json` or **Ads Mediation > Network Manager** before choosing.

## SDK 9.5.0+ — per instance

Subscribe right after constructing the ad, unsubscribe with the rest in `OnDestroy()`. Ordering
relative to `Init()` is irrelevant on this branch, because the ad object cannot exist before the SDK
is up.

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class RewardedAdManager : MonoBehaviour
{
    private LevelPlayRewardedAd rewardedAd;
    private string adUnitId = "YOUR_REWARDED_AD_UNIT_ID";

    void Start()
    {
        rewardedAd = new LevelPlayRewardedAd(adUnitId);

        // ILRD, SDK 9.5.0+. Fires on a BACKGROUND thread — no Unity API calls in the handler.
        rewardedAd.OnAdImpressionDataReady += OnImpressionDataReady;

        // ... other events, then the load trigger
    }

    void OnDestroy()
    {
        if (rewardedAd != null)
        {
            rewardedAd.OnAdImpressionDataReady -= OnImpressionDataReady;
            // ... other unsubscriptions
        }
    }

    private void OnImpressionDataReady(LevelPlayImpressionData impressionData)
    {
        if (impressionData == null) return;
        Debug.Log($"ILRD - {impressionData.AdNetwork} / {impressionData.AdFormat} / ${impressionData.Revenue}");
    }
}
```

Repeat on the interstitial and banner managers. Each format reports through its own instance, so an
ad object you forgot to subscribe simply reports nothing — and that is by far the most common reason
one format's revenue is missing from a dashboard while the others are fine.

## SDK 9.4.x and earlier — one global event

Subscribed before `Init()`, or impressions that land during startup are lost:

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class ImpressionRevenueManager : MonoBehaviour
{
    void Start()
    {
        // Before Init, so nothing is missed. Fires on a background thread.
        LevelPlay.OnImpressionDataReady += ImpressionDataReadyEvent;

        LevelPlay.OnInitSuccess += OnInitSuccess;
        LevelPlay.OnInitFailed += OnInitFailed;

        LevelPlay.Init("YOUR_APP_KEY");
    }

    void OnDestroy()
    {
        LevelPlay.OnImpressionDataReady -= ImpressionDataReadyEvent;
        LevelPlay.OnInitSuccess -= OnInitSuccess;
        LevelPlay.OnInitFailed -= OnInitFailed;
    }

    private void ImpressionDataReadyEvent(LevelPlayImpressionData impressionData)
    {
        // Background thread. Do not touch Unity objects from here.
        Debug.Log($"ILR - Ad Network: {impressionData.AdNetwork}");
        Debug.Log($"ILR - Revenue: ${impressionData.Revenue}");
    }

    private void OnInitSuccess(LevelPlayConfiguration config)
        => Debug.Log("LevelPlay initialized");

    private void OnInitFailed(LevelPlayInitError error)
        => Debug.LogError($"Init failed: {error.ErrorMessage}");
}
```

One subscription covers every format on this branch.

## Threading

The callback arrives off the main thread. That rules out everything that reaches a Unity object —
`GameObject.Find`, transforms, components, UI updates, starting a coroutine. What is safe: reading
the fields, `Debug.Log`, thread-safe operations, and queueing the data for the main thread to pick
up next frame.

The crash this prevents is not deterministic. It fires occasionally, on device, under load — which is
exactly the kind of bug that survives a test pass.

## `LevelPlayImpressionData`

| Property | Type | Meaning |
|---|---|---|
| `AllData` | string/dictionary | The whole payload as one structured object |
| `AuctionId` | string | Auction identifier |
| `MediationAdUnitName` | string | Mediation ad unit name |
| `MediationAdUnitId` | string | Mediation ad unit identifier |
| `AdFormat` | string | `"REWARDED"`, `"INTERSTITIAL"`, `"BANNER"` |
| `AdNetwork` | string | Network that served the ad |
| `InstanceName` | string | Network instance name |
| `InstanceId` | string | Network instance identifier |
| `Country` | string | Country code |
| `Placement` | string | Placement the ad was shown in |
| `Revenue` | double? | Estimated USD — **nullable** |
| `Precision` | string | Revenue precision |
| `Ab` | string | A/B segment |
| `SegmentName` | string | User segment |
| `EncryptedCpm` | string | Encrypted CPM |
| `ConversionValue` | number? | iOS SKAdNetwork conversion value |
| `CreativeId` | string | Creative identifier |

```csharp
private void ImpressionDataReadyEvent(LevelPlayImpressionData impressionData)
{
    string allData = impressionData.AllData;
    string adNetwork = impressionData.AdNetwork;
    double? revenue = impressionData.Revenue;
}
```

**Fields can be null**, `Revenue` most often — some networks do not report it. Guard before use;
`impressionData.Revenue ?? 0` or a `HasValue` check. An unguarded dereference here crashes on a
background thread, where the stack trace is least helpful.

## Forwarding to analytics

Firebase, as the shape most platforms follow — a parameter array and one event:

```csharp
private void ImpressionDataReadyEvent(LevelPlayImpressionData impressionData)
{
    if (impressionData == null) return;

    Firebase.Analytics.Parameter[] AdParameters = {
        new Firebase.Analytics.Parameter("ad_platform", "LevelPlay"),
        new Firebase.Analytics.Parameter("ad_source", impressionData.AdNetwork),
        new Firebase.Analytics.Parameter("ad_format", impressionData.AdFormat),
        new Firebase.Analytics.Parameter("ad_unit_name", impressionData.InstanceName),
        new Firebase.Analytics.Parameter("currency", "USD"),
        new Firebase.Analytics.Parameter("value", impressionData.Revenue ?? 0)
    };

    Firebase.Analytics.FirebaseAnalytics.LogEvent("custom_ad_impression", AdParameters);
}
```

The same data feeds an attribution provider, a warehouse, or your own endpoint. Whatever the
destination, check that its SDK tolerates being called off the main thread — several do not, and then
the data has to be queued for the main thread first.

## When it never fires

- **9.5.0+:** the ad object being shown is not the one you subscribed to, or a format's manager was
  never wired at all.
- **9.4.x:** the global event was subscribed after `Init()`.
- Initialization never succeeded.
- No ad has been shown yet.
- **You are testing in the Editor.** Mock ads generate no impression data at all, on either branch.
  Confirming this path takes a device build.

Two further failures worth naming: Unity APIs called from the handler (crash, background thread), and
a null `Revenue` used without a check (crash, same thread).

## Checks worth running

- Subscribed on the correct branch for the resolved version.
- Fires on a device build when an ad is shown — for **every** format that ships.
- Null checks on `Revenue` and on the payload itself.
- No Unity API call anywhere in the handler.
- Unsubscribed in `OnDestroy()`.
- The analytics platform actually receives the event, not just the log line.
