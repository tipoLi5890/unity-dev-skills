# `IAPProductCatalog.json` — the file, and the second store it can start

`Assets/Resources/IAPProductCatalog.json` is a Unity-managed JSON asset read back through
`JsonUtility.FromJson<ProductCatalog>`. Editing it as text is safe and faster than driving the
Editor window, provided the serialisation rules below are respected — `JsonUtility` is a field
serialiser, so a field name that does not match exactly is not an error, it is a value that
silently disappears.

## The short version

1. Read the file as raw text. It is canonical JSON on a single line.
2. Parse it.
3. Edit against the schema below.
4. Write it back. Names and casing must match exactly; key order does not matter.
5. Refresh, or nothing will see the change.

Adding a $1.99 consumable in one append:

```jsonc
{
  "id": "gems_50",
  "type": 0,
  "storeIDs": [],
  "defaultDescription": { "googleLocale": 21, "title": "50 Gems", "description": "A small pouch of gems." },
  "screenshotPath": "",
  "applePriceTier": 0,
  "googlePrice": { "data": [199, 0, 0, 131072], "num": 1.99 },
  "pricingTemplateID": "",
  "descriptions": [],
  "payouts": []
}
```

## Where the file lives

- Current: `Assets/Resources/IAPProductCatalog.json` (`ProductCatalog.kCatalogPath`).
- Legacy: `Assets/Plugins/UnityPurchasing/Resources/IAPProductCatalog.json`
  (`ProductCatalog.kPrevCatalogPath`), migrated on Editor load. If both exist, the current path wins.

`Resources.Load("IAPProductCatalog")` is how the runtime reads it, so it has to stay under a
`Resources/` folder.

## Schema

```jsonc
{
  "appleSKU": "",                                  // app-level Apple SKU, for the Apple XML exporter
  "appleTeamID": "",                               // Apple team ID, same
  "enableCodelessAutoInitialization": true,        // starts a store on load — see the race below
  "enableUnityGamingServicesAutoInitialization": false,
  "products": [
    {
      "id": "gold_100",                            // required, non-empty, unique — the canonical SKU
      "type": 0,                                   // ProductType as int
      "storeIDs": [
        { "store": "AppleAppStore", "id": "com.example.gold100" }
      ],
      "defaultDescription": {
        "googleLocale": 21,                        // TranslationLocale as int; en_US = 21
        "title": "",
        "description": ""
      },
      "screenshotPath": "",                        // Apple screenshot path
      "applePriceTier": 0,
      "googlePrice": { "data": [99,0,0,131072], "num": 0.99 },
      "pricingTemplateID": "",                     // Google Play pricing template
      "descriptions": [
        { "googleLocale": 30, "title": "...", "description": "..." }
      ],
      "payouts": [
        { "t": "Currency", "st": "Gold", "q": 100, "d": "" }
      ]
    }
  ]
}
```

At runtime the only field a product must have is a non-empty trimmed `id`. The exporters and the
Editor window are much stricter — see the validation section.

## Serialisation rules

### The round trip

- Field names are the `[SerializeField]` **backing field** names, not the public property names.
  `title` and `description` inside a `LocalizedProductDescription`, not `Title` and `Description`.
- Unknown fields are dropped on the next save.
- Missing fields deserialise to defaults, so omitting them is safe; the Editor window writes them
  out anyway.
- The file is one line. Pretty-printing is harmless — the next Editor save collapses it again.
- Removing a top-level key is fine (it defaults). Renaming one loses the data with no error.

### `Price.data` — the field that bites

`Price` keeps a `decimal` in two mirrored fields, and **`data` is the one that is read**:

```csharp
public void OnBeforeSerialize() {
    data = decimal.GetBits(value);        // int[4]: [low, mid, high, flags]
    num  = decimal.ToDouble(value);
}
public void OnAfterDeserialize() {
    if (data != null && data.Length == 4)
        value = new decimal(data);        // num is not consulted
}
```

Editing `num` alone changes nothing. `data` is `decimal.GetBits`: three mantissa ints and a flags
int, where bits 16–23 hold the scale (0–28) and bit 31 the sign. A negative price is never valid
here, so bit 31 stays 0 and every other unused bit must be 0 too. Scale 2 — cents — is
`0x00020000`, decimal `131072`; scale 0, for whole-unit currencies, is `0`.

| Display price | Mantissa | Scale | `data` |
|---|---|---|---|
| 0.99 | 99 | 2 | `[99, 0, 0, 131072]` |
| 1.99 | 199 | 2 | `[199, 0, 0, 131072]` |
| 2.99 | 299 | 2 | `[299, 0, 0, 131072]` |
| 4.99 | 499 | 2 | `[499, 0, 0, 131072]` |
| 9.99 | 999 | 2 | `[999, 0, 0, 131072]` |
| 19.99 | 1999 | 2 | `[1999, 0, 0, 131072]` |
| 99.99 | 9999 | 2 | `[9999, 0, 0, 131072]` |
| 1000 (¥, ₩) | 1000 | 0 | `[1000, 0, 0, 0]` |

For anything else, with an unscaled value inside `int` range:

```
unscaled = round(price * 10^scale)      // 2.99, scale 2 → 299
data     = [unscaled, 0, 0, scale << 16]
```

Keep `num` matching the display price even though nothing reads it: the Editor shows it and the diff
becomes legible. Above roughly $21M the unscaled value overflows into the upper mantissa ints — at
that point stop hand-building bits and let `Price.OnBeforeSerialize` do the conversion from a
batchmode run.

### Enums as integers

`type` is `ProductType`:

| Int | Enum | For |
|---|---|---|
| 0 | `Consumable` | Coins, gems, lives, ammo — granted then spent |
| 1 | `NonConsumable` | Remove-ads, unlocks, character packs |
| 2 | `Subscription` | Recurring entitlements |

`googleLocale` is the zero-based index into `TranslationLocale`. Common ones:

| Int | Locale |
|---|---|
| 13 | `zh_CN` |
| 14 | `zh_TW` |
| 17 | `da_DK` |
| 18 | `nl_NL` |
| 21 | `en_US` — what a new description gets |
| 22 | `en_GB` |
| 30 | `fr_FR` |
| 33 | `de_DE` |
| 41 | `it_IT` |
| 42 | `ja_JP` |
| 46 | `ko_KR` |
| 63 | `pl_PL` |
| 64 | `pt_BR` |
| 69 | `ru_RU` |
| 75 | `es_ES` |

Anything not listed: count down the `TranslationLocale` enum declaration — the position is the
index.

`payouts[].t` is the exception that is **serialised as a string** — the `ProductCatalogPayoutType`
names: `"Other"`, `"Currency"`, `"Item"`, `"Resource"`.

### Store keys

`storeIDs[].store` must be one of `AppleAppStore`, `GooglePlay`, `MacAppStore`. Anything else —
`"Apple"`, `"google"` — does not throw; the override is simply never matched, which looks like a
store that forgot your SKU. An empty `storeIDs` array means `id` is used as the SKU everywhere.

### Non-ASCII text

The title and description setters escape every code point above 127 as `\uXXXX`
(`EncodeNonLatinCharacters`), and the getter decodes both forms, so either representation reads
correctly:

```jsonc
{ "title": "Caf\\u00e9 Pack" }   // what the Editor writes
{ "title": "Café Pack" }         // also accepted
```

Write the escaped form when generating the file, so a later Editor save produces no diff. Mixed
forms in one file work; the next save normalises them all.

`payouts[].st` caps at 64 characters (`ProductCatalogPayout.MaxSubtypeLength`), `payouts[].d` at
1024 (`MaxDataLength`).

## Validation, before saving

Per product:

- `id` non-empty after trim — `ProductCatalog.allValidProducts` filters on exactly this.
- `id` unique across the array.
- `type` in `{0, 1, 2}`.
- Every `googleLocale`, in `defaultDescription` and in `descriptions[]`, a valid
  `TranslationLocale` index.
- `storeIDs[].store` a canonical key.
- `googlePrice.data`, if present, a 4-element int array with bit 31 of `data[3]` clear.

Only if an export is actually intended:

- **Apple XML** (`AppleXMLProductCatalogExporter.Validate`) — catalogue level: `appleSKU` and
  `appleTeamID` non-empty, no duplicate product IDs, Apple store IDs or runtime IDs. Per item: `id`,
  `defaultDescription.Title`, `defaultDescription.Description` and **`screenshotPath` all
  non-empty** — the screenshot is required here, not optional. `applePriceTier` is written into the
  XML as `<wholesale_price_tier>` and not validated at all.
- **Google CSV** (`GooglePlayProductCatalogExporter.Validate`) — catalogue level: no duplicate
  product, Google store or runtime IDs. Per item: `id` non-empty, starting with a lowercase letter
  or digit, and containing only `a-z`, `0-9`, `_` and `.` — the same rule applies to a `GooglePlay`
  override in `storeIDs[].id`. Titles non-empty and at most 55 characters (a warning past 25),
  descriptions non-empty and at most 80, on `defaultDescription` and on every entry in
  `descriptions`. Price: either a non-zero `googlePrice` mantissa or a non-empty
  `pricingTemplateID`.

Top level: `enableCodelessAutoInitialization` is a JSON bool, not `0`/`1`. And note that a catalogue
with no valid product short-circuits codeless initialisation entirely — toggling the flag on an
empty catalogue does nothing until a product exists.

## Getting the change seen

The Editor caches the catalogue as a `TextAsset` keyed by its Resources path.

| Situation | What picks the edit up |
|---|---|
| Editor open, not playing | The asset re-imports on next focus. **Assets → Refresh** forces it |
| Editor open, in Play Mode | The `TextAsset` was loaded at play start. Restart play mode, or re-import and re-`Resources.Load` |
| Editor closed | Next launch |
| Already built | Nothing. The catalogue is baked in at build time — rebuild |

A batchmode start with no `-executeMethod` is enough to import assets, if a scripted refresh is
wanted:

```
"<unity>/Unity" -batchmode -quit -projectPath "<path>" -logFile -
```

## When the Editor window is the better tool

Hand this back to **Services → In-App Purchasing → IAP Catalog** when:

- the price is above roughly $21M and would need the upper mantissa ints;
- there are many payouts with custom subtypes, where the window validates lengths inline;
- an App Store export is wanted — that flow is a dialog with its own validation panel;
- a `JsonUtility` round-trip is failing for a reason the rules above do not explain.

Adding and removing products, ordinary price changes, descriptions, store overrides and the
auto-init flags are all faster and safer as direct file edits.

## The catalogue is also Codeless IAP

The same file plays two roles, and which one is in force changes what an edit does.

| What is wanted | Which |
|---|---|
| A buy button with no C# at all | **Codeless** — catalogue plus `CodelessIAPButton` |
| Custom UI states, server validation, control over the purchase flow | **Scripted** — a `StoreController` and an IAP manager, see [`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md) |
| Catalogue-driven product list, scripted purchase flow | **Mixed** — the catalogue registers products through `CodelessIAPStoreListener` and your code subscribes to it |
| Bulk-import files for App Store Connect or Play Console | The catalogue — it is the only built-in export path |

Starting from nothing, prefer scripted. Codeless is a good prototype and a poor production
architecture: it couples the project to a global singleton (`CodelessIAPStoreListener.Instance`) and
hides the initialisation and purchase flow that a shipping game eventually has to customise.

### The auto-init race

> **A non-empty catalogue with `enableCodelessAutoInitialization: true` plus a scripted
> `StoreController` is two initialisations competing for one native store.** Neither errors. What
> you see instead is duplicate `OnPurchasePending` callbacks — one per listener set — "store already
> connected" warnings out of `Connect()`, and a product list whose contents depend on which
> initialisation happened to win.

Three ways out; pick one and say which:

1. **Keep scripted, stand the catalogue down.** Set `"enableCodelessAutoInitialization": false`. The
   file stays readable through `ProductCatalog.LoadDefaultCatalog()`.
2. **Keep codeless, drop the scripted init.** Remove the `StoreController` setup and work through
   `CodelessIAPStoreListener.Instance`.
3. **Empty the catalogue.** `products: []` short-circuits
   `CodelessIAPStoreListener.InitializeCodelessPurchasingOnLoad` even with the flag on.

Raise this *before* adding scripted IAP to a project that already has a populated catalogue.

### Pushing the catalogue to the stores

The window's **App Store Export** opens `ProductCatalogExportWindow` and writes bulk-import files.
Nothing in the package talks to App Store Connect or the Play Console — the upload is manual.

| Exporter | Output | Goes to |
|---|---|---|
| `AppleXMLProductCatalogExporter` | Application Loader XML | App Store Connect, via Transporter |
| `GooglePlayProductCatalogExporter` | CSV | Play Console → In-app products → Import |

Editing the JSON fills the same fields the exporters read; `ExporterValidationResults` in the window
is the visible signal that something is missing.

### What to check, in order

1. Does `Assets/Resources/IAPProductCatalog.json` exist?
2. Is `enableCodelessAutoInitialization` true?
   `grep enableCodelessAutoInitialization Assets/Resources/IAPProductCatalog.json`
3. Are there `CodelessIAPButton` or older `IAPButton` components in any scene or prefab?
4. Does the project's own code build a `StoreController` — `UnityIAPServices.StoreController(...)`?
5. Does it reference `CodelessIAPStoreListener.Instance`?

| Catalogue | Auto-init | Scripted controller | What it means |
|---|---|---|---|
| Present, non-empty | true | absent | Pure codeless. Edit the catalogue freely |
| Present, non-empty | true | present | The race. Surface it, apply one of the three fixes |
| Present | false | present | The catalogue is dormant unless `LoadDefaultCatalog()` is called. Edits are safe |
| Present, empty | either | present | Codeless short-circuits. Treat as scripted-only |
| Absent | — | present | Ordinary scripted IAP |
| Absent | — | absent | No IAP — start at [`pre-check.md`](pre-check.md) |
