---
name: unity-ads-levelplay
description: >-
  Integrate LevelPlay ad mediation into a Unity game through the Ads Mediation
  package (`com.unity.services.levelplay`): rewarded, interstitial and banner
  units for the SDK version that resolved. Load for "add ads to my game",
  "implement rewarded ads", "set up mediation", every LevelPlay symbol
  reporting CS0246, an Android or iOS build that fails on ad dependencies after
  a clean Editor compile, no ads when you press Play, GDPR/CCPA/COPPA or iOS
  ATT wiring for ads, ad revenue that never reaches analytics, migrating off
  IronSource.Agent or Unity Ads, or an Android build that suddenly cannot
  resolve `com.ironsource.sdk`. Store declarations and manifest permissions
  are `unity-monetization`.
---

# unity-ads-levelplay — the resolved version decides everything downstream

> **Read `Packages/packages-lock.json` before you write a line of ad code.** Only it says whether the
> package is really installed (if not, every LevelPlay symbol is a `CS0246`) and **which SDK version
> resolved**, which picks the GDPR call and the impression-revenue event. Code written against the
> wrong half of that fork looks correct and is wrong.

## The working contract

> **Report, then wait.** This skill changes package state, build settings and shipping code, and one
> of its steps deletes folders. Read what the project files can tell you (installed package, resolved
> version, manifest, build target), report it, then confirm what only the publisher knows (dashboard
> credentials, target platforms, which regulations apply) before generating code.

- **What you can settle yourself, settle yourself.** Package id, resolved version, build target: do
  not ask the publisher to read Package Manager back to you.
- **What you cannot settle, do not guess.** App Key, ad unit ids, installed networks, whether GDPR
  applies.
- **Never install or upgrade the package on the user's behalf.** It rewrites the native Android and
  iOS dependency graph (§4), the one build-breaking change here. Name the package and version; the
  publisher installs it in Package Manager.
- **The scripts here are files for their project**, attached to a GameObject in the Editor; ad SDKs do
  nothing in an Editor `eval`.

## Before you start: the installed version decides

- **Which branch.** The `com.unity.services.levelplay` version in `Packages/packages-lock.json` picks
  **9.4.x or 9.5.0+**, the fork §6 and §10 branch on; older floors sit in the references where they
  apply. Where a reference and the installed package disagree, believe the package.
- **Whether it is there at all.** In an Editor session,
  `PackageInfo.FindForAssetPath("Packages/com.unity.services.levelplay/package.json")` returning
  **null** means the package is not installed.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| `CS0246` on `Unity.Services.LevelPlay`, red underlines everywhere | §3: the package is not resolved |
| Compiles in the Editor, Gradle or CocoaPods build fails | §4, `reference/dependency-resolution.md` |
| Android stopped resolving `com.ironsource.sdk`, nothing changed | `reference/migration-sdk-9.md` §D: the old repository is gone |
| Press Play, nothing happens, no ads at all | §11: the build target is not Android or iOS |
| `SetGDPRConsent` does not compile / `SetGDPRConsents` is obsolete | §6: the other side of the 9.4/9.5 fork |
| Ads never load | §7: ad objects created before `OnInitSuccess`, or a wrong App Key |
| Callbacks never fire | §7: subscribe before `Init()`, keep the object alive |
| Reward granted twice, or never | `reference/rewarded-api.md`: grant in `OnAdRewarded` |
| Error 1037 / 1036 in the log | `reference/interstitial-api.md`: a load fired while one was in flight |
| Banner is the wrong size or under the notch | `reference/banner-api.md` |
| No revenue reaching Firebase / AppsFlyer / Adjust | §10, `reference/ilrd-api.md` |
| Test Suite never appears on device | §11: `SetMetaData` must run before `Init` |
| iOS submission rejected over tracking | `reference/ios-setup.md` |
| Permissions or store declarations changed by the SDK | `unity-monetization` |

## 1. Is this new, a migration, or a repair?

| Situation | Where to start |
|---|---|
| Nothing integrated yet | §2 |
| Upgrading the SDK, replacing `IronSource.Agent` calls, coming off Unity Ads, or an Android build that can no longer resolve `is.com` dependencies | `reference/migration-sdk-9.md`: pick one of five scenarios, finish with its completeness checklist |
| Integration works; adding consent, ILRD, the Test Suite, or a format | The section that covers it |

A migration is not finished when the code translates: several 9.x requirements, an explicit rewarded
load among them, have **no line in the legacy code to translate from**. That checklist catches them.

## 2. Verify the project, then fix the platform

Confirm `Assets/` and `ProjectSettings/` are at your working path. **Switch the active build target to
Android or iOS now, not later.** LevelPlay runs on those two only: on Standalone the SDK reports an
unsupported platform and returns no ads, so `Init()`, every load and the Editor mock ads (§11) appear
to do nothing. **File ▸ Build Profiles** (**Build Settings** before Unity 6) → **Switch Platform**.
Which platforms ship decides ATT (§6), dependency resolution (§4) and testing (§11); ask.

## 3. The Ads Mediation package, and the gate that follows

Package Manager lists it as **Ads Mediation** (**Unity Registry**); the project files record
`com.unity.services.levelplay`. Not **Ads IAP Mediation Adaptor** (a separate in-app-purchase package)
nor **Advertisement Legacy** (deprecated Unity Ads; `reference/migration-sdk-9.md` §E). The publisher
installs it, accepting the **Mobile Dependency Resolver** import if offered: §4 needs one.

> **The gate: no LevelPlay code until `com.unity.services.levelplay` appears in
> `Packages/packages-lock.json` with a concrete version.** Both files are plain JSON: read them.
>
> - Absent from `manifest.json` → the install never happened. Say so and ask for it.
> - In `manifest.json`, absent from the lock file → not resolved yet (importing, or resolution
>   failed). With no Editor run since the id was added, the lag is expected; re-read after the Editor
>   next opens the project.
>
> Say which you found, and stop. **Never write the entry into `packages-lock.json` by hand**: it is
> Unity's resolution output, and a typed entry is a manufactured pass.

Report the resolved version: the Package Manager window, an earlier turn or a recollection is not
evidence, and §6 and §10 branch on it. **Re-read the file at §7** even if §3 passed this session; it is
the check most often skipped. **Ads Mediation > Network Manager** adds adapters, checks for updates,
shows the installed SDK version.

## 4. Native dependencies, or the build fails after the code compiles

UPM does not fetch LevelPlay's native Android and iOS libraries; a dependency manager does: Mobile
Dependency Resolver (MDR), Unity External Dependency Manager (UEDM) or EDM4U. Skip it and you get the
signature failure: **clean compile in the Editor, Gradle or CocoaPods error at build time.** Run
`reference/dependency-resolution.md` (Custom Main Gradle Template included) for **every** shipped
platform. The API 33+ `com.google.android.gms.permission.AD_ID` declaration is `unity-monetization`.

## 5. App Key, ad unit ids, AdMob keys

The **App Key** (**Apps** → your app, needed for §7) and one **ad unit id** per format (**Ad units** →
your app, §9) come from the dashboard at <https://platform.ironsrc.com/>. **AdMob as a mediated network
needs its own keys** under **Ads Mediation > Developer Settings > LevelPlay Mediation Settings**.
Details, and a missing **Ads Mediation** menu: `reference/initialization-api.md`.

## 6. Privacy settings run before `Init()`, and the GDPR call forks by version

Technical wiring, not legal advice. Every call runs **before** `LevelPlay.Init()`; after, it is
silently late. All are on `LevelPlayPrivacySettings`:

- **GDPR — the version you read in §3 picks the call.** 9.5.0+: `SetGDPRConsent(bool)`, one boolean for
  every network. 9.4.x: `SetGDPRConsents(Dictionary<string, bool>)`, one entry per installed adapter.
  **This is the current API on 9.4.x**, `[Obsolete]` only from 9.5.0: do not report it as deprecated
  there. If neither compiles, the SDK predates 9.4.0; say so, and the upgrade is the publisher's,
  through **Network Manager**.
- **CCPA and COPPA are the same on both branches** (SDK 9.4.0+): `SetCCPA(true)` when the user opted
  out of data sale, `SetCOPPA(true)` for a child-directed app.
- **iOS needs App Tracking Transparency regardless of any of the above.** The request resolves before
  `LevelPlay.Init()`: `reference/ios-setup.md`.

Code for both branches, network keys, consent UI and the older `LevelPlay.SetConsent(bool)`:
`reference/privacy-settings.md`.

## 7. Initialize once, early, with the callbacks already subscribed

Re-read `packages-lock.json` (§3); confirm resolution ran clean (§4), the App Key is in hand and AdMob
keys are entered if AdMob is in the waterfall (§5). If one is missing, name it and go back rather than
generate code that cannot work. Four rules:

- **Subscribe before `Init()`.** Both `OnInitSuccess` and `OnInitFailed`; "callbacks never fire" is
  almost always a late subscription.
- **`DontDestroyOnLoad`, initialize once.** A second scene re-running `Init()` is not a fresh start.
- **Create ad objects inside `OnInitSuccess`**, not in the same `Start()`.
- **Set the App Key in the Inspector**: a component added at runtime never receives its
  `[SerializeField]` value, so its key is empty.

The `LevelPlayInitializer` template, its four placements (the publisher's call), `Init(appKey, userId)`,
`SetSegment`, `SetDynamicUserId`, `SetPauseGame`, `SetAdaptersDebug`, error codes:
`reference/initialization-api.md`. **If ATT was set up in §6, the iOS coroutine initializer replaces
this template rather than sitting beside it.**

## 8. The optimisation goal picks the format mix

Ask once, before building any format, whether the game optimises for **revenue**, **user experience**
or **balanced**; record it, since it picks the formats and their order. Undecided means balanced: say
so, and let them move once they have seen the options. **Bid floors** (a minimum CPM per ad unit:
higher average eCPM, lower fill) are optional and usually wait for real dashboard data; per format via
`Config.Builder().SetBidFloor(...)`, the plain constructor otherwise. Mix per goal, placements,
frequency code: `reference/ad-strategy.md`.

## 9. Ad units

Per format: `reference/rewarded-api.md`, `reference/interstitial-api.md`, `reference/banner-api.md`;
shared payload types: `reference/ad-callbacks.md`. Across all three:

- **`MonoBehaviour`, attached to the same persistent GameObject as the initializer.**
- **Subscribe on creation, unsubscribe in `OnDestroy()`**; banner and interstitial also call
  `DestroyAd()` there to release the native ad.
- **Rewarded and interstitial check `IsAdReady()` before `ShowAd()`.** Banner has no `IsAdReady()`;
  it is showable once `OnAdLoaded` fires.
- **If the game uses dashboard placements, also check the static `IsPlacementCapped(placementName)`.**
  A capped placement fails with 524 or 526.
- **Never block progression on an ad.** Advance the player, then show opportunistically.

The trap that costs the most time: **the rewarded format does not load itself.** Legacy IronSource
rewarded video loaded on its own, so migrated code has no `LoadAd()` to translate. Add an explicit
trigger; an always-ready preload (`LoadAd()` after subscribing, again in `OnAdClosed`) is a choice.

## 10. Impression-level revenue forks the same way §6 does

ILRD forwards per-impression revenue to analytics or attribution. **9.5.0+:** `OnAdImpressionDataReady`
on each ad object as it is created; the global event is deprecated there and warns, so the initializer
gets nothing. **9.4.x and earlier:** `LevelPlay.OnImpressionDataReady`, one global event, subscribed
once **before** `LevelPlay.Init()`.

**The callback runs on a background thread.** Touching Unity APIs from it is the crash; queue the data
for the main thread. `Revenue` is nullable (some networks omit it). Mock ads produce no impression
data: only a device build confirms it. Payload, forwarding, per-branch wiring: `reference/ilrd-api.md`.

## 11. Testing: mock ads first, Test Suite before release

**Mock ads** cover the Editor happy path, no dashboard needed, **provided the active build target is
Android or iOS** (§2). They fire `OnAdLoaded`, `OnAdDisplayed`, `OnAdRewarded` and `OnAdClosed`, never
the load-failure, display-failure, click, expand/collapse or impression callbacks: error handling is
untested until a device. **The Test Suite** checks real networks on a device; two lines on the existing
initializer:

```csharp
LevelPlay.SetMetaData("is_test_suite", "enable");   // before LevelPlay.Init()
LevelPlay.LaunchTestSuite();                        // inside OnInitSuccess
```

Order is the whole trick: `SetMetaData` after `Init` and the suite silently never launches. It needs a
**Development Build** on device (or the SDK's logs are invisible) and the production App Key; on the
iOS coroutine initializer `SetMetaData` goes at the top of `InitializeLevelPlay()`, not in `Start()`.
**Both lines come out before release.** Details: `reference/testing-and-validation.md`.

## 12. Before release

The release checklist closes `reference/testing-and-validation.md`. Artifact size, ABIs and merged
permissions before and after the SDK: `unity-android-release`.

## Scope — what this skill does NOT do

Everything the SDK does to the **shipped artifact and the store listing** is `unity-monetization`:
manifest-merge additions, the `com.google.android.gms.permission.AD_ID` declaration, data-safety and
privacy-nutrition disclosures, iOS ATT as a submission requirement, and Gradle or CocoaPods version
conflicts between two SDKs pulling the same transitive dependency. Reading any of that back off the
built APK or AAB (permissions, size, ABIs) is `unity-android-release`.

In-app purchases are `unity-iap`, including an ad SDK and a billing SDK colliding in one build.
Server-side reward verification, the backend a rewarded server-to-server callback talks to, and where
currency is actually granted are `unity-live-services`.

Not covered: dashboard mediation strategy (waterfall, instance setup, bidder onboarding), ad
network account setup, revenue forecasting. This skill stops where the SDK's API surface stops.

## Reference

By section: `reference/migration-sdk-9.md` (§1), `reference/dependency-resolution.md` (§4),
`reference/initialization-api.md` (§5, §7), `reference/privacy-settings.md` and `reference/ios-setup.md`
(§6), `reference/ad-strategy.md` (§8), `reference/rewarded-api.md`, `reference/interstitial-api.md`,
`reference/banner-api.md`, `reference/ad-callbacks.md` (§9), `reference/ilrd-api.md` (§10),
`reference/testing-and-validation.md` (§11, §12). Failures by shape: `reference/troubleshooting.md`.
