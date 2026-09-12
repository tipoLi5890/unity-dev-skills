# Pre-check — what is already billing, and where that sends you

Two billing systems on one device is not a configuration to tune; it is a bug that eats purchases.
Android's `PurchasesUpdatedListener` and iOS's `SKPaymentQueue` observer both hand a transaction to
exactly one listener, and the other one never learns the purchase happened. So the first question is
never "how do I add IAP" but "what is here already".

Run the scan below before opening another file in this skill and before editing anything. The first
match wins — stop scanning at that point and route.

## When the request itself is ambiguous

"Set up IAP", "add a purchase manager", "upgrade IAP to the latest" do not say which billing backend
is meant. Two very different implementations answer to them: platform billing (Apple App Store /
Google Play) and a third-party payment provider reached through Unity Cloud (Stripe, Coda).

Ask which one, and wait for the answer. Do not pick a default — the wrong guess is a full
re-implementation, not a tweak.

## If the answer is the third-party payment provider

That path does not follow the scan order below.

- Something else is already billing — v4, a native bridge, a third-party SDK — clear that first with
  the scan, then come back.
- No IAP at all, or `com.unity.purchasing` **5.4+** → [`path-implement-iap-d2c.md`](path-implement-iap-d2c.md).
- `com.unity.purchasing` **5.0–5.3** → the payment-provider surface does not exist in those
  versions; 5.4 is the floor the payment-provider documentation names. Say so, ask for a Package
  Manager upgrade to 5.4+, and continue once it is confirmed.

## The scan

### 1. Third-party billing SDKs

These bring their own native billing and their own conversion story. Each match routes to exactly
one file — say which SDK was found and which path applies.

| Look for | Where | Route |
|---|---|---|
| `com.voxelbusters.essentialkit` | `Packages/manifest.json`, `Packages/packages-lock.json` | [`convert-essentialkit.md`](convert-essentialkit.md) |
| `com\.flobuk\.unipay`, `UniPay`, `Assets/Plugins/UniPay`, `Assets/Plugins/SIS` | manifest, lockfile, `Assets/Plugins/` | [`convert-unipay.md`](convert-unipay.md) |
| `com.revenuecat.purchases-unity` | manifest, lockfile | [`convert-revenuecat.md`](convert-revenuecat.md) |
| `com\.adapty`, `Assets/Adapty`, `AdaptySDK` | manifest, lockfile, `Assets/` | [`convert-adapty.md`](convert-adapty.md) |

### 2. A native Google Play Billing bridge

```
Assets/**/*.cs            AndroidJavaObject|AndroidJavaClass|BillingClient|BillingManager|GoogleBilling|BillingBridge
Assets/Plugins/Android/**/*.java, *.kt   com\.android\.billingclient
*Template.gradle          com\.android\.billingclient:billing
```

→ [`path-convert-native-google-billing.md`](path-convert-native-google-billing.md). If
`com.unity.purchasing` is missing or old, that is a Package Manager step for the user before the
conversion starts.

### 3. A native iOS StoreKit plugin

```
Assets/Plugins/iOS/**/*.m, *.mm, *.h, *.swift
    SKProductsRequest|SKPaymentQueue|SKPaymentTransaction|SKPaymentTransactionObserver
    Product\.products|Transaction\.currentEntitlements
Assets/**/*.cs
    DllImport.*__Internal  (alongside purchase-shaped method names)
    UnitySendMessage       (with StoreKit callbacks on the other end)
```

→ [`path-convert-native-storekit.md`](path-convert-native-storekit.md).

### 4. Unity IAP v4

`com.unity.purchasing` at a `4.` version in `Packages/manifest.json`, or the v4 API still in the
source:

```
IStoreListener|UnityPurchasing\.Initialize|ConfigurationBuilder
```

Either signal is enough — a v5 package with v4 code in it is still a v4 project as far as the work
goes. → [`migration-v4-to-v5.md`](migration-v4-to-v5.md).

### 5. Unity IAP v5 already present

`com.unity.purchasing` at a `5.` version and none of the above matched. There is nothing to migrate,
so do not send this to the greenfield path — ask what should change. Adding products, adding a
platform feature, and adding a payment provider are three different jobs on the same working
integration.

### 6. Nothing

No `com.unity.purchasing`, no bridge, no third-party SDK →
[`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md).

## Routing table

| Detected | Path |
|---|---|
| Essential Kit | [`convert-essentialkit.md`](convert-essentialkit.md) |
| UniPay | [`convert-unipay.md`](convert-unipay.md) |
| RevenueCat | [`convert-revenuecat.md`](convert-revenuecat.md) |
| Adapty | [`convert-adapty.md`](convert-adapty.md) |
| Native Google BillingClient | [`path-convert-native-google-billing.md`](path-convert-native-google-billing.md) |
| Native iOS StoreKit plugin | [`path-convert-native-storekit.md`](path-convert-native-storekit.md) |
| `com.unity.purchasing` 4.x, or v4 API in code | [`migration-v4-to-v5.md`](migration-v4-to-v5.md) |
| `com.unity.purchasing` 5.x, clean | Ask what to extend |
| Nothing | [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md) |
| Third-party payment provider requested | [`path-implement-iap-d2c.md`](path-implement-iap-d2c.md) |

## One more thing to check, whichever route won

Does `Assets/Resources/IAPProductCatalog.json` exist, and is `enableCodelessAutoInitialization`
true in it?

That combination is independent of everything above and it does not block any route — but a
non-empty catalogue with auto-init on will bring up its own store connection alongside any
`StoreController` you write, and the two race. Surface it before generating scripted IAP code;
[`codeless-catalog.md`](codeless-catalog.md) has the symptoms and the three ways out.
