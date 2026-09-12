# v4 → v5

v4 was a listener you implemented. v5 is a controller you subscribe to. That is the whole change,
and it touches every line of IAP code in the project.

The part that makes this migration deceptive: **most of v4 still compiles.** `IStoreListener`,
`ConfigurationBuilder` and `SubscriptionManager` are `[Obsolete]`, not removed, so a project can
upgrade the package, build green, and ship a purchase flow that no longer matches the store's
behaviour. The compile is not the test — the mapping tables below are.

## Initialization

| v4 | v5 |
|---|---|
| `UnityPurchasing.Initialize(listener, builder)` | `UnityIAPServices.StoreController()`, then `await store.Connect()` |
| `ConfigurationBuilder.Instance(StandardPurchasingModule.Instance())` | Gone. Pass `List<ProductDefinition>` to `FetchProducts()`, or use `CatalogProvider` for store-specific IDs and payouts |
| `builder.AddProduct("id", ProductType.Consumable)` | `new ProductDefinition("id", ProductType.Consumable)` in a list |
| `IStoreListener.OnInitialized(controller, extensions)` | `store.OnStoreConnected` |
| `IStoreListener.OnInitializeFailed(error)` | `store.OnStoreDisconnected` |

## Purchase flow

| v4 | v5 |
|---|---|
| `controller.InitiatePurchase(product)` | `store.PurchaseProduct(product)`. There is no developer-payload argument any more — that went with Google Billing v3 |
| `ProcessPurchase(args)` for a **new** purchase | `store.OnPurchasePending` → grant → `store.ConfirmPurchase(pendingOrder)` |
| `ProcessPurchase(args)` for a **restored** purchase | `store.OnPurchasesFetched`. The same grant logic has to run in both places |
| `ProcessPurchase` returning `PurchaseProcessingResult.Pending` | Hold the `PendingOrder` and do not confirm yet. There is no return value to give |
| `IStoreListener.OnPurchaseFailed(product, reason)` | `store.OnPurchaseFailed`, with a `FailedOrder` carrying `FailureReason` and `Details` |
| `controller.ConfirmPendingPurchase(product)` | `store.ConfirmPurchase(pendingOrder)` — the order, not the product |
| `product.hasReceipt` | `store.CheckEntitlement(product)` + `store.OnCheckEntitlement`, checking `EntitlementStatus.FullyEntitled`. A tracked `bool` updated in `OnPurchasePending` and `OnPurchasesFetched` also works, but entitlement is the intended answer |

> **`ProcessPurchase` was one method and its replacement is two handlers.** The single most common
> migration bug is porting the grant into `OnPurchasePending` and forgetting
> `OnPurchasesFetched` — new purchases work, and everything the player already owned stops being
> restored.

## Products and configuration

| v4 | v5 |
|---|---|
| `ConfigurationBuilder` with `AddProduct()` | `CatalogProvider.AddProduct()`, or a plain `List<ProductDefinition>` handed to `store.FetchProducts()` |
| `builder.AddProduct("id", type, new IDs { { "store_id", store } })` | `catalogProvider.AddProduct("id", type, new StoreSpecificIds { { "store_id", store } })`, or `new ProductDefinition("id", "store_id", type)` for a single store |
| `controller.products.WithID("id")` | `store.GetProductById("id")` |
| `controller.products.all` | `store.GetProducts()` |

## Restore

| v4 | v5 |
|---|---|
| `extensions.GetExtension<IAppleExtensions>().RestoreTransactions(cb)` | `store.RestoreTransactions(cb)` — on the controller, both platforms |
| An explicit restore call was the only way | `store.FetchPurchases()` and `store.CheckEntitlement()` already bring confirmed purchases back. `RestoreTransactions` is for the user-facing button, which iOS still requires |

## Receipt validation

| v4 | v5 |
|---|---|
| `CrossPlatformValidator` with Apple and Google | Still the class, but Apple validation returns an empty array under StoreKit 2. Use the Google-only constructor: `CrossPlatformValidator(GooglePlayTangle.Data(), Application.identifier)`. The 4-arg constructor works too; the older constructors that share one bundle ID between Apple and Google are `[Obsolete]` |
| `AppleTangle.Data()` | Deprecated. Apple validation belongs on a server, from `order.Info.Apple?.jwsRepresentation` |
| Parsing the receipt by hand | Same: server-side, from the JWS |
| `product.receipt` | `order.Info.Receipt` — the receipt lives on the order |

## Platform extensions

`GetExtension<T>()` is gone; the extensions are properties, and each is `null` off its own platform.
Method calls can go through `?.`; **event subscriptions need a real `if`**, because `?.` does not
combine with `+=`.

| v4 | v5 |
|---|---|
| `extensions.GetExtension<IAppleExtensions>()` | `store.AppleStoreExtendedService` / `store.AppleStoreExtendedPurchaseService` |
| `extensions.GetExtension<IGooglePlayStoreExtensions>()` | `store.GooglePlayStoreExtendedService` / `store.GooglePlayStoreExtendedPurchaseService` |
| `builder.Configure<IAppleConfiguration>().SetApplePromotionalPurchaseInterceptorCallback(cb)` | `store.AppleStoreExtendedPurchaseService.OnPromotionalPurchaseIntercepted += cb` — an `Action<Product>` |
| `appleExtensions.ContinuePromotionalPurchases()` | `store.AppleStoreExtendedPurchaseService?.ContinuePromotionalPurchases()` |
| `appleExtensions.RegisterPurchaseDeferredListener(cb)` | `store.OnPurchaseDeferred += cb` — on the controller |
| `appleExtensions.simulateAskToBuy` | `store.AppleStoreExtendedPurchaseService?.simulateAskToBuy` |
| `appleExtensions.PresentCodeRedemptionSheet()` | `store.AppleStoreExtendedPurchaseService?.PresentCodeRedemptionSheet()` |
| `appleExtensions.RestoreTransactions(cb)` | `store.RestoreTransactions(cb)` |
| `appleExtensions.SetApplicationUsername(hashedString)` | `store.AppleStoreExtendedService?.SetAppAccountToken(Guid)` — a `Guid` identifying your user, not a hash, and only **after** `Connect()` |
| `builder.Configure<IAppleConfiguration>().SetEntitlementsRevokedListener(cb)` | `store.AppleStoreExtendedPurchaseService.OnEntitlementRevoked += cb` — an `Action<string>` receiving **one product ID**, not a list |
| `appleExtensions.GetTransactionReceiptForProduct(product)` | `order.Info.Receipt`, inside `OnPurchasePending` |
| `builder.Configure<IAppleConfiguration>().canMakePayments` | `store.AppleStoreExtendedService?.canMakePayments` — after `Connect()`, not before init |
| `appleExtensions.GetIntroductoryPriceDictionary()` | `store.AppleStoreExtendedProductService?.GetIntroductoryPriceDictionary()`. Moved, not removed — a `Dictionary<string, string>` of store-specific ID to offer JSON |
| `appleExtensions.GetProductDetails()` | `store.AppleStoreExtendedProductService?.GetProductDetails()`. Moved, not removed. Title, description and price are on `product.metadata` directly |
| `appleExtensions.SetStorePromotionOrder(products)` | `store.AppleStoreExtendedProductService?.SetStorePromotionOrder(...)` |
| `appleExtensions.SetStorePromotionVisibility(product, visibility)` | `store.AppleStoreExtendedProductService?.SetStorePromotionVisibility(...)` |
| `appleExtensions.FetchStorePromotionOrder(ok, fail)` | `store.AppleStoreExtendedProductService?.FetchStorePromotionOrder(...)` — `Action<List<Product>>`, `Action<string>` |
| `appleExtensions.FetchStorePromotionVisibility(product, ok, fail)` | `store.AppleStoreExtendedProductService?.FetchStorePromotionVisibility(...)` — `Action<string, AppleStorePromotionVisibility>`, `Action<string>` |
| `googlePlayConfig.SetDeferredPurchaseListener(cb)` | `store.OnPurchaseDeferred += cb` — on the controller |
| `googlePlayConfig.SetDeferredProrationUpgradeDowngradeSubscriptionListener(cb)` | `store.GooglePlayStoreExtendedPurchaseService.OnDeferredPaymentUntilRenewalDate += cb` — an `Action<DeferredPaymentUntilRenewalDateOrder>`, not `Action<Product>`. The product is `deferredOrder.SubscriptionOrdered` |
| `googlePlayExtensions.UpgradeDowngradeSubscription(currentId, newId, mode)` | `store.GooglePlayStoreExtendedPurchaseService?.UpgradeDowngradeSubscription(currentOrder, newProduct, replacementMode)` — objects, not strings; `GooglePlayReplacementMode`, not the deprecated proration mode; after `Connect()` |
| `googlePlayExtensions.IsPurchasedProductDeferred(product)` | `store.GooglePlayStoreExtendedPurchaseService?.IsOrderDeferred(order)`, itself `[Obsolete]`. Track deferral through `OnPurchaseDeferred` / `OnPurchasePending` instead |
| `googlePlayExtensions.RestoreTransactions(cb)` | `store.RestoreTransactions(cb)` |
| `googlePlayConfig.SetObfuscatedAccountId(id)` | `store.GooglePlayStoreExtendedService?.SetObfuscatedAccountId(id)` — **after** `Connect()` |
| `googlePlayConfig.SetObfuscatedProfileId(id)` | `store.GooglePlayStoreExtendedService?.SetObfuscatedProfileId(id)` — **after** `Connect()` |

## Subscriptions

| v4 | v5 |
|---|---|
| `new SubscriptionManager(product, introJson).getSubscriptionInfo()` | `order.Info.PurchasedProductInfo.FirstOrDefault(p => p.productId == productId)?.subscriptionInfo`. It hangs off `IPurchasedProductInfo`, not `CartItem` — a `CartItem` has `Product` and `Quantity` and nothing else |
| `subscriptionInfo.isSubscribed() == Result.True` | `purchasedProductInfo?.subscriptionInfo?.IsSubscribed() == Result.True`. PascalCase now, still a `Result`, still three-valued. `?? false` does not compile against a `Result?` |
| `product.receipt == null` as an ownership test | `store.CheckEntitlement(product)` + `OnCheckEntitlement`, or a tracked flag updated on both new and restored purchases |
| `product.metadata.GetAppleProductMetadata()?.isFamilyShareable` | Unchanged — the extension method on `ProductMetadata` survives |

## Codeless

| v4 | v5 |
|---|---|
| `CodelessIAPStoreListener.Instance` | Still there, now running on v5 underneath |
| `CodelessIAPStoreListener.initializationComplete` | `CodelessIAPStoreListener.IsInitialized()` |

## The fourteen breaking changes, and why each one matters

1. **`IStoreListener` is deprecated.** Replace the interface with event subscriptions. It still
   compiles, which is why this is easy to miss.
2. **The two-step purchase flow is not optional.** There is no equivalent of returning
   `PurchaseProcessingResult.Complete`; every purchase goes pending → confirm.
3. **`ConfigurationBuilder` is deprecated.** `CatalogProvider`, or `List<ProductDefinition>` into
   `FetchProducts()`.
4. **Apple local receipt validation does nothing under StoreKit 2.** `CrossPlatformValidator` is
   not itself deprecated, but its Apple side returns an empty array silently. Google-only
   constructor for local validation; `order.Info.Apple?.jwsRepresentation` and a server for Apple.
5. **Extensions are properties, not `GetExtension<T>()`** — and `null` on any platform they do not
   belong to.
6. **`product.receipt` and `product.hasReceipt` are gone.** `order.Info.Receipt` for the receipt,
   `CheckEntitlement` for ownership.
7. **`Purchase()` has no payload.** Developer payload went away with Google Billing v3.
8. **The old `ProcessPurchase` logic now lives in two handlers** — `OnPurchasePending` and
   `OnPurchasesFetched`.
9. **Restore is mostly implicit.** `FetchPurchases()` re-delivers anything unconfirmed;
   `RestoreTransactions()` remains for the iOS button.
10. **`SubscriptionManager` is replaced** by `order.Info.PurchasedProductInfo`, with PascalCase
    methods.
11. **Platform configuration moved after `Connect()`** — `SetAppAccountToken`,
    `SetObfuscatedAccountId` / `ProfileId` and `canMakePayments` were all configuration-time calls
    in v4 and are post-connect calls now.
12. **Apple promotion APIs moved to `IAppleStoreExtendedProductService`** —
    `SetStorePromotionOrder`, `SetStorePromotionVisibility` and both fetches.
13. **`OnPurchaseConfirmed` gives you an `Order`.** Pattern-match: `ConfirmedOrder` succeeded,
    `FailedOrder` means the confirmation itself failed. Assuming success turns a failure into a sale.
14. **Platform events are on the extended services.** `OnPromotionalPurchaseIntercepted` and
    `OnEntitlementRevoked` on the Apple purchase service, `OnDeferredPaymentUntilRenewalDate` on the
    Google one. Only `OnPurchaseDeferred` sits on the controller itself.

## The mistakes this migration produces

- **Subscribing only to the success events.** Every asynchronous call has a failure event, and an
  unhandled failure is a runtime warning, not an error — so it goes unnoticed until a player
  reports it.
- **Skipping `OnPurchaseDeferred`.** Ask-to-Buy and Google's deferred payments arrive there.
  Unsubscribed, they vanish.
- **Rebuilding ownership as a `bool` when `CheckEntitlement` exists.** The entitlement API handles
  refunds and subscription expiry; a flag you maintain does not.
- **`StoreConnectionFailureDescription.reason`.** The member is `.message` / `.Message`. Porting
  `OnInitializeFailed(error, message)` is where this one gets invented.
- **`ProductFetchFailed.Message`.** That type carries `.FailureReason`.
- **Subscribing after `Connect()`.** A purchase left unconfirmed by the previous session is
  re-delivered as the store comes up, and lands on nobody.
- **Treating `OnPurchaseConfirmed` as success.** See breaking change 13.
- **Initialising in `Start()`.** `Awake()` means anything reading a price or an entitlement in its
  own `Start()` finds the controller built.

## v5, minimally

```csharp
StoreController m_StoreController;

async void Awake()
{
    m_StoreController = UnityIAPServices.StoreController();

    // Subscribed before Connect — an unconfirmed purchase from last session may arrive at once.
    m_StoreController.OnPurchasePending += (order) =>
    {
        var product = order.CartOrdered.Items().FirstOrDefault()?.Product;
        GrantContent(product);
        m_StoreController.ConfirmPurchase(order);
    };
    m_StoreController.OnPurchaseConfirmed += (order) =>
    {
        switch (order)
        {
            case ConfirmedOrder: Debug.Log("Purchase confirmed"); break;
            case FailedOrder failed: Debug.LogError($"Confirmation failed: {failed.FailureReason}"); break;
        }
    };
    m_StoreController.OnPurchaseFailed   += (failed)   => Debug.LogError($"{failed.FailureReason} - {failed.Details}");
    m_StoreController.OnPurchaseDeferred += (deferred) => Debug.Log("Deferred — awaiting approval");

    m_StoreController.OnStoreConnected    += OnStoreConnected;
    m_StoreController.OnStoreDisconnected += (failure) => Debug.LogError($"Store disconnected: {failure.Message}");

    await m_StoreController.Connect();
}

void OnStoreConnected()
{
    var products = new List<ProductDefinition>
    {
        new ProductDefinition("com.mygame.coins100", ProductType.Consumable)
    };

    m_StoreController.OnProductsFetched     += (fetched) => Debug.Log("Products ready");
    m_StoreController.OnProductsFetchFailed += (failure) => Debug.LogError($"Product fetch failed: {failure.FailureReason}");
    m_StoreController.FetchProducts(products);

    m_StoreController.OnPurchasesFetched     += (orders) => Debug.Log($"{orders.PendingOrders.Count} carried over");
    m_StoreController.OnPurchasesFetchFailed += (failure) => Debug.LogError($"Purchase fetch failed: {failure.Message}");
    m_StoreController.FetchPurchases();
}
```
