# Banner ads

A rectangle that stays on screen while the player carries on. Lowest revenue per impression, but it
accumulates, and it is the format most likely to be in the way. Two facts separate it from the other
two:

> **A banner object takes exactly one `LoadAd()` in its lifetime.** New creatives arrive through
> auto-refresh, configured on the platform; visibility is `ShowAd()` and `HideAd()`. Reloading is
> never the way to refresh a banner.

> **There is no `IsAdReady()` on a banner.** Rewarded and interstitial have one; this format does
> not. It is showable once `OnAdLoaded` fires — there is nothing to poll.

## Manager

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class BannerAdManager : MonoBehaviour
{
    private LevelPlayBannerAd bannerAd;
    private string adUnitId = "YOUR_BANNER_AD_UNIT_ID";

    void Start()
    {
        bannerAd = new LevelPlayBannerAd(adUnitId);

        // ILRD on SDK 9.5.0+:
        //   bannerAd.OnAdImpressionDataReady += OnImpressionDataReady;   // see ilrd-api.md

        bannerAd.OnAdLoaded += OnAdLoaded;
        bannerAd.OnAdLoadFailed += OnAdLoadFailed;
        bannerAd.OnAdDisplayed += OnAdDisplayed;
        bannerAd.OnAdDisplayFailed += OnAdDisplayFailed;
        bannerAd.OnAdClicked += OnAdClicked;
        bannerAd.OnAdExpanded += OnAdExpanded;
        bannerAd.OnAdCollapsed += OnAdCollapsed;
        bannerAd.OnAdLeftApplication += OnAdLeftApplication;

        LoadBanner();
    }

    void OnDestroy()
    {
        if (bannerAd != null)
        {
            bannerAd.OnAdLoaded -= OnAdLoaded;
            bannerAd.OnAdLoadFailed -= OnAdLoadFailed;
            bannerAd.OnAdDisplayed -= OnAdDisplayed;
            bannerAd.OnAdDisplayFailed -= OnAdDisplayFailed;
            bannerAd.OnAdClicked -= OnAdClicked;
            bannerAd.OnAdExpanded -= OnAdExpanded;
            bannerAd.OnAdCollapsed -= OnAdCollapsed;
            bannerAd.OnAdLeftApplication -= OnAdLeftApplication;
            // ILRD on 9.5.0+: bannerAd.OnAdImpressionDataReady -= OnImpressionDataReady;
        }

        DestroyBanner();
    }

    // The only LoadAd() this object gets, apart from a retry after failure.
    public void LoadBanner()
    {
        Debug.Log("Loading banner ad...");
        bannerAd.LoadAd();
    }

    public void ShowBanner() => bannerAd.ShowAd();
    public void HideBanner() => bannerAd.HideAd();

    public void DestroyBanner()
    {
        if (bannerAd != null)
        {
            bannerAd.DestroyAd();
            bannerAd = null;
        }
    }

    private void OnAdLoaded(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Banner ad loaded - network: {adInfo.AdNetwork}, revenue: ${adInfo.Revenue}");
        // Showable from here — call ShowAd() if DisplayOnLoad was turned off.
    }

    private void OnAdLoadFailed(LevelPlayAdError error)
    {
        Debug.LogWarning($"Banner ad load failed: {error.ErrorMessage}");
        Invoke(nameof(LoadBanner), 60f);
    }

    private void OnAdDisplayed(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Banner ad displayed - network: {adInfo.AdNetwork}, placement: {adInfo.PlacementName}");
    }

    private void OnAdDisplayFailed(LevelPlayAdInfo adInfo, LevelPlayAdError error)
    {
        Debug.LogError($"Banner ad display failed: {error.ErrorMessage}");
        Invoke(nameof(LoadBanner), 60f);
    }

    private void OnAdClicked(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Banner ad clicked - network: {adInfo.AdNetwork}");
    }

    private void OnAdExpanded(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Banner ad expanded - network: {adInfo.AdNetwork}");
        // The banner is now covering the screen — pause gameplay if that matters.
    }

    private void OnAdCollapsed(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Banner ad collapsed - network: {adInfo.AdNetwork}");
        // Resume whatever OnAdExpanded paused.
    }

    private void OnAdLeftApplication(LevelPlayAdInfo adInfo)
    {
        Debug.Log($"Banner ad left application - network: {adInfo.AdNetwork}");
    }
}
```

## Size, position and behaviour

Everything configurable is set at construction through the builder — there is no API to move or
resize a live banner. Changing either means destroying the object and creating a new one:

```csharp
var configBuilder = new LevelPlayBannerAd.Config.Builder();

configBuilder.SetSize(LevelPlayAdSize.LARGE);                       // 320x90
configBuilder.SetPosition(LevelPlayBannerPosition.BottomCenter);
configBuilder.SetDisplayOnLoad(true);                               // show as soon as it loads
configBuilder.SetRespectSafeArea(true);                             // Android: clear of notches
configBuilder.SetPlacementName("main_menu_banner");                 // reporting
configBuilder.SetBidFloor(1.0);                                     // minimum CPM in USD

var bannerConfig = configBuilder.Build();
bannerAd = new LevelPlayBannerAd(adUnitId, bannerConfig);
```

### Sizes — `LevelPlayAdSize`

The constants are **uppercase**. `.Banner` does not compile; `.BANNER` does.

| Value | Dimensions |
|---|---|
| `LevelPlayAdSize.BANNER` | 320 × 50 |
| `LevelPlayAdSize.LARGE` | 320 × 90 |
| `LevelPlayAdSize.MEDIUM_RECTANGLE` | 300 × 250 |
| `LevelPlayAdSize.LEADERBOARD` | 728 × 90 |
| `LevelPlayAdSize.CreateAdaptiveAdSize()` | adapts to screen width |
| `LevelPlayAdSize.CreateCustomBannerSize(int width, int height)` | as given |

`BANNER` for most cases; `CreateAdaptiveAdSize()` when the game spans phones and tablets. From SDK
8.8.0 the size object reports its own dimensions, which is what you offset UI against:

```csharp
LevelPlayAdSize adSize = LevelPlayAdSize.BANNER;
int width = adSize.Width;    // 320
int height = adSize.Height;  // 50
```

### Positions — `LevelPlayBannerPosition`

`TopLeft`, `TopCenter`, `TopRight`, `CenterLeft`, `Center`, `CenterRight`, `BottomLeft`,
`BottomCenter`, `BottomRight`. A `Vector2` constructor covers anything else.

`BottomCenter` is the common choice and the least intrusive on a phone held one-handed.

## API

### Methods

| Member | Notes |
|---|---|
| `LoadAd()` | Once per object. Auto-refresh supplies new creatives |
| `ShowAd()` | Make it visible; needs a completed load |
| `HideAd()` | Hide, keep the instance loaded |
| `DestroyAd()` | Tear the instance down. Showing again needs a new object and a new `LoadAd()` |
| `PauseAutoRefresh()` | Stop burning impressions while hidden |
| `ResumeAutoRefresh()` | Resume with visibility |

> **`HideAd()` and `DestroyAd()` are not interchangeable.** Hide is a visibility toggle — cheap,
> reversible, keeps the ad loaded. Destroy is lifecycle teardown, and coming back from it costs a new
> object plus a fresh load. Toggling visibility with destroy is the expensive mistake; the legacy
> `destroyBanner()` maps onto whichever of the two the old code actually meant.

### Events

Instance events on `LevelPlayBannerAd`. **All fire on the Unity main thread** — unlike the impression
callback in [`ilrd-api.md`](ilrd-api.md).

| Event | Signature | Use it for |
|---|---|---|
| `OnAdLoaded` | `Action<LevelPlayAdInfo>` | The banner is showable |
| `OnAdLoadFailed` | `Action<LevelPlayAdError>` | Retry on a long delay |
| `OnAdDisplayed` | `Action<LevelPlayAdInfo>` | Confirm visibility |
| `OnAdDisplayFailed` | `Action<LevelPlayAdInfo, LevelPlayAdError>` | Diagnose, retry |
| `OnAdClicked` | `Action<LevelPlayAdInfo>` | Analytics |
| `OnAdExpanded` | `Action<LevelPlayAdInfo>` | It now covers the screen — pause |
| `OnAdCollapsed` | `Action<LevelPlayAdInfo>` | Back to banner size — resume |
| `OnAdLeftApplication` | `Action<LevelPlayAdInfo>` | The player has left for the advertiser |

`OnAdExpanded` / `OnAdCollapsed` are the pair people forget. An expanded banner is a full-screen
takeover, and a game that keeps running underneath it looks broken when the player returns.

### Types

`LevelPlayAdInfo` and `LevelPlayAdError` fields, shared by all three formats: [`ad-callbacks.md`](ad-callbacks.md).

## Visibility by context

The realistic pattern is a persistent manager that shows in menus and hides during play. Note that
hiding and pausing auto-refresh go together — a hidden banner that keeps refreshing spends
impressions nobody sees:

```csharp
void OnGameplayStart()
{
    bannerAd.HideAd();
    bannerAd.PauseAutoRefresh();
}

void OnGameplayEnd()
{
    bannerAd.ShowAd();
    bannerAd.ResumeAutoRefresh();
}
```

Driven off scene loads, with a `DontDestroyOnLoad` manager holding one banner across the session:

```csharp
using UnityEngine;
using UnityEngine.SceneManagement;
using Unity.Services.LevelPlay;

public class ContextAwareBannerManager : MonoBehaviour
{
    private LevelPlayBannerAd bannerAd;
    private string adUnitId = "YOUR_BANNER_AD_UNIT_ID";

    private string[] bannerEnabledScenes = { "MainMenu", "LevelSelect", "Shop" };
    private bool isBannerLoaded = false;

    void Start()
    {
        DontDestroyOnLoad(gameObject);

        bannerAd = new LevelPlayBannerAd(adUnitId);
        bannerAd.OnAdLoaded += OnAdLoaded;
        bannerAd.OnAdLoadFailed += OnAdLoadFailed;

        SceneManager.sceneLoaded += OnSceneLoaded;

        bannerAd.LoadAd();

        OnSceneLoaded(SceneManager.GetActiveScene(), LoadSceneMode.Single);
    }

    void OnDestroy()
    {
        if (bannerAd != null)
        {
            bannerAd.OnAdLoaded -= OnAdLoaded;
            bannerAd.OnAdLoadFailed -= OnAdLoadFailed;
            bannerAd.DestroyAd();
        }

        SceneManager.sceneLoaded -= OnSceneLoaded;
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        if (ShouldShowBannerInScene(scene.name)) ShowBanner();
        else HideBanner();
    }

    private bool ShouldShowBannerInScene(string sceneName)
    {
        foreach (string enabledScene in bannerEnabledScenes)
            if (sceneName == enabledScene) return true;
        return false;
    }

    private void ShowBanner()
    {
        if (isBannerLoaded && bannerAd != null) bannerAd.ShowAd();
    }

    private void HideBanner()
    {
        if (bannerAd != null) bannerAd.HideAd();
    }

    private void OnAdLoaded(LevelPlayAdInfo adInfo)
    {
        isBannerLoaded = true;

        if (ShouldShowBannerInScene(SceneManager.GetActiveScene().name))
            ShowBanner();
    }

    private void OnAdLoadFailed(LevelPlayAdError error)
    {
        Debug.LogWarning($"Banner ad load failed: {error.ErrorMessage}");
        isBannerLoaded = false;
        Invoke(nameof(LoadBanner), 60f);
    }

    private void LoadBanner()
    {
        if (bannerAd != null)
        {
            isBannerLoaded = false;
            bannerAd.LoadAd();
        }
    }
}
```

## Failure modes

**Repeated `LoadAd()`.** Every-frame loads, a load on each scene re-entry, or a load intended as a
manual refresh:

```csharp
void Update()
{
    // Wrong. A banner loads once; auto-refresh handles the rest.
    bannerAd.LoadAd();
}
```

Banners do not raise an error for this the way interstitials raise 1037, which is exactly why it
survives in shipped code — it just wastes requests and produces odd behaviour. Load once after
construction. The **one** legitimate later call is a retry after `OnAdLoadFailed` — one per failure,
on a long delay, which is why a device with no fill keeps trying without flooding the network. After
`DestroyAd()`, it is a new object with its own single load.

**Overlapping UI.** Reserve the space: read `adSize.Height`, offset the canvas, and test on the
narrowest and widest devices you ship to. `SetRespectSafeArea(true)` keeps Android clear of cutouts.

**Nothing appears.** Constructed before `OnInitSuccess`; `ShowAd()` before `OnAdLoaded`; still hidden
from an earlier `HideAd()`; or `SetDisplayOnLoad(false)` with no manual show.

**Wrong size.** Lowercase enum members, or no `SetSize` call and a default that is not what you
assumed.

## Checks worth running

- Loads, displays, and lands in the intended position.
- Does not cover anything the player needs.
- Hide and show both work, repeatedly.
- Auto-refresh pauses while hidden and resumes with visibility.
- `DestroyAd()` runs when the manager goes away.
- Portrait and landscape, several screen sizes.
- Safe area respected on a notched Android device.
- A load failure schedules one delayed retry, and nothing else reloads the banner.
