# Essential Kit billing → Unity IAP

For a project using Essential Kit's Billing Services that is moving to `com.unity.purchasing`. This
is a genuine conversion path, not an assessment: Essential Kit's billing is a self-contained service
that can be switched off without touching anything else it does.

That is the shape of the whole job. **Nothing gets deleted.** One flag in a settings asset stops the
billing service initialising; every other Essential Kit service keeps working, and every Essential
Kit source file keeps compiling.

## The rules

- **Do not delete any Essential Kit file.** Turning the Billing service off in the settings asset is
  enough to stop it reaching native billing at runtime. No source change is needed.
- **Touch only Billing.** Every other service, and every other field in the settings asset, is out
  of scope.
- **Product IDs do not change** — they are the join key to the stores and to existing purchases.
- **Backend endpoints do not change** unless the receipt format forces it; where it does, say so.
- **Store billing only.** A third-party payment provider is a separate path.

## 1. Confirm there is something to convert

**Installed** — `com.voxelbusters.essentialkit` in `Packages/manifest.json`, and
`Assets/Plugins/VoxelBusters/` on disk.

**Billing enabled** — read `Resources/EssentialKitSettings.asset` (Unity YAML) and look for the
enabled flag:

```
billingServicesEnabled|isBillingServicesEnabled|BillingServices.*enabled: 1
```

Also read whatever `BillingServicesSettings` section is there.

If the flag is not set to 1, stop:

> Essential Kit Billing Services is not enabled in the project settings (Window > Voxel Busters >
> Essential Kit > Open Settings → Services). There is nothing to convert.

**Unity IAP** — `com.unity.purchasing` in the manifest. Absent or old is a Package Manager step for
the user before anything else.

## 2. Pull the products out

The products live under `BillingServicesSettings` in the same asset:

| Field | What it is |
|---|---|
| `Id` | The identifier the game's code uses, e.g. `coins_100` |
| `PlatformId` | The store SKU when it is the same everywhere |
| `PlatformIdOverrides` | Per-platform SKUs — separate Apple and Google entries |
| `ProductType` | `Consumable`, `NonConsumable` or `Subscription` |
| `Title` | Display name |
| `Description` | User-facing text |

No products defined is a second stop:

> No billing products are configured in Essential Kit Billing Settings. There is nothing to convert.

The type mapping is one-to-one — `Consumable`, `NonConsumable` and `Subscription` map to the
`ProductType` members of the same names.

Where `PlatformIdOverrides` carries separate Apple and Google SKUs, that becomes `StoreSpecificIds`:

```csharp
new ProductDefinition("coins_100", ProductType.Consumable,
    new StoreSpecificIds
    {
        { "apple_coins_100",  AppleAppStore.Name },
        { "google_coins_100", GooglePlay.Name }
    })
```

A single `PlatformId` is just the product ID.

## 3. The report, before any edit

1. How Essential Kit billing is wired here — the `OnTransactionStateChange` event model, and whether
   `AutoFinishTransactions` is on.
2. Every file that references `BillingServices`, plus the shop scenes and prefabs.
3. The extracted catalogue: IDs, types, store-specific SKUs.
4. The `AutoFinishTransactions` setting. Off means the project verifies server-side, which changes
   the receipt field mapping — see §7.
5. What the backend receives now versus what it will receive.
6. Restore: `RestorePurchases()` becomes `RestoreTransactions()` plus `FetchPurchases()`.
7. Shop UI: which buttons and callbacks get rewired.
8. The proposed Unity IAP shape and the catalogue definition.
9. Files to create and modify.
10. What is left manual — §8.

## 4. Add Unity IAP

The catalogue from §2 is the input; the implementation is
[`path-add-iap-to-new-project.md`](path-add-iap-to-new-project.md) in full. Specifically: match the
project's existing patterns for the manager, apply the save-before-confirm contract, apply the
per-type rules — and note that the consumable rule is the same on both sides, an old consumable
order is never restored — use the save system already present, and rewire the existing shop buttons
to `Buy(productId)`.

## 5. Switch Essential Kit billing off

Once Unity IAP is in place. Two native billing layers initialising at startup is the failure mode
this step exists to prevent.

In `Resources/EssentialKitSettings.asset`:

```yaml
# before
billingServicesEnabled: 1

# after
billingServicesEnabled: 0
```

Nothing else in that file changes, and the file is not deleted. That one flag stops Essential Kit
calling `BillingClient.startConnection()` on Android or initialising StoreKit on iOS. Its billing
source files stay where they are and compile as before; the service simply never starts.

## 6. Remove the duplicate Gradle dependency

Look in
`Assets/Plugins/VoxelBusters/EssentialKit/Essentials/Editor/CrossPlatformEssentialKitDependencies.xml`
for `com.android.billingclient`. No file, or no such entry, means this step does not apply — skip it
rather than inventing work.

If it is there, it collides with Unity IAP's own BillingClient. Remove only the billing lines:

```xml
<androidPackage spec="com.android.billingclient:billing:VERSION" />
<androidPackage spec="com.android.billingclient:billing-ktx:VERSION" />
```

Every other `<androidPackage>` stays. Then **Assets > External Dependency Manager > Android
Resolver > Resolve** (or Force Resolve) to regenerate the dependency list.

## 7. The mapping

| Essential Kit | Unity IAP |
|---|---|
| `BillingServices.InitializeStore()` | `store.Connect()` then `store.FetchProducts(definitions)` |
| `BillingServices.OnInitializeStoreComplete` | `store.OnStoreConnected` plus `store.OnProductsFetched` |
| `BillingServices.BuyProduct(product, options)` | `store.PurchaseProduct(product)` |
| `OnTransactionStateChange` — Purchased | `store.OnPurchasePending` |
| `OnTransactionStateChange` — Failed | `store.OnPurchaseFailed` |
| `OnTransactionStateChange` — Deferred | `store.OnPurchaseDeferred` |
| `BillingServices.FinishTransactions(transactions)` | `store.ConfirmPurchase(pendingOrder)` |
| `BillingServices.RestorePurchases(forceRefresh)` | `store.RestoreTransactions(callback)` for the button, `store.FetchPurchases()` at startup |
| `BillingServices.OnRestorePurchasesComplete` | `store.OnPurchasesFetched` plus the restore callback |
| `BillingServices.IsProductPurchased(id)` | `store.CheckEntitlement(product)` plus `OnCheckEntitlement` |
| `BillingServices.CanMakePayments()` | `store.AppleStoreExtendedService?.canMakePayments` — Apple only |
| `BillingServices.GetProductWithId(id)` | `store.GetProductById(id)` |
| `BillingServices.GetTransactions()` | `store.GetPurchases()` |
| `IBillingProduct` | `Product` |
| `IBillingTransaction` | `PendingOrder`, on `OnPurchasePending` |
| `product.Price.LocalizedText` | `product.metadata.localizedPriceString` |
| `product.LocalizedTitle` | `product.metadata.localizedTitle` |
| `product.LocalizedDescription` | `product.metadata.localizedDescription` |

**Note the split on one event.** A single `OnTransactionStateChange` becomes three separate handlers,
and the deferred branch is the one most likely to be dropped in translation — it grants nothing and
waits.

### Receipts

| Essential Kit | Unity IAP |
|---|---|
| `transaction.Receipt` — the iOS JWS token | `pendingOrder.Info.Apple?.jwsRepresentation` |
| `transaction.RawData` JSON on Android, carrying `transaction` and `signature` | `pendingOrder.Info.Receipt`, holding the full Google receipt JSON |

A backend parsing `transaction.RawData` will not find the same shape. That is a backend change, and
it belongs in the report.

### `AutoFinishTransactions`

The setting maps onto the two-step flow rather than disappearing:

| Setting | Unity IAP |
|---|---|
| `true` | `ConfirmPurchase(pendingOrder)` straight after the grant is saved |
| `false` — server verification | Hold the `PendingOrder`, send the receipt, confirm only once the server has answered |

Either way the confirm comes after the grant is safe. That was already true in Essential Kit's
manual-finish mode; the false case is simply the one where the wait is longer.

## 8. What to report

1. Files changed, and what changed in each.
2. The catalogue — IDs, types, store-specific SKUs.
3. Essential Kit Billing confirmed disabled in `EssentialKitSettings.asset`.
4. The Gradle dependency confirmed removed, or confirmed absent.
5. Any backend change the receipt mapping requires.
6. What is left for a human:
   - **Assets > External Dependency Manager > Android Resolver > Force Resolve** after the XML edit;
   - check the Android build for duplicate `BillingClient` classes (`./gradlew dependencies`, or the
     Unity build log);
   - confirm Billing shows as disabled in **Window > Voxel Busters > Essential Kit > Open Settings →
     Services**;
   - confirm every product ID matches App Store Connect and the Play Console exactly;
   - test with sandbox and licence-test accounts.
