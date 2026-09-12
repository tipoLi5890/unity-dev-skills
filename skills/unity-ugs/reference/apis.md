# Services APIs — four clients, and the only way to write game data from the Editor

Package `com.unity.services.apis`; namespace and assembly `Unity.Services.Apis`.

Generated REST clients for every UGS service behind one dependency. Most gameplay code should keep
using the friendly SDKs (`CloudSaveService.Instance`, `EconomyService.Instance`); this package is
for what those cannot reach.

## The four clients

| Client | Runs | Authenticated by | Reach |
|---|---|---|---|
| `IGameClient` | Player device, runtime | The signed-in player | That player's own data |
| `IServerClient` | Dedicated game server | Server key | Server-side service calls |
| `ITrustedClient` | Dedicated game server | Service account | Any player's data, elevated |
| `IAdminClient` | **Editor only** | Service account key id + secret | Admin surface of every service |

`IAdminClient` is guarded by `#if UNITY_EDITOR || ENABLE_RUNTIME_ADMIN_APIS`, so a runtime
assembly referencing it fails to compile for a player build — which is the correct outcome, given
what its credentials are.

## When it has to be this package

> **Admin operations have no other supported path.** An Editor tool, a Deployment Window provider,
> or a build step that needs to read or write UGS data with elevated rights goes through
> `IAdminClient`. The client SDKs have no equivalent, and the REST endpoints are not something to
> hand-roll against.

The three cases that come up:

- **A custom deploy command** that pushes data into Cloud Save, Economy or Leaderboards
  ([`deployment.md`](deployment.md)).
- **An Editor tool** — an inspector or window that reads or edits game-wide data.
- **A build step** that publishes config to an environment before packaging.

## `IAdminClient`

```csharp
using Unity.Services.Apis;

var adminClient = UnityServicesApiClient.AdminClient;
adminClient.SetServiceAccount(keyId, keySecret);
```

Service account credentials come from the dashboard, under the project's Service Accounts. They
are passed in at run time from a gitignored file or a CI secret — `unity-live-services` §2 —
because a key committed to the project is a key that ships.

### Service areas

| Property | Type | Service |
|---|---|---|
| `CloudSaveData` | `ICloudSaveDataAdminApi` | Cloud Save player data in every access class, plus custom data |
| `CloudSaveFiles` | `ICloudSaveFilesAdminApi` | Cloud Save file storage |
| `CloudCodeModules` | `ICloudCodeModulesAdminApi` | C# modules |
| `CloudCodeScripts` | `ICloudCodeScriptsAdminApi` | JS scripts |
| `Economy` | `IEconomyAdminApi` | Economy configuration and player data |
| `RemoteConfig` | `IConfigsAdminApi` | Remote Config |
| `RemoteConfigSchemas` | `ISchemasAdminApi` | Remote Config schemas |
| `GameOverrides` | `IGameOverridesAdminApi` | Game Overrides |
| `Leaderboards` | `ILeaderboardsAdminApi` | Leaderboards |
| `Environment` | `IEnvironmentAdminApi` | Environments |
| `Logs` | `ILogsAdminApi` | Logs |
| `PlayerAuthentication` | `IPlayerAuthenticationAdminApi` | Player auth management |
| `PlayerPolicy` | `IPlayerPolicyAdminApi` | Player access policies |
| `ProjectPolicy` | `IProjectPolicyAdminApi` | Project access policies |
| `Scheduler` | `ISchedulerAdminApi` | Scheduler |
| `ServiceAuthentication` | `IServiceAuthenticationAdminApi` | Service auth |
| `Triggers` | `ITriggersAdminApi` | Triggers |

`ProjectPolicy` is the programmatic face of the `.ac` files in [`tooling.md`](tooling.md) — worth
knowing about before writing a tool that edits those files as text.

### `ICloudSaveDataAdminApi`

The interface most Editor tooling ends up on. Every method takes `projectId` and `environmentId`.

Player data, Default bucket:

| Method | |
|---|---|
| `GetItems(projectId, envId, playerId, keys?, after?)` | Read |
| `SetItem(projectId, envId, playerId, body)` | Write one |
| `SetItemBatch(projectId, envId, playerId, body)` | Write several |
| `DeleteItem(projectId, envId, playerId, key, writeLock?)` | Delete one |
| `DeleteItems(projectId, envId, playerId)` | Delete all |
| `GetKeys(projectId, envId, playerId, after?)` | List keys |

The **Public** and **Protected** buckets repeat that shape with the bucket in the name —
`GetPublicItems` / `SetPublicItem`, `GetProtectedItems` / `SetProtectedItem`, and so on. Picking
the wrong one here fails the same silent way it does on the client
([`cloud-save.md`](cloud-save.md)).

Custom (game-wide) data. `customId` is a namespace, 1–50 characters of letters, digits,
underscores and hyphens:

| Method | |
|---|---|
| `GetCustomItems(projectId, envId, customId, keys?, after?)` | Read |
| `SetCustomItem(projectId, envId, customId, body)` | Write one |
| `SetCustomItemBatch(projectId, envId, customId, body)` | Write several |
| `DeleteCustomItem(projectId, envId, customId, key, writeLock?)` | Delete one |
| `DeleteCustomItems(projectId, envId, customId)` | Delete all in that namespace |
| `GetCustomKeys(projectId, envId, customId, after?)` | List keys |

Private custom data mirrors it as `GetPrivateCustomItems`, `SetPrivateCustomItem` and friends.

> **This is the write path for game data.** `CloudSaveService.Instance.Data.Custom` is read-only
> from the client by design, so a level table or a shared config gets there either from a Cloud
> Code module or from `IAdminClient.CloudSaveData` here.

## `IGameClient`

`UnityServicesApiClient.GameClient`, after the player has signed in. Runtime only.

| Property | Service |
|---|---|
| `CloudSaveData` / `CloudSaveFiles` | Cloud Save |
| `CloudCode` | Cloud Code invocation |
| `EconomyConfiguration` / `EconomyCurrencies` / `EconomyInventory` / `EconomyPurchases` | Economy |
| `Leaderboards` | Scores |
| `Lobby` | Lobbies |
| `RemoteConfig` | Config settings |
| `PlayerAuthentication` / `PlayerNames` | Identity |
| `FriendsRelationships` / `FriendsPresence` | Friends |
| `RelayAllocations` / `QosDiscovery` | Relay and QoS |
| `Analytics` | Events |

Reach for this only where the high-level SDK has no equivalent — it is generated, so its
ergonomics are worse and its breaking changes are less curated.

## `IServerClient`

```csharp
var serverClient = UnityServicesApiClient.ServerClient;
await serverClient.SignInFromServer();
```

Exposes `CloudSaveData`, `CloudSaveFiles`, `CloudCode`, the four Economy areas, `Leaderboards`,
`Lobby` and `PlayerNames`. The auth token comes from the hosting environment.

## `ITrustedClient`

```csharp
var trustedClient = UnityServicesApiClient.TrustedClient;
trustedClient.SetServiceAccount(keyId, keySecret);
await trustedClient.SignInWithServiceAccount(projectId, environmentId);
```

The same service areas as `IServerClient`, plus `PlayerAuthentication`, `MultiplayAllocations`
and `MultiplayFleets`. Use it when a dedicated server has to act on *another* player's data — and
note it carries a service account key, so it belongs on a server you operate and nowhere near a
client build.

## Templates

### Write game data from the Editor

```csharp
using Unity.Services.Apis;
using Unity.Services.Apis.Admin.CloudSave;

var adminClient = UnityServicesApiClient.AdminClient;
adminClient.SetServiceAccount(keyId, keySecret);

string projectId     = CloudProjectSettings.projectId;
string environmentId = "your-environment-id";
string customId      = "game-config";   // the namespace, not a key

var body = new SetItemBody("level_data", levelDataJson);
await adminClient.CloudSaveData.SetCustomItem(projectId, environmentId, customId, body);

var batchBody = new SetItemBatchBody(new List<SetItemBatchBodyItem>
{
    new SetItemBatchBodyItem("enemies", enemiesJson),
    new SetItemBatchBodyItem("weapons", weaponsJson)
});
await adminClient.CloudSaveData.SetCustomItemBatch(projectId, environmentId, customId, batchBody);
```

`environmentId` is a value someone has to supply; hard-coding it beside a service account key is
how a tool ends up writing to production from a developer's machine. Read it from the same place
the deploy configuration comes from.

### Seed a player's Protected bucket

```csharp
var body = new SetItemBody("achievements", achievementsJson);
await adminClient.CloudSaveData.SetProtectedItem(projectId, environmentId, playerId, body);
```

Useful for fixtures and for support. It writes the same bucket a Cloud Code module writes, so the
client reads it back with `ProtectedReadAccessClassOptions()` and nothing else has to change.

### Game client

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;
using Unity.Services.Apis;

async Task SetupGameClient()
{
    await UnityServices.InitializeAsync();
    await AuthenticationService.Instance.SignInAnonymouslyAsync();

    // Authenticated implicitly by the signed-in player — no extra credential.
    var client = UnityServicesApiClient.GameClient;
    var scores = await client.Leaderboards.GetScoresAsync("WEEKLY_LB");
}
```

### Server client

```csharp
using Unity.Services.Apis;

var serverClient = UnityServicesApiClient.ServerClient;
await serverClient.SignInFromServer();

await serverClient.Lobby.CreateOrJoinLobbyAsync(/* … */);
```

## Where to go next

- The buckets these methods address: [`cloud-save.md`](cloud-save.md)
- Custom deploy commands that use the admin client: [`deployment.md`](deployment.md)
- Where a service account key may live: `unity-live-services` §2
- [Unity Gaming Services documentation](https://docs.unity.com/ugs/en-us/manual)
