# Cloud Save — four buckets, and the read has to match the write

`CloudSaveService.Instance` (`ICloudSaveService`), namespace `Unity.Services.CloudSave`,
assembly `Unity.Services.CloudSave`. Needs `UnityServices.InitializeAsync()` and a signed-in
player first.

## The two traps, before anything else

> **A load from the wrong access class returns an empty result and throws nothing.** Default,
> Public, Protected and Custom are separate stores that happen to share key names. The day a
> feature moves from a direct client write to a Cloud Code write, its data moves bucket, and a
> read left on the old options silently reports "no save".

> **`SaveOptions`, `LoadOptions` and `DeleteOptions` each exist twice** — once at the root of
> `Unity.Services.CloudSave` and once under `Unity.Services.CloudSave.Models.Data.Player`. The
> access-class overloads are only on the second set; the root pair is what the *file* APIs take.
> Import both namespaces without aliases and you get an ambiguous-reference error, so declare
> them:

```csharp
using PlayerLoadOptions    = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using PlayerLoadAllOptions = Unity.Services.CloudSave.Models.Data.Player.LoadAllOptions;
using PlayerSaveOptions    = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;
using PlayerDeleteOptions  = Unity.Services.CloudSave.Models.Data.Player.DeleteOptions;
```

## Wrong → Correct

| Wrong | Correct |
|---|---|
| `await ...SaveAsync(data);` treating the result as void | `SaveAsync` returns `Task<Dictionary<string, string>>` — the new write-lock token per key |
| `(int)item.Value` | `Value` is `IDeserializable`: `item.Value.GetAs<T>()` or `.GetAsString()` |
| `SaveAsync(Dictionary<string, object>)` as the declared parameter type | The signature takes `IDictionary<string, object>` |
| `SaveAsync(data, Dictionary<string, WriteLockOptions>)` | No such overload. Bundle value and lock in a `SaveItem` and pass `IDictionary<string, SaveItem>` |
| `Data.Custom.SaveAsync(...)` | Custom data has **no client write path** — see below |
| `catch (CloudSaveException)` for a lock clash | `CloudSaveConflictException` first: it carries a per-key `Details` list |
| `CloudSaveExceptionReason.WriteLockConflict` | `CloudSaveExceptionReason.Conflict` (11) |
| `item.Modified.Timestamp` | `Item.Modified` and `Item.Created` are plain `DateTime?`. Same on `FileItem` |
| `DeleteAsync(key, new CloudSave.DeleteOptions { ... })` | `Models.Data.Player.DeleteOptions` for *player data*. The root one is not deprecated — it is what the file APIs take |
| `Data.Custom.LoadAllAsync()` | Every custom-data method takes `customDataID` as its first argument |

## Three subsystems

| Reached through | Holds |
|---|---|
| `CloudSaveService.Instance.Data.Player` | Key-value data for the signed-in player, in any of the three player access classes |
| `CloudSaveService.Instance.Data.Custom` | Game-wide data, not owned by a player. **Read-only from the client** |
| `CloudSaveService.Instance.Files.Player` | Binary blobs per player — screenshots, replays, anything that is not a value |

## `IPlayerDataService`

```csharp
// Keys and metadata, without the values.
Task<List<ItemKey>> ListAllKeysAsync()
Task<List<ItemKey>> ListAllKeysAsync(ListAllKeysOptions options)

// Load named keys, or everything.
Task<Dictionary<string, Item>> LoadAsync(ISet<string> keys)
Task<Dictionary<string, Item>> LoadAsync(ISet<string> keys, LoadOptions options)
Task<Dictionary<string, Item>> LoadAllAsync()
Task<Dictionary<string, Item>> LoadAllAsync(LoadAllOptions options)

// Save. The return value is key -> new write-lock token; keep it if you plan to save again.
Task<Dictionary<string, string>> SaveAsync(IDictionary<string, object> data)
Task<Dictionary<string, string>> SaveAsync(IDictionary<string, object> data, SaveOptions options)

// Save with optimistic concurrency: SaveItem bundles the value and the lock you read earlier.
Task<Dictionary<string, string>> SaveAsync(IDictionary<string, SaveItem> data)
Task<Dictionary<string, string>> SaveAsync(IDictionary<string, SaveItem> data, SaveOptions options)

// Delete one key, or the player's whole store.
Task DeleteAsync(string key, Models.Data.Player.DeleteOptions options)
Task DeleteAllAsync()
Task DeleteAllAsync(DeleteAllOptions options)

// Server-side search across players' data.
Task<List<EntityData>> QueryAsync(Query query, QueryOptions options)
```

Option classes for all of the above (`SaveOptions`, `LoadOptions`, `DeleteOptions`,
`DeleteAllOptions`, `ListAllKeysOptions`, `LoadAllOptions`, `QueryOptions`) live in
`Unity.Services.CloudSave.Models.Data.Player`.

## `ICustomDataService`

Game-wide storage, read-only from the client, written either by a Cloud Code module or from the
Editor through `IAdminClient.CloudSaveData.SetCustomItem` / `SetCustomItemBatch`
([`apis.md`](apis.md)). Every method's first argument is the `customDataID` — the namespace
configured in the dashboard, not a key.

```csharp
Task<List<ItemKey>> ListAllKeysAsync(string customDataID)
Task<Dictionary<string, Item>> LoadAllAsync(string customDataID)
Task<Dictionary<string, Item>> LoadAsync(string customDataID, ISet<string> keys)
Task<List<EntityData>> QueryAsync(Query query, Models.Data.Custom.QueryOptions options = default)
```

Note the second `QueryOptions`: custom queries take the one under `Models.Data.Custom`, player
queries the one under `Models.Data.Player`.

## `IPlayerFilesService`

Files take the **root** `CloudSave.SaveOptions` and `CloudSave.DeleteOptions`, not the
`Models.Data.Player` ones. This is the exception that makes the alias block above worth reading
twice.

```csharp
Task<List<FileItem>> ListAllAsync()
Task SaveAsync(string key, byte[] bytes, SaveOptions options = default)
Task SaveAsync(string key, Stream stream, SaveOptions options = default)
Task<byte[]> LoadBytesAsync(string key)
Task<Stream> LoadStreamAsync(string key)
Task DeleteAsync(string key, DeleteOptions options = default)
Task<FileItem> GetMetadataAsync(string key)
```

## Models

All in `Unity.Services.CloudSave.Models`.

**`Item`** — `Key` (`string`), `Value` (`IDeserializable`), `WriteLock` (`string`),
`Created` and `Modified` (`DateTime?`).

**`ItemKey`** — `Key`, `WriteLock`, `Modified`. What `ListAllKeysAsync` returns: enough to decide
what to load without paying for the values.

**`FileItem`** — `Key`, `Size` (`long`), `WriteLock`, `ContentType`, `Created`, `Modified`.

**`SaveItem`** — a value plus the lock it is conditional on:

```csharp
new SaveItem(value: myObject, writeLock: previousItem.WriteLock)
```

**`Query`** — `Fields` (`List<FieldFilter>`, required), `ReturnKeys` (`HashSet<string>`, projects
the result), `Offset` and `Limit` (`int`, pagination), `SampleSize` (`int?`).

**`FieldFilter`**:

```csharp
new FieldFilter(key: "level", value: 10, op: FieldFilter.OpOptions.GE, asc: true)
```

| `OpOptions` | |
|---|---|
| `EQ` | equal |
| `NE` | not equal |
| `LT` / `LE` | less than / or equal |
| `GT` / `GE` | greater than / or equal |

**`EntityData`** — one per matching player: `Id` (`string`) and `Data` (`List<Item>`).

## Access classes

`AccessClass` lives in `Unity.Services.CloudSave.Models.Data.Player`.

| Value | | Read | Write |
|---|---|---|---|
| `Default` | 0 | Owner | Owner |
| `Private` | 1 | alias for `Default` | |
| `Protected` | 2 | Owner | Server only |
| `Public` | 3 | Any player | Owner |

The option objects you actually pass:

| For a load or key listing | Reads |
|---|---|
| `DefaultReadAccessClassOptions()` | your own Default data |
| `PublicReadAccessClassOptions()` | your own Public data |
| `PublicReadAccessClassOptions(playerId)` | **another player's** Public data |
| `ProtectedReadAccessClassOptions()` | your own Protected data — always self, there is no player-id form |

| For a save or delete | Writes |
|---|---|
| `DefaultWriteAccessClassOptions()` | Default keys |
| `PublicWriteAccessClassOptions()` | Public keys |

There is deliberately no protected write option on the client. That path exists only inside a
Cloud Code module, via `IGameApiClient.CloudSaveData.SetProtectedItemAsync`
([`cloud-code.md`](cloud-code.md)).

## Templates

### Save, and keep the tokens

```csharp
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models;
using System.Collections.Generic;

var data = new Dictionary<string, object>
{
    { "level", 10 },
    { "gold", 500 },
    { "inventory", new string[] { "sword", "shield" } }
};

// One token per key, and each is the lock a later conditional save must present.
Dictionary<string, string> writeLocks =
    await CloudSaveService.Instance.Data.Player.SaveAsync(data);
```

### Load named keys

```csharp
var keys = new HashSet<string> { "level", "gold" };
var result = await CloudSaveService.Instance.Data.Player.LoadAsync(keys);

if (result.TryGetValue("level", out var levelItem))
{
    int level = levelItem.Value.GetAs<int>();
    Debug.Log($"Level {level}, last written {levelItem.Modified}");
}
```

A missing key is simply absent from the dictionary — `TryGetValue`, not a null check on an
indexer.

### Conditional save with `SaveItem`

Read first, save with the lock you read, and a save that lost the race fails instead of
overwriting. This is the mechanism behind "two devices, one account, no lost progress".

```csharp
using Unity.Services.CloudSave.Models;

var items = await CloudSaveService.Instance.Data.Player.LoadAsync(new HashSet<string> { "gold" });
var goldItem = items["gold"];

var saveData = new Dictionary<string, SaveItem>
{
    { "gold", new SaveItem(value: 600, writeLock: goldItem.WriteLock) }
};

Dictionary<string, string> newLocks =
    await CloudSaveService.Instance.Data.Player.SaveAsync(saveData);
```

### Handle the clash

```csharp
try
{
    await CloudSaveService.Instance.Data.Player.SaveAsync(saveData);
}
catch (CloudSaveConflictException ex)
{
    foreach (var detail in ex.Details)
    {
        Debug.LogError($"Conflict on '{detail.Key}': " +
            $"sent '{detail.AttemptedWriteLock}', server holds '{detail.ExistingWriteLock}'");
    }
    // Reload, merge in whatever the other writer did, retry. Never retry with the same lock.
}
```

### Delete

```csharp
using Unity.Services.CloudSave.Models.Data.Player;

await CloudSaveService.Instance.Data.Player.DeleteAsync(
    "gold", new DeleteOptions { WriteLock = knownWriteLock });

await CloudSaveService.Instance.Data.Player.DeleteAllAsync();
```

### Public and Protected, both directions

```csharp
using Unity.Services.CloudSave.Models.Data.Player;

// Written Public, so it must be read Public — the pairing is the whole point.
var publicData = new Dictionary<string, object> { { "displayName", "Hero123" }, { "rank", 42 } };
await CloudSaveService.Instance.Data.Player.SaveAsync(
    publicData, new SaveOptions(new PublicWriteAccessClassOptions()));

// Someone else's public profile.
var otherPlayerData = await CloudSaveService.Instance.Data.Player.LoadAsync(
    new HashSet<string> { "displayName", "rank" },
    new LoadOptions(new PublicReadAccessClassOptions(otherPlayerId)));

// Your own Protected data — whatever a Cloud Code module last wrote for you.
var serverData = await CloudSaveService.Instance.Data.Player.LoadAllAsync(
    new LoadAllOptions(new ProtectedReadAccessClassOptions()));
```

### Read game-wide data

```csharp
// customDataID is the dashboard-configured namespace, not a key.
var customData = await CloudSaveService.Instance.Data.Custom.LoadAllAsync("my-game-config");

if (customData.TryGetValue("seasonConfig", out var config))
{
    var season = config.Value.GetAs<SeasonConfig>();
    Debug.Log($"Season: {season.Name}");
}
```

### Query across players

```csharp
using Unity.Services.CloudSave.Models;
using Unity.Services.CloudSave.Models.Data.Player;

var query = new Query(
    fields: new List<FieldFilter>
    {
        new FieldFilter(key: "level", value: 10, op: FieldFilter.OpOptions.GE, asc: true)
    },
    returnKeys: new HashSet<string> { "level", "displayName" },
    offset: 0,
    limit: 20);

var results = await CloudSaveService.Instance.Data.Player.QueryAsync(query, new QueryOptions());

foreach (var entity in results)
foreach (var item in entity.Data)
    Debug.Log($"{entity.Id}  {item.Key} = {item.Value.GetAsString()}");
```

A query only sees the access class it was issued against, and only keys the caller is allowed to
read — a leaderboard-shaped query therefore wants Public data, not Default.

### Files

```csharp
byte[] screenshotBytes = await CaptureScreenshot();
await CloudSaveService.Instance.Files.Player.SaveAsync("screenshot_latest", screenshotBytes);

byte[] loaded = await CloudSaveService.Instance.Files.Player.LoadBytesAsync("screenshot_latest");

var meta = await CloudSaveService.Instance.Files.Player.GetMetadataAsync("screenshot_latest");
Debug.Log($"{meta.Size} bytes, {meta.ContentType}, modified {meta.Modified}");
```

## Errors

Order the catches from specific to general — the first two carry per-item detail the base
exception loses.

```csharp
try { /* … */ }
catch (CloudSaveConflictException ex)
{
    foreach (var d in ex.Details)
        Debug.LogError($"'{d.Key}': attempted={d.AttemptedWriteLock}, existing={d.ExistingWriteLock}");
}
catch (CloudSaveValidationException ex)
{
    foreach (var d in ex.Details)
        Debug.LogError($"field '{d.Field}' key '{d.Key}': {string.Join(", ", d.Messages)}");
}
catch (CloudSaveRateLimitedException ex)
{
    Debug.LogError($"Rate limited; retry after {ex.RetryAfter}s");
}
catch (CloudSaveException ex)
{
    Debug.LogError($"Cloud Save: {ex.Message} (reason: {ex.Reason})");
}
```

| `CloudSaveExceptionReason` | Value | |
|---|---|---|
| `Unknown` | 0 | |
| `NoInternetConnection` | 1 | |
| `ProjectIdMissing` | 2 | the project is not linked |
| `PlayerIdMissing` | 3 | not signed in |
| `AccessTokenMissing` | 4 | |
| `InvalidArgument` | 5 | |
| `Unauthorized` | 6 | usually a deployed `.ac` policy — see [`tooling.md`](tooling.md) |
| `KeyLimitExceeded` | 7 | too many keys for this player |
| `NotFound` | 8 | |
| `TooManyRequests` | 9 | |
| `ServiceUnavailable` | 10 | |
| `Conflict` | 11 | write-lock clash |

`Unauthorized` on a write that used to succeed is the signature of Access Control arriving in the
environment: the code did not change, the policy did.

## Where to go next

- Writing Protected or Custom data: [`cloud-code.md`](cloud-code.md)
- Writing Custom data from the Editor: [`apis.md`](apis.md)
- Denying the direct path so §4 of SKILL.md has teeth: [`tooling.md`](tooling.md)
- Worked features on top of these buckets: [`achievements.md`](achievements.md),
  [`battlepass.md`](battlepass.md), [`player-account.md`](player-account.md)
- [Cloud Save manual](https://docs.unity.com/ugs/en-us/manual/cloud-save/manual)
