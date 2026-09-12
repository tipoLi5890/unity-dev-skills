# Selling through a third-party payment provider

The direct-to-customer path: checkout runs through Stripe or Coda via Unity Cloud rather than
through the App Store or Google Play. It is a different `StoreController`, a different catalogue, and
a compliance problem the platform holders own — not a variant of the standard flow.

Reachable only when the project has no IAP or already has `com.unity.purchasing` 5.x. IAP v4, a
native bridge or a third-party billing SDK has to be resolved first — [`pre-check.md`](pre-check.md).

## Prerequisites — check all of them before writing anything

| Requirement | Detail |
|---|---|
| Unity Editor | 2022.3 or later |
| `com.unity.purchasing` | 5.4+ |
| `com.unity.services.authentication` | 3.7.1+ — initialisation fails below this |
| `com.unity.services.core` | 1.18.0+ |
| Live services initialised | `UnityServices.InitializeAsync()` and sign-in both complete **before** the payment-provider controller is created |
| Deployment package | Needed to push catalogues to the Remote Catalog — **Window > Package Manager > Unity Registry > Deployment** |
| Unity Cloud project linked | To an organisation |
| Provider account | Stripe or Coda connected in the Unity Cloud IAP dashboard |
| Catalogue deployed | Products created and deployed to the Remote Catalog, or the client fetches nothing |

Any of these missing is a stop. List what is missing and wait. Confirm the version floors against the
current payment-provider documentation before asking for a package upgrade — moving a services
package is the user's call.

## 1. Scan

**Existing IAP** — `com.unity.purchasing` in `Packages/manifest.json`:

- 5.4+ → the payment provider is added alongside;
- 5.0–5.3 → that surface does not exist; ask for an upgrade and continue once confirmed;
- absent → added fresh.

**Authentication** — `com.unity.services.authentication` in the manifest. Without a signed-in player
nothing initialises.

**What a purchase credits** — `Assets/**/*.cs`:

```
\bcoins\b|\bgems\b|\blives\b|\binventory\b|\bcurrency\b
PlayerData|SaveAsync|CloudSave|SaveDataAsync|SaveGame
```

**Where the shop is** — `.unity` and `.prefab` for `Shop|Store|Purchase|Buy|IAP|Product`.

## 2. The catalogue

**`.ucat` files already present** — use them.

**Existing `ProductDefinition` objects** — those are local store products. The payment-provider path
reads a remote catalogue instead, so they have to be re-created as `.ucat` files and deployed; keep
the IDs identical, or the purchase history stops matching.

**Nothing** — stop and ask:

> Which product ID and type should the first one be — `com.mygame.coins100` as a Consumable, say —
> and what should it credit?

Default to Consumable if no type is given, and say so. **Subscriptions are not supported on this
path in 5.4+**: exclude them, name the ones excluded, and continue with the consumables and
non-consumables. If nothing survives the exclusion, stop.

### The `.ucat` file

One product per file, JSON, anywhere under `Assets/`. The local shape is `CatalogItem`; the upload
converts it into the wire DTO — the two differ, and the differences below are where a "correct" file
uploads wrong.

**The filename carries two identifiers.** On load:

- **`CatalogListingId` is always `"catalog/" + <filename stem>`.** This is what
  `PurchaseProduct(catalogListingId)` takes and what the remote catalogue matches. It is never
  written in the JSON body — the property carries `[IgnoreDataMember, JsonIgnore]`, so the field is
  ignored on both read and write, and the `catalog/` prefix is the SDK's, not yours.
- **`uSKU` is the JSON field if present, otherwise the filename stem.** Omit it when they should
  match, which is the common case; include it only when the store SKU has to differ, such as a
  legacy ID nobody can rename. On save, a `uSKU` equal to the stem is stripped out again.

So `coins_100.ucat` with no `uSKU` gives `uSKU = "coins_100"` and
`CatalogListingId = "catalog/coins_100"` with nothing written down.

```json
{
  "type": "Consumable",
  "productDetails": [
    {
      "language": "en_US",
      "title": "100 Coins",
      "subtitle": "Best value",
      "description": "A pack of 100 coins.",
      "badge": { "text": "Popular", "imageUrl": "https://example.com/badges/popular.png" }
    }
  ],
  "pricing": [
    { "currencyCode": "USD", "amount": 1.99 },
    { "currencyCode": "EUR", "amount": 1.79, "webshopPrice": 1.49 }
  ],
  "imageUrl": "https://example.com/img/coins100.png",
  "storeIdOverrides": [
    { "store": "apple",  "value": "com.mygame.coins100.ios" },
    { "store": "google", "value": "com.mygame.coins100.android" }
  ],
  "isWebshopAvailable": true,
  "categories": ["currency", "starter"],
  "hdImages": [
    { "url": "https://example.com/hd/coins100.png", "altText": "100 coins bundle" }
  ],
  "promotion": {
    "type": "Sale",
    "startsAt": "YYYY-MM-DDTHH:MM:SSZ",
    "endsAt": "YYYY-MM-DDTHH:MM:SSZ"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `uSKU` | string | | The product ID. Defaults to the filename stem — include it only to override. `^[a-zA-Z0-9._-]+$`, max 141 chars |
| `type` | enum | yes | `Consumable`, `NonConsumable`, `Subscription` |
| `productDetails` | array | yes | At least one entry |
| `pricing` | array | yes | At least one entry |
| `imageUrl` | string | | HTTPS, max 2048 chars |
| `storeIdOverrides` | array | | Per-store SKUs |
| `isWebshopAvailable` | bool | | **Local only, never uploaded.** True adds the webshop `$schema` and emits the three webshop fields; false strips them on upload and erases the server-side webshop data |
| `categories` | string[] | | Webshop taxonomy, only meaningful with the toggle on |
| `hdImages` | array | | Webshop hero images, same |
| `promotion` | object | | Webshop promotion overlay, same |

Sub-shapes: `productDetails[]` is `language` (required enum), `title` (required, 1–50), `subtitle`
(1–50), `description` (1–250), `badge` (`text` required, `imageUrl` optional HTTPS).
`pricing[]` is `currencyCode` (ISO 4217), `amount` (decimal **major units** — `1.99`, not micros),
`webshopPrice` (major units, only when the webshop price differs; below `0.001` counts as unset).
`storeIdOverrides[]` is `store` (`apple`, `google`, `xbox`, `applemacos`) and `value`.
`hdImages[]` is `url` (HTTPS) and `altText`. `promotion` is `type` (`Sale`, `Bonus`, `Limited`),
`startsAt` and `endsAt` (ISO 8601 UTC).

**What the upload changes.** `LiveContentConfigClient.ConvertToDto` is not a pass-through:

- `amount` and `webshopPrice` go from decimal major units on disk to **micros integer** on the wire
  — `1.99` becomes `1990000`, rounded `AwayFromZero`.
- `$schema` is added by the SDK and never appears on disk. Always the `UnityRemoteCatalog` 1.1.0
  URL; plus the `UnityRemoteCatalogWebshop` 1.1.0 URL when the webshop toggle is on.
- `isWebshopAvailable` is never uploaded — the server infers webshop-ness from `$schema`.
- `categories`, `hdImages` and `promotion` go up only with the toggle on. Turning it off and
  re-uploading **erases** what the server had.

### The `.catalog.csv` alternative

One file for the whole catalogue, anywhere under `Assets/`, parsed by `CatalogCsvParser`. Rows
aggregate by `CatalogListingId` into the same model, so the uploaded result is identical to the
`.ucat` route.

| Column | Maps to | Aggregation |
|---|---|---|
| `CatalogListingId` | Row identity. If filled in it **must** carry the `catalog/` prefix. Blank means the parser derives `"catalog/" + Sku` | per item |
| `Sku` | `uSKU`. Required; also seeds the listing ID when the first column is blank | per item |
| `ProductType` | `type` | per item |
| `Language` | `productDetails[].language` | per row |
| `Title` | `productDetails[].title` | per row |
| `Subtitle` | `productDetails[].subtitle` | per row |
| `Description` | `productDetails[].description` | per row |
| `BadgeText` | `productDetails[].badge.text` | per row |
| `BadgeImageUrl` | `productDetails[].badge.imageUrl` | per row |
| `CurrencyCode` | `pricing[].currencyCode` | per row |
| `Amount` | `pricing[].amount`, major units | per row |
| `WebshopPrice` | `pricing[].webshopPrice`, major units | per row |
| `ImageUrl` | `imageUrl` | per item |
| `GoogleOverride` | `storeIdOverrides[store="google"].value` | per item |
| `AppleOverride` | `storeIdOverrides[store="apple"].value` | per item |
| `XboxStoreOverride` | `storeIdOverrides[store="xbox"].value` | per item |
| `MacAppStoreOverride` | `storeIdOverrides[store="applemacos"].value` | per item |
| `IsWebshopAvailable` | `isWebshopAvailable` | per item |
| `Category` | one `categories[]` entry | per row, aggregated |
| `HdImageUrl` | one `hdImages[].url` | per row, aggregated |
| `HdImageAltText` | `hdImages[].altText` | per row, aggregated |
| `PromotionType` | `promotion.type` | per item — first row wins, later disagreement is flagged |
| `PromotionStartsAt` | `promotion.startsAt` | per item, first row wins |
| `PromotionEndsAt` | `promotion.endsAt` | per item, first row wins |

Per-item columns are read from the first row of a listing and conflict-checked on the rest. Plain
per-row columns each contribute one `productDetails` or `pricing` entry. The three aggregated
columns each contribute one array element per row.

```csv
CatalogListingId,Sku,ProductType,Language,Title,Description,CurrencyCode,Amount,ImageUrl
,com.mygame.coins100,Consumable,en_US,100 Coins,A pack of 100 coins.,USD,1.99,https://example.com/img/coins100.png
,com.mygame.coins100,Consumable,fr_FR,100 Pièces,Un lot de 100 pièces.,EUR,1.79,
```

The blank first column is deliberate — the parser derives `catalog/com.mygame.coins100`. Filling it
in with a bare `coins_100` fails validation: a catalog listing ID has to start with `catalog/`.

## 3. Deploying the catalogue

Files under `Assets/` are local definitions and nothing else. Until they are deployed to the Remote
Catalog for the active environment, `FetchRemoteCatalog()` returns nothing and no purchase can
start. Deploy **before** writing or running the client code below.

1. **Services > Deployment** in the Editor. If the menu is not there, the Deployment package is not
   installed — **Window > Package Manager > Unity Registry > Deployment**.
2. The window lists the `.ucat` and `.catalog.csv` files it found.
3. Select them and deploy.
4. Each one is marked deployed, and the client can now fetch them.

The target is whichever environment is selected in **Edit > Project Settings > Services >
Environments**. Moving a catalogue between environments means switching and re-deploying. Environment
setup, project linking and multi-environment workflow are `unity-ugs`.

## 4. The controller

The one API difference at the entry point:

```csharp
_storeController = UnityIAPServices.StoreController();                    // platform billing
_storeController = UnityIAPServices.StoreController(PaymentProvider.Name); // payment provider
```

`PaymentProvider.Name` is a constant identifying the integration. It is not the provider's display
name, and it is not "Stripe".

### Order of initialisation

1. `await UnityServices.InitializeAsync()`
2. Sign the player in
3. Only then: `StoreController(PaymentProvider.Name)` and `Connect()`

> **Do not sign in anonymously for this.** An anonymous session's purchases do not survive the loss
> of its token — a reinstall or a cleared app data leaves the player with an unrecoverable purchase
> history and you with a refund request you cannot answer. Use a persistent identity.

### The two service properties

The payment-provider APIs hang off the controller under two properties, and the naming is not
symmetrical. Do not substitute the interface name for the property name, and do not reach for
`PurchaseService.PaymentProviders` — that is a different entry point returning the purchase-extended
interface.

| Property | Interface | Used for |
|---|---|---|
| `store.PaymentProviderStoreExtendedService` | `IPaymentProvidersExtendedService` | `GetEligiblePaymentProviders`, `GetPaymentOptionProviderUGUI`, `GetPaymentOptionProviderUITK`, `SetCheckoutPresentationMode`, `SetWebshopPresentationMode`, `SetDeepLinkScheme` |
| `store.PaymentProvidersExtendedPurchaseService` | `IPaymentProvidersExtendedPurchaseService` | `PurchaseProduct`, `RedirectToWebshop`, `GenerateURL`, `SetComplianceCheck`, `SetPaymentProviderOverride` |

Singular on the presentation side, plural on the purchase side — mirroring the Apple and Google
`...ExtendedService` / `...ExtendedPurchaseService` split. Both are typed nullable, but on a
controller scoped to `PaymentProvider.Name` the factory always fills them; they are null only when
reached from a controller scoped to Apple or Google. Guard with `?.` where one code path can see
either kind.

### Living beside an existing Apple / Google controller

- **Build a second, separate controller.** Never repurpose the existing one.
- They are independent: different products, different backends, no interference.
- Once the new one connects, ask:

  > An existing Apple/Google `StoreController` was found. Keep both — platform billing and the
  > payment provider side by side — or retire the Apple/Google one and move everything across?

- **Keep both**: leave the existing controller and its initialisation untouched, and document the
  dual setup in a comment where the next reader will find it.
- **Retire it**: wrap it in `#if !USE_IAP_D2C_ONLY` rather than deleting it, mark it `[Obsolete]`,
  and note that the corresponding products may need retiring in App Store Connect and the Play
  Console too.

### Is there anything to sell through

Call this after `Connect()` and the product fetch:

```csharp
var svc = store.PaymentProviderStoreExtendedService;
if (svc == null) return;                       // no payment-provider service — hide the UI

var eligible = await svc.GetEligiblePaymentProviders();
if (eligible == null || eligible.Providers.Count == 0) return;   // nothing available here

if (!eligible.PaymentOptionPopupEnabled)
{
    // One provider, and the server says not to show a picker — go straight through
}
```

`Providers` is priority-ordered. An empty list means no routing rule matches this player, or no
provider serves their region. `PaymentOptionPopupEnabled` is a server-side switch for suppressing
the picker.

### The built-in picker

5.4 ships a purchase-options UI covering native billing, the payment provider and the webshop.
`ShowPurchaseOption` is the intended entry point for this path.

```csharp
// once, after connect
var m_PaymentOptionProvider = store.PaymentProviderStoreExtendedService?.GetPaymentOptionProviderUGUI();
// or, for UI Toolkit:
var m_PaymentOptionProvider = store.PaymentProviderStoreExtendedService?.GetPaymentOptionProviderUITK(hostDocument);

public async void Buy(string catalogListingId)
{
    var svc = store.PaymentProviderStoreExtendedService;
    var eligibility = svc != null ? await svc.GetEligiblePaymentProviders() : null;

    if (eligibility?.Providers.Count > 0)
    {
        await m_PaymentOptionProvider.ShowPurchaseOption(catalogListingId);
    }
    else if (m_NativeStore != null)
    {
        // `store` is scoped to PaymentProvider.Name, so PurchaseProduct on it routes through the
        // provider regardless. A native fallback has to be a separately scoped controller the app
        // kept alive — see the coexistence section above.
        m_NativeStore.PurchaseProduct(catalogListingId);
    }
    else
    {
        Debug.LogWarning($"No payment path available for {catalogListingId}.");
    }
}
```

> **A provider-scoped controller has no native fallback in it.** `PurchaseProduct` on that
> controller goes through the payment provider whatever the eligibility said. Reaching platform
> billing needs a controller built with the default constructor. A project that already has one
> should reuse it; a payment-provider-only project has no fallback and should surface "payment
> unavailable" rather than pretending.

### Reading the picker's answer

`ShowPurchaseOption(catalogListingId)` returns `Task<string?>`, naming what the player chose:

- `IPaymentOptionProvider.NativeAlias` (`"native"`) — the platform default at the moment of the tap;
- `IPaymentOptionProvider.WebshopAlias` (`"webshop"`) — the webshop button, which only appears when
  the listing has one;
- a provider identifier (`"stripe"`, `"codapay"`, …);
- `null` — dismissed.

The cross-product overload `ShowPurchaseOption(IReadOnlyList<PurchaseOption>)` returns
`Task<PurchaseOption?>`, each option being `(StoreName, CatalogListingId, Badge?)`. Failures come
back as `PurchaseChoiceFailedException` on the awaited task, carrying the `PurchaseOption` and the
inner exception.

### The picker remembers

The SDK remembers which provider a player last used on that device and pre-selects it. This is
deliberate, and it has three consequences worth knowing before someone files it as a bug:

- A picker that seems to skip its options is a player with a remembered provider.
- After changing providers in the dashboard, a test device keeps routing to the old one. Clear the
  app's data to reset it.
- There is no runtime API to clear or override the memory. A UX that must always show the full list
  needs a "change payment method" affordance that re-invokes `ShowPurchaseOption` — the remembered
  provider is still pre-selected, but the player can move off it.

### What the manager owns

Everything from [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md) §4, plus:

- the `PaymentProvider.Name`-scoped controller;
- the `IPaymentOptionProvider`, matching the project's UI system;
- `Buy(string catalogListingId)`;
- `RestorePurchases()` only if there are non-consumables;
- initialisation and sign-in completing before the controller exists;
- `GetEligiblePaymentProviders()` after connect, gating the purchase UI.

Only automatic entitlement delivery is supported here. Do not build server-authoritative grant logic
on this path unless asked for it.

## 5. The remote catalogue at runtime

Products come from Unity Cloud, not a local list:

```csharp
var catalogProvider = new RemoteCatalogProvider();

var result = await catalogProvider.FetchRemoteCatalog();
if (!result.Success)
    throw result.Exception;

var productDefinitions = catalogProvider.GetProducts();
_storeController.FetchProducts(productDefinitions);
```

`FetchRemoteCatalog` takes no arguments and reads the environment selected in Project Settings. Call
it after `Connect()` succeeds. `GetProducts()` hands back a `List<ProductDefinition>` that goes
straight into `FetchProducts()`. A false `Success` is a stop, not a warning.

### Several offers on one product

A product can carry more than one purchasable listing — regional pricing, promotions. Each has its
own `catalogListingId`.

```csharp
var product = _storeController.GetProductByCatalogListingId("catalog/coins_100_offer_usd");
if (product != null
    && product.catalogListings.TryGetValue("catalog/coins_100_offer_usd", out var listing)
    && listing.availableToPurchase)
{
    // listing.definition — ProductDefinition
    // listing.metadata   — ProductMetadata: title, localizedPriceString, …
    _storeController.PaymentProvidersExtendedPurchaseService?
        .PurchaseProduct("catalog/coins_100_offer_usd", PaymentProvider.Name);
}
```

Where every product has exactly one offer, `GetProductById(uSKU)` is enough and none of this is
needed.

```csharp
void OnProductsFetched(List<Product> products)
{
    foreach (var product in products)
        foreach (var catalogListing in product.catalogListings.Values)
            Debug.Log($"ID: {catalogListing.definition.id} - Price: {catalogListing.metadata.localizedPriceString}");
}
```

`catalogListings` is a `Dictionary<string, CatalogListing>` keyed by listing ID.

### Webshop-aware metadata

Products fetched through this store carry an extended metadata type:

```csharp
var pspMeta = product.metadata.GetPaymentProviderProductMetadata();
if (pspMeta?.hasWebshop == true)
{
    var webshopPrice       = pspMeta.localizedWebshopPrice;  // decimal?, null when there is none
    var webshopPriceString = pspMeta.webshopPriceString;     // already formatted for the locale
}
```

It returns `null` for a product that was not fetched through the payment-provider store. The built-in
picker reads `hasWebshop` itself to decide whether to offer the webshop button; this accessor is for
a custom UI that needs the same signal.

### Opening the webshop directly

```csharp
var svc = store.PaymentProvidersExtendedPurchaseService;
if (svc == null) return;

await svc.RedirectToWebshop("catalog/coins_100_offer_usd");   // null for the generic webshop
```

The SDK fetches the URL, runs whatever compliance callback is registered, and opens it on approval.
Network failures surface as exceptions on the task; a compliance rejection goes through the ordinary
`OnPurchaseFailed` path.

## 6. Deep links

Payment happens in a browser, and the browser has to get back into the game.

**Use an app scheme** — a custom scheme of your own, `mygame://iapresult/okay` — rather than an
HTTPS App Link. An App Link needs Google's Digital Asset Links domain verification; a custom scheme
does not.

Ask which one is configured:

> Which redirect URL is set in the Unity Cloud IAP provider dashboard — something like
> `mygame://iapresult/okay`? If it is not set yet, set it there first.

### Registering it

```csharp
// The scheme only — the part before "://".
store.PaymentProviderStoreExtendedService?.SetDeepLinkScheme("mygame");
```

Call it before `Connect()`.

> **Passing the whole URL here silently never matches.** The SDK builds its matcher as
> `<scheme>:`, so `"mygame://iapresult/okay"` becomes the prefix `"mygame://iapresult/okay:"`,
> which no incoming link will ever start with. Pass only the scheme.

### And the Android manifest

Android needs the scheme declared as well; the API call alone does not route the redirect. If the
project has no custom manifest, turn it on at **Edit > Project Settings > Player > Publishing
Settings > Custom Main Manifest**, then add inside the `<activity>`:

```xml
<intent-filter>
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="mygame" android:host="iapresult" />
</intent-filter>
```

Scheme and host come from the configured redirect URL. What that manifest edit does to the merged
manifest and to the store submission is `unity-monetization`.

### A proxy page, for production

Some Android and iOS configurations drop an app-scheme redirect that originates from a payment
provider's domain — silently, with the player left in a browser. The fix is a page on a domain you
control:

```html
<!DOCTYPE html>
<html>
<head><title>Redirecting…</title></head>
<body>
<script>
  window.location = "mygame://iapresult/okay";
</script>
<p>Redirecting back to the app…</p>
</body>
</html>
```

Host it at a stable HTTPS URL, set **that** as the Success Redirect URL in the dashboard rather than
the app-scheme URL, and let its script perform the final hop. The manifest filter and
`SetDeepLinkScheme` are unchanged — they still handle that last leg. In the Editor, or on a
controlled device where the direct redirect works, the proxy is optional; for a production build
across a broad device range it is not.

### In the Editor

The purchase callback arrives directly, with no browser round trip. Nothing to configure.

### One dev-only define

If Android external-link validation gets in the way during QA:

```
IAP_SKIP_EXTERNAL_LINK_VALIDATION
```

in **Edit > Project Settings > Player > Scripting Define Symbols**.

> **This define must not reach a production build.** Shipping with it violates Google Play policy.
> If it is present, it is a release blocker, not a warning.

## 7. Purchase handling

Same save-before-confirm contract as everywhere else —
[`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md) §5. What is specific here:

**Where checkout appears.** By default the external browser. 5.4 also offers an in-app WebView:

```csharp
store.PaymentProviderStoreExtendedService?.SetCheckoutPresentationMode(CheckoutPresentationMode.ExternalBrowser);
store.PaymentProviderStoreExtendedService?.SetCheckoutPresentationMode(CheckoutPresentationMode.WebView);
```

With the external browser the game is suspended and resumes on the deep link; with the WebView it
stays alive and the view is dismissed on completion. `OnPurchasePending` fires either way.

**The webshop has its own setter.** `RedirectToWebshop` reads `SetWebshopPresentationMode`, which is
independent of the checkout mode. Setting checkout to `WebView` does **not** move the webshop
in-app; with no explicit webshop-mode call it opens the external browser.

```csharp
store.PaymentProviderStoreExtendedService?.SetWebshopPresentationMode(CheckoutPresentationMode.ExternalBrowser);
store.PaymentProviderStoreExtendedService?.SetWebshopPresentationMode(CheckoutPresentationMode.WebView);
```

`OnPurchaseDeferred` fires when payment does not complete immediately: pending UI, no grant.
`ConfirmPurchase` after the entitlement is granted and saved — for consumables, a re-purchase is
blocked until the previous order is confirmed.

### Compliance is the developer's

Apple and Google permit external web payments only in some regions and under their own programme
rules. Unity does not check eligibility for you. Three tools:

**Gate the purchase.** A callback that runs before any purchase starts; return false to block:

```csharp
store.PaymentProvidersExtendedPurchaseService?.SetComplianceCheck(async (context) =>
{
    bool isEligible = await CheckRegionalEligibility(context);
    return isEligible;
});
```

It runs for `PurchaseProduct` and `Purchase`. It does **not** gate `GenerateURL`.

**Show the URL first.** Some programme rules require disclosing the checkout URL before the
redirect. `GenerateURL` produces it without opening anything:

```csharp
string url = await store.PaymentProvidersExtendedPurchaseService.GenerateURL(catalogListingId);
// disclose it, then:
store.PaymentProvidersExtendedPurchaseService.PurchaseProduct(catalogListingId, PaymentProvider.Name);
```

A `GenerateURL` already made for that listing is reused by `PurchaseProduct` — no second order, no
double charge.

**Attach platform tokens.** Where a programme requires reporting a token back:

```csharp
var tokens = new List<PaymentProviderToken>
{
    new PaymentProviderToken { store = "apple", token = appleToken, type = "acquisition" },
    new PaymentProviderToken { store = "google", token = googleToken }
};
await store.PaymentProvidersExtendedPurchaseService.GenerateURL(catalogListingId, tokens);
```

They are stored with the order and appear in the `order.paid` webhook under
`externalTransactionTokens`. Up to two per order — one for the EU and one for Japan, for instance.

## 8. Product types

As standard IAP — [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md) §6 — with one
exclusion: **subscriptions are not supported on this path in 5.4+.** Skip them, name what was
skipped, and record it as a TODO for whenever support arrives.

## 9. Saving

As standard IAP — §7 of the same file. The save completes before `ConfirmPurchase`.

## 10. What to report

1. Files changed.
2. The catalogue: product IDs, types, `.ucat` or CSV files.
3. What each product grants.
4. Deep link scheme, host, and the manifest entry.
5. Which save method runs and when.
6. What is restorable and how.
7. Pending and deferred handling.
8. Everything below, which nobody here can do.

## 11. What a human has to do

1. **Deploy the catalogue** from the Editor, or author the products directly in the Unity Cloud IAP
   dashboard.
2. **Connect the provider account** — Stripe or Coda, under IAP > Payment Providers > Connect. If
   the feature is not enabled for the organisation, that is a request to Unity with the org ID.
3. **Set the redirect URLs** in the provider dashboard. A cancel URL adds a back button to the
   checkout page.
4. **Choose how entitlements are delivered** — IAP > Payment Providers > Entitlement Delivery
   Method: your own webhook endpoint receiving `order.paid`, a deployed Cloud Code module, or
   client-side fulfilment through `ConfirmPurchase` alone. The last needs no configuration and is
   the weakest; server-side is what production wants.
5. **Add a routing rule** — IAP > Payment Providers > Provider routing. **Without at least one rule
   no provider is ever offered**, connected account or not. Platform, country and rollout percentage
   per rule.
6. **Confirm the environment** in Edit > Project Settings > Services > Environments.
7. **Verify the Android deep link** — Digital Asset Links domain verification, if an HTTPS App Link
   was chosen over an app scheme.
8. **Establish platform eligibility.** External web payments are permitted in select regions under
   Apple's and Google's own programmes, and meeting those requirements is the developer's
   responsibility before shipping.
9. **Review the provider's content rules** — Stripe's restricted-business list, Coda's prohibited
   content policy.
