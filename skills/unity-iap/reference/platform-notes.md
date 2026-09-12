# Apple and Google, where the two stores stop agreeing

The extended services are plain properties, and each is `null` on every platform it does not belong
to — including the Editor, where all five are null.

| Service | iOS | Android | Editor |
|---|---|---|---|
| `AppleStoreExtendedService` | present | `null` | `null` |
| `AppleStoreExtendedProductService` | present | `null` | `null` |
| `AppleStoreExtendedPurchaseService` | present | `null` | `null` |
| `GooglePlayStoreExtendedService` | `null` | present | `null` |
| `GooglePlayStoreExtendedPurchaseService` | `null` | present | `null` |

> **`?.` does not work with `+=`.** Subscribing to an event on an extended service needs a real
> null test, not a null-conditional:
>
> ```csharp
> if (store.AppleStoreExtendedPurchaseService != null)
>     store.AppleStoreExtendedPurchaseService.OnPromotionalPurchaseIntercepted += HandlePromo;
> ```
>
> Calling a *method* through `?.` is fine. It is only the event subscription that needs the `if`.

## Apple

### Promotional purchases

Apple can start a purchase from the App Store product page, before your game is even open. If you
intercept it, you own it:

```csharp
if (store.AppleStoreExtendedPurchaseService != null)
{
    store.AppleStoreExtendedPurchaseService.OnPromotionalPurchaseIntercepted += (product) =>
    {
        Debug.Log($"Promotional purchase intercepted: {product.definition.id}");
        // Load a scene, show a confirmation, whatever the game needs first — then release it:
        store.AppleStoreExtendedPurchaseService.ContinuePromotionalPurchases();
    };
}
```

> **An interception that is never continued hangs forever.** `ContinuePromotionalPurchases()` is
> the only way the transaction resumes. Subscribing to the event and then returning early on any
> code path — an error, a scene load that fails, a guard clause — strands the purchase.

### Ask-to-Buy

A child account under Family Sharing needs a parent's approval, and the purchase arrives twice: once
as deferred, later as pending.

```csharp
store.OnPurchaseDeferred += (deferredOrder) =>
{
    // Show "waiting for approval". Grant nothing.
};
```

Approval brings it back through `OnPurchasePending`; rejection ends it. To exercise the path in a
sandbox build:

```csharp
store.AppleStoreExtendedPurchaseService.simulateAskToBuy = true;
```

### Offer codes

```csharp
store.AppleStoreExtendedPurchaseService?.PresentCodeRedemptionSheet();
```

### Revocation

A refund takes an entitlement back, and Apple tells you which product by ID — a `string`, not a
product:

```csharp
store.AppleStoreExtendedPurchaseService.OnEntitlementRevoked += (productId) =>
{
    // Remove the feature. The player has been refunded.
};
```

### Store capabilities

All three are post-`Connect()` calls.

```csharp
bool canPay = store.AppleStoreExtendedService.canMakePayments;      // parental controls can say no

store.AppleStoreExtendedService.SetAppAccountToken(Guid.NewGuid()); // surfaces in the JWS payload

store.AppleStoreExtendedService.FetchStorefront(
    (storefront) => Debug.Log($"Storefront: {storefront.CountryCode}"),
    (error)      => Debug.LogError($"Storefront error: {error}"));
```

## Google Play

### Changing a subscription tier

Upgrades and downgrades take the current *order* and the new *product*, not two IDs:

```csharp
Order   currentOrder = /* the player's active subscription order */;
Product newProduct   = store.GetProductById("com.mygame.vip_annual");

store.GooglePlayStoreExtendedPurchaseService.UpgradeDowngradeSubscription(
    currentOrder,
    newProduct,
    GooglePlayReplacementMode.ChargeFullPrice);
```

The replacement mode decides who pays what and when — it is a pricing decision, not a technical one,
so pick it deliberately:

| Mode | What happens |
|---|---|
| `UnknownReplacementMode` | Default |
| `WithTimeProration` | Remaining time is adjusted |
| `ChargeProratedPrice` | Prorated charge now for the upgrade |
| `WithoutProration` | New plan takes effect at the next billing date |
| `ChargeFullPrice` | Full price charged immediately |
| `Deferred` | The change lands at the next billing date |

`GooglePlayProrationMode` is the deprecated predecessor — the third parameter is a
`GooglePlayReplacementMode`.

### Obfuscated IDs

Google uses these for fraud signals. They moved from configuration time to post-`Connect()`:

```csharp
store.GooglePlayStoreExtendedService?.SetObfuscatedAccountId("hashed_account_id");
store.GooglePlayStoreExtendedService?.SetObfuscatedProfileId("hashed_profile_id");

string accountId = store.GooglePlayStoreExtendedPurchaseService?.GetObfuscatedAccountId(order);
string profileId = store.GooglePlayStoreExtendedPurchaseService?.GetObfuscatedProfileId(order);
```

### Payment deferred to the renewal date

```csharp
store.GooglePlayStoreExtendedPurchaseService.OnDeferredPaymentUntilRenewalDate += (deferredOrder) =>
{
    Debug.Log($"Payment deferred until renewal: {deferredOrder.SubscriptionOrdered.definition.id}");
};
```

## Server-side Apple validation

The signed transaction is on the pending order, and it is per-transaction — not an app-wide receipt
bundle:

```csharp
store.OnPurchasePending += (pendingOrder) =>
{
    string jws = pendingOrder.Info.Apple?.jwsRepresentation;
    ValidateOnServer(jws);   // Apple's App Store Server API verifies the signature
};
```

Where the grant itself should happen once that server answers is `unity-live-services`.

## The same subscription method, two different answers

| Method | Apple returns | Google returns |
|---|---|---|
| `GetPurchaseDate()` | The most recent renewal date | The original purchase date |
| `GetCancelDate()` | The real cancellation date | `DateTime.MinValue` — not supported |

So "how long has this player been subscribed" is not one expression across both stores. Ask
`IsSubscribed()` first: a `Result.Unsupported` means the platform does not carry that answer at all,
and treating it as `False` is how a paying subscriber loses access.

## Carrying both stores at once

| Concern | Where it lands |
|---|---|
| Restore button | Required on iOS. Wire it to `store.RestoreTransactions()`, and show it only when the catalogue has a non-consumable or a subscription |
| Receipt validation | Google Play locally via `CrossPlatformValidator(GooglePlayTangle.Data(), Application.identifier)`; Apple on a server from `order.Info.Apple?.jwsRepresentation`, because local Apple validation is inert under StoreKit 2 |
| Pending purchases | One handler, both stores: grant, save, then `ConfirmPurchase`. Anything unconfirmed outlives the process |
| Product IDs | Reverse domain, one canonical ID, store overrides through `StoreSpecificIds` rather than a second catalogue |
| Testing | Apple sandbox accounts and Google licence-test accounts. Neither charges, and neither behaves quite like production |
| Subscriptions | Re-check at every launch. They expire, get cancelled from the store's own UI, and get refunded, and none of that notifies the running app |
