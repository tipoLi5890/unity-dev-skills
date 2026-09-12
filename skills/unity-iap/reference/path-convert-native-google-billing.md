# Native Google Play Billing → Unity IAP

For a project whose purchases go C# → `AndroidJavaObject` → BillingClient, and which is moving to
`com.unity.purchasing`.

> **Two billing systems on one device is not a migration strategy.** Android hands a transaction to
> a single `PurchasesUpdatedListener`. If both the native bridge and Unity IAP are live, one of them
> receives every callback and the other silently receives none — lost purchases, unacknowledged
> tokens, double grants. There is no "gradual cutover per product". Everything moves, or nothing
> does.

## The rules this conversion runs under

- **Do not delete the native billing files.** Guard their call sites behind `#if !USE_UNITY_IAP_V5`,
  so the old path is one Player Settings edit away.
- **Build the new adapter first**, then mark the old one obsolete.
- **Keep the game-facing API.** A facade over the new service means gameplay code does not get
  rewritten as part of a billing change.
- **Product IDs do not change.** They are the join key to the Play Console and to every purchase
  already made.
- **Backend endpoints do not change** unless the receipt format forces it — and where it does, say
  so loudly rather than quietly.
- **Do not move a server-validated grant onto the client.** If the project validates server-side, it
  keeps validating server-side.
- **Classify every product.** Assuming they are all consumables is how a non-consumable stops
  restoring.
- **Subscriptions are where this gets hard.** Base plans, offer tokens, pricing phases — if they are
  in use, surface them and let the user choose. Do not silently drop them.
- **A third-party billing SDK in the project stops this path.** Route back to
  [`pre-check.md`](pre-check.md).

## 1. Scan

Nothing is edited until the report below has been accepted.

**C# bridge** — `Assets/**/*.cs`:

```
AndroidJavaObject|AndroidJavaClass|UnityPlayer\.currentActivity
UnitySendMessage
GoogleBilling|BillingManager|BillingClient|BillingBridge|AndroidBillingBridge|PlayBilling
purchaseToken|originalJson|signature|productId|orderId
\backnowledge\b|\bconsume\b
restore.?purchases|query.?products|query.?purchases
subscription.?status|receipt.?valid|entitlement.?grant
```

**Java / Kotlin** — `Assets/Plugins/Android/**/*.java`, `*.kt`:

```
com\.android\.billingclient\.api\.BillingClient
PurchasesUpdatedListener|BillingClientStateListener
ProductDetails|ProductDetails\.SubscriptionOfferDetails
QueryProductDetailsParams|BillingFlowParams
AcknowledgePurchaseParams|ConsumeParams|QueryPurchasesParams
launchBillingFlow|acknowledgePurchase|consumeAsync
queryProductDetailsAsync|queryPurchasesAsync|enablePendingPurchases
offerToken|basePlanId|offerId|pricingPhases
```

**Gradle and manifest** — `mainTemplate.gradle`, `launcherTemplate.gradle`,
`baseProjectTemplate.gradle`, `AndroidManifest.xml`, for `com\.android\.billingclient:billing` and
its `-ktx` variant. List every `.jar` and `.aar` under `Assets/Plugins/Android/` as well —
pre-compiled billing code hides there and greps do not find it.

**Scenes and prefabs** — `.unity`, `.prefab`, `.asset` for the MonoBehaviour names the C# scan
turned up, so the rewiring list is complete before anything moves.

## 2. Classify every product

Each one is Consumable, NonConsumable, Subscription or Unknown. In order of how much the signal is
worth:

1. `BillingClient.ProductType.INAPP` (consumable or not) versus `.SUBS`.
2. `consumeAsync` on it → Consumable. `acknowledgePurchase` without a consume → NonConsumable.
3. The ID itself — `coins`, `gems`, `pack` read consumable; `remove_ads`, `unlock` read
   non-consumable; `monthly`, `annual`, `sub` read subscription.
4. What the entitlement or backend grant code does with it.
5. Comments and config files.

Anything still ambiguous is Unknown, and Unknown goes on the question list rather than into a guess.

## 3. The report, before any edit

1. The current architecture — how the bridge is shaped, C# through JNI to BillingClient.
2. Every file that touches native billing, and what each does.
3. The product catalogue found.
4. Per product: inferred type, confidence, and which signal produced it.
5. Purchase flow, native step to Unity IAP step.
6. Restore flow — `queryPurchasesAsync` becomes `FetchPurchases` plus `RestoreTransactions`.
7. Backend validation: what the old flow sent (`purchaseToken`, `originalJson`, `signature`,
   `packageName`) against what Unity IAP provides.
8. Consumption: `consumeAsync` becomes `ConfirmPurchase`, after the grant.
9. Acknowledgement: `acknowledgePurchase` becomes the same call.
10. Subscriptions — which products, how they restore, how renewals are handled.
11. Google-specific features found.
12. Which of those cannot be expressed in Unity IAP.
13. The proposed architecture.
14. Files to create.
15. Files to modify, and what changes in each.
16. Play Console checks that a human has to make.
17. The test plan.
18. The rollback plan.

## 4. Blockers

Report these; do not remove them quietly. A hard blocker means the conversion stops until the user
decides.

| Feature | Signal | Level |
|---|---|---|
| Multiple subscription base plans | `basePlanId`, several `SubscriptionOfferDetails` per product | **Hard** |
| Explicit offer token selection | `offerToken` on `BillingFlowParams` | **Hard** |
| Introductory offer chosen by `offerId` | `offerId` in the offer params | **Hard** |
| Offer tags | `offerTags` read off `SubscriptionOfferDetails` | Soft — record the loss |
| Pricing phase inspection | `pricingPhases` / `PricingPhase` read | Soft — record the loss |
| Quantity above one | `quantity > 1` in `BillingFlowParams` | **Hard** |
| Alternative billing / external offers | `setExternalOfferToken`, alternative billing config | **Hard** |
| Personalised price disclosure | `setIsPersonalizedPrice(true)` | **Hard** |
| Obfuscated account / profile IDs | `setObfuscatedAccountId`, `setObfuscatedProfileId` | Soft — Unity IAP has both, post-`Connect()` |
| Other `BillingFlowParams` builder calls | anything not listed above | Soft — record the loss |
| `ProductDetails` fields with no `Product.metadata` equivalent | direct metadata reads | Soft — record the loss |

### When a hard subscription blocker lands

Two options, and a third that must not be offered.

**A — Simplify the Play Console configuration.** Collapse extra base plans and offers so each
product has one base plan. Unity IAP then covers everything, including subscriptions. This is the
recommended path: one system, nothing to coexist with.

**B — Stay on native billing for now.** Do not migrate. Keep the BillingClient implementation until
the Play Console configuration can be simplified, or until Unity IAP exposes what is missing. Stop
here and write the blocker and the decision into the migration notes.

There is no option C. A mixed architecture loses purchases for the reason at the top of this file;
if the user asks for one, explain the listener conflict and go back to A or B.

## 5. Target shape

Under `Assets/Scripts/IAP/`:

| File | Role |
|---|---|
| `IStorePurchaseService.cs` | The stable game-facing interface |
| `UnityIapStorePurchaseService.cs` | The Unity IAP implementation |
| `ProductCatalogDefinition.cs` | One authoritative product list |
| `ProductDefinitionEntry.cs` | ID, type, store-specific IDs, notes |
| `PurchaseEntitlementMapper.cs` | Order data → the game's grant calls |
| `PurchaseValidationRequest.cs` | What goes to the backend |
| `PurchaseValidationResult.cs` | What comes back |
| `PurchaseRestoreResult.cs` | The restore outcome |
| `LegacyGoogleBillingAdapterDeprecated.cs` | The facade, only if game code calls the old API |
| `IapMigrationNotes.md` | What changed, what blocked, what a human still has to do |

```csharp
public interface IStorePurchaseService
{
    Task InitializeAsync();
    Task FetchProductsAsync();
    IReadOnlyList<StoreProductInfo> GetProducts();
    Task PurchaseAsync(string productId);
    Task RestorePurchasesAsync();
    bool IsInitialized { get; }
}
```

Adapt the signatures to whatever the project's existing billing API looks like — the point of the
facade is that gameplay code does not notice.

## 6. Phases

**Package.** Confirm `com.unity.purchasing` and its version. Missing or old is a Package Manager
step for the user, not a manifest edit.

**Catalogue.** Turn the scanned IDs and inferred types into `ProductCatalogDefinition` /
`ProductDefinitionEntry`.

**The service.** `UnityIapStorePurchaseService`, in this order:

1. `UnityIAPServices.StoreController()`, every event subscribed before `Connect()`.
2. `List<ProductDefinition>` from the catalogue → `FetchProducts()`, both events handled.
3. `PurchaseProduct(product)`.
4. `OnPurchasePending`: validate, grant, save, then `ConfirmPurchase`. In that order.
5. `OnPurchaseDeferred`: pending UI, no grant.
6. `OnPurchaseFailed`: `FailureReason` mapped to something a player can read.
7. `FetchPurchases()` at startup, `RestoreTransactions(callback)` behind the restore button.
8. Validation handoff: `order.Info.Receipt` instead of the token/JSON/signature triple, and a
   written note of the backend change that implies.

**Facade.** If game code calls the old bridge by name, implement the same signatures over the new
service and mark them `[Obsolete("Use IStorePurchaseService — remove after migration validation")]`.

**Unhook the native path.** Stop calling the bridge for migrated products; wrap those calls in
`#if !USE_UNITY_IAP_V5`. Leave the Gradle billing dependency unless the user asks for its removal.

**Scaffolding.** Logging at every IAP event, an Editor stub for sandbox work, and the checklist below
copied into the migration notes.

## 7. What changes in behaviour

### Acknowledge and consume become one call

| Native | Unity IAP |
|---|---|
| `consumeAsync` on a consumable | `ConfirmPurchase(pendingOrder)`, after the grant |
| `acknowledgePurchase` on a non-consumable or subscription | the same call |

The distinction that BillingClient made explicit is now internal. What stays your responsibility is
the ordering: the entitlement is safe before the confirm, never after.

### The backend sees a different shape

| Native field | Unity IAP |
|---|---|
| `purchaseToken` | inside `order.Info.Receipt` |
| `originalJson` | inside `order.Info.Receipt` |
| `signature` | inside `order.Info.Receipt` |
| `packageName` | `Application.identifier` |
| `productId` | `pendingOrder.CartOrdered.Items().First().Product.definition.id` |

A backend that reads `purchaseToken` or `originalJson` as top-level fields will not find them. That
is a required backend change, and it belongs in the report rather than in a surprise.

### Obfuscated IDs move after `Connect()`

```csharp
store.GooglePlayStoreExtendedService?.SetObfuscatedAccountId("hashed_id");
store.GooglePlayStoreExtendedService?.SetObfuscatedProfileId("hashed_profile_id");

string accountId = store.GooglePlayStoreExtendedPurchaseService?.GetObfuscatedAccountId(order);
```

### Pending purchases become deferred orders

Code that called `enablePendingPurchases()` or tested for a `PENDING` purchase state now listens on
`OnPurchaseDeferred`: show the pending state, grant nothing, and let the approval come back through
`OnPurchasePending`.

### Subscription upgrades

`launchBillingFlow` with subscription update params becomes:

```csharp
store.GooglePlayStoreExtendedPurchaseService?.UpgradeDowngradeSubscription(
    currentOrder,      // the Order of the active subscription
    newProduct,        // what they are moving to
    GooglePlayReplacementMode.ChargeFullPrice);
```

The replacement modes are in [`platform-notes.md`](platform-notes.md), and the choice between them
is a pricing decision.

## 8. Concept map

| Native Google Billing | Unity IAP |
|---|---|
| `ProductDetails` | `Product`, via `store.GetProductById` |
| `Purchase` | `PendingOrder`, on `OnPurchasePending` |
| `purchaseToken` | inside `order.Info.Receipt` |
| `originalJson` | inside `order.Info.Receipt` |
| `signature` | inside `order.Info.Receipt` |
| `acknowledgePurchase` | `store.ConfirmPurchase(pendingOrder)` |
| `consumeAsync` | `store.ConfirmPurchase(pendingOrder)` |
| `queryPurchasesAsync` | `store.FetchPurchases()` → `OnPurchasesFetched` |
| `BillingResult` / `BillingResponseCode` | `FailedOrder.FailureReason`, `StoreConnectionFailureDescription` |
| `ProductType.INAPP` | `ProductType.Consumable` or `.NonConsumable`, told apart by consume behaviour |
| `ProductType.SUBS` | `ProductType.Subscription` |
| `offerToken`, `basePlanId`, `pricingPhases` | no equivalent — a blocker, not a mapping |

## 9. Rollback

New code inside `#if USE_UNITY_IAP_V5`, replaced bridge calls inside `#if !USE_UNITY_IAP_V5`.
Reverting is then removing `USE_UNITY_IAP_V5` from **Edit > Project Settings > Player > Scripting
Define Symbols** — no code change. Never define both paths active for the same product. Write the
steps into the migration notes while they are still obvious.

## 10. Test checklist

Copy into `IapMigrationNotes.md`. None of it can be run from the Editor alone.

- [ ] Fresh install: products load, prices display
- [ ] Upgrade from the pre-migration build: no duplicate entitlements
- [ ] Consumable purchase grants
- [ ] Consumable purchase repeats
- [ ] Non-consumable grants once
- [ ] Non-consumable restores after reinstall
- [ ] Subscription purchase activates
- [ ] Subscription state refreshes at launch
- [ ] Deferred purchase: pending UI, nothing granted early
- [ ] Purchase interrupted mid-flow: re-delivered next launch
- [ ] App killed during purchase: pending order re-delivered
- [ ] App resumed after the Play purchase UI: `OnPurchasePending` fires
- [ ] Backend validation succeeds → granted
- [ ] Backend validation fails → not granted, not confirmed
- [ ] Network failure during validation → left pending, re-delivered
- [ ] Sandbox tester account: no real charge
- [ ] Internal testing track build
- [ ] Every product ID matches the Play Console exactly
- [ ] No base plan configuration Unity IAP cannot reach
- [ ] No duplicate grant, no unacknowledged purchase, no double consumption

## 11. Questions worth asking

Only what cannot be inferred:

1. Which IDs are consumable, non-consumable, subscription?
2. Does the backend read the raw `purchaseToken` field?
3. Do any subscriptions use multiple base plans or offer tokens?
4. Keep the old public C# billing API as a facade?
5. Keep, disable or remove the native billing files?

Where enough can be inferred, proceed on a best-effort plan and mark the uncertain parts as TODO
rather than stalling on a questionnaire.
