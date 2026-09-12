# Strategy, placement, and the rules every ad manager follows

> Revenue figures below are industry-typical ranges; measure your own before planning on them.

Two halves. The first is what to build and where to put it, driven by the optimisation goal. The
second is the set of rules any generated ad manager has to satisfy regardless of that goal.

## The trade, stated plainly

Every ad decision moves revenue and experience in opposite directions. Naming which one the game is
optimising for, before writing a line, is what makes the rest of the decisions fall out rather than
be argued.

| Goal | What it protects | What it costs |
|---|---|---|
| **Revenue** | Impression opportunities | Some early abandonment, lower satisfaction |
| **Experience** | Retention and word of mouth | A large fraction of short-term revenue |
| **Balanced** | Long-term value | Neither maximised |

Four questions usually settle it: how mature is the app (early → protect experience), is the business
model ads-only or hybrid, how substitutable is the game, and what do players of this genre already
tolerate.

## Format mix per goal

The mix, and the order to build it in:

| Goal | Mix | Order |
|---|---|---|
| **Revenue** | Rewarded across several high-value moments; interstitials at every transition, capped 3–5 min; banner persistent in gameplay | Rewarded → Interstitial → Banner |
| **User experience** | Rewarded only, always opt-in, generous; interstitials at session boundaries if at all; banners menu-only or none | Rewarded → (optional) Interstitial |
| **Balanced** | Rewarded at 2–3 placements; interstitials at natural breaks, capped 5–7 min; banner in menus and low-attention moments | Rewarded → Interstitial → selective Banner |

### Revenue

**Rewarded, primary.** Three to five placements at high-value moments — hints, extra lives,
power-ups, bonus currency, skipping a level. Keep one loaded and reload immediately after each show.

**Interstitial, secondary.** Every natural transition, capped at 3–5 minutes of play. Level complete,
game over, back to menu. Load ahead of the transition, not during it.

**Banner, tertiary.** Persistent through gameplay, bottom-positioned, loaded for the whole session.
This is where the visual clutter is accepted deliberately.

Industry-typical outcome, not a LevelPlay figure: roughly 30–50% more ad revenue, 5–15% more early
abandonment, weaker satisfaction scores, strong monetisation of the players who stay.

### Experience

**Rewarded, and preferably only rewarded.** One or two placements. Always opt-in, always generous,
never forced.

**Interstitial, rarely if at all.** Session boundaries only — returning to menu, closing the app.
Ten minutes or more between, or once per session. Never during play.

**Banner, minimal.** Menus only, standard 320×50 rather than a rectangle, hidden during any active
engagement.

Industry-typical outcome: 40–60% less ad revenue than the revenue-first mix, better retention and
satisfaction, more organic growth.

### Balanced — the default for most games

**Rewarded** at two or three well-chosen moments where engagement is already high. Rewards that feel
worth the time.

**Interstitial** at natural breaks only, capped at 5–7 minutes.

**Banner** in menus and low-attention moments, hidden when the game gets immersive, bottom-positioned
with the UI offset to match.

Industry-typical outcome: 70–85% of the revenue-first figure, good retention, positive sentiment.

## Where ads go, and where they do not

**Rewarded belongs at positive moments** — after a win, at a progression milestone, at an unlock.
Someone who just succeeded is far more willing to trade thirty seconds than someone who just failed.

**Interstitials belong at transitions** — level complete, game over, returning to menu, between
sessions. Places the player was already stopping.

**Banners belong in low-attention periods** — waiting screens, loading, menu browsing.

Six placements that reliably do damage:

- Interrupting active play with a full-screen ad.
- Offering a reward and delivering an unrewarded interstitial instead.
- One ad every minute or two.
- Ads as a consequence of failing, which reads as punishment.
- Ads that must be watched to continue.
- Ads immediately before a reveal or a cliffhanger.

## Patterns

These build on the managers in [`rewarded-api.md`](rewarded-api.md),
[`interstitial-api.md`](interstitial-api.md) and [`banner-api.md`](banner-api.md), using only their
public surface — `LoadAd()`, `ShowAd()`, `IsAdReady()`, the banner manager's `ShowBanner()` and
`HideBanner()`, and the rewarded manager's `OnRewardGranted` hook. Generate those first or these will
not compile.

### Free first, then the ad

```csharp
public class HintSystem : MonoBehaviour
{
    [SerializeField] private RewardedAdManager adManager;
    [SerializeField] private int hintsAvailable = 3;

    public void RequestHint()
    {
        if (hintsAvailable > 0)
        {
            UseHint();
            hintsAvailable--;
            return;
        }

        if (adManager.IsAdReady())
            ShowHintAdOffer();
        else
            ShowHintNotAvailableMessage();
    }

    private void ShowHintAdOffer()
    {
        // "Watch an ad for a hint?" — on accept:
        adManager.OnRewardGranted = OnHintAdRewardEarned;
        adManager.ShowAd();
    }

    private void OnHintAdRewardEarned() => UseHint();

    private void UseHint() => Debug.Log("Showing hint");

    private void ShowHintNotAvailableMessage() => Debug.Log("Hints not available at the moment");
}
```

The structure carries the message: free hints come first, the ad is an option rather than a toll, the
exchange is legible, and an unavailable ad degrades into a message instead of a dead button.

### Count-based interstitial gate

```csharp
public class LevelTransitionAds : MonoBehaviour
{
    [SerializeField] private InterstitialAdManager adManager;
    private int levelsCompletedSinceAd = 0;
    private int levelsRequiredBetweenAds = 3;

    public void OnLevelComplete()
    {
        levelsCompletedSinceAd++;

        if (levelsCompletedSinceAd >= levelsRequiredBetweenAds)
        {
            ShowInterstitialOpportunistically();
            levelsCompletedSinceAd = 0;
        }

        ProceedToNextLevel();
    }

    private void ShowInterstitialOpportunistically()
    {
        if (adManager.IsAdReady())
            adManager.ShowAd();
    }

    private void ProceedToNextLevel()
    {
        // Runs whether or not an ad appeared.
    }
}
```

Every-third-level is a rhythm players adapt to, unlike a timer they cannot perceive. And the ad
attempt never gates progression.

### Context-switched banner

```csharp
public class ContextAwareBanners : MonoBehaviour
{
    [SerializeField] private BannerAdManager bannerManager;

    public enum AppContext { MainMenu, Playing, Paused, GameOver }

    private AppContext currentContext;

    public void SetContext(AppContext newContext)
    {
        currentContext = newContext;
        UpdateBannerVisibility();
    }

    private void UpdateBannerVisibility()
    {
        switch (currentContext)
        {
            case AppContext.MainMenu:
            case AppContext.GameOver:
                bannerManager.ShowBanner();
                break;

            case AppContext.Playing:
                bannerManager.HideBanner();
                break;

            case AppContext.Paused:
                // Experience-first: hide. Revenue-first: show.
                bannerManager.ShowBanner();
                break;
        }
    }
}
```

One switch statement holds the whole banner policy, which is what makes it changeable later.

## Frequency

Time-based:

```csharp
public class FrequencyManager : MonoBehaviour
{
    private float minSecondsBetweenInterstitials = 300f;
    private float lastInterstitialTime = -300f;   // first opportunity is eligible

    public bool CanShowInterstitial()
        => Time.realtimeSinceStartup - lastInterstitialTime >= minSecondsBetweenInterstitials;

    public void RecordInterstitialShown()
        => lastInterstitialTime = Time.realtimeSinceStartup;
}
```

Count-based, which players can actually perceive:

```csharp
private int actionsRequiredBetweenAds = 3;
private int actionsSinceLastAd = 0;

public void OnUserAction()
{
    actionsSinceLastAd++;

    if (actionsSinceLastAd >= actionsRequiredBetweenAds)
    {
        TryShowAd();
        actionsSinceLastAd = 0;
    }
}
```

An "action" is whatever the game counts in: levels finished, rounds played, sessions started, a
feature used. Intervals by goal: 3–5 min revenue-first, 5–7 min balanced, 10+ min experience-first.

## Failing gracefully

An ad that will not load must never become the player's problem:

```csharp
public void OnAdLoadFailed()
{
    Debug.LogWarning("Ad failed to load");

    ProceedWithoutAd();                    // the player's flow, unconditionally
    Invoke(nameof(RetryLoadAd), 30f);      // the retry, quietly, later
}
```

For rewarded specifically, there is a judgement call when the *show* fails after the player already
opted in:

```csharp
public void OnRewardedAdShowFailed()
{
    if (shouldBeGenerousOnFailure)
    {
        GrantReward();
        ShowMessage("Reward granted! (Ad unavailable)");
    }
    else
    {
        ShowMessage("Ad unavailable, please try again later");
    }
}
```

Granting anyway is right when the strategy is experience-first, when the player is valuable, and when
the failure was on your side. It is wrong where the reward has real economic weight — that is the
`unity-live-services` conversation about server-side grants.

## What to test, and against what

High-impact variables, roughly in order: the frequency cap (3 vs 5 vs 7 minutes), immediate versus
delayed interstitials, reward generosity, banner visibility policy, and whether interstitials ship at
all.

Split into cohorts, run for at least one to two weeks, and **track revenue and retention together**.
A revenue metric alone will always favour more ads.

| Family | Metrics |
|---|---|
| Revenue | ARPDAU, impressions per DAU, eCPM |
| Experience | D1/D7/D30 retention, session length, session frequency, organic referrals |
| Combined | LTV, ARPU-to-retention ratio, satisfaction |

Rough targets by strategy, again industry-typical rather than platform-specific: revenue-first
ARPDAU > $0.15 with impressions/DAU > 8 and D7 > 20%; experience-first D7 > 35%, sessions > 15 min,
weekly uninstall under 5%, ARPDAU > $0.05; balanced ARPDAU > $0.10, D7 > 28%, impressions/DAU > 5.

## Recurring mistakes

1. Monetising hard before players are engaged.
2. Reading revenue without reading retention.
3. Requiring an ad to progress.
4. Capping too loosely, or not at all.
5. Making a rewarded ad compulsory — at which point it is not rewarded.
6. Treating load failures as impossible.
7. One strategy for every segment.
8. Shipping a monetisation change without measuring it.

The order to move in: start conservative, add monetisation as engagement builds, measure everything,
and watch retention closely — adding ads later is easy, winning back a churned player is not.

## Platform differences

**iOS.** Lower tracking opt-in since 14.5; players who decline see lower-value inventory; the user
base skews privacy-conscious. A lighter touch tends to pay better.

**Android.** Higher fill, more tolerance for frequency, far more hardware variation — which means
banner layout and safe-area handling need testing across more devices.

## Rules for generated ad managers

Whatever structure the publisher picks — one manager per format, a single unified manager, or loose
snippets — the same requirements hold.

**Always:**

- Every manager is a `MonoBehaviour`. `Start()` and `OnDestroy()` are the whole lifecycle, and the
  script has to be attachable.
- After generating one, say where it goes: the persistent GameObject that carries the initializer,
  the one with `DontDestroyOnLoad`.
- Banner and interstitial managers call `DestroyAd()` in `OnDestroy()`.
- Rewarded and interstitial show paths check `IsAdReady()` first. Banner has no such method.
- Where dashboard placements are in use, the show path also checks the static
  `IsPlacementCapped(placementName)` — showing into a capped placement fails with 524 or 526.
- Subscribe once, unsubscribe in `OnDestroy()`.
- Null checks on the ad object before every call.
- A debug log on every callback, so a silent integration can be diagnosed without a debugger.
- Load failures handled; the game keeps working.

**If the publisher already has ad code, read it before writing any.** A targeted fix to a working
manager beats a fresh file that has to be reconciled with theirs — and existing code is where you
find out whether they are still on `IronSource.Agent`
([`migration-sdk-9.md`](migration-sdk-9.md)).

**Structure, per the choice made:**

| Choice | Shape |
|---|---|
| One manager per format | Complete `.cs` files: `RewardedAdManager.cs`, `InterstitialAdManager.cs`, `BannerAdManager.cs`. One format each, fully self-contained |
| One unified manager | A single `AdManager.cs` covering every requested format, with method names that disambiguate (`LoadRewardedAd()`, `LoadInterstitial()`) and regions separating the formats |
| Snippets | Focused blocks, each labelled, each with a note on where it goes and what it depends on |

**Bid floors, per format.** A floor sets a minimum CPM in USD: higher average eCPM, lower fill. Most
publishers skip it until the dashboard has real numbers, and it is a per-format decision — a floor on
rewarded and none on banner is a perfectly normal combination. Starting ranges: rewarded $0.50–$2.00,
interstitial $0.20–$1.00, banner $0.05–$0.20.

```csharp
// With a floor
var config = new LevelPlayRewardedAd.Config.Builder()
    .SetBidFloor(0.80)
    .Build();
rewardedAd = new LevelPlayRewardedAd(adUnitId, config);
```

```csharp
// Without
rewardedAd = new LevelPlayRewardedAd(adUnitId);
```

## Adding a format later

The setup steps do not repeat. Confirm the existing initialization still logs success, then go
straight to the new format's reference, follow whatever structure the project already uses, and test
it the way §11 of the skill describes. Existing formats keep working while the new one is added.
