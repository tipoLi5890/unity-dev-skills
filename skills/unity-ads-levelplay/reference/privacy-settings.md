# Privacy and regulation settings

Technical wiring for GDPR, CCPA and COPPA through `LevelPlayPrivacySettings`. Which of them applies
to a given app depends on its audience, its data practices and where it is distributed — that is a
question for counsel, not for this file. Unity's
[regulation settings](https://docs.unity.com/en-us/grow/levelplay/sdk/unity/regulation-advanced-settings)
page is the authority for the API surface.

> **Every call here has to precede `LevelPlay.Init()`.** Applied afterwards they do not retroactively
> govern the session, and nothing complains. This is the single rule the whole file rests on.

Current APIs need SDK 9.4.0 or later. Below that, only the superseded calls at the bottom exist.

## The three calls, by version

| Regulation | SDK 9.5.0+ | SDK 9.4.x | Applies to |
|---|---|---|---|
| **GDPR** | `LevelPlayPrivacySettings.SetGDPRConsent(bool)` | `LevelPlayPrivacySettings.SetGDPRConsents(Dictionary)` | EU users; explicit consent required |
| **CCPA** | `LevelPlayPrivacySettings.SetCCPA(true)` | `LevelPlayPrivacySettings.SetCCPA(true)` | California residents opting out of data sale |
| **COPPA** | `LevelPlayPrivacySettings.SetCOPPA(true)` | `LevelPlayPrivacySettings.SetCOPPA(true)` | Apps directed at children under 13 |

Only GDPR forks. CCPA and COPPA are stable across both branches.

## GDPR

Read the installed version (**Ads Mediation > Network Manager**, or the resolved version in
`Packages/packages-lock.json`) before choosing.

**9.5.0 and later — one boolean, all networks:**

```csharp
using Unity.Services.LevelPlay;

// true = consent granted; false = no consent, non-personalised ads only
LevelPlayPrivacySettings.SetGDPRConsent(true);
```

**9.4.x — one entry per installed network:**

```csharp
using Unity.Services.LevelPlay;
using System.Collections.Generic;

LevelPlayPrivacySettings.SetGDPRConsents(new Dictionary<string, bool> {
    { "UnityAds", true },
    { "IronSource", true }
});
```

> **The dictionary form is not a legacy API on 9.4.x — it is *the* API there.** `SetGDPRConsent(bool)`
> arrives in 9.5.0; the dictionary becomes `[Obsolete]` at the same moment. Telling a 9.4.x publisher
> their current call is deprecated sends them chasing a member that does not exist in their package.
> The direction of the advice depends entirely on which version resolved.

Neither one compiling means the installed SDK predates 9.4.0 — upgrade through **Network Manager**,
or fall back to `LevelPlay.SetConsent(bool)` (see below) if the upgrade is not possible.

### Network keys for `SetGDPRConsents`

One entry per adapter actually installed; entries for absent networks do nothing.

| Key | Network |
|---|---|
| `UnityAds` | Unity Ads |
| `AdMob` | Google AdMob |
| `AppLovin` | AppLovin |
| `APS` | Amazon Publisher Services |
| `BidMachine` | BidMachine |
| `Bigo` | Bigo Ads |
| `Chartboost` | Chartboost |
| `Facebook` | Meta Audience Network |
| `Fyber` | Digital Turbine (Fyber) |
| `HyprMx` | HyprMX |
| `InMobi` | InMobi |
| `Line` | LINE Ads |
| `Mintegral` | Mintegral |
| `MobileFuse` | MobileFuse |
| `Moloco` | Moloco |
| `MyTarget` | myTarget |
| `Ogury` | Ogury |
| `Pangle` | Pangle (TikTok) |
| `PubMatic` | PubMatic |
| `Smaato` | Smaato |
| `SuperAwesome` | SuperAwesome |
| `Verve` | Verve |
| `Voodoo` | Voodoo |
| `Vungle` | Vungle |
| `Yandex` | Yandex Ads |
| `YSO` | YSO |

### Consent flow shape

The structural point in the code below is that **initialization is deferred until the answer is
known**. A consent dialog that returns after `Init()` has already run is decoration.

```csharp
using UnityEngine;
using Unity.Services.LevelPlay;

public class GDPRConsentManager : MonoBehaviour
{
    [SerializeField] private string appKey;

    void Start()
    {
        if (IsUserInGDPRRegion())
            ShowConsentDialog();      // initialization waits for OnConsentReceived
        else
            InitializeLevelPlay();
    }

    private bool IsUserInGDPRRegion()
    {
        // Region detection is yours: IP geolocation, device locale, or a consent-management platform.
        return false;
    }

    private void ShowConsentDialog()
    {
        // Your consent UI. Call OnConsentReceived(bool) when the player answers.
    }

    private void OnConsentReceived(bool userConsented)
    {
        PlayerPrefs.SetInt("GDPR_Consent", userConsented ? 1 : 0);
        PlayerPrefs.Save();

        LevelPlayPrivacySettings.SetGDPRConsent(userConsented);   // before Init
        InitializeLevelPlay();
    }

    private void InitializeLevelPlay()
    {
        LevelPlay.OnInitSuccess += OnInitSuccess;
        LevelPlay.OnInitFailed += OnInitFailed;
        LevelPlay.Init(appKey);
    }

    private void OnInitSuccess(LevelPlayConfiguration config)
        => Debug.Log("LevelPlay initialized with GDPR consent applied");

    private void OnInitFailed(LevelPlayInitError error)
        => Debug.LogError($"LevelPlay init failed: {error.ErrorMessage}");
}
```

**Persist the answer and reapply it on every launch.** The consent decision belongs to the player,
not to the session; re-prompting because nothing was stored is both annoying and, in some readings,
non-compliant.

Changing consent mid-session is allowed — `SetGDPRConsent(false)` after a revocation applies to
subsequent ad requests. Already-loaded ads are unaffected.

## CCPA

```csharp
using Unity.Services.LevelPlay;

LevelPlayPrivacySettings.SetCCPA(true);   // player opted out of data sale
```

`true` restricts collection; `false` is the default. Wire it to whatever settings toggle exposes the
opt-out, save the choice, and reapply before `Init()` on the next launch:

```csharp
public void OnUserToggleCCPAOptOut(bool optOut)
{
    PlayerPrefs.SetInt("CCPA_OptOut", optOut ? 1 : 0);
    PlayerPrefs.Save();
    LevelPlayPrivacySettings.SetCCPA(optOut);
}
```

## COPPA

```csharp
using Unity.Services.LevelPlay;

LevelPlayPrivacySettings.SetCOPPA(true);  // app is directed at children under 13
```

This is a property of the app, not of the player, so it is normally a constant rather than a stored
preference:

```csharp
[SerializeField] private bool isChildDirectedApp = true;

void Start()
{
    if (isChildDirectedApp)
        LevelPlayPrivacySettings.SetCOPPA(true);

    LevelPlay.OnInitSuccess += OnInitSuccess;
    LevelPlay.OnInitFailed += OnInitFailed;
    LevelPlay.Init(appKey);
}
```

The flag is one piece of a child-directed release, not the whole of it: non-personalised ads only,
Google Play Families requirements if shipping there, age ratings in both stores, and a privacy policy
that states what is collected from children. The store-facing half is `unity-monetization`.

## All three together

Order matters only in that everything precedes `Init()`. The branch worth copying is the GDPR one —
when consent has not yet been obtained, the method **returns without initializing** and the dialog's
callback resumes the sequence:

```csharp
void Start()
{
    if (isChildDirectedApp)
        LevelPlayPrivacySettings.SetCOPPA(true);

    if (IsUserInGDPRRegion())
    {
        if (HasStoredGDPRConsent())
        {
            LevelPlayPrivacySettings.SetGDPRConsent(LoadGDPRConsent());
        }
        else
        {
            ShowGDPRConsentDialog();
            return;                     // Init happens in the dialog's callback
        }
    }

    if (IsUserInCalifornia() && LoadCCPAOptOut())
        LevelPlayPrivacySettings.SetCCPA(true);

    InitializeLevelPlay();
}
```

## Superseded calls

These still compile in places but are marked obsolete in the SDK. Recognise them in existing code and
replace them; do not write new ones.

```csharp
LevelPlay.SetConsent(true);                            // → SetGDPRConsent / SetGDPRConsents
LevelPlay.SetMetaData("do_not_sell", "true");          // → SetCCPA(true)
LevelPlay.SetMetaData("is_child_directed", "true");    // → SetCOPPA(true)
```

`LevelPlay.SetConsent(bool)` is the one exception worth keeping in mind: on an SDK older than 9.4.0
it is the only GDPR API available, so it is the correct answer for a publisher who genuinely cannot
upgrade.

## Verifying

There is no getter — nothing reads a privacy setting back. What you can check:

- The SDK's own console output after `Init()`, on a development build, mentions the applied settings.
- Consent granted vs denied changes what fills. Denied should still serve non-personalised ads, at a
  lower rate.
- The stored preference survives a relaunch and is reapplied before `Init()` — this is the one that
  regresses quietly, because the first session always looks right.

## Further reading

- [LevelPlay documentation](https://docs.unity.com/en-us/grow/levelplay)
- [GDPR overview](https://gdpr.eu/)
- [CCPA](https://oag.ca.gov/privacy/ccpa)
- [COPPA rule](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa)
- [Google Play Families policy](https://support.google.com/googleplay/android-developer/answer/9893335)
