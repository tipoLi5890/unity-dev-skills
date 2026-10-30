---
name: unity-iap
description: >-
  Unity In-App Purchasing v5: catalogue, purchase flow, receipts, restore,
  subscriptions, v4 code.
---

# unity-iap — a purchase is not yours until you answer it

> **Every v5 purchase arrives as a question.** The store hands you a `PendingOrder`; you grant the
> content, save it, and only then answer with `ConfirmPurchase`. A question you never answer comes
> back on the next launch — which is the safe failure. A question you answer before the grant is
> saved is money the player spent on nothing, and the store will not ask again.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| "add IAP to this game"; deciding what to do at all — existing SDK, native bridge, v4, nothing | `reference/pre-check.md`, then *The working contract* |
| Converting a native BillingClient or StoreKit bridge, or a third-party billing SDK | `reference/pre-check.md` routes to the `path-convert-*` / `convert-*` file |
| `OnStoreConnectionFailed` or `product.hasReceipt` does not compile | §8 — shapes that do not exist |
| Products list is empty, or prices are stale | §2 |
| The same purchase is granted twice | §3 |
| A purchase re-appears on every launch | §3 — it was never confirmed |
| Player paid, got nothing | §3 — confirmed before the grant was saved |
| Ask-to-Buy purchases never arrive | §1 — `OnPurchaseDeferred` was not subscribed |
| Non-consumables lost after reinstall | §4 |
| Apple receipt validates to an empty array | §5 |
| `IsSubscribed()` will not cast to `bool` | §6 |
| `CS1061` on a failure description | §7 |
| `IStoreListener` / `ConfigurationBuilder` code | `reference/migration-v4-to-v5.md` |
| Apple promotions, Ask-to-Buy simulation, Google subscription upgrades | `reference/platform-notes.md` |
| `Assets/Resources/IAPProductCatalog.json` edits, codeless race | `reference/codeless-catalog.md` |
| A third-party payment provider: Stripe / Coda / webshop checkout | `reference/path-implement-iap-d2c.md` |

## The working contract

> **Scan, then route.** Two billing systems on one device fight over the same callback slot and one
> of them silently loses purchases, so the first job is finding out what is already there:
> third-party SDK, native bridge, IAP v4, IAP v5, a codeless catalogue.
> `reference/pre-check.md` is the scan and the routing table. Resolve it
> before opening any other file here, and **report what you found and where it routes before
> writing code**.

- **Never install or upgrade the package on the user's behalf.** `com.unity.purchasing` changes the
  Android dependency graph. Say which version is needed and let them do it through Package Manager.
- **Never change a product ID.** IDs are the join key to App Store Connect and Play Console, and to
  every purchase already made. A renamed product is a lost purchase history.
- **Never delete an existing billing integration.** Guard its call sites behind a scripting define
  so the old path is one Player Settings edit away.
- **Package and presence.** `com.unity.purchasing` in `Packages/manifest.json` (namespaces
  `UnityEngine.Purchasing`, `.Security`); without it `UnityIAPServices` and `StoreController` do
  not resolve. 5.4 is the floor for the payment-provider and `OnAuthAccountChanged` features.

## 1. Initialization — subscribe first, connect second

IAP has its own entry point: no `UnityServices.InitializeAsync()` needed, though it coexists with
one; with Analytics initialized, transaction events are forwarded automatically.

```csharp
m_Store = UnityIAPServices.StoreController();   // or DefaultStore/DefaultProduct/DefaultPurchase
// ... every event subscribed here ...
await m_Store.Connect();                        // OnStoreConnected → FetchProducts → OnProductsFetched
```

> **`Connect()` can raise handlers before it returns.** A purchase left unconfirmed by a previous
> session is re-delivered as soon as the store connects. Subscribe in `Awake()`, before `Connect()`,
> or that re-delivery lands on nobody and the player's content is gone until the next launch.

Subscribe both halves of every asynchronous call (`reference/api-notes.md`): a missing failure
handler only logs a runtime warning, and the failure disappears.

**`OnPurchaseDeferred` has no failure twin and is easy to skip.** It carries Ask-to-Buy (a child
account waiting on a parent) and Google Play's deferred payments; unsubscribed, those purchases are
dropped without a trace. Subscribe it, show a pending state, and grant nothing — the approved
purchase arrives later through `OnPurchasePending`.

**`OnAuthAccountChanged` (v5.4+) empties both caches before it fires.** Held `Product` and `Order`
references are stale and `GetProducts()` / `GetPurchases()` return nothing inside the handler, so
re-run the fetch sequence from the start. Full initialization and the handler:
`reference/api-notes.md`.

## 2. Products — the cache and the store are two different things

| Call | What it reads |
|---|---|
| `GetProducts()` / `GetProductById(id)` | The local cache. Synchronous. Empty or stale until a fetch has landed |
| `FetchProducts(List<ProductDefinition>)` | The store. Refreshes prices and availability, then updates the cache |
| `GetPurchases()` | The cached order list |
| `FetchPurchases()` | The store, and **replaces** the cached list wholesale |

Display prices from `product.metadata.localizedPriceString` after `OnProductsFetched`, never a
hard-coded string — the store owns currency, formatting and tax.

Types are `Consumable`, `NonConsumable`, `Subscription`; per-store IDs go in `StoreSpecificIds`, a
large mapping in a `CatalogProvider` (`reference/api-notes.md`).

## 3. The two-step flow, and the three ways it goes wrong

```
PurchaseProduct(product)
  → OnPurchasePending(pendingOrder)
      → validate  → grant  → SAVE
      → ConfirmPurchase(pendingOrder)
  → OnPurchaseConfirmed(order)   // Order, not ConfirmedOrder — pattern-match it
```

**Confirm after the save, never before.** If the save fails, do not confirm. An unconfirmed order is
re-delivered on the next launch and costs the player nothing; a confirmed order that was never
persisted is unrecoverable.

**`OnPurchasePending` may fire more than once for the same purchase** — a crash between grant and
confirm guarantees it. Grant idempotently: keep a ledger of processed order IDs and skip a repeat
rather than crediting twice.

**`OnPurchaseConfirmed` receives the `Order` base type**: `ConfirmedOrder` stuck, `FailedOrder`
(with `FailureReason`, `Details`) did not — assuming success treats a failure as a sale.

**Confirmed consumables never come back.** `FetchPurchases()` returns non-consumables and
subscriptions only, so the store cannot tell you how many coin packs a player has bought. Consumable
balances are yours to persist — see `unity-live-services` for where that state belongs.

`ProcessPendingOrdersOnPurchasesFetched(false)` turns off the re-delivery that makes the flow safe;
leave it unless asked by name. The grant contract: `reference/path-add-iap-to-new-project.md` §5.

## 4. Restore, entitlement, and existing purchases

- **`RestoreTransactions(callback)` is required on iOS** — Apple's review guidelines expect a
  visible "Restore Purchases" button. Each restored purchase arrives through `OnPurchasePending`,
  so the same grant path handles it. Offer the button only when the catalogue actually contains a
  `NonConsumable` or `Subscription`.
- **Apple non-renewing subscriptions are not restorable this way.** Their ownership has to live on
  your own server.
- **`FetchPurchases()` at startup is the routine path**, and it re-delivers anything unconfirmed.
  Explicit restore is for the button.
- **`CheckEntitlement(product)` + `OnCheckEntitlement` is the ownership question** when you have a
  product but no order. Where you do hold the order, its type already answers.

Code for each, the `EntitlementStatus` values and the order-type mapping:
`reference/api-notes.md`.

## 5. Receipt validation splits by platform

| Store | Where validation happens |
|---|---|
| Google Play | Locally, with `CrossPlatformValidator(GooglePlayTangle.Data(), Application.identifier)` |
| Apple App Store | On your server, from `order.Info.Apple?.jwsRepresentation` |

> **Under StoreKit 2 the Apple half of `CrossPlatformValidator` does nothing.** It returns an empty
> array without throwing or warning, which reads as "no receipts" or, depending on the caller, as
> "valid".
> `AppleTangle.Data()` is deprecated for the same reason. On Apple, the only real check is a server
> verifying `jwsRepresentation` against Apple's App Store Server API.

Google tangle data is generated in the Editor under **Services > In-App Purchasing > Receipt
Validation Obfuscator**; it is per-project and belongs in the repo. An `IAPSecurityException` from
`Validate` means grant nothing. Both halves in code: `reference/api-notes.md`.

## 6. Subscriptions

Subscription state hangs off `order.Info.PurchasedProductInfo`, **not** off `CartItem` — a
`CartItem` carries only `Product` and `Quantity`, and reaching for `subscriptionInfo` there is a
compile error.

`IsSubscribed()` returns a `Result` (`True` / `False` / `Unsupported`), not a `bool`. Compare with
`== Result.True`: null-safe through the whole `order.Info…?.subscriptionInfo?.` chain, and
`Unsupported` — a platform that does not know — never reads as active. `?? false` does not compile.

Check subscription state at launch, not only at purchase: lapses, cancellations from the store's own
UI and refunds are not reported to your app when they happen. The access path and every state
method: `reference/api-notes.md`; platform differences in the dates:
`reference/platform-notes.md`.

## 7. Failure descriptions — four types, four spellings

Some failure-description types carry lowercase public fields alongside the PascalCase read-only
properties; where both exist, prefer the properties. Guessing across types is where `CS1061` comes
from: `StoreConnectionFailureDescription` has `.Message` and no `.reason`; `ProductFetchFailed` has
`.FailureReason` and `.FailedFetchProducts` and no `.Message`. The full table:
`reference/api-notes.md`.

## 8. What to check before you call it done

The compile is the only local gate. Then read for what still compiles or never existed:
`[Obsolete]` v4 shapes (`IStoreListener`, `ConfigurationBuilder`, `GetExtension<T>()`); names that
do not exist (`OnStoreConnectionFailed` → `OnStoreDisconnected`, `product.receipt` →
`order.Info.Receipt`, `product.hasReceipt` → `CheckEntitlement`, `pendingOrder.OrderInfo` →
`.Info`); every subscription before `Connect()`; an idempotent grant with `ConfirmPurchase` after
the save; `IsSubscribed()` compared to `Result.True`. The full list and the hand-back report:
`reference/done-checklist.md`. Sandbox testing is on the developer; nothing here proves a purchase works.

## Scope — what this skill does NOT do

| Not here | Go to |
|---|---|
| Shipping seams: what the package adds to the merged Android manifest and the Gradle or CocoaPods build, store declarations, release-build sandbox behaviour — read before you submit | `unity-live-services` → `reference/monetization.md` |
| Server-side entitlement: off-device receipt checks, the idempotent grant behind a retried request, consumable balances, the identity a purchase attaches to (this skill stops at sending `order.Info.Receipt` or `jwsRepresentation`) | `unity-live-services` |
| Environments, project linking, Editor deployment of a remote catalogue (the D2C path assumes both) | `unity-ugs` |
| Ad revenue and mediation · shop layout, price display, button states | `unity-ads-levelplay` · `unity-ui-ugui` or `unity-game-ui` |
| Pricing and monetisation design, store-side product creation, tax and compliance, a real payment | Not covered |

## Reference

`reference/pre-check.md` is read first and routes to every path file: `path-add-iap-to-new-project`
(greenfield), `migration-v4-to-v5`, `path-implement-iap-d2c`, `path-convert-native-google-billing`,
`path-convert-native-storekit`, `convert-essentialkit`, `convert-unipay`, `convert-revenuecat`,
`convert-adapty`. API, platform and catalogue references are linked above.
