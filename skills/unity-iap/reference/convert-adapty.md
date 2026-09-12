# Adapty → Unity IAP: assess first, convert second

For a project with the Adapty SDK installed where the user wants to stop using it. Not for adding
Unity IAP alongside Adapty for some other purpose.

Adapty has its own native Swift and Kotlin SDKs talking to StoreKit and BillingClient directly. It
is not a wrapper around Unity IAP, so nothing here is a swap. The work is an assessment: what the
project actually uses Adapty for, and what of that Unity IAP can carry.

| Case | When | Ending |
|---|---|---|
| 1 | Already in observer mode with IAP 5 | Report, change nothing |
| 2 | An Adapty-only feature is in use | Report the limits, offer two choices |
| 3 | Neither | Offer two conversion paths |

Collect every finding before routing.

## 1. Is it already observing?

**Unity IAP present** — `com.unity.purchasing` at a `5.` version in `Packages/manifest.json`.

**Observer mode configured** — `Assets/**/*.cs`:

```
Adapty\.Activate.*observerMode|observerMode\s*=\s*true|AdaptyProfileParameters|ReportTransaction
```

and any class implementing `AdaptyObserverModeDelegate`.

Both true → **Case 1**.

## 2. Which features would be lost

Search `Assets/**/*.cs`, `*.prefab`, `*.unity`, and record everything.

**Remote paywalls / Paywall Builder**

```
GetPaywall|PaywallView|AdaptyUI|AdaptyPaywall|GetPaywallForDefaultAudience|ShowPaywall|PresentCodeRedemptionSheet
```

plus `adapty-ui` or `AdaptyUI` among the imported packages. Paywall Builder changes layouts and copy
without an app update; Unity IAP has no remote paywall, so all of it becomes code and each change
becomes a release.

> **Paywall Builder is also unavailable in Adapty's own observer mode.** So the "keep Adapty,
> partially migrate" option does not preserve it either. Anyone reaching for observer mode to keep
> their paywalls should be told this before they choose.

**A/B testing**

```
variationId|GetPaywall.*audience|LogShowPaywall|LogStartCheckout
```

Server-side experiments on layout and price. Unity IAP has none, and in Adapty's observer mode A/B
testing stops being automatic and becomes manual instrumentation.

**Cross-platform entitlement**

```
Adapty\.Identify|Adapty\.Profile|AdaptyProfile|accessLevels|isActive
```

`Adapty.Identify` with a customer user ID means Adapty is the source of truth for who owns what
across stores. Unity IAP has no cross-platform entitlement layer — an iOS purchase does not follow
the player to Android without a server you build.

**Webhook-driven backend events**

```
webhook|SubscriptionCancelled|BillingIssue|AccessLevelUpdated
```

Ask as well: does the backend receive Adapty webhooks for renewals, cancellations or billing
problems? Unity IAP emits no server-side lifecycle events.

**Third-party analytics integrations**

```
AdaptyAttributionNetwork|UpdateAttribution|SetFallbackPaywalls|Amplitude|Mixpanel|AppsFlyer|Adjust
```

Adapty forwards purchase and paywall events onward by itself. Unity IAP has no integration layer —
every event becomes manual instrumentation.

## 3. Native billing alongside

`Assets/**/*.cs` for `AndroidJavaObject|AndroidJavaClass|BillingClient|BillingManager|GoogleBilling`,
and `Assets/Plugins/Android/**/*.java`, `*.kt` for `com\.android\.billingclient`.

Custom native billing beside Adapty is unusual. Flag it: it will fight Unity IAP for the listener at
runtime and has to be removed or replaced as part of the conversion. Live rather than scaffolding
makes it a blocker.

## 4. Routing

```
Native BillingClient            → Case 2, as an additional blocker
Any feature from step 2         → Case 2
Nothing                         → Case 3
```

## Case 1 — already observing

> Unity IAP 5 is installed and Adapty is already in observer mode. Unity IAP runs the transactions
> and Adapty validates and tracks them server-side through `ReportTransaction`.
>
> Removing Adapty entirely is a different job — ask for it specifically and it routes to a full
> removal assessment.

Change nothing.

## Case 2 — Adapty-only features in use

List every one, with its consequence, then two options:

> These Adapty features are in use and have no Unity IAP equivalent:
>
> - **Remote paywalls / Paywall Builder** — layouts and copy become hardcoded. Note that observer
>   mode does not preserve this either.
> - **A/B testing** — no equivalent, and in observer mode it needs substantial manual
>   instrumentation.
> - **Cross-platform entitlement** — an iOS purchase will not carry to Android without your own
>   server.
> - **Webhook-driven backend events** — no server-side lifecycle events; you would be building that
>   tracking.
> - **Third-party analytics forwarding** — each event becomes manual.
>
> Two options:
>
> **(a) Stop here.** Keep Adapty. Nothing is changed.
>
> **(b) Move to observer mode plus Unity IAP anyway.** Unity IAP takes the transactions; Adapty drops
> to observer mode for validation and lifecycle. Accepted: Paywall Builder stops working and
> replacement UI has to be built in Unity, each feature above is lost as described, and the
> BillingClient Gradle conflict has to be resolved.

(a) ends it. (b) continues into Path A, with the accepted consequences at the top of the report.

## Case 3 — no blockers

> No blockers found — Adapty is only handling basic purchase initiation and receipts. Two paths:
>
> **(a) Observer mode plus Unity IAP.** Unity IAP runs the transactions; Adapty stays, receiving
> `ReportTransaction` for validation and lifecycle. Lower risk — the webhooks and analytics keep
> working.
>
> **(b) Full removal.** Unity IAP alone. You lose server-side validation, lifecycle tracking and
> analytics; any Adapty paywall UI needs replacing. Simpler, and no subscription fee.

### Path A — observer mode

1. **Install Unity IAP** if absent — §1 of
   [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md).

2. **Untangle the BillingClient dependency.** Both SDKs bring one. Unity IAP declares
   `com.android.billingclient:billing:9.0.0` through
   `Plugins/UnityPurchasing/Android/IAPResolver/IAPAndroidDependencies.cs`. Read the declared
   version out of that file in the project before writing any exclusion.

   > **A project-wide `configurations.all { exclude group: 'com.android.billingclient' }` in
   > `mainTemplate.gradle` is the wrong fix.** It removes Unity IAP's own BillingClient as well as
   > Adapty's, and the Android build ends up with no billing library.

   Remove only Adapty's: delete the
   `<androidPackage spec="com.android.billingclient:billing:..."/>` entry from Adapty's dependency
   XML (typically under `Assets/Adapty/Editor/`), or, after a Force Resolve, delete the
   Adapty-contributed `billing-*.aar` from `Assets/Plugins/Android/` and keep Unity IAP's. Then
   **Assets > External Dependency Manager > Android Resolver > Delete Resolved Libraries**, then
   **Force Resolve**.

3. **Turn observer mode on.** Confirm the configuration shape against the Adapty version installed in
   this project before writing it — the same habit as step 2.

   ```csharp
   var config = new AdaptyConfig("YOUR_PUBLIC_SDK_KEY")
   {
       ObserverMode = true
   };
   Adapty.Activate(config);
   ```

4. **Build the Unity IAP purchase flow** — [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md),
   with the catalogue taken from the existing `GetPaywall` calls or the product ID strings already in
   the code.

5. **Report every confirmed transaction.** In `OnPurchasePending`, once the grant is saved:

   ```csharp
   Adapty.ReportTransaction(pendingOrder.Info.TransactionID, null, (error) =>
   {
       if (error != null) Debug.LogWarning($"Adapty ReportTransaction failed: {error}");
   });
   ```

   On Android, also call `Adapty.RestorePurchases` at startup to pick up anything Adapty missed.

6. **Report**: files changed, the Gradle conflict resolved and how, where observer mode is set, where
   `ReportTransaction` is called, and the manual checks — sandbox purchases appearing in the Adapty
   dashboard, and confirmation that nothing still depends on Paywall Builder.

### Path B — full removal

1. **Extract the catalogue** — product ID strings, `GetPaywall` and `GetPaywallForDefaultAudience`
   calls.
2. **Find the paywall UI** — `AdaptyUI`, `PaywallView`, `ShowPaywall`. Every one of those views has
   to be rebuilt as Unity UI wired to `Buy(productId)`. Say this before removal starts: it is
   usually the largest single piece of work, and it is UI work, not billing work.
3. **Build Unity IAP** from the extracted catalogue, in full.
4. **Strip the SDK from the code** — `using Adapty;` and every `Adapty.*` call. Purchase calls map to
   the new manager; paywall presentation calls have nothing to map to and are replaced by the new
   shop UI.
5. **Remove the package** — delete the imported Adapty assets (typically `Assets/Adapty/`) and any
   dependency files it registered.
6. **Force Resolve** afterwards.
7. **Report**: files changed and references removed, every product ID confirmed preserved, the
   paywall replacement either done or listed as an open TODO, and the manual checks — no orphaned
   Gradle entries, and a sandbox purchase working end to end on Unity IAP.
