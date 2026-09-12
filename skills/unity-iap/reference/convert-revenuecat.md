# RevenueCat → Unity IAP: assess first, convert second

For a project with `com.revenuecat.purchases-unity` installed where the user wants to stop using it.
Not for adding Unity IAP alongside RevenueCat for some other purpose.

RevenueCat is not a layer over Unity IAP — it drives Apple StoreKit and Google BillingClient through
its own native SDKs. So there is no swap to perform. What there is, is an assessment: which
RevenueCat features the project actually leans on, which platforms it ships to, and how much of what
RevenueCat provides Unity IAP can replace. Often the honest answer is "less than the user expects",
and saying so is the useful outcome.

Three endings, and steps 1–3 decide which:

| Case | When | Ending |
|---|---|---|
| 1 | Already in observer mode with IAP 5 | Report, change nothing |
| 2 | Amazon, or a RevenueCat-only feature in use | Report the blockers, offer two choices |
| 3 | Neither | Offer two conversion paths |

Collect every finding before routing — a report that stops at the first blocker sends the user back
around the loop.

## 1. Is it already observing?

**Unity IAP present** — `com.unity.purchasing` at a `5.` version in `Packages/manifest.json`.

**Observer mode configured** — in `Assets/**/*.cs`:

```
PurchasesAreCompletedBy\.MyApp|PurchasesAreCompletedBy\.YourApp|observerMode\s*=\s*true|SetPurchasesAreCompletedBy
```

Both true → **Case 1**. Skip the rest of the scan.

## 2. Which features would be lost

Search `Assets/**/*.cs`, `*.prefab` and `*.unity`. Record everything found, not the first hit.

**Remote paywalls and Offerings**

```
GetOfferings|Offerings|Offering\b.*revenuecat|RevenueCatUI|PaywallView|PresentPaywall
```

plus `com.revenuecat.purchases-ui-unity` in the manifest. Offerings let products and paywall layouts
change without an app update. Unity IAP has no remote paywall and no Offerings equivalent: products
live in code or a local catalogue, and changing them is a release.

**A/B testing**

```
GetCurrentOffering|Experiments|currentOffering
```

Server-side experiments on price and layout. Unity IAP has no such thing.

**Cross-platform entitlement**

```
LogIn|LogOut|Purchases\.SharedPurchases|appUserId|CustomerInfo
```

`LogIn` with a user ID is the signal that RevenueCat is the source of truth for who owns what across
devices and stores. Unity IAP has no cross-platform entitlement layer at all — each store's receipt
stands alone, and a purchase on iOS does not follow the player to Android without a server you
build.

**Webhook-driven backend events**

```
webhook|SubscriptionStatusChange|EntitlementRevoked|BillingIssue
```

And ask outright: does the backend receive RevenueCat webhooks for renewals, cancellations or
billing problems? Unity IAP emits no server-side lifecycle events. Losing them means building
subscription tracking.

**Offline entitlement caching**

```
offlineCustomerInfo|OfflineEntitlements|entitlementVerification
```

RevenueCat can serve cached entitlements through an outage. Unity IAP cannot: an unreachable store
means no entitlement state.

## 3. Platforms

**A native BillingClient alongside RevenueCat** — `Assets/**/*.cs` for
`AndroidJavaObject|AndroidJavaClass|BillingClient|BillingManager|GoogleBilling`, and
`Assets/Plugins/Android/**/*.java`, `*.kt` for `com\.android\.billingclient`. Unusual, and worth
flagging: native billing code will fight Unity IAP for the listener at runtime and has to go or be
replaced as part of the conversion. If it is live rather than scaffolding, it is a blocker.

**Amazon Appstore** — `amazon` in the manifest or lockfile;
`useAmazon|SetUseAmazon|AmazonStore|SyncAmazonPurchase` in C#; Amazon as a build target in
`ProjectSettings/ProjectSettings.asset`.

> **Amazon is a hard stop.** Unity IAP has no Amazon Appstore support. Nor does RevenueCat's
> observer mode paper over it — `syncPurchases()` does not work on Amazon builds, and syncing needs
> `syncAmazonPurchase()` with the full purchase detail. If Unity IAP is to be the only billing
> backend, Amazon support is being dropped, and that has to be said out loud.

## 4. Routing

```
Amazon                          → Case 2
Native BillingClient            → Case 2, as an additional blocker
Any feature from step 2         → Case 2
Nothing                         → Case 3
```

## Case 1 — already observing

> Unity IAP 5 is installed and RevenueCat is already in observer mode
> (`PurchasesAreCompletedBy.MyApp`). The two are co-operating as designed: Unity IAP runs the
> transactions, RevenueCat validates and tracks them server-side.
>
> Removing RevenueCat entirely is a different job — ask for that specifically and it routes to a
> full removal assessment.

Change nothing.

## Case 2 — blockers

List every one found, with its consequence spelled out, then offer exactly two ways forward:

> These block a clean conversion to Unity IAP 5:
>
> - **Amazon Appstore** — no Unity IAP support, and observer mode does not cover it either.
>   Dropping Amazon is the only path if Unity IAP is to be the sole backend.
> - **Cross-platform entitlement** (`LogIn` found) — a player who buys on iOS loses access on
>   Android unless you build the server side yourself.
> - **Remote paywalls / Offerings** — layouts and product sets become code, and changing them
>   becomes a release.
> - **Subscription webhooks** — the backend stops receiving lifecycle events; that infrastructure
>   would be yours to build.
>
> Two options:
>
> **(a) Stop here.** Keep RevenueCat. What is in use has no Unity IAP equivalent, and nothing is
> changed.
>
> **(b) Move to observer mode plus Unity IAP anyway.** Unity IAP takes the transactions on Google
> Play and the App Store; RevenueCat drops to observer mode and keeps validating and tracking. The
> accepted consequences are: Amazon billing stops, each feature above is lost as described, and the
> BillingClient Gradle conflict has to be resolved.

Choosing (a) ends it. Choosing (b) continues into Path A below, with the accepted consequences
written at the top of the report.

## Case 3 — no blockers

> No blockers found — RevenueCat is being used for the basic purchase flow only. Two paths:
>
> **(a) Observer mode plus Unity IAP.** Unity IAP runs the transactions; RevenueCat stays for
> server-side validation and subscription lifecycle. Lower risk — `CustomerInfo` and the webhooks
> keep working.
>
> **(b) Full removal.** Unity IAP alone. You lose RevenueCat's server-side validation, lifecycle
> tracking and analytics, and gain a simpler architecture and no subscription fee.

### Path A — observer mode

1. **Install Unity IAP** if it is not there — §1 of
   [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md).

2. **Untangle the BillingClient dependency.** Both SDKs bring one. Unity IAP declares
   `com.android.billingclient:billing:9.0.0` through
   `Plugins/UnityPurchasing/Android/IAPResolver/IAPAndroidDependencies.cs`. Open that file in the
   project and take the declared version from it before writing any exclusion.

   > **Do not add a project-wide
   > `configurations.all { exclude group: 'com.android.billingclient' }` to `mainTemplate.gradle`.**
   > That exclusion is not selective — it strips Unity IAP's own BillingClient along with
   > RevenueCat's and leaves the Android build with no billing library at all.

   Remove only RevenueCat's copy: either delete the
   `<androidPackage spec="com.android.billingclient:billing:..."/>` entry from RevenueCat's
   dependency XML (typically under `Assets/RevenueCat/Editor/`), or, after a Force Resolve, delete
   the RevenueCat-contributed `billing-*.aar` from `Assets/Plugins/Android/` and keep Unity IAP's.
   Then **Assets > External Dependency Manager > Android Resolver > Delete Resolved Libraries**,
   followed by **Force Resolve**.

3. **Put RevenueCat into observer mode.** Confirm the configuration shape against the RevenueCat
   version installed in this project before writing it — the same habit as step 2.

   ```csharp
   var config = PurchasesConfiguration.Builder.Init("your_api_key")
       .SetPurchasesAreCompletedBy(PurchasesAreCompletedBy.MyApp)
       .Build();
   Purchases.Configure(config);
   ```

4. **Build the Unity IAP purchase flow** — [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md),
   with the catalogue taken from the existing `Purchases.GetOfferings()` usage or the product ID
   strings already in the code.

5. **Sync after every confirmed purchase.** In `OnPurchasePending`, once the grant is saved:

   ```csharp
   Purchases.SharedPurchases.SyncPurchases();
   ```

   That is what registers the purchase token with RevenueCat so it can validate and update
   `CustomerInfo`. Skipping it leaves the dashboard blind.

6. **Report**: files changed, the Gradle conflict resolved and how, where observer mode is
   configured, where `SyncPurchases()` is called, and the manual check — that the RevenueCat
   dashboard shows sandbox purchases from the new build.

### Path B — full removal

1. **Extract the catalogue** — product ID strings and `GetOfferings()` calls.
2. **Build Unity IAP** from that catalogue, in full.
3. **Strip the SDK from the code** — `using RevenueCat;` and every `Purchases.*` call, replaced by
   the new manager's equivalents.
4. **Remove the packages** — `com.revenuecat.purchases-unity` and
   `com.revenuecat.purchases-ui-unity` from `Packages/manifest.json`, and the scoped registry entry
   for `com.revenuecat` if nothing else needs it.
5. **Force Resolve** afterwards, to clear the native dependencies.
6. **Report**: files changed and references removed, every product ID confirmed preserved, and the
   manual steps — retire the dashboard project if it is no longer wanted, and check the Android
   build for orphaned Gradle entries.
