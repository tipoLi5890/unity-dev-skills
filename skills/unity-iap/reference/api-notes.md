# The v5 API surface

Signatures, worked examples, and the names that look right and are not.

## `StoreController` members

```csharp
// Store lifecycle
Task Connect()
void SetStoreReconnectionRetryPolicyOnDisconnection(IRetryPolicy? retryPolicy)
event Action? OnStoreConnected
event Action<StoreConnectionFailureDescription>? OnStoreDisconnected

// Products
void FetchProducts(List<ProductDefinition> defs, IRetryPolicy? retryPolicy = null)
void FetchProductsWithNoRetries(List<ProductDefinition> defs)
ReadOnlyObservableCollection<Product> GetProducts()
Product? GetProductById(string productId)
event Action<List<Product>>? OnProductsFetched
event Action<ProductFetchFailed>? OnProductsFetchFailed

// Purchasing
void PurchaseProduct(Product product)
void PurchaseProduct(string? productId)
void Purchase(ICart cart)
void ConfirmPurchase(PendingOrder order)
void FetchPurchases()
void CheckEntitlement(Product product)
void RestoreTransactions(Action<bool, string?>? callback)
ReadOnlyObservableCollection<Order> GetPurchases()
void ProcessPendingOrdersOnPurchasesFetched(bool shouldProcess)

// Purchase events
event Action<PendingOrder>? OnPurchasePending
event Action<Order>? OnPurchaseConfirmed          // Order base type — pattern-match it
event Action<FailedOrder>? OnPurchaseFailed
event Action<DeferredOrder>? OnPurchaseDeferred
event Action<Orders>? OnPurchasesFetched
event Action<PurchasesFetchFailureDescription>? OnPurchasesFetchFailed
event Action<Entitlement>? OnCheckEntitlement

// Account change (5.4+)
event Action? OnAuthAccountChanged

// Platform extensions — null on any platform they do not belong to
IAppleStoreExtendedService? AppleStoreExtendedService { get; }
IGooglePlayStoreExtendedService? GooglePlayStoreExtendedService { get; }
IAppleStoreExtendedProductService? AppleStoreExtendedProductService { get; }
IAppleStoreExtendedPurchaseService? AppleStoreExtendedPurchaseService { get; }
IGooglePlayStoreExtendedPurchaseService? GooglePlayStoreExtendedPurchaseService { get; }
```

`StoreController` is the union of three interfaces, and you can take them separately when you would
rather keep the concerns apart:

```csharp
IStoreService    storeService    = UnityIAPServices.DefaultStore();     // Connect, extensions
IProductService  productService  = UnityIAPServices.DefaultProduct();   // FetchProducts, GetProducts, GetProductById
IPurchaseService purchaseService = UnityIAPServices.DefaultPurchase();  // PurchaseProduct, ConfirmPurchase, FetchPurchases
```

Every asynchronous call has a success and a failure event, and both need a subscriber:

| Call | Success | Failure |
|---|---|---|
| `Connect()` | `OnStoreConnected` | `OnStoreDisconnected` |
| `FetchProducts()` | `OnProductsFetched` | `OnProductsFetchFailed` |
| `FetchPurchases()` | `OnPurchasesFetched` | `OnPurchasesFetchFailed` |
| `PurchaseProduct()` | `OnPurchasePending` | `OnPurchaseFailed` |
| `CheckEntitlement()` | `OnCheckEntitlement` | — |

## Names that look plausible and do not exist

Reaching for any of these is a compile error, and each has one replacement.

| Reached for | Actually |
|---|---|
| `store.OnStoreConnectionFailed` | `store.OnStoreDisconnected`, carrying `StoreConnectionFailureDescription` |
| `store.FetchProducts(defs, onOk, onFail)` | `FetchProducts(List<ProductDefinition>)`; results arrive on `OnProductsFetched` / `OnProductsFetchFailed` |
| `store.FetchPurchases(onOk, onFail)` | `FetchPurchases()`; results on `OnPurchasesFetched` / `OnPurchasesFetchFailed` |
| `product.receipt` | `order.Info.Receipt` — the receipt belongs to the order |
| `product.hasReceipt` | `store.CheckEntitlement(product)` + `OnCheckEntitlement` |
| `new SubscriptionManager(product, introJson)` | `order.Info.PurchasedProductInfo` — see below |
| `pendingOrder.OrderInfo.Apple.jwsRepresentation` | `pendingOrder.Info.Apple?.jwsRepresentation` — `Info`, and the null-conditional matters off Apple |

## Initialization, in full

```csharp
StoreController m_StoreController;

async void Awake()
{
    m_StoreController = UnityIAPServices.StoreController();

    // Everything subscribed before Connect — a purchase left over from the last session
    // can be re-delivered the moment the store comes up.
    m_StoreController.OnPurchasePending  += OnPurchasePending;
    m_StoreController.OnPurchaseConfirmed += (order) => Debug.Log("Purchase complete");
    m_StoreController.OnPurchaseFailed   += (failed) => Debug.LogError($"{failed.FailureReason} - {failed.Details}");
    m_StoreController.OnPurchaseDeferred += (deferred) => Debug.Log("Purchase deferred, awaiting approval");

    m_StoreController.OnStoreConnected    += OnStoreConnected;
    m_StoreController.OnStoreDisconnected += (failure) => Debug.LogError($"Store disconnected: {failure.Message}");

    await m_StoreController.Connect();
}

void OnStoreConnected()
{
    var products = new List<ProductDefinition>
    {
        new ProductDefinition("com.mygame.coins100",   ProductType.Consumable),
        new ProductDefinition("com.mygame.removeads",  ProductType.NonConsumable),
        new ProductDefinition("com.mygame.vip_monthly", ProductType.Subscription)
    };

    m_StoreController.OnProductsFetched     += (fetched) => Debug.Log("Products ready");
    m_StoreController.OnProductsFetchFailed += (failure) => Debug.LogError($"Product fetch failed: {failure.FailureReason}");
    m_StoreController.FetchProducts(products);

    m_StoreController.OnPurchasesFetched     += (orders) => Debug.Log($"{orders.PendingOrders.Count} pending purchases carried over");
    m_StoreController.OnPurchasesFetchFailed += (failure) => Debug.LogError($"Purchase fetch failed: {failure.Message}");
    m_StoreController.FetchPurchases();
}
```

`Awake()` rather than `Start()`: anything whose `Start()` reads a price or an entitlement then finds
the controller already built.

## Product definitions

```csharp
// One ID everywhere
new ProductDefinition("com.mygame.coins100", ProductType.Consumable)

// A different SKU per store
new ProductDefinition("com.mygame.coins100", ProductType.Consumable,
    new StoreSpecificIds
    {
        { "apple_coins_100",  AppleAppStore.Name },
        { "google_coins_100", GooglePlay.Name }
    })
```

Each entry is the store-specific ID first, the store name second — the shape v4's `IDs` had. Confirm
it against `StoreSpecificIds.Add` in the installed package before typing out a long mapping.

### `CatalogProvider`

When the store-specific mapping is big enough to want a home of its own:

```csharp
var catalogProvider = new CatalogProvider();

var products = new List<ProductDefinition>
{
    new ProductDefinition("com.mygame.gems50", ProductType.Consumable),
    new ProductDefinition("com.mygame.pass",   ProductType.Subscription)
};

var storeSpecificIds = new Dictionary<string, StoreSpecificIds>
{
    { "com.mygame.pass", new StoreSpecificIds
        {
            { "com.mygame.google.pass", GooglePlay.Name },
            { "com.mygame.ios.pass",    AppleAppStore.Name }
        }
    }
};

catalogProvider.AddProducts(products, storeSpecificIds);
catalogProvider.FetchProducts(productService.FetchProductsWithNoRetries);
```

### `CatalogListings` and `uSku` (5.4+)

`product.definition.id` and `productId` keep working. New code has two more precise handles: `uSku`
is the canonical cross-platform identifier, and `catalogListings` is every purchasable listing
attached to that product — a product can carry several, for different price tiers or offers.

```csharp
string id = product.uSku;

foreach (var (listingId, listing) in product.catalogListings)
{
    bool   canBuy  = listing.availableToPurchase;
    string storeId = listing.definition.storeSpecificId;
    string price   = listing.metadata.localizedPriceString;
}
```

| `CatalogListing` property | Type | Holds |
|---|---|---|
| `id` | `string` | The listing identifier — the dictionary key |
| `availableToPurchase` | `bool` | Whether this listing can be bought right now |
| `definition` | `ProductDefinition` | Store-side definition: id, store-specific id, type, payouts |
| `metadata` | `ProductMetadata` | Localized title, description, price, currency |

Buying by listing rather than by product ID saves the second lookup — pass the listing.

## The purchase flow

```csharp
store.PurchaseProduct(product);

store.OnPurchasePending += (pendingOrder) =>
{
    var product = pendingOrder.CartOrdered.Items().FirstOrDefault()?.Product;
    GrantContent(product);                 // and persist it
    store.ConfirmPurchase(pendingOrder);   // only once the grant is safe
};

store.OnPurchaseConfirmed += (order) =>
{
    switch (order)
    {
        case ConfirmedOrder confirmed:
            Debug.Log($"Confirmed: {confirmed.CartOrdered.Items().First().Product.definition.id}");
            break;
        case FailedOrder failed:
            Debug.LogError($"Confirmation failed: {failed.FailureReason} - {failed.Details}");
            break;
    }
};

store.OnPurchaseFailed   += (failed)   => Debug.LogError($"Purchase failed: {failed.FailureReason} - {failed.Details}");
store.OnPurchaseDeferred += (deferred) => Debug.Log("Awaiting approval — grant nothing yet");
```

A crash between the grant and the confirm leaves the order pending, and the store re-delivers it
through `OnPurchasePending` next launch. That is the design, and it is why the grant has to be
idempotent.

`ProcessPendingOrdersOnPurchasesFetched(false)` switches that re-delivery off to reproduce v4's
behaviour. It exists for projects that need the old shape during a migration; it is a worse default
and should not be suggested.

## Restore

```csharp
store.RestoreTransactions((success, error) =>
{
    if (success) Debug.Log("Restore finished — each restored purchase arrives on OnPurchasePending.");
    else         Debug.LogError($"Restore failed: {error}");
});
```

## Entitlement

```csharp
store.CheckEntitlement(product);

store.OnCheckEntitlement += (entitlement) =>
{
    if (entitlement.Status == EntitlementStatus.FullyEntitled)
        Debug.Log($"Owned: {entitlement.Product.definition.id}");
};
```

`EntitlementStatus` is `FullyEntitled`, `EntitledUntilConsumed`, `EntitledButNotFinished`,
`NotEntitled`, `Unknown`. Where you already hold the order, its type answers without the call: a
`PendingOrder` is `EntitledUntilConsumed` for a consumable and `EntitledButNotFinished` otherwise, a
`ConfirmedOrder` is `FullyEntitled`.

## Existing purchases

```csharp
store.FetchPurchases();

store.OnPurchasesFetched += (orders) =>
{
    foreach (var confirmed in orders.ConfirmedOrders)
    {
        var product = confirmed.CartOrdered.Items().FirstOrDefault()?.Product;
        Debug.Log($"Already owned: {product?.definition.id}");
    }
};
```

## `OnAuthAccountChanged` (5.4+)

The caches are cleared *before* the event is raised, so every `Product` and `Order` reference you
held is stale and both getters return empty inside the handler. Re-run the fetch instead of reading:

```csharp
store.OnAuthAccountChanged += async () =>
{
    await catalogProvider.FetchRemoteCatalog();   // payment-provider path only
    store.FetchProducts(productDefinitions);
    store.FetchPurchases();
};
```

## Receipt validation

### Google Play — local

```csharp
using UnityEngine.Purchasing.Security;

var validator = new CrossPlatformValidator(GooglePlayTangle.Data(), Application.identifier);

try
{
    var result = validator.Validate(order.Info.Receipt);
    foreach (IPurchaseReceipt receipt in result)
    {
        Debug.Log($"Valid: {receipt.productID}, purchased {receipt.purchaseDate}");
        if (receipt is GooglePlayReceipt googleReceipt)
            Debug.Log($"Token: {googleReceipt.purchaseToken}");
    }
}
catch (IAPSecurityException ex)
{
    Debug.LogError($"Invalid receipt: {ex.Message}");
    // grant nothing
}
```

Constructors:

```csharp
new CrossPlatformValidator(byte[] googlePublicKey, string googleBundleId)                                  // Google-only
new CrossPlatformValidator(byte[] googlePublicKey, byte[] appleRootCert, string googleBundleId, string appleBundleId)  // legacy 4-arg
IPurchaseReceipt[] Validate(string unityIAPReceipt)   // throws IAPSecurityException
```

Both of those are current. The older constructors that share one bundle ID between Apple and Google
are `[Obsolete]`. `"GooglePlay"` is the store this class still
validates for; `"AppleAppStore"` and `"MacAppStore"` are deprecated here.

### Apple — server-side

The Apple half of `CrossPlatformValidator` is inert under StoreKit 2: it returns an empty array
rather than throwing, so a caller written to "grant unless it throws" grants everything and a caller
written to "grant if the array is non-empty" grants nothing. `AppleTangle.Data()` is deprecated for
the same reason. Send the signed transaction to a server instead:

```csharp
var jws = order.Info.Apple?.jwsRepresentation;
// verify against Apple's App Store Server API on your backend
```

### `IAppleOrderInfo`

`order.Info.Apple` is `IAppleOrderInfo?` and is `null` everywhere except Apple platforms.

| Member | Type | Holds |
|---|---|---|
| `jwsRepresentation` | `string?` | The JWS-signed transaction — the input to server-side validation |
| `AppAccountToken` | `Guid?` | Whatever was passed to `SetAppAccountToken(Guid)`, linking the transaction to your user |
| `AppReceipt` | `string?` | Base64 app receipt. Can be null after a reinstall until refreshed. Prefer the JWS |
| `OriginalTransactionID` | `string?` | Links a renewal back to the original subscription purchase |
| `OwnershipType` | `OwnershipType` | `Purchased` or `FamilyShared` |
| `StoreName` | `string` | e.g. `"AppleAppStore"` |

## Events that live on the extended services, not on `StoreController`

`?.` cannot be used with `+=`, so these need an `if`.

```csharp
// Apple — IAppleStoreExtendedPurchaseService
event Action<string>? OnEntitlementRevoked            // a product ID, not a List<Product>
event Action<Product>? OnPromotionalPurchaseIntercepted

// Google — IGooglePlayStoreExtendedPurchaseService
event Action<DeferredPaymentUntilRenewalDateOrder>? OnDeferredPaymentUntilRenewalDate
// that order carries .CurrentOrder (Order) and .SubscriptionOrdered (Product)

if (store.AppleStoreExtendedPurchaseService != null)
    store.AppleStoreExtendedPurchaseService.OnEntitlementRevoked += OnRevoked;
```

## `IAppleStoreExtendedProductService`

```csharp
Dictionary<string, string> GetIntroductoryPriceDictionary()
Dictionary<string, string> GetProductDetails()

void SetStorePromotionOrder(List<string> catalogListingIds)    // canonical from 5.4
void SetStorePromotionOrder(List<Product> products)            // convenience

void SetStorePromotionVisibility(string catalogListingId, AppleStorePromotionVisibility visible)   // canonical from 5.4
void SetStorePromotionVisibility(Product product, AppleStorePromotionVisibility visible)           // convenience

void FetchStorePromotionOrder(Action<List<Product>> onOk, Action<string> onError)
void FetchStorePromotionVisibility(string catalogListingId, Action<string, AppleStorePromotionVisibility> onOk, Action<string> onError)
void FetchStorePromotionVisibility(Product product, Action<string, AppleStorePromotionVisibility> onOk, Action<string> onError)
```

> **`AppleProductMetadata` is thinner than it looks.** Beyond what it inherits from
> `ProductMetadata` its only public property is `isFamilyShareable` — `introductoryPrice`,
> `introductoryPriceLocale`, `introductoryNumberOfPeriods` and `subscriptionPeriod` are not on it.
> Introductory pricing comes from `SubscriptionInfo` (`GetIntroductoryPrice()`,
> `GetIntroductoryPricePeriod()`, `GetIntroductoryPricePeriodCycles()`), or from
> `GetIntroductoryPriceDictionary()` as raw JSON.

## Subscription info — the access path

```csharp
// The one that compiles
var purchasedInfo = order.Info.PurchasedProductInfo?.FirstOrDefault(p => p.productId == productId);
bool isSubscribed = purchasedInfo?.subscriptionInfo?.IsSubscribed() == Result.True;

// The one that does not: CartItem carries Product and Quantity, nothing else
order.CartOrdered.Items().FirstOrDefault().subscriptionInfo;   // no such member
```

`Result` is a three-state enum, so `== Result.True` is the comparison: it is null-safe across the
whole chain and it does not turn `Unsupported` into a yes. `?? false` will not compile against
`Result?`.

```csharp
// State — each returns Result: True | False | Unsupported
Result IsSubscribed()
Result IsExpired()
Result IsCancelled()
Result IsFreeTrial()
Result IsAutoRenewing()
Result IsIntroductoryPricePeriod()

// Dates and durations
string   GetProductId()
DateTime GetPurchaseDate()
DateTime GetExpireDate()
DateTime GetCancelDate()
TimeSpan GetRemainingTime()
TimeSpan GetSubscriptionPeriod()
TimeSpan GetFreeTrialPeriod()
TimeSpan GetIntroductoryPricePeriod()
string   GetIntroductoryPrice()
long     GetIntroductoryPricePeriodCycles()
```

## Failure description property names

Some of these types carry lowercase fields alongside the PascalCase properties; where both exist,
both compile and the properties are the ones to prefer. The trap is assuming one type's spelling
holds for the next.

| Type | Fields | Properties | Not present |
|---|---|---|---|
| `StoreConnectionFailureDescription` | `.message` | `.Message` | `.reason` |
| `ProductFetchFailed` | — | `.FailureReason`, `.FailedFetchProducts` | `.Message` |
| `FailedOrder` | — | `.FailureReason`, `.Details` | — |
| `PurchasesFetchFailureDescription` | `.message`, `.failureReason` | `.Message`, `.FailureReason` | — |

## Interface split

```
StoreController implements
  IStoreService     Connect(), the Apple/Google service extensions
  IProductService   FetchProducts(), GetProducts(), GetProductById()
  IPurchaseService  PurchaseProduct(), ConfirmPurchase(), FetchPurchases(), the purchase extensions
```

## A minimal fetch, end to end

```csharp
using UnityEngine;
using UnityEngine.Purchasing;
using System.Collections.Generic;

public static class FetchProductsExample
{
    // Store callbacks land after Connect() has returned, so Run() reports through the
    // console rather than a return value.
    public static async void Run()
    {
        var store = UnityIAPServices.StoreController();

        store.OnStoreConnected += () =>
        {
            var products = new List<ProductDefinition>
            {
                new ProductDefinition("com.mygame.coins100",  ProductType.Consumable),
                new ProductDefinition("com.mygame.removeads", ProductType.NonConsumable)
            };

            store.OnProductsFetched += (fetched) =>
            {
                foreach (var p in fetched)
                    Debug.Log($"{p.definition.id}: {p.metadata.localizedPriceString}");
            };
            store.OnProductsFetchFailed += (failure) => Debug.LogError($"Product fetch failed: {failure.FailureReason}");

            store.FetchProducts(products);
        };
        store.OnStoreDisconnected += (failure) => Debug.LogError($"Store disconnected: {failure.Message}");

        await store.Connect();
    }
}
```
