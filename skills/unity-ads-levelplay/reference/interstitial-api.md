# Interstitial ads

Full-screen, dismissible, shown between things rather than during them. Good revenue at an
acceptable cost to experience — provided two rules hold: it appears at a boundary the player was
already crossing, and it never delays them.

> **The player's progress does not wait for an ad.** Advance to the next level, then try to show. An
> interstitial that gates progression converts a monetisation moment into an uninstall.

## Manager

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class InterstitialAdManager : MonoBehaviour
{
    private LevelPlayInterstitialAd interstitialAd;
    private string adUnitId = "YOUR_INTERSTITIAL_AD_UNIT_ID";

    void Start()
    {
        interstitialAd = new LevelPlayInterstitialAd(adUnitId);

        // ILRD on SDK 9.5.0+:
        //   interstitialAd.OnAdImpressionDataReady += OnImpressionDataReady;   // see ilrd-api.md

        interstitialAd.OnAdLoaded += OnAdLoaded;
        interstitialAd.OnAdLoadFailed += OnAdLoadFailed;
        interstitialAd.OnAdDisplayed += OnAdDisplayed;
        interstitialAd.OnAdDisplayFailed += OnAdDisplayFailed;
        interstitialAd.OnAdClicked += OnAdClicked;
        interstitialAd.OnAdClosed += OnAdClosed;
        interstitialAd.OnAdInfoChanged += OnAdInfoChanged;

        LoadAd();
    }

    void OnDestroy()
    {
        if (interstitialAd != null)
        {
            interstitialAd.OnAdLoaded -= OnAdLoaded;
            interstitialAd.OnAdLoadFailed -= OnAdLoadFailed;
            interstitialAd.OnAdDisplayed -= OnAdDisplayed;
            interstitialAd.OnAdDisplayFailed -= OnAdDisplayFailed;
            interstitialAd.OnAdClicked -= OnAdClicked;
            interstitialAd.OnAdClosed -= OnAdClosed;
            interstitialAd.OnAdInfoChanged -= OnAdInfoChanged;
            // ILRD on 9.5.0+: interstitialAd.OnAdImpressionDataReady -= OnImpressionDataReady;

            // Release the native ad along with this manager
            interstitialAd.DestroyAd();
        }
    }

    public void LoadAd()
    {
        Debug.Log("Loading interstitial ad...");
        interstitialAd.LoadAd();
    }

    public void ShowAd()
    {
        if (interstitialAd.IsAdReady())
        {
            Debug.Log("Showing interstitial ad");
            interstitialAd.ShowAd();
        }
        else
        {
            Debug.LogWarning("Interstitial ad is not ready yet");
        }
    }

    // Ask before deciding to show opportunistically.
    public bool IsAdReady() => interstitialAd != null && interstitialAd.IsAdReady();

    private void OnAdLoaded(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Interstitial ad loaded successfully");
    }

    private void OnAdLoadFailed(LevelPlayAdError error)
    {
        Debug.LogWarning($"Interstitial ad failed to load: {error.ErrorMessage}");
        Invoke(nameof(LoadAd), 30f);
    }

    private void OnAdDisplayed(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Interstitial ad displayed");
    }

    private void OnAdDisplayFailed(LevelPlayAdInfo adInfo, LevelPlayAdError error)
    {
        Debug.LogError($"Interstitial ad failed to display: {error.ErrorMessage}");
        LoadAd();
    }

    private void OnAdClicked(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Interstitial ad clicked");
    }

    private void OnAdClosed(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Interstitial ad closed");
        LoadAd();   // next one, ready for the next boundary
    }

    private void OnAdInfoChanged(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Interstitial ad info changed - network: {adInfo.AdNetwork}, revenue: ${adInfo.Revenue}");
    }
}
```

Unlike rewarded, an interstitial preloads by default: load once at start, reload in `OnAdClosed`, and
one is always waiting for the next transition.

## Frequency capping in code

Dashboard capping exists, but a time floor enforced locally is what stops two ads landing inside one
minute of play. Record the time in `OnAdDisplayed` — the moment it actually appeared, not the moment
you asked:

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class FrequencyCappedInterstitialManager : MonoBehaviour
{
    private LevelPlayInterstitialAd interstitialAd;
    private string adUnitId = "YOUR_INTERSTITIAL_AD_UNIT_ID";

    private float minTimeBetweenAds = 300f;   // 5 minutes
    private float lastAdShownTime = -999f;    // so the first opportunity is eligible

    void Start()
    {
        interstitialAd = new LevelPlayInterstitialAd(adUnitId);

        interstitialAd.OnAdLoaded += OnAdLoaded;
        interstitialAd.OnAdLoadFailed += OnAdLoadFailed;
        interstitialAd.OnAdDisplayed += OnAdDisplayed;
        interstitialAd.OnAdClosed += OnAdClosed;
        interstitialAd.OnAdDisplayFailed += OnAdDisplayFailed;

        interstitialAd.LoadAd();
    }

    void OnDestroy()
    {
        if (interstitialAd != null)
        {
            interstitialAd.OnAdLoaded -= OnAdLoaded;
            interstitialAd.OnAdLoadFailed -= OnAdLoadFailed;
            interstitialAd.OnAdDisplayed -= OnAdDisplayed;
            interstitialAd.OnAdClosed -= OnAdClosed;
            interstitialAd.OnAdDisplayFailed -= OnAdDisplayFailed;

            interstitialAd.DestroyAd();
        }
    }

    public void TryShowInterstitial()
    {
        float timeSinceLastAd = Time.time - lastAdShownTime;

        if (timeSinceLastAd < minTimeBetweenAds)
        {
            Debug.Log($"Frequency cap: {minTimeBetweenAds - timeSinceLastAd:F0}s until next ad");
            return;
        }

        if (interstitialAd.IsAdReady())
        {
            interstitialAd.ShowAd();
        }
        else
        {
            Debug.LogWarning("Interstitial not ready, loading...");
            interstitialAd.LoadAd();
        }
    }

    private void OnAdDisplayed(LevelPlayAdInfo adInfo)
    {
        lastAdShownTime = Time.time;   // recorded on display, not on request
    }

    private void OnAdClosed(LevelPlayAdInfo adInfo)      => interstitialAd.LoadAd();
    private void OnAdLoaded(LevelPlayAdInfo adInfo)      => Debug.Log("Interstitial loaded");

    private void OnAdLoadFailed(LevelPlayAdError error)
    {
        Debug.LogWarning($"Interstitial load failed: {error.ErrorMessage}");
        Invoke(nameof(LoadAd), 30f);
    }

    private void OnAdDisplayFailed(LevelPlayAdInfo adInfo, LevelPlayAdError error)
    {
        Debug.LogError($"Interstitial display failed: {error.ErrorMessage}");
        interstitialAd.LoadAd();
    }

    private void LoadAd()
    {
        if (interstitialAd != null) interstitialAd.LoadAd();
    }
}
```

Intervals by goal: revenue 3–5 min, balanced 5–7 min, experience-first 10+ min or none.

## Placements

Named contexts on one ad unit, for separate reporting and separate dashboard caps. Both checks apply
before showing — your own time floor and the SDK's placement cap:

```csharp
private const string PLACEMENT_LEVEL_COMPLETE = "level_complete";
private const string PLACEMENT_GAME_OVER      = "game_over";
private const string PLACEMENT_MAIN_MENU      = "main_menu";

private void TryShowWithPlacement(string placementName)
{
    if (Time.time - lastAdShownTime < minTimeBetweenAds)
    {
        Debug.Log($"Frequency cap active for {placementName}");
        return;
    }

    if (LevelPlayInterstitialAd.IsPlacementCapped(placementName))
    {
        Debug.Log($"Placement {placementName} is capped");
        return;
    }

    if (interstitialAd.IsAdReady())
    {
        Debug.Log($"Showing interstitial with placement: {placementName}");
        interstitialAd.ShowAd(placementName: placementName);
    }
}
```

## API

### Construction

```csharp
LevelPlayInterstitialAd interstitialAd = new LevelPlayInterstitialAd("your_ad_unit_id");
```

With a bid floor:

```csharp
var configBuilder = new LevelPlayInterstitialAd.Config.Builder();
configBuilder.SetBidFloor(1.0);
var config = configBuilder.Build();
LevelPlayInterstitialAd interstitialAd = new LevelPlayInterstitialAd("your_ad_unit_id", config);
```

After `OnInitSuccess`, not before.

### Methods

| Member | Returns | Notes |
|---|---|---|
| `LoadAd()` | — | After init, after each close, after a failure |
| `ShowAd()` | — | Guard with `IsAdReady()` |
| `ShowAd(placementName: string)` | — | Same, tagged for reporting |
| `IsAdReady()` | `bool` | Loaded and showable |
| `DestroyAd()` | — | Release native resources in `OnDestroy()` |
| `LevelPlayInterstitialAd.IsPlacementCapped(string)` | `bool` | **Static** |

### Events

Instance events on `LevelPlayInterstitialAd`. **All fire on the Unity main thread** — safe for UI
work, unlike the impression callback in [`ilrd-api.md`](ilrd-api.md).

| Event | Signature | Use it for |
|---|---|---|
| `OnAdLoaded` | `Action<LevelPlayAdInfo>` | Mark one as available |
| `OnAdLoadFailed` | `Action<LevelPlayAdError>` | Backoff retry |
| `OnAdDisplayed` | `Action<LevelPlayAdInfo>` | Stamp the frequency clock, pause audio |
| `OnAdDisplayFailed` | `Action<LevelPlayAdInfo, LevelPlayAdError>` | Load a replacement |
| `OnAdClicked` | `Action<LevelPlayAdInfo>` | Analytics |
| `OnAdClosed` | `Action<LevelPlayAdInfo>` | Resume, and load the next |
| `OnAdInfoChanged` | `Action<LevelPlayAdInfo>` | A new auction winner replaced the loaded ad |

`OnAdInfoChanged` means the loaded ad was replaced by a different auction winner with different
revenue — use the freshest `adInfo` when logging. With ILRD wired, the authoritative revenue comes
through the impression data instead and this stays a development hook.

### Types

`LevelPlayAdInfo` and `LevelPlayAdError` fields, shared by all three formats: [`ad-callbacks.md`](ad-callbacks.md).

## Where to show, and where not to

Boundaries the player is already crossing: level complete, game over, returning to the menu, the gap
between sessions. Not mid-level, not mid-action, and not immediately before a cliffhanger — an ad
placed there reads as a punishment for playing well.

The correct shape of a level-complete handler puts progression first:

```csharp
public void OnLevelComplete()
{
    LoadNextLevel();          // the player's flow, unconditionally
    TryShowInterstitial();    // then the ad, if one happens to be ready
}
```

## Failure modes

**Error 1037 — a load while a load is running.** The same per-frame poll that catches rewarded:

```csharp
void Update()
{
    // Wrong: re-issues a load that is already in flight.
    if (!interstitialAd.IsAdReady())
        interstitialAd.LoadAd();
}
```

A boolean the callbacks clear is the whole fix:

```csharp
private bool isLoadingAd = false;

void LoadInterstitialAd()
{
    if (isLoadingAd) return;

    isLoadingAd = true;
    interstitialAd.LoadAd();
}

void OnAdLoaded(LevelPlayAdInfo adInfo)     => isLoadingAd = false;
void OnAdLoadFailed(LevelPlayAdError error) => isLoadingAd = false;
```

**Error 1036** is the show-side twin: a second `ShowAd()` while one interstitial is on screen.

**Too many ads.** No local frequency cap, or the clock stamped on request rather than on
`OnAdDisplayed`.

**Loads but will not show.** `IsAdReady()` was not checked, or the ad has been sitting loaded for a
long time and expired. Load close to the moment of showing.

**Never loads.** Constructed before `OnInitSuccess`, wrong ad unit id, no fill, or no connection.

## Checks worth running

- Loads after init and reloads after each close.
- Appears only at transitions, never during play.
- The frequency cap holds under repeated attempts.
- The player progresses whether or not an ad shows.
- Load failure retries and recovers.
- Placement reporting and capping behave (where used).
- `DestroyAd()` and unsubscription both happen in `OnDestroy()`.
- More than one device, and a poor connection among them.
