# Ad callback payloads

The two types the rewarded, interstitial and banner instance events hand you. The events, and what
each format uses them for, are in [`rewarded-api.md`](rewarded-api.md),
[`interstitial-api.md`](interstitial-api.md) and [`banner-api.md`](banner-api.md). Impression data is
a separate type, `LevelPlayImpressionData`, tabled in [`ilrd-api.md`](ilrd-api.md).

## `LevelPlayAdInfo`

| Property | Type |
|---|---|
| `AdId` | string — this ad instance |
| `AdUnitId`, `AdUnitName` | string |
| `AdSize` | LevelPlayAdSize (banner-relevant, may be null) |
| `AdFormat` | string: `"REWARDED"`, `"INTERSTITIAL"` or `"BANNER"` |
| `PlacementName` | string |
| `AuctionId`, `CreativeId` | string |
| `Country` | string (ISO 3166-1) |
| `Ab`, `SegmentName` | string |
| `AdNetwork`, `InstanceName`, `InstanceId` | string |
| `Revenue` | double? — **nullable** |
| `Precision` | string |
| `EncryptedCPM` | string |

## `LevelPlayAdError`

`ErrorCode` (int), `ErrorMessage` (string), `AdUnitId` (string), `AdId` (string). What each code
means: the error-code table in [`initialization-api.md`](initialization-api.md).

## Rules across all three formats


- **`MonoBehaviour`, attached to the same persistent GameObject as the initializer.**
- **Subscribe on creation, unsubscribe in `OnDestroy()`**; banner and interstitial also call
  `DestroyAd()` there to release the native ad.
- **Rewarded and interstitial check `IsAdReady()` before `ShowAd()`.** Banner has no `IsAdReady()`;
  it is showable once `OnAdLoaded` fires.
- **If the game uses dashboard placements, also check the static `IsPlacementCapped(placementName)`.**
  A capped placement fails with 524 or 526.
- **Never block progression on an ad.** Advance the player, then show opportunistically.

The trap that costs the most time: **the rewarded format does not load itself.** Legacy IronSource
rewarded video loaded on its own, so migrated code has no `LoadAd()` to translate. Add an explicit
trigger; an always-ready preload (`LoadAd()` after subscribing, again in `OnAdClosed`) is a choice.
