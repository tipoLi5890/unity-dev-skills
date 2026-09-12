# UniPay — there is usually nothing to convert

For a project with UniPay (FLOBUK) installed where someone has asked to migrate, convert or upgrade
IAP. **This path performs no conversion.** It establishes the project's state and then stops, one of
three ways.

The reason is structural: UniPay already sits on `com.unity.purchasing` for the App Store, Google
Play and Amazon. Converting it to Unity IAP means removing a layer that is already using the thing
it would be converted to. Its other backends — Steam, Meta Quest, PayPal, Facebook Instant Games —
are its own plugins, and Unity IAP has no equivalent for any of them.

| Outcome | When |
|---|---|
| Unsupported platform — stop | Steam, Meta Quest, PayPal or Facebook Instant Games in the project |
| Upgrade required — stop | UniPay present with Unity IAP v4 |
| Nothing to do | UniPay 6.2.0+ with Unity IAP v5 |

## 1. Versions

**UniPay**, in this order:

1. `Assets/Plugins/UniPay/package.json` — the `version` field.
2. `Assets/Plugins/SIS/package.json` — the older path, from when it was called Simple IAP System.
3. `Assets/Plugins/UniPay/Scripts/IAPManager.cs`, or any file with a version constant.
4. `ProjectSettings/ProjectSettings.asset`, for a `UniPay` or `SIS` key.

If none of those resolve, that is not a stop — say so and carry on with the version unknown:

> UniPay is installed but its version could not be determined from the project. Check
> **Edit > Project Settings > UniPay In-App Purchasing** and confirm whether it is 6.2.0 or later.

**Unity IAP** — the `com.unity.purchasing` entry in `Packages/manifest.json`. A `4.` and a `5.` route
differently below; absent is unexpected, because UniPay depends on it — report the missing
dependency and stop.

## 2. Platforms

Read the enabled build targets from `ProjectSettings/ProjectSettings.asset`, and scan
`Assets/**/*.cs` and `Assets/Plugins/` for integration signals:

| Signal | Platform |
|---|---|
| `Steamworks|SteamManager|SteamAPI|com\.rlabrecque\.steamworks` | Steam |
| `OculusSDK|OVRManager|com\.oculus|Meta Quest|com\.unity\.xr\.oculus` | Meta Quest |
| `PayPal|PayPalManager|PAYPAL` | PayPal |
| `FacebookSDK|FB\.Init|com\.facebook\.sdk` | Facebook Instant Games |

Each of those is billed through UniPay's own plugin, and **Unity IAP has no equivalent for any of
them.** Any hit is a blocker.

## 3. Route

First match wins.

### A — an unsupported platform is in the project

> This project uses UniPay's [platform] integration, and Unity IAP has no [platform] billing backend
> to migrate it to. Nothing has been changed.
>
> Keeping [platform] billing means keeping UniPay. If [platform] support is being dropped anyway,
> remove that platform's UniPay integration first, then come back.

Name every unsupported platform found, not just the first. Change nothing.

### B — Unity IAP v4 underneath

Whatever the UniPay version:

> This project runs UniPay on Unity IAP v4. UniPay 6.2.0 and later require Unity IAP v5 and Unity 6.
>
> Three upgrades have to happen before any IAP work:
> 1. The Editor, to the latest stable Unity 6.
> 2. `com.unity.purchasing`, to the latest stable v5, through **Window > Package Manager**.
> 3. UniPay, to 6.2.0 or later — from the Asset Store, following FLOBUK's upgrade instructions.
>
> Come back once all three are done.

No code changes, no package changes. The three versions in that report follow FLOBUK's stated
requirement.

### C — UniPay 6.2.0+ on Unity IAP v5

Also the route when the UniPay version could not be read but IAP v5 is confirmed. Read the exact
`com.unity.purchasing` version out of `Packages/manifest.json` and put it in the report.

**On 5.0–5.3:**

> UniPay [version] is running on Unity IAP [version] as its billing layer. There is no migration to
> perform — UniPay already is the IAP layer.
>
> One thing to note for later: a third-party payment provider (Stripe, Coda) needs
> `com.unity.purchasing` 5.4 or later. If that is on the roadmap, the package upgrade comes first.
>
> To add products, change purchase logic or handle platform-specific billing, work inside UniPay's
> own API. Removing UniPay and using Unity IAP directly is a manual refactor — ask for it
> specifically, and say which UniPay features are being replaced.

**On 5.4 or later:** the same, without the upgrade note.

Change nothing. This is an informational stop, and it is the correct outcome, not a failure to act.
