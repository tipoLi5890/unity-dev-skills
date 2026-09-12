# Adding IAP to a project that has none

Reached from [`pre-check.md`](pre-check.md) when nothing is billing yet. The API is in
[`api-notes.md`](api-notes.md); this file is the order of work and the contract that keeps a grant
from being lost.

## 1. The package

Look for `com.unity.purchasing` in `Packages/manifest.json`.

- **Absent** — the user installs it: **Window > Package Manager > Unity Registry > In App
  Purchasing**. Do not edit `manifest.json` unless they say to, and wait for confirmation before
  going on. The install changes the Android dependency graph, which is theirs to accept.
- **Below 5.0** — an upgrade, through Package Manager, before anything else.
- **5.0 or later** — note the exact version and continue. The payment-provider surface and
  `OnAuthAccountChanged` need 5.4.

Take the latest stable unless the user names a version, and never move a project backwards.

## 2. Read the project before writing to it

**Existing IAP signals** in `Assets/**/*.cs` — even a project that came out of the pre-check clean
can have half of something:

```
ProductType|ProductDefinition|StoreController|IAPButton|CodelessIAP
ProcessPurchase|PendingOrder|DeferredOrder|ConfirmPurchase|FetchPurchases
IStoreListener|UnityPurchasing\.Initialize|ConfigurationBuilder
```

**What a purchase would credit** — the grant has to land somewhere that already exists:

```
\bcoins\b|\bgems\b|\blives\b|\binventory\b|\bcurrency\b
PlayerData|SaveAsync|CloudSave|SaveDataAsync|SaveGame
Economy
```

**Where the shop is** — search `.unity`, `.prefab` and `.asset` for `Shop|Store|Purchase|Buy|IAP|
Product|Monetiz`, and collect scene names, prefab paths, button components and any product ID
strings already serialised into them. Those strings are the existing catalogue whether or not
anyone calls them that.

## 3. The catalogue

If the scan turned up product definitions, use them, and confirm any type you had to guess.

If it did not, stop and ask:

> Which product ID and type should the first purchase be — for example `com.mygame.coins100` as a
> Consumable — and what should it credit: which field, currency or item?

A product ID with no type defaults to Consumable, but say so out loud rather than silently assuming
it. Collect every product before writing code; for each one record the ID, the `ProductType`, and
the grant target — field, method, amount.

## 4. Shape of the manager

**Match the project, do not import a house style.** Look at whether it uses MonoBehaviour
singletons, ScriptableObject services or injection, and at the namespace convention in
`Assets/Scripts/`. Use whichever is already there.

One IAP manager, holding the `StoreController`, and responsible for:

- `Buy(string productId)`.
- `RestorePurchases()` — only when the catalogue actually has a `NonConsumable` or a
  `Subscription`.
- UI-facing events: initialised, products loaded, purchase succeeded, failed, deferred.
- Initialising once in `Awake()`, with every event subscribed before `Connect()` — the ordering is
  §1 of the skill.
- Registering every product from one authoritative list.

That list belongs in one place — a ScriptableObject, a `List<ProductDefinition>`, a constants class
— and not inside button handlers. Buttons call `Buy(productId)` with an ID from the catalogue.

## 5. The grant contract

The mechanics are in the skill's §3. What is specific to a fresh integration is the ordering around
the save:

```
OnPurchasePending fires
  → grant the reward: inventory, currency, entitlement
  → save the player data
  → save succeeded?  ConfirmPurchase(pendingOrder)
  → save failed?     do nothing — the store re-delivers next launch
```

> **An unconfirmed purchase costs nothing; a confirmed one that was never saved costs the player.**
> That asymmetry is the whole reason the two-step flow exists. Confirm last.

**Duplicate grants.** `OnPurchasePending` can fire twice for one purchase — a process killed between
grant and confirm guarantees it. Keep a ledger of processed order IDs, in save data or in the cloud,
and make a repeat a no-op rather than a second credit.

**Deferred.** Grant nothing, raise the "awaiting approval" event, wait for `OnPurchasePending`.

**Failed.** Grant nothing, raise the failure with its reason. The property names differ per type —
the skill's §7 table.

## 6. Per product type

**Consumable** — credit the inventory or currency, persist it before confirming, and never restore
one. Confirmed consumables are not returned by `FetchPurchases()`, so re-granting from a restore
path is either impossible or a duplicate. Their history is yours to keep.

**NonConsumable** — set a durable entitlement, and re-apply it at startup: `FetchPurchases()` and
re-check in `OnPurchasesFetched`, or `CheckEntitlement(product)`. Ship the restore button; iOS
requires it and Android benefits.

**Subscription** — check state at launch, not only at purchase. Subscriptions expire, get cancelled
from the store's own UI and get refunded, and none of that reaches a running app. Use
`CheckEntitlement` or the fetched orders to move between active, expired and unknown; the access
path and the `Result` comparison are the skill's §6.

## 7. Saving

Find the save system before writing any:

```
\.SaveAsync\(\)|CloudSaveService\.Instance
SaveGame\(|SaveDataAsync\(|PlayerPrefs\.SetInt|JsonUtility\.ToJson|JsonConvert\.Serialize
```

Use what is there. A purchase flow is a bad place to introduce a second persistence layer. If there
genuinely is none, `PlayerPrefs` is an acceptable floor — say plainly in the report that it is a
placeholder, because a purchase ledger in `PlayerPrefs` is not a shipping answer. Whichever it is,
the save completes before `ConfirmPurchase`.

Where that state belongs when it needs to survive a reinstall or a device change is
`unity-live-services`.

## 8. The shop UI

Wire existing buttons to `Buy(productId)` with an ID from the catalogue. The shop script listens to
the manager's events.

| State | Raised by | UI |
|---|---|---|
| Initialising | before the initialised event | Buttons disabled, or a spinner |
| Products loaded | products-loaded | Show `product.metadata.localizedPriceString` — never a hard-coded price |
| Product unavailable | absent from the fetched list | Hide or grey the button |
| Purchase in flight | `Buy` called | Disable the button, show progress |
| Deferred | deferred | "Waiting for approval" |
| Succeeded | success | Confirmation, and update the inventory display |
| Failed | failure | The message, and re-enable the button |

The restore button appears only if the catalogue has a non-consumable or a subscription.

Layout, scaling and text for that screen are `unity-ui-ugui` or `unity-game-ui`.

## 9. What to report

1. Files changed, and what changed in each.
2. The final catalogue — product IDs and types.
3. What each product grants: ID → field or method.
4. Which save method runs, and at which point.
5. What is restorable and how.
6. Pending and deferred handling — show that the save precedes the confirm, and that deferred grants
   nothing.
7. How duplicate grants are prevented, and where the order-ID ledger lives.
8. What is left for a human: the Receipt Validation Obfuscator in the Editor if Google local
   validation is used, product setup in App Store Connect and Play Console, and sandbox test
   accounts. None of that can be done from here, and none of it is optional before shipping.
