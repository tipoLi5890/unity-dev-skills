# What to check before you call it done

> Part of the `unity-iap` skill (SKILL.md §8). The local compile gate, the v4 residue it does not
> catch, and the hand-back report.

The compile is the only gate that runs locally, and it catches most of the v4 residue. Run it, then
read the code for the rest.

- **The project compiles.** Then look for v4 shapes that still compile because they are `[Obsolete]`
  rather than removed: `IStoreListener`, `UnityPurchasing.Initialize`, `ConfigurationBuilder`,
  `SubscriptionManager`, and anything reached through `GetExtension<T>()`.
- **The shapes that do not exist at all** — `OnStoreConnectionFailed` (it is `OnStoreDisconnected`),
  callbacks passed to `FetchProducts` / `FetchPurchases` (they are events), `product.receipt` (it is
  `order.Info.Receipt`), `product.hasReceipt` (it is `CheckEntitlement`),
  `pendingOrder.OrderInfo` (it is `.Info`).
- **Every subscription is registered before `Connect()`**, and every asynchronous call has both its
  events.
- **The grant path is idempotent** and `ConfirmPurchase` happens after the save.
- **`IsSubscribed()` is compared to `Result.True`.**
- **A v5 file living beside an unremoved v4 one needs its own namespace**, or the two collide on
  `CS0101` / `CS0111`.
- **`OnAuthAccountChanged`, if handled, re-fetches** rather than reading the emptied caches.

Report what changed, which product IDs and types are now in the catalogue, what each grants, where
the save happens, and what still has to be done by hand in App Store Connect, Play Console and the
Editor. Sandbox testing is on the developer; nothing here proves a purchase works.
