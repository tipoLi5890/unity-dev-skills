# Mock ads and the Test Suite — what each one proves

Two validation stages, and they answer different questions. Mock ads say "my flow is wired
correctly". The Test Suite says "real networks fill and render on this device". Neither substitutes
for the other.

## Mock ads, in the Editor

> **The prerequisite that catches everyone: the active build target must be Android or iOS.** On a
> Standalone/PC/Mac target — the default for a desktop project — the SDK treats the platform as
> unsupported and returns nothing, so `Init()` and every `LoadAd()` appear to do nothing at all. No
> error, no ad. **File ▸ Build Profiles** (**Build Settings** before Unity 6) → **Android** or
> **iOS** → **Switch Platform**, then press Play. When mock ads never show up, check this first.

With a mobile target set, pressing Play produces mock ads with no extra code and no dashboard
configuration. They accept **any** App Key and ad unit id — literal `"test"` works. Use the real
credentials anyway, so nobody has to remember to swap them in before a device build:

```csharp
// The same initialization serves both: mock ads in the Editor, real ads on device.
LevelPlay.Init("abc123youractualappkey");
```

```csharp
// Inside OnInitSuccess — again, real ad unit id even though mock ads ignore it.
LevelPlayRewardedAd rewardedAd = new LevelPlayRewardedAd("12345youractualadunitid");
rewardedAd.OnAdLoaded += OnAdLoaded;
rewardedAd.OnAdRewarded += OnAdRewarded;
rewardedAd.LoadAd();
```

No conditional compilation, no separate Editor path.

### Which callbacks a mock ad fires

| Fires | Does not fire |
|---|---|
| `OnAdLoaded` — always, after `LoadAd()` | `OnAdLoadFailed` — a mock load never fails |
| `OnAdDisplayed` — on `ShowAd()` | `OnAdDisplayFailed` — a mock show never fails |
| `OnAdRewarded` — with a test reward | `OnAdClicked` — no simulated clicks |
| `OnAdClosed` — on dismissal | `OnAdExpanded` / `OnAdCollapsed` |
| | `OnAdLeftApplication` |
| | `OnAdInfoChanged` |
| | impression data — `OnAdImpressionDataReady` (9.5.0+) or `LevelPlay.OnImpressionDataReady` (9.4.x) |

The right-hand column is the point: **every failure path is untested after a green Editor run.** So
is every revenue path. Mock ads also do not model latency, real creatives, or server-side reward
verification.

**Editor init quirk:** `LevelPlay.OnInitSuccess` does not always fire inside the Editor. If it never
logs after `Init()`, and the ad objects were waiting on it, construct them in `Start()` right after
`Init()` instead — mock ads appear regardless. Keep the callback as the gate for device builds.

## The Test Suite, on device

Real networks, real fill, real rendering, production App Key. The Ads Mediation package ships the
Unity Ads adapter, so at least one network is available with no extra setup — though fill still
depends on the dashboard having live instances configured for those ad units.

Turn on **Development Build** in Build Profiles before building. Without it the SDK's console output
is invisible, and diagnosing a Test Suite that does not appear becomes guesswork.

### The two lines

Add them to the existing initializer. Do not create a second one.

```csharp
LevelPlay.SetMetaData("is_test_suite", "enable");   // at the top of Start(), before Init
```

```csharp
LevelPlay.LaunchTestSuite();                        // inside OnInitSuccess
```

> **Ordering is the entire mechanism.** `SetMetaData` after `Init()` means the suite never launches
> and nothing says why. On the iOS coroutine initializer from [`ios-setup.md`](ios-setup.md), `Init`
> lives inside `InitializeLevelPlay()` rather than `Start()` — so `SetMetaData` goes as the **first
> line of `InitializeLevelPlay()`**, not in `Start()` and not after `Init`. `LaunchTestSuite()` stays
> in `OnInitSuccess` either way.

**Both lines come out before release.**

### Template, if there is no initializer yet

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class LevelPlayInitializer : MonoBehaviour
{
    [SerializeField] private string appKey;

    void Awake()
    {
        DontDestroyOnLoad(gameObject);
    }

    void Start()
    {
        // Test Suite — remove before release
        LevelPlay.SetMetaData("is_test_suite", "enable");

        LevelPlay.OnInitSuccess += OnInitSuccess;
        LevelPlay.OnInitFailed += OnInitFailed;
        LevelPlay.Init(appKey);
    }

    private void OnInitSuccess(LevelPlayConfiguration config)
    {
        Debug.Log("LevelPlay initialized successfully");
        // Test Suite — remove before release
        LevelPlay.LaunchTestSuite();
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

Attach it to a GameObject in the first scene and paste the App Key into the Inspector field. The
production key, not the `"test"` placeholder from the mock-ads section — the Test Suite talks to real
networks.

### The run

Build to the device, launch, and the Test Suite UI comes up by itself after initialization. Work
through each format it offers and watch the console for the callbacks. What you are looking for is
not "an ad appeared" but "the ad appeared **and** the callbacks my game depends on arrived in the
order my code assumes".

## Before release

- Test Suite run through on a physical device, every implemented format loading and every callback
  firing.
- Production App Key and production ad unit ids in place — not the values used for mock ads.
- Both Test Suite lines removed.
- Airplane mode: ads fail, the game keeps working.
- Frequency capping actually in effect where interstitials ship.
- More than one device — screen sizes and OS versions.
- **iOS**: SKAdNetwork ids present in `Info.plist`, ATT implemented and tested in both the granted
  and denied states, privacy manifest reviewed, physical device not simulator.
- **Android**: dependency resolution clean, AD_ID declared where API 33+ is targeted, physical
  device.
- Artifact size, ABI list and merged permissions recorded before and after adding the SDK —
  `unity-android-release`.
