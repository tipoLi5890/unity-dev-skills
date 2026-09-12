# Rewarded ads

The player opts in and gets something for it. Highest revenue per impression of the three formats,
and the only one whose presence a player can genuinely be pleased about — extra lives, hints,
currency, power-ups, skipping a wait.

Two things about this format cost more time than everything else combined, so they lead:

> **It does not load itself.** The legacy IronSource rewarded video managed loading internally. This
> API does not: `LoadAd()` is an explicit call, and code migrated line by line from the old API has
> no line to translate into it. The symptom is an ad that is never ready and no error anywhere.

> **Grant the reward in `OnAdRewarded`, never in `OnAdClosed`.** A player who closes early still
> earns nothing from `OnAdClosed` logic that assumed otherwise — and the two callbacks are
> asynchronous, so `OnAdRewarded` can arrive *after* `OnAdClosed`. Nothing in `OnAdClosed` may assume
> the reward has already been granted.

## Manager

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class RewardedAdManager : MonoBehaviour
{
    private LevelPlayRewardedAd rewardedAd;
    private string adUnitId = "YOUR_REWARDED_AD_UNIT_ID";

    // Optional hook for the caller that asked for the ad (a hint system, a shop).
    public System.Action OnRewardGranted;

    void Start()
    {
        // Create and subscribe. Loading is triggered separately — see LoadAd() below.
        rewardedAd = new LevelPlayRewardedAd(adUnitId);

        // ILRD on SDK 9.5.0+:
        //   rewardedAd.OnAdImpressionDataReady += OnImpressionDataReady;   // see ilrd-api.md

        rewardedAd.OnAdLoaded += OnAdLoaded;
        rewardedAd.OnAdLoadFailed += OnAdLoadFailed;
        rewardedAd.OnAdDisplayed += OnAdDisplayed;
        rewardedAd.OnAdDisplayFailed += OnAdDisplayFailed;
        rewardedAd.OnAdRewarded += OnAdRewarded;
        rewardedAd.OnAdClosed += OnAdClosed;
        rewardedAd.OnAdClicked += OnAdClicked;
        rewardedAd.OnAdInfoChanged += OnAdInfoChanged;
    }

    void OnDestroy()
    {
        if (rewardedAd != null)
        {
            rewardedAd.OnAdLoaded -= OnAdLoaded;
            rewardedAd.OnAdLoadFailed -= OnAdLoadFailed;
            rewardedAd.OnAdDisplayed -= OnAdDisplayed;
            rewardedAd.OnAdDisplayFailed -= OnAdDisplayFailed;
            rewardedAd.OnAdRewarded -= OnAdRewarded;
            rewardedAd.OnAdClosed -= OnAdClosed;
            rewardedAd.OnAdClicked -= OnAdClicked;
            rewardedAd.OnAdInfoChanged -= OnAdInfoChanged;
            // ILRD on 9.5.0+: rewardedAd.OnAdImpressionDataReady -= OnImpressionDataReady;
        }
    }

    // Call from wherever the ad should become available: a button handler,
    // a scene entry, a point in gameplay. Nothing loads without this.
    public void LoadAd()
    {
        Debug.Log("Loading rewarded ad...");
        rewardedAd.LoadAd();
    }

    public void ShowAd()
    {
        if (rewardedAd.IsAdReady())
        {
            Debug.Log("Showing rewarded ad");
            rewardedAd.ShowAd();
        }
        else
        {
            Debug.LogWarning("Rewarded ad is not ready yet");
        }
    }

    // Ask this before offering the ad in the UI.
    public bool IsAdReady() => rewardedAd != null && rewardedAd.IsAdReady();

    private void OnAdLoaded(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Rewarded ad loaded successfully");
    }

    private void OnAdLoadFailed(LevelPlayAdError error)
    {
        Debug.LogWarning($"Rewarded ad failed to load: {error.ErrorMessage}");
        Invoke(nameof(LoadAd), 30f);
    }

    private void OnAdDisplayed(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Rewarded ad displayed");
    }

    private void OnAdDisplayFailed(LevelPlayAdInfo adInfo, LevelPlayAdError error)
    {
        Debug.LogError($"Rewarded ad failed to display: {error.ErrorMessage}");
        LoadAd();
    }

    private void OnAdRewarded(LevelPlayAdInfo adInfo, LevelPlayReward reward)
    {
        Debug.Log($"User earned reward: {reward.Amount} {reward.Name}");
        GrantReward(reward);
        OnRewardGranted?.Invoke();
    }

    private void OnAdClosed(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Rewarded ad closed");
        // No LoadAd() here by default. Add one only if this game preloads eagerly;
        // otherwise the next load comes from the player's next trigger.
    }

    private void OnAdClicked(LevelPlayAdInfo adInfo)
    {
        Debug.Log("Rewarded ad clicked");
    }

    private void OnAdInfoChanged(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Rewarded ad info changed - network: {adInfo.AdNetwork}, revenue: ${adInfo.Revenue}");
    }

    private void GrantReward(LevelPlayReward reward)
    {
        Debug.Log($"Granting {reward.Amount} {reward.Name} to the user");
    }
}
```

## Several placements, one ad unit

Placements are dashboard-configured labels on the same ad unit. They separate reporting and let each
one carry its own cap. One ad object serves them all; remember which one is in flight so the reward
can be routed:

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class MultiPlacementRewardedAdManager : MonoBehaviour
{
    private string adUnitId = "YOUR_REWARDED_AD_UNIT_ID";
    private LevelPlayRewardedAd rewardedAd;

    private string currentPlacement;

    void Start()
    {
        rewardedAd = new LevelPlayRewardedAd(adUnitId);

        rewardedAd.OnAdLoaded += OnAdLoaded;
        rewardedAd.OnAdLoadFailed += OnAdLoadFailed;
        rewardedAd.OnAdRewarded += OnAdRewarded;
        rewardedAd.OnAdClosed += OnAdClosed;
        rewardedAd.OnAdDisplayFailed += OnAdDisplayFailed;

        rewardedAd.LoadAd();
    }

    void OnDestroy()
    {
        if (rewardedAd != null)
        {
            rewardedAd.OnAdLoaded -= OnAdLoaded;
            rewardedAd.OnAdLoadFailed -= OnAdLoadFailed;
            rewardedAd.OnAdRewarded -= OnAdRewarded;
            rewardedAd.OnAdClosed -= OnAdClosed;
            rewardedAd.OnAdDisplayFailed -= OnAdDisplayFailed;
        }
    }

    public void ShowAdForHints()      => ShowAdWithPlacement("hints");
    public void ShowAdForExtraLives() => ShowAdWithPlacement("extra_lives");
    public void ShowAdForCoins()      => ShowAdWithPlacement("bonus_coins");

    private void ShowAdWithPlacement(string placementName)
    {
        if (!rewardedAd.IsAdReady())
        {
            Debug.LogWarning("Rewarded ad is not ready");
            return;
        }

        if (LevelPlayRewardedAd.IsPlacementCapped(placementName))
        {
            Debug.LogWarning($"Placement '{placementName}' is capped");
            return;
        }

        currentPlacement = placementName;
        rewardedAd.ShowAd(placementName: placementName);
    }

    private void OnAdRewarded(LevelPlayAdInfo adInfo, LevelPlayReward reward)
    {
        switch (currentPlacement)
        {
            case "hints":       GrantHints(reward);      break;
            case "extra_lives": GrantExtraLives(reward); break;
            case "bonus_coins": GrantCoins(reward);      break;
        }
    }

    private void OnAdClosed(LevelPlayAdInfo adInfo)
    {
        // `currentPlacement` is deliberately left set: OnAdRewarded can still arrive
        // after this. ShowAdWithPlacement overwrites it before the next show.
        LoadAd();
    }

    private void OnAdDisplayFailed(LevelPlayAdInfo adInfo, LevelPlayAdError error)
    {
        Debug.LogError($"Rewarded ad display failed: {error.ErrorMessage}");
        LoadAd();
    }

    private void OnAdLoaded(LevelPlayAdInfo adInfo) => Debug.Log("Rewarded ad loaded");

    private void OnAdLoadFailed(LevelPlayAdError error)
    {
        Debug.LogWarning($"Rewarded ad load failed: {error.ErrorMessage}");
        Invoke(nameof(LoadAd), 30f);
    }

    private void LoadAd()
    {
        if (rewardedAd != null) rewardedAd.LoadAd();
    }
}
```

## API

### Construction

```csharp
LevelPlayRewardedAd rewardedAd = new LevelPlayRewardedAd("your_ad_unit_id");
```

With a bid floor — a minimum CPM in USD that raises average eCPM and lowers fill:

```csharp
var configBuilder = new LevelPlayRewardedAd.Config.Builder();
configBuilder.SetBidFloor(1.0);
var config = configBuilder.Build();
LevelPlayRewardedAd rewardedAd = new LevelPlayRewardedAd("your_ad_unit_id", config);
```

Construct only after `OnInitSuccess`.

### Methods

| Member | Returns | Notes |
|---|---|---|
| `LoadAd()` | — | Explicit; nothing loads without it |
| `ShowAd()` | — | Check `IsAdReady()` first |
| `ShowAd(placementName: string)` | — | Same, tagged with a dashboard placement |
| `IsAdReady()` | `bool` | Loaded and showable |
| `GetReward(string placementName = null)` | `LevelPlayReward` | The configured reward, before showing |
| `LevelPlayRewardedAd.IsPlacementCapped(string)` | `bool` | **Static.** True when that placement has hit its cap |

`GetReward()` is what lets the button say "Watch for 5 coins" instead of "Watch an ad":

```csharp
LevelPlayReward placementReward = rewardedAd.GetReward("extra_lives");
Debug.Log($"Extra lives reward: {placementReward.Amount} {placementReward.Name}");
```

### Events

All `LevelPlayRewardedAd` instance events. **They run on the Unity main thread**, so Unity APIs are
safe inside them — unlike the impression-data callback in [`ilrd-api.md`](ilrd-api.md), which does
not.

| Event | Signature | Use it for |
|---|---|---|
| `OnAdLoaded` | `Action<LevelPlayAdInfo>` | Enable the offer button |
| `OnAdLoadFailed` | `Action<LevelPlayAdError>` | Backoff retry; disable the button |
| `OnAdDisplayed` | `Action<LevelPlayAdInfo>` | Pause gameplay if needed |
| `OnAdDisplayFailed` | `Action<LevelPlayAdInfo, LevelPlayAdError>` | Load a replacement |
| `OnAdRewarded` | `Action<LevelPlayAdInfo, LevelPlayReward>` | **Grant the reward here** |
| `OnAdClosed` | `Action<LevelPlayAdInfo>` | Resume; reload if preloading eagerly |
| `OnAdClicked` | `Action<LevelPlayAdInfo>` | Analytics |
| `OnAdInfoChanged` | `Action<LevelPlayAdInfo>` | A new auction winner replaced the loaded ad |

`OnAdInfoChanged` signals that the loaded ad changed — different network, different revenue estimate.
It matters for logging accuracy: always use the latest `adInfo`. If ILRD is wired, though, the final
revenue comes through the impression data instead, and this event is mostly a waterfall-watching hook
for development.

### Types

`LevelPlayReward` — `Name` (string), `Amount` (int).

```csharp
private void OnAdRewarded(LevelPlayAdInfo adInfo, LevelPlayReward reward)
{
    if (reward.Name == "coins")
        playerCoins += reward.Amount;
}
```

`LevelPlayAdInfo` and `LevelPlayAdError` fields, shared by all three formats: [`ad-callbacks.md`](ad-callbacks.md).

## Load strategy — pick one on purpose

**Triggered load** is the default and the one the API is shaped for. Create and subscribe in
`OnInitSuccess`; load when the game reaches a point where the ad should be available.

```csharp
void OnInitSuccess(LevelPlayConfiguration config)
{
    rewardedAd = new LevelPlayRewardedAd(adUnitId);
    rewardedAd.OnAdLoaded += OnAdLoaded;
    rewardedAd.OnAdClosed += OnAdClosed;
    // No LoadAd() here.
}

public void OnPlayerReachesRewardedAdOpportunity()
{
    rewardedAd.LoadAd();
}
```

**Eager preload** keeps one ready at all times, at the cost of loading ads that may never be shown.
Valid, but choose it — do not inherit it from legacy code that had no choice:

```csharp
void OnInitSuccess(LevelPlayConfiguration config)
{
    rewardedAd = new LevelPlayRewardedAd(adUnitId);
    rewardedAd.OnAdLoaded += OnAdLoaded;
    rewardedAd.OnAdClosed += OnAdClosed;
    rewardedAd.LoadAd();
}

void OnAdClosed(LevelPlayAdInfo adInfo)
{
    rewardedAd.LoadAd();
}
```

## Wiring the button

Drive availability off the callbacks, not off a per-frame poll:

```csharp
public Button watchAdButton;

void OnAdLoaded(LevelPlayAdInfo adInfo)      => watchAdButton.interactable = true;
void OnAdLoadFailed(LevelPlayAdError error)  => watchAdButton.interactable = false;
```

A permanently disabled button means one of three things: the load never happened (the trap at the top
of this file), a load failure with no retry, or subscriptions that never took. Log every callback and
the answer appears immediately.

## Failure modes

**A load fired while one was in flight.** Almost always this:

```csharp
void Update()
{
    // Wrong: polls every frame and re-issues a load that is already running.
    if (!rewardedAd.IsAdReady())
        rewardedAd.LoadAd();
}
```

Track load state yourself and let the callbacks clear it:

```csharp
private bool isLoadingAd = false;

void LoadRewardedAd()
{
    if (isLoadingAd) return;

    isLoadingAd = true;
    rewardedAd.LoadAd();
}

void OnAdLoaded(LevelPlayAdInfo adInfo)     => isLoadingAd = false;
void OnAdLoadFailed(LevelPlayAdError error) => isLoadingAd = false;
```

**Reward never arrives.** The grant is in `OnAdClosed`, or the player closed before earning it.

**Reward arrives twice.** `OnAdRewarded` is subscribed more than once — usually a manager that got
duplicated across a scene load, or subscriptions added outside `Start()` without matching removals.
Subscribe once, unsubscribe in `OnDestroy()`.

**Nothing loads at all.** The object was constructed before `OnInitSuccess`, the ad unit id is wrong,
or there is no fill in the test region. Test on hardware with a real connection.

## Checks worth running

- Loads after init; `IsAdReady()` flips to true.
- Shows on `ShowAd()`; `OnAdRewarded` fires and the grant lands exactly once.
- The offer button tracks availability in both directions.
- A load failure retries and recovers.
- Placement routing and placement capping behave (where placements are used).
- Events unsubscribed in `OnDestroy()`.
- More than one device, and a poor connection among them.
