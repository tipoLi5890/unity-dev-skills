---
name: unity-iap
description: >-
  Unity In-App Purchasing v5: connecting to a store, the product catalogue, the
  pending/confirm purchase flow, receipt validation, entitlement, restore and
  subscriptions. Load for: "add IAP to this game", content granted twice or not
  at all, a purchase that comes back every launch, Ask-to-Buy purchases that
  silently disappear, `OnStoreConnectionFailed` or `product.hasReceipt` not
  compiling, v4 `IStoreListener` / `ConfigurationBuilder` code, converting a
  native BillingClient or StoreKit bridge or a third-party billing SDK to
  `com.unity.purchasing`, editing `IAPProductCatalog.json`, a third-party
  payment provider. Manifest, build and store-declaration seams are
  `unity-monetization`.
---

# unity-iap — a purchase is not yours until you answer it

> **Every v5 purchase arrives as a question.** The store hands you a `PendingOrder`; you grant the
> content, save it, and only then answer with `ConfirmPurchase`. A question you never answer comes
> back on the next launch — which is the safe failure. A question you answer before the grant is
> saved is money the player spent on nothing, and the store will not ask again.

## The working contract

> **Scan, then route.** Two billing systems on one device fight over the same callback slot and one
> of them silently loses purchases, so the first job is finding out what is already there:
> third-party SDK, native bridge, IAP v4, IAP v5, a codeless catalogue.
> [`reference/pre-check.md`](reference/pre-check.md) is the scan and the routing table. Resolve it
> before opening any other file here, and **report what you found and where it routes before
> writing code**.

- **Never install or upgrade the package on the user's behalf.** `com.unity.purchasing` changes the
  Android dependency graph. Say which version is needed and let them do it through Package Manager.
- **Never change a product ID.** IDs are the join key to App Store Connect and Play Console, and to
  every purchase already made. A renamed product is a lost purchase history.
- **Never delete an existing billing integration.** Guard its call sites behind a scripting define
  so the old path is one Player Settings edit away.
- **Package and version.** `com.unity.purchasing`; namespaces `UnityEngine.Purchasing` and
  `UnityEngine.Purchasing.Security`. 5.4 is the floor for the payment-provider and
  `OnAuthAccountChanged` features below.
- **Presence check.** The `com.unity.purchasing` entry in `Packages/manifest.json`. Without the
  package neither `UnityEngine.Purchasing.UnityIAPServices` nor `UnityEngine.Purchasing.StoreController`
  resolves, and no `Purchasing` assembly is loaded.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Deciding what to do at all — existing SDK, native bridge, v4, nothing | [`reference/pre-check.md`](reference/pre-check.md) |
| Products list is empty, or prices are stale | §2 |
| The same purchase is granted twice | §3 |
| A purchase re-appears on every launch | §3 — it was never confirmed |
| Player paid, got nothing | §3 — confirmed before the grant was saved |
| Ask-to-Buy purchases never arrive | §1 — `OnPurchaseDeferred` was not subscribed |
| Non-consumables lost after reinstall | §4 |
| Apple receipt validates to an empty array | §5 |
| `IsSubscribed()` will not cast to `bool` | §6 |
| `CS1061` on a failure description | §7 |
| `IStoreListener` / `ConfigurationBuilder` code | [`reference/migration-v4-to-v5.md`](reference/migration-v4-to-v5.md) |
| Apple promotions, Ask-to-Buy simulation, Google subscription upgrades | [`reference/platform-notes.md`](reference/platform-notes.md) |
| `Assets/Resources/IAPProductCatalog.json` edits, codeless race | [`reference/codeless-catalog.md`](reference/codeless-catalog.md) |
| Stripe / Coda / webshop checkout | [`reference/path-implement-iap-d2c.md`](reference/path-implement-iap-d2c.md) |

## 1. Initialization — subscribe first, connect second

IAP has its own entry point. It does not need `UnityServices.InitializeAsync()`, and it coexists
with one when the project uses other live services; with Analytics present and initialized,
transaction events are forwarded automatically.

```csharp
m_Store = UnityIAPServices.StoreController();   // or DefaultStore/DefaultProduct/DefaultPurchase
// ... every event subscribed here ...
await m_Store.Connect();                        // OnStoreConnected → FetchProducts → OnProductsFetched
```

> **`Connect()` can raise handlers before it returns.** A purchase left unconfirmed by a previous
> session is re-delivered as soon as the store connects. Subscribe in `Awake()`, before `Connect()`,
> or that re-delivery lands on nobody and the player's content is gone until the next launch.

Subscribe both halves of every asynchronous call; the success and failure event of each is tabled
in [`reference/api-notes.md`](reference/api-notes.md). A missing failure handler is not an error —
the package logs a runtime warning and the failure disappears.

**`OnPurchaseDeferred` has no failure twin and is easy to skip.** It carries Ask-to-Buy (a child
account waiting on a parent) and Google Play's deferred payments; unsubscribed, those purchases are
dropped without a trace. Subscribe it, show a pending state, and grant nothing — the approved
purchase arrives later through `OnPurchasePending`.

**`OnAuthAccountChanged` (v5.4+) empties both caches before it fires.** Held `Product` and `Order`
references are stale and `GetProducts()` / `GetPurchases()` return nothing inside the handler, so
re-run the fetch sequence from the start. Full initialization and the handler:
[`reference/api-notes.md`](reference/api-notes.md).

## 2. Products — the cache and the store are two different things

| Call | What it reads |
|---|---|
| `GetProducts()` / `GetProductById(id)` | The local cache. Synchronous. Empty or stale until a fetch has landed |
| `FetchProducts(List<ProductDefinition>)` | The store. Refreshes prices and availability, then updates the cache |
| `GetPurchases()` | The cached order list |
| `FetchPurchases()` | The store, and **replaces** the cached list wholesale |

Nothing here is interchangeable. Display prices from `product.metadata.localizedPriceString` after
`OnProductsFetched`, never from a hard-coded string — the store owns the currency, the formatting
and the tax.

Product types are `Consumable`, `NonConsumable`, `Subscription`. A product ID that differs per store
carries `StoreSpecificIds` on its `ProductDefinition`; a mapping big enough to want its own home goes
in a `CatalogProvider`. Signatures: [`reference/api-notes.md`](reference/api-notes.md).

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

**`OnPurchaseConfirmed` receives the `Order` base type.** `ConfirmedOrder` means it stuck;
`FailedOrder` means confirmation itself failed, carrying `FailureReason` and `Details`. Code that
assumes success here will quietly treat a failure as a sale.

**Confirmed consumables never come back.** `FetchPurchases()` returns non-consumables and
subscriptions only, so the store cannot tell you how many coin packs a player has bought. Consumable
balances are yours to persist — see `unity-live-services` for where that state belongs.

`ProcessPendingOrdersOnPurchasesFetched(false)` restores v4's behaviour by turning off the automatic
re-delivery that makes the flow safe. Leave it alone unless someone asks for it by name. The grant
contract in order of work: [`reference/path-add-iap-to-new-project.md`](reference/path-add-iap-to-new-project.md) §5.

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
[`reference/api-notes.md`](reference/api-notes.md).

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
`Validate` means grant nothing. Both halves in code: [`reference/api-notes.md`](reference/api-notes.md).

## 6. Subscriptions

Subscription state hangs off `order.Info.PurchasedProductInfo`, **not** off `CartItem` — a
`CartItem` carries only `Product` and `Quantity`, and reaching for `subscriptionInfo` there is a
compile error.

`IsSubscribed()` returns a `Result` (`True` / `False` / `Unsupported`), not a `bool`. Compare with
`== Result.True`: null-safe through the whole `order.Info…?.subscriptionInfo?.` chain, and
`Unsupported` — a platform that does not know — never reads as active. `?? false` does not compile.

Check subscription state at launch, not only at purchase: lapses, cancellations from the store's own
UI and refunds are not reported to your app when they happen. The access path and every state
method: [`reference/api-notes.md`](reference/api-notes.md); platform differences in the dates:
[`reference/platform-notes.md`](reference/platform-notes.md).

## 7. Failure descriptions — four types, four spellings

Some failure-description types carry lowercase public fields alongside the PascalCase read-only
properties; where both exist, prefer the properties. Guessing across types is where `CS1061` comes
from: `StoreConnectionFailureDescription` has `.Message` and no `.reason`; `ProductFetchFailed` has
`.FailureReason` and `.FailedFetchProducts` and no `.Message`. The full table:
[`reference/api-notes.md`](reference/api-notes.md).

## 8. What to check before you call it done

The compile is the only gate that runs locally, and it catches most of the v4 residue. Run it, then
read the code for the rest.

- **The project compiles.** Then look for v4 shapes that still compile because they are `[Obsolete]`
  rather than removed: `IStoreListener`, `UnityPurchasing.Initialize`, `ConfigurationBuilder`,
  `SubscriptionManager`, and anything reached through `GetExtension<T>()`.
- **The shapes that do not exist at all** — `OnStoreConnectionFailed` (it is `OnStoreDisconnected`),
  callbacks passed to `FetchProducts` / `FetchPurchases` (they are events), `product.receipt` (it is
  `order.Info.Receipt`), `product.hasReceipt` (it is `CheckEntitlement`),
  `pendingOrder.OrderInfo` (it is `.Info`).
- **Every subscription is registered before `Connect()`**, and every asynchronous call has both its
  events.
- **The grant path is idempotent** and `ConfirmPurchase` happens after the save.
- **`IsSubscribed()` is compared to `Result.True`.**
- **A v5 file living beside an unremoved v4 one needs its own namespace**, or the two collide on
  `CS0101` / `CS0111`.
- **`OnAuthAccountChanged`, if handled, re-fetches** rather than reading the emptied caches.

Report what changed, which product IDs and types are now in the catalogue, what each grants, where
the save happens, and what still has to be done by hand in App Store Connect, Play Console and the
Editor. Sandbox testing is on the developer; nothing here proves a purchase works.

## Scope — what this skill does NOT do

**Shipping seams belong to `unity-monetization`**: what the package adds to the merged Android
manifest and to the Gradle or CocoaPods build, the store declarations that follow from selling
things, and how sandbox behaviour differs in a release build. Come back here for the API, go there
before you submit.

**Server-side entitlement is `unity-live-services`**: verifying a receipt off-device, the
idempotent grant that survives a retried request, where a consumable balance lives, and the
identity a purchase is attached to. This skill stops at "send `order.Info.Receipt` or
`jwsRepresentation` to a server" and does not describe the server.

**Environments, project linking and Editor deployment of a remote catalogue are `unity-ugs`** —
the D2C path here assumes an environment is already selected and a catalogue already deployable.
Ad revenue and mediation are `unity-ads-levelplay`. Shop layout, price display and button states are
`unity-ui-ugui` or `unity-game-ui`.

Not covered at all: pricing and monetisation design, store-side product creation, tax and
compliance advice, and anything that requires a real payment.

## Reference

[`reference/pre-check.md`](reference/pre-check.md) is read first and routes to every path file:
`reference/path-add-iap-to-new-project.md` (greenfield), `reference/migration-v4-to-v5.md`,
`reference/path-implement-iap-d2c.md` (payment provider and webshop),
`reference/path-convert-native-google-billing.md` and `reference/path-convert-native-storekit.md`,
`reference/convert-essentialkit.md`, `reference/convert-unipay.md`,
`reference/convert-revenuecat.md` and `reference/convert-adapty.md`. The API, platform and catalogue
references are linked from the sections above.
