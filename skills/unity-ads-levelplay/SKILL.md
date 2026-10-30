---
name: unity-ads-levelplay
description: >-
  LevelPlay ad mediation: rewarded, interstitial, banner, consent, ad revenue,
  IronSource migration.
---

# unity-ads-levelplay — the resolved version decides everything downstream

> **Read `Packages/packages-lock.json` before you write a line of ad code.** Only it says whether the
> package is really installed (if not, every LevelPlay symbol is a `CS0246`) and **which SDK version
> resolved**, which picks the GDPR call and the impression-revenue event. Code written against the
> wrong half of that fork looks correct and is wrong.

## Start here — symptom → where to look

| Symptom | Go to |
|---|---|
| Adding ads through LevelPlay: "set up mediation", "implement rewarded ads"; new, a migration or a repair; interstitial or banner units | §1, then §3 → §9 |
| Migrating off `IronSource.Agent` or Unity Ads (Advertisement Legacy) | `reference/migration-sdk-9.md` |
| GDPR, CCPA, COPPA or iOS ATT wiring for ads | §6, `reference/privacy-settings.md`, `reference/ios-setup.md` |
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
| Any other failure, by its shape | `reference/troubleshooting.md` |
| Permissions or store declarations changed by the SDK | `unity-live-services` → `reference/monetization.md` |

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

The `com.unity.services.levelplay` version in `Packages/packages-lock.json` picks **9.4.x or
9.5.0+**, the fork §6 and §10 branch on (older floors sit in the references); where a reference and
the package disagree, believe the package. In an Editor session a **null**
`PackageInfo.FindForAssetPath("Packages/com.unity.services.levelplay/package.json")` means it is
not installed.

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

Package Manager calls it **Ads Mediation** (Unity Registry), id `com.unity.services.levelplay` —
not **Ads IAP Mediation Adaptor**, not **Advertisement Legacy**. The publisher installs it,
accepting the **Mobile Dependency Resolver** import (§4). **The gate: no LevelPlay code until the
id appears in `Packages/packages-lock.json` with a concrete version** — absent from `manifest.json`,
the install never happened; in the manifest but not the lock, not resolved yet. Say which, and
stop; **never write the lock entry by hand**. Report the resolved version from the file and
re-read it at §7. **Ads Mediation > Network Manager** adds adapters and shows the SDK version.
In full: `reference/package-gate.md`.

## 4. Native dependencies, or the build fails after the code compiles

UPM does not fetch LevelPlay's native Android and iOS libraries; a dependency manager does: Mobile
Dependency Resolver (MDR), Unity External Dependency Manager (UEDM) or EDM4U. Skip it and you get the
signature failure: **clean compile in the Editor, Gradle or CocoaPods error at build time.** Run
`reference/dependency-resolution.md` (Custom Main Gradle Template included) for **every** shipped
platform. The API 33+ `com.google.android.gms.permission.AD_ID` declaration is
`unity-live-services` → `reference/monetization.md`.

## 5. App Key, ad unit ids, AdMob keys

The **App Key** (**Apps** → your app, needed for §7) and one **ad unit id** per format (**Ad units** →
your app, §9) come from the dashboard at <https://platform.ironsrc.com/>. **AdMob as a mediated network
needs its own keys** under **Ads Mediation > Developer Settings > LevelPlay Mediation Settings**.
Details, and a missing **Ads Mediation** menu: `reference/initialization-api.md`.

## 6. Privacy settings run before `Init()`, and the GDPR call forks by version

Technical wiring, not legal advice; every `LevelPlayPrivacySettings` call runs **before**
`LevelPlay.Init()`, or it is silently late. **GDPR, by the version read in §3:** 9.5.0+
`SetGDPRConsent(bool)`; 9.4.x `SetGDPRConsents(Dictionary<string, bool>)` per adapter — current
there, `[Obsolete]` only from 9.5.0; neither compiling means an SDK before 9.4.0 (the publisher
upgrades through **Network Manager**). **CCPA and COPPA** are the same on both: `SetCCPA(true)` on
an opt-out of sale, `SetCOPPA(true)` for a child-directed app. **iOS ATT** resolves before `Init()`
regardless (`reference/ios-setup.md`). Both branches' code, network keys, consent UI and the older
`LevelPlay.SetConsent(bool)`: `reference/privacy-settings.md`.

## 7. Initialize once, early, with the callbacks already subscribed

Re-read `packages-lock.json` (§3); confirm resolution ran clean (§4), the App Key is in hand and
AdMob keys are entered (§5) — if one is missing, name it and go back. **Subscribe `OnInitSuccess`
and `OnInitFailed` before `Init()`** ("callbacks never fire" is a late subscription);
**`DontDestroyOnLoad`, initialize once**; **create ad objects inside `OnInitSuccess`**; **set the
App Key in the Inspector** (a component added at runtime never gets its `[SerializeField]` value).
The `LevelPlayInitializer` template, its placements, `Init(appKey, userId)`, `SetSegment`,
`SetDynamicUserId`, `SetPauseGame`, `SetAdaptersDebug`, error codes:
`reference/initialization-api.md`. **With ATT set up in §6, the iOS coroutine initializer
replaces this template.**

## 8. The optimisation goal picks the format mix

Ask once, before any format: **revenue**, **user experience** or **balanced** (undecided means
balanced; say so). **Bid floors** — a minimum CPM per ad unit, higher eCPM and lower fill — are
optional and usually wait for dashboard data (`Config.Builder().SetBidFloor(...)`). Mix per goal,
placements, frequency code: `reference/ad-strategy.md`.

## 9. Ad units

Per format: `reference/rewarded-api.md`, `reference/interstitial-api.md`, `reference/banner-api.md`;
shared payload types and the rules across all three: `reference/ad-callbacks.md`. A `MonoBehaviour`
on the initializer's persistent GameObject; subscribe on creation, unsubscribe (and `DestroyAd()`
for banner and interstitial) in `OnDestroy()`; `IsAdReady()` before `ShowAd()` (banner: once
`OnAdLoaded` fires); `IsPlacementCapped` for dashboard placements (524/526); never block
progression on an ad. **The rewarded format does not load itself**: migrated IronSource code has no
`LoadAd()` to translate, so add a trigger.

## 10. Impression-level revenue forks the same way §6 does

**9.5.0+:** `OnAdImpressionDataReady` on each ad object (the global event is deprecated and the
initializer gets nothing). **9.4.x and earlier:** `LevelPlay.OnImpressionDataReady`, global,
subscribed before `Init()`. **It runs on a background thread** — queue for the main thread;
`Revenue` is nullable; mock ads produce none, so only a device build confirms it. Payload,
forwarding to Firebase / AppsFlyer / Adjust, per-branch wiring: `reference/ilrd-api.md`.

## 11. Testing: mock ads first, Test Suite before release

**Mock ads** cover the Editor happy path with no dashboard, **only with Android or iOS as the
build target** (§2), and fire `OnAdLoaded`, `OnAdDisplayed`, `OnAdRewarded`, `OnAdClosed` — never
the failure, click, expand/collapse or impression callbacks. **The Test Suite** checks real
networks on a Development Build with the production App Key:
`LevelPlay.SetMetaData("is_test_suite", "enable")` **before** `Init()` (at the top of
`InitializeLevelPlay()` on the iOS coroutine initializer), `LevelPlay.LaunchTestSuite()` inside
`OnInitSuccess`; after `Init` it silently never launches. **Both lines come out before release.**
Details: `reference/testing-and-validation.md`.

## 12. Before release

The release checklist closes `reference/testing-and-validation.md`. Artifact size, ABIs and merged
permissions before and after the SDK: `unity-android-release`.

## Scope — what this skill does NOT do

- **The shipped artifact and the store listing** — manifest-merge additions, the `AD_ID`
  permission, data-safety and privacy-nutrition disclosures, ATT as a submission requirement,
  Gradle or CocoaPods conflicts between two SDKs: `unity-live-services` → `reference/monetization.md`;
  reading permissions, size and ABIs off the built APK or AAB: `unity-android-release`.
- **In-app purchases**, an ad SDK and a billing SDK colliding included: `unity-iap`. Server-side
  reward verification and where currency is granted: `unity-live-services`.
- **Not covered:** dashboard mediation strategy (waterfall, instances, bidders), ad network
  accounts, revenue forecasting. This skill stops where the SDK's API surface stops.
