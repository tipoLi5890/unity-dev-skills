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
