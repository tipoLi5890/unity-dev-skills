# Native iOS StoreKit → Unity IAP

For a project whose purchases go through a hand-written Objective-C or Swift plugin, bridged with
`[DllImport("__Internal")]` and `UnitySendMessage`, and which is moving to `com.unity.purchasing`.

> **Two `SKPaymentQueue` observers is a lost-purchase bug, not a transition state.** Only one
> observer reliably receives transaction callbacks. If the existing plugin registers its own and
> Unity IAP is also live, transactions go to whichever won and the other side never learns. There is
> no per-product cutover.

Two things about this conversion are worse than the Android one. The receipt format changes in a way
that breaks the backend, and Objective-C and Swift cannot be `#if`-guarded by a C# define — the
guards have to go on the call sites.

## The rules this conversion runs under

- **Do not delete the plugin files.** Guard the C# call sites with `#if !USE_UNITY_IAP_V5`; leave
  the `.m` / `.mm` / `.swift` where they are.
- **Build the new adapter first**, mark the old one obsolete second.
- **Keep the game-facing API** behind a facade, so gameplay code is untouched by a billing change.
- **Product IDs do not change.**
- **Backend endpoints do not change** unless the receipt format forces it — and here it does. The
  move from an app-wide receipt bundle to a per-transaction JWS is a breaking backend change; put it
  at the top of the report, not in a footnote.
- **A server-validated grant stays server-validated.**
- **Classify every product** rather than assuming consumables.
- **Subscriptions carry the hard blockers** — promotional offer signing, offer codes, introductory
  price handling. Surface them; let the user choose.
- **A third-party billing SDK stops this path.** Back to [`pre-check.md`](pre-check.md).

## 1. Scan

**The plugin.** Everything under `Assets/Plugins/iOS/`: `.m`, `.mm`, `.h`, `.swift`. For each, note
whether it imports StoreKit, and which generation.

**The C# bridge** — `Assets/**/*.cs`:

```
DllImport.*__Internal
UnitySendMessage
SKProduct|SKPayment|SKPaymentTransaction|SKPaymentQueue|SKReceiptRefresh
StoreKit|AppStore|AppleIAP|iOSBilling|iOSIAP|iOSPurchase
Application\.platform.*IPhonePlayer|RuntimePlatform\.IPhonePlayer
```

Also pull the callback method names out of the `UnitySendMessage` calls in the native files — those
are C# methods that the grep above will not find by name.

**StoreKit 1**, in `.m` / `.mm` / `.h`:

```
SKProductsRequest|SKProductsRequestDelegate
SKPaymentQueue|SKPaymentTransactionObserver
SKPaymentTransaction|SKPayment|SKMutablePayment
SKProduct|SKProductSubscriptionPeriod|SKProductDiscount
paymentQueue:updatedTransactions:|finishTransaction:
SKReceiptRefreshRequest
SKPaymentDiscount|paymentDiscount
SKStorefront|paymentQueueDidChangeStorefront
canMakePayments
```

**StoreKit 2**, in `.swift`:

```
import StoreKit
Product\.products\(for:\)|product\.purchase\(\)
Transaction\.currentEntitlements|Transaction\.updates|Transaction\.finish
verificationResult|JWSTransaction
winBackOffer|eligibleWinBackOffers
```

**Scenes and prefabs** — the MonoBehaviour names from the C# scan, so the rewiring list is complete.

## 2. Which StoreKit

| Generation | Signals | Where it comes from |
|---|---|---|
| StoreKit 1 | `SKPaymentQueue`, `SKPaymentTransaction`, `SKProductsRequest` | Most Unity plugins written before 2023 |
| StoreKit 2 | `Product.products(for:)`, `Transaction.currentEntitlements`, `Transaction.updates` | Swift 5.5+, iOS 15+ |
| Mixed | Both | Treat as StoreKit 1 for blockers, and flag the SK2 usage for review |

Record it in the report. StoreKit 2 brings blockers of its own.

## 3. Classify every product

Consumable, NonConsumable, Subscription or Unknown, in order of signal strength:

1. `SKProduct.subscriptionPeriod` non-nil → Subscription.
2. `finishTransaction:` after the grant with no restore path → Consumable.
3. `restoreCompletedTransactions` handling, or a check on `originalTransaction` → NonConsumable or
   Subscription.
4. The ID: `coins`, `gems`, `pack` / `remove_ads`, `unlock`, `premium` / `monthly`, `annual`, `sub`.
5. What the entitlement or grant code does.
6. Comments, config files.

Unknown goes on the question list, not into a guess.

## 4. The report, before any edit

1. The current architecture — C# `[DllImport("__Internal")]` into the plugin into StoreKit.
2. StoreKit generation: 1, 2 or mixed.
3. Every file involved, and its role — plugin, bridge, callback receiver, UI.
4. The product catalogue found.
5. Per product: inferred type, confidence, source of the inference.
6. Purchase flow, native step to Unity IAP step.
7. Restore flow — `restoreCompletedTransactions` / `Transaction.currentEntitlements` become
   `FetchPurchases()` plus `RestoreTransactions()`.
8. Backend validation, and the receipt format change in full.
9. Finishing: `finishTransaction:` becomes `ConfirmPurchase`, after the grant.
10. Subscriptions — which products, restore, renewals, introductory pricing.
11. StoreKit-specific features found.
12. Which of them block.
13. The proposed architecture.
14. Files to create.
15. Files to modify.
16. App Store Connect checks a human has to make.
17. The test plan.
18. The rollback plan.

## 5. Blockers

| Feature | Signal | Level |
|---|---|---|
| SK1 promotional offer signing | `SKPaymentDiscount`, `paymentDiscount`, `offerIdentifier`, `keyIdentifier`, `nonce`, `signature` | **Hard** — needs server-signed offers; no equivalent |
| SK2 promotional offer signing | `promotionalOffer`, `PromotionalOffer`, `eligiblePromotionOfferSignature` | **Hard** — not exposed |
| Win-back offers | `winBackOffer`, `eligibleWinBackOffers` | **Hard** — not supported |
| Manual receipt refresh | `SKReceiptRefreshRequest` | Soft — `FetchPurchases()` covers re-delivery; record the loss of the explicit refresh |
| Storefront change observer | `SKStorefront`, `paymentQueueDidChangeStorefront` | Soft — record the loss |
| Quantity above one | `quantity > 1` on `SKMutablePayment` | **Hard** — one transaction, one unit |
| Another `addTransactionObserver` left registered | any observer not being removed | **Hard** — the conflict at the top of this file |
| `SKOverlay` / `SKStoreProductViewController` | those types | Soft — store UI, not IAP. Out of scope; say so |
| Receipt-bundle validation | `appStoreReceiptURL`, `receiptData`, `/verifyReceipt` in backend URLs | **Hard for the backend** — see below |

### When a hard subscription blocker lands

**A — Remove the blocking feature and simplify App Store Connect.** Drop promotional offer signing,
or simplify the subscription configuration, so Unity IAP can carry every product. Recommended: one
system, nothing competing for the queue.

**B — Stay on native StoreKit.** Do not migrate now. Keep the plugin until App Store Connect can be
simplified or the feature becomes reachable. Stop, and write the blocker and the decision into the
migration notes.

Not an option: running both. If it is asked for, explain the observer conflict and return to A or B.

## 6. Target shape

Under `Assets/Scripts/IAP/`:

| File | Role |
|---|---|
| `IStorePurchaseService.cs` | The stable game-facing interface |
| `UnityIapStorePurchaseService.cs` | The Unity IAP implementation |
| `ProductCatalogDefinition.cs` | One authoritative product list |
| `ProductDefinitionEntry.cs` | ID, type, store-specific IDs, notes |
| `PurchaseEntitlementMapper.cs` | Order data → grant calls |
| `PurchaseValidationRequest.cs` | To the backend |
| `PurchaseValidationResult.cs` | From the backend |
| `PurchaseRestoreResult.cs` | Restore outcome |
| `LegacyStoreKitAdapterDeprecated.cs` | Facade, only if game code calls the bridge directly |
| `IapMigrationNotes.md` | What changed, what blocked, what remains manual |

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

## 7. Phases

**Package.** `com.unity.purchasing` present and current, installed by the user through Package
Manager. Confirm before continuing.

**Catalogue.** Scanned IDs and inferred types into `ProductCatalogDefinition` /
`ProductDefinitionEntry`.

**The service:**

1. `UnityIAPServices.StoreController()`, every event subscribed before `Connect()`.
2. Catalogue → `List<ProductDefinition>` → `FetchProducts()`, both events handled.
3. `PurchaseProduct(product)`.
4. `OnPurchasePending`: validate, grant, save, then `ConfirmPurchase`.
5. `OnPurchaseDeferred` for Ask-to-Buy: pending UI, no grant; the approval returns through
   `OnPurchasePending`.
6. Promotional interception, if the plugin did it:
   ```csharp
   if (store.AppleStoreExtendedPurchaseService != null)
       store.AppleStoreExtendedPurchaseService.OnPromotionalPurchaseIntercepted += OnPromotionalPurchase;
   ```
   and `ContinuePromotionalPurchases()` when the game is ready — an interception never continued
   hangs.
7. `OnPurchaseFailed` mapped to a readable message.
8. `FetchPurchases()` at startup for re-delivery; `RestoreTransactions(callback)` behind the restore
   button, which iOS requires.
9. Validation handoff: `order.Info.Apple?.jwsRepresentation` in place of the receipt bundle, with
   the backend change written down.

**Facade.** Same signatures over the new service, every method
`[Obsolete("Use IStorePurchaseService — remove after migration validation")]`.

**Unhook the plugin.** Stop calling the `__Internal` bridge for migrated products and wrap those
call sites in `#if !USE_UNITY_IAP_V5`. Leave the ObjC and Swift files alone — the C# guards are
enough to stop the bridge being invoked. But note in the migration notes that if the plugin
registers its own `SKPaymentQueue` observer, that registration has to be removed or disabled before
shipping: a guarded call site does not unregister an observer the plugin added at launch.

**Scaffolding.** Event logging, Editor stubs, the checklist below in the notes.

## 8. What changes in behaviour

### The receipt, and the backend

| Native | Unity IAP |
|---|---|
| SK1: the base64 app receipt from `appStoreReceiptURL`, verified against Apple's `/verifyReceipt` | `order.Info.Apple?.jwsRepresentation` — one JWS per transaction, verified against Apple's App Store Server API |
| SK2: the per-transaction JWS out of `verificationResult` | the same `jwsRepresentation` |

Unity IAP runs on StoreKit 2 on iOS 15+, so what reaches the backend is a signed per-transaction
string, not an app-wide bundle. A backend calling `/verifyReceipt` with a base64 receipt has to move
to the App Store Server API (`GET /inApps/v1/transactions/{transactionId}`) or verify the JWS
itself. **This is the single largest piece of work in the conversion and it is not in the Unity
project.** Coming from SK2 already, it is nearly free.

### Finishing a transaction

| Native | Unity IAP |
|---|---|
| `SKPaymentQueue.default().finishTransaction(transaction)`, after the grant, for every type | `store.ConfirmPurchase(pendingOrder)`, after the grant, for every type |

Same shape, same rule: the entitlement is granted and saved before the confirm.

### Restore

| Native | Unity IAP |
|---|---|
| `restoreCompletedTransactions()` | `store.RestoreTransactions(callback)` — the user-facing button |
| Checking for outstanding transactions at launch | `store.FetchPurchases()` — re-delivers anything unconfirmed through `OnPurchasePending` |

### `applicationUsername` becomes an app account token

```csharp
store.AppleStoreExtendedService?.SetAppAccountToken(Guid.Parse(userAccountGuid));
```

After `Connect()`, and a `Guid` rather than a hashed string. It rides along in the JWS payload,
which is where the backend picks the user up.

### Ask-to-Buy

| Native | Unity IAP |
|---|---|
| `SKPaymentTransactionStatePurchasing` with approval pending, then `paymentQueue:removedTransactions:` | `store.OnPurchaseDeferred` — pending UI, no grant |
| approval, arriving as `SKPaymentTransactionStatePurchased` | `store.OnPurchasePending` — grant, then confirm |

`store.AppleStoreExtendedPurchaseService?.simulateAskToBuy` is still how the path is exercised in a
sandbox.

### Code redemption

```csharp
store.AppleStoreExtendedPurchaseService?.PresentCodeRedemptionSheet();
```

After `Connect()`, and null off iOS.

### Promotional purchases

```csharp
if (store.AppleStoreExtendedPurchaseService != null)
    store.AppleStoreExtendedPurchaseService.OnPromotionalPurchaseIntercepted += OnPromotionalPurchase;

void OnPromotionalPurchase(Product product)
{
    // whatever the game has to do first, then release it:
    store.AppleStoreExtendedPurchaseService?.ContinuePromotionalPurchases();
}
```

Note the `if`: `?.` does not combine with `+=`.

## 9. Concept map

### StoreKit 1

| Native | Unity IAP |
|---|---|
| `SKProduct` | `Product`, via `store.GetProductById` |
| `SKPaymentTransaction` | `PendingOrder`, on `OnPurchasePending` |
| `SKPaymentTransaction.transactionIdentifier` | `pendingOrder.Info.TransactionID` |
| `payment.productIdentifier` | `pendingOrder.CartOrdered.Items().First().Product.definition.id` |
| the app receipt | `order.Info.Apple?.jwsRepresentation` — per transaction, not a bundle |
| `finishTransaction:` | `store.ConfirmPurchase(pendingOrder)` |
| `restoreCompletedTransactions()` | `store.RestoreTransactions(callback)` |
| `SKPaymentTransactionStatePurchased` | `store.OnPurchasePending` |
| `SKPaymentTransactionStateFailed` | `store.OnPurchaseFailed` |
| `SKPaymentTransactionStateDeferred` | `store.OnPurchaseDeferred` |
| `SKPaymentTransactionStateRestored` | `store.OnPurchasesFetched`, or `OnPurchasePending` via restore |
| `SKProductsRequest` + `didReceiveResponse:` | `store.FetchProducts(definitions)` → `OnProductsFetched` |
| `SKPaymentQueue.canMakePayments()` | `store.AppleStoreExtendedService?.canMakePayments`, after `Connect()` |
| `SKMutablePayment.applicationUsername` | `SetAppAccountToken(Guid)`, after `Connect()` |
| `SKPaymentDiscount` | no equivalent — hard blocker |
| `SKReceiptRefreshRequest` | no direct equivalent; `FetchPurchases()` covers re-delivery |
| `SKStorefront` | not exposed |
| `product.subscriptionPeriod` | `AppleStoreExtendedProductService?.GetProductDetails()`, raw JSON |
| `product.introductoryPrice` | `AppleStoreExtendedProductService?.GetIntroductoryPriceDictionary()` |

### StoreKit 2

| Native | Unity IAP |
|---|---|
| `Product.products(for:)` | `store.FetchProducts(definitions)` → `OnProductsFetched` |
| `product.purchase()` | `store.PurchaseProduct(product)` |
| `Transaction.currentEntitlements` | `store.FetchPurchases()` → `OnPurchasesFetched` |
| `Transaction.updates` | `store.OnPurchasePending` |
| `transaction.finish()` | `store.ConfirmPurchase(pendingOrder)` |
| the JWS from `verificationResult` | `order.Info.Apple?.jwsRepresentation` |
| `Transaction.currentEntitlements` as an ownership check | `store.CheckEntitlement(product)` → `OnCheckEntitlement` |
| `winBackOffer` / `eligibleWinBackOffers` | no equivalent — hard blocker |

## 10. Rollback

New C# inside `#if USE_UNITY_IAP_V5`, replaced `[DllImport("__Internal")]` calls inside
`#if !USE_UNITY_IAP_V5`. The native files stay untouched — they cannot see a C# define, and the
guarded call sites are what stops the bridge running. Reverting is removing `USE_UNITY_IAP_V5` from
**Edit > Project Settings > Player > Scripting Define Symbols**. Never leave both live. Write the
steps into the migration notes.

## 11. Test checklist

- [ ] Fresh install: products load, prices display
- [ ] Upgrade from the pre-migration build: no duplicate entitlements
- [ ] Consumable purchase grants
- [ ] Consumable purchase repeats
- [ ] Non-consumable grants once
- [ ] Restore button returns it after reinstall
- [ ] Subscription purchase activates
- [ ] Subscription state refreshes at launch
- [ ] Ask-to-Buy: pending UI, nothing granted early, completes on approval
- [ ] Promotional purchase intercepted and continued
- [ ] Code redemption sheet opens
- [ ] Purchase interrupted mid-flow: re-delivered next launch
- [ ] App killed during purchase: pending order re-delivered
- [ ] Backend accepts the JWS and grants
- [ ] Backend rejects: nothing granted, nothing confirmed
- [ ] Network failure during validation: left pending, re-delivered
- [ ] Sandbox account: no real charge
- [ ] TestFlight build: products load, sandbox purchases succeed
- [ ] Every product ID matches App Store Connect exactly
- [ ] Subscription group configuration is reachable from Unity IAP
- [ ] No duplicate grant, no unfinished transaction, no double consumption

## 12. Questions worth asking

1. Which IDs are consumable, non-consumable, subscription?
2. Does the backend validate the SK1 receipt bundle through `/verifyReceipt`? If so, a JWS migration
   is required.
3. Does the plugin intercept App Store promotional purchases
   (`paymentQueue:shouldAddStorePayment:forProduct:`)?
4. Do any subscriptions use promotional offer signing? That is a hard blocker.
5. Keep the old public C# billing API as a facade?
6. Keep, disable or remove the ObjC and Swift files after validation?

Where enough can be inferred, proceed on a best-effort plan and mark the rest TODO.
