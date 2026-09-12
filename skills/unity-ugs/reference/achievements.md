# Achievements — definitions in config, records on the server

The first worked example of SKILL.md §10's "config + state + server writes" shape. Remote Config
holds what the achievements *are*, Cloud Save holds what a player has *done*, a Cloud Code module
is the only thing that writes the second, and an `.ac` policy makes that true rather than
customary.

| Concern | Service | Address |
|---|---|---|
| Definitions | Remote Config | the `"achievements"` key, a JSON array |
| Player records | Cloud Save, Protected or Public | the `"achievements"` key, a JSON array |
| Writes | Cloud Code module | `AchievementModule` |
| Enforcement | Access Control | an `.ac` denying player writes to Cloud Save |

```
Remote Config "achievements"          Cloud Save "achievements"
  AchievementDefinition[]      read     AchievementRecord[]
    Id                        ------>     Id
    Title                                 Unlocked
    Description                           ProgressCount
    IsHidden                                   ^
    ProgressTarget                             |
                                    two ways in, pick one
                        +--------------------------+--------------------------+
                        |                                                     |
                 direct write                                        write through the server
                (development only)                                      (what ships)
                        |                                                     |
                        v                                                     v
              PublicWriteAccessClassOptions                          AchievementModule
              -> the Public bucket                                   -> SetProtectedItemAsync
                                                                     -> the Protected bucket
```

Two paths in, two buckets out — and **the read side has to follow whichever one you chose**. That
is the whole trap in this feature.

## Data models

Client-side, `[Serializable]` fields:

```csharp
using System;

[Serializable]
public class AchievementDefinition
{
    public string Id;
    public string Title;
    public string Description;
    public bool   IsHidden;        // secret until unlocked
    public int    ProgressTarget;  // <= 1 single unlock, > 1 multi-stage
}

[Serializable]
public class AchievementRecord
{
    public string Id;              // matches AchievementDefinition.Id
    public bool   Unlocked;
    public int    ProgressCount;
}
```

`ProgressTarget` doing double duty is deliberate: one field decides whether the UI shows a bar and
whether the client calls `UnlockAsync` or `AddProgressAsync`, so a definition cannot disagree with
itself.

The server sees the same record as **properties**, not fields — `Newtonsoft.Json` on the module
side serialises properties, and a mismatch here produces a record that round-trips as all
defaults with no error anywhere:

```csharp
public class AchievementRecord
{
    public string Id { get; set; }
    public bool Unlocked { get; set; }
    public int ProgressCount { get; set; }
}
```

## Namespace aliases

Cloud Save's option classes collide across namespace levels ([`cloud-save.md`](cloud-save.md)).
Every file below opens with:

```csharp
using PlayerLoadOptions   = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using PlayerSaveOptions   = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;
using PlayerDeleteOptions = Unity.Services.CloudSave.Models.Data.Player.DeleteOptions;
```

## Which bucket, and reading it back

| Options class | Read | Write | For |
|---|---|---|---|
| `DefaultReadAccessClassOptions` / `DefaultWriteAccessClassOptions` | Owner | Owner | Private player data |
| `PublicReadAccessClassOptions(playerId)` / `PublicWriteAccessClassOptions` | Anyone | Owner | Profiles, scores, achievements on the direct path |
| `ProtectedReadAccessClassOptions` | Owner | Server only | Achievements on the trusted path |

> **A wrong read here looks like data loss, not like an error.** Switch the write path and the
> read has to move with it: the module's writes land in Protected, direct writes land in Public,
> and each is invisible from the other. If achievements "reset themselves" the day server writes
> were turned on, this is why.

## Load the definitions

```csharp
using Unity.Services.RemoteConfig;
using Newtonsoft.Json.Linq;
using System.Collections.Generic;
using System.Threading.Tasks;

struct UserAttributes {}
struct AppAttributes {}

async Task<List<AchievementDefinition>> LoadDefinitionsAsync()
{
    var result = await RemoteConfigService.Instance.FetchConfigsAsync(
        new UserAttributes(), new AppAttributes());

    var token = result.config["achievements"];
    return token.ToObject<List<AchievementDefinition>>();
}
```

## Load the records

```csharp
using System.Collections.Generic;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models.Data.Player;
using PlayerLoadOptions = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;

async Task<List<AchievementRecord>> LoadRecordsAsync(string playerId, bool useTrustedWrites)
{
    // The access class follows the write path, not the other way round.
    ReadAccessClassOptions accessClass = useTrustedWrites
        ? new ProtectedReadAccessClassOptions()
        : new PublicReadAccessClassOptions(playerId);

    var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
        new HashSet<string> { "achievements" },
        new PlayerLoadOptions(accessClass));

    if (!result.TryGetValue("achievements", out var item))
        return new List<AchievementRecord>();

    return JsonConvert.DeserializeObject<List<AchievementRecord>>(item.Value.GetAsString());
}
```

`ProtectedReadAccessClassOptions()` takes no player id — it always reads the caller. The public
form takes one, so pass `AuthenticationService.Instance.PlayerId` to read yourself.

## The direct path

Fine while prototyping, and only then. It writes Public, which the player owns and can therefore
forge.

```csharp
using System.Collections.Generic;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models;
using Unity.Services.CloudSave.Models.Data.Player;
using PlayerSaveOptions = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;

async Task SaveRecordsAsync(List<AchievementRecord> records)
{
    var json = JsonConvert.SerializeObject(records);
    await CloudSaveService.Instance.Data.Player.SaveAsync(
        new Dictionary<string, SaveItem> { { "achievements", new SaveItem(json, null) } },
        new PlayerSaveOptions(new PublicWriteAccessClassOptions()));
}
```

## The trusted path

The module writes Protected with its service token, which the Access Control policy does not
apply to.

```csharp
await CloudCodeService.Instance.CallModuleEndpointAsync(
    "AchievementModule", "UnlockAchievement",
    new Dictionary<string, object> { { "achievementId", achievementId } });

await CloudCodeService.Instance.CallModuleEndpointAsync(
    "AchievementModule", "UpdateAchievementProgress",
    new Dictionary<string, object>
    {
        { "achievementId", achievementId },
        { "count", amount }
    });

await CloudCodeService.Instance.CallModuleEndpointAsync(
    "AchievementModule", "ResetAchievements", new Dictionary<string, object>());
```

## Client

One `MonoBehaviour` covering both paths, with the choice on a serialised field so a build can be
flipped without a code change.

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Unity.Services.Authentication;
using Unity.Services.CloudCode;
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models;
using Unity.Services.CloudSave.Models.Data.Player;
using PlayerSaveOptions   = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;
using PlayerLoadOptions   = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using PlayerDeleteOptions = Unity.Services.CloudSave.Models.Data.Player.DeleteOptions;
using Unity.Services.Core;
using Unity.Services.RemoteConfig;
using UnityEngine;

public class AchievementManager : MonoBehaviour
{
    // True routes writes through Cloud Code — required once the .ac policy is deployed.
    // False writes Cloud Save directly, which is a development-only arrangement.
    [SerializeField] bool m_UseTrustedWrites = true;

    public List<AchievementDefinition> Definitions { get; private set; } = new();
    public List<AchievementRecord> Records { get; private set; } = new();

    public event Action<AchievementDefinition> AchievementUnlocked;
    public event Action Loaded;

    async void Start()
    {
        await UnityServices.InitializeAsync();
        if (!AuthenticationService.Instance.IsSignedIn)
            await AuthenticationService.Instance.SignInAnonymouslyAsync();
        await LoadAsync();
        Loaded?.Invoke();
    }

    public async Task LoadAsync()
    {
        Definitions = await LoadDefinitionsAsync();
        Records     = await LoadRecordsAsync(AuthenticationService.Instance.PlayerId);
    }

    struct UserAttributes {}
    struct AppAttributes {}

    async Task<List<AchievementDefinition>> LoadDefinitionsAsync()
    {
        var result = await RemoteConfigService.Instance.FetchConfigsAsync(
            new UserAttributes(), new AppAttributes());

        var token = result.config["achievements"];
        return token.ToObject<List<AchievementDefinition>>();
    }

    async Task<List<AchievementRecord>> LoadRecordsAsync(string playerId)
    {
        ReadAccessClassOptions accessClass = m_UseTrustedWrites
            ? new ProtectedReadAccessClassOptions()
            : new PublicReadAccessClassOptions(playerId);

        var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
            new HashSet<string> { "achievements" },
            new PlayerLoadOptions(accessClass));

        if (!result.TryGetValue("achievements", out var item))
            return new List<AchievementRecord>();

        return JsonConvert.DeserializeObject<List<AchievementRecord>>(item.Value.GetAsString());
    }

    public async Task UnlockAsync(string achievementId)
    {
        var def = Definitions.FirstOrDefault(d => d.Id == achievementId);
        if (def == null)
        {
            Debug.LogWarning($"[Achievements] No definition for '{achievementId}'.");
            return;
        }

        var record = GetOrCreateRecord(achievementId);
        if (record.Unlocked)
            return;

        if (m_UseTrustedWrites)
        {
            await CloudCodeService.Instance.CallModuleEndpointAsync(
                "AchievementModule", "UnlockAchievement",
                new Dictionary<string, object> { { "achievementId", achievementId } });
        }
        else
        {
            record.Unlocked = true;
            await SaveRecordsAsync(Records);
        }

        record.Unlocked = true;
        AchievementUnlocked?.Invoke(def);
    }

    public async Task AddProgressAsync(string achievementId, int amount)
    {
        var def = Definitions.FirstOrDefault(d => d.Id == achievementId);
        if (def == null || def.ProgressTarget <= 1)
            return;

        var record = GetOrCreateRecord(achievementId);
        if (record.Unlocked)
            return;

        var newCount = record.ProgressCount + amount;

        if (m_UseTrustedWrites)
        {
            await CloudCodeService.Instance.CallModuleEndpointAsync(
                "AchievementModule", "UpdateAchievementProgress",
                new Dictionary<string, object>
                {
                    { "achievementId", achievementId },
                    { "count", amount }
                });
        }
        else
        {
            record.ProgressCount = newCount;
            await SaveRecordsAsync(Records);
        }

        record.ProgressCount = newCount;

        if (record.ProgressCount >= def.ProgressTarget)
            await UnlockAsync(achievementId);
    }

    public async Task ResetAsync()
    {
        if (m_UseTrustedWrites)
        {
            await CloudCodeService.Instance.CallModuleEndpointAsync(
                "AchievementModule", "ResetAchievements", new Dictionary<string, object>());
        }
        else
        {
            await CloudSaveService.Instance.Data.Player.DeleteAsync(
                "achievements",
                new PlayerDeleteOptions(new PublicWriteAccessClassOptions()));
        }

        Records.Clear();
    }

    AchievementRecord GetOrCreateRecord(string id)
    {
        var record = Records.FirstOrDefault(r => r.Id == id);
        if (record == null)
        {
            record = new AchievementRecord { Id = id };
            Records.Add(record);
        }
        return record;
    }

    async Task SaveRecordsAsync(List<AchievementRecord> records)
    {
        var json = JsonConvert.SerializeObject(records);
        await CloudSaveService.Instance.Data.Player.SaveAsync(
            new Dictionary<string, SaveItem> { { "achievements", new SaveItem(json, null) } },
            new PlayerSaveOptions(new PublicWriteAccessClassOptions()));
    }
}
```

Two things to notice about that shape. The local record is updated **after** the call returns, so
a failed server write leaves the UI honest rather than optimistic. And `ResetAsync` branches on
the same flag the reads and writes do, because it has to: on the trusted path the records live in
the Protected bucket, so a client delete aimed at Public clears nothing and reports no error —
the same class of bug this file opened with.

## The module

Scaffolding is the generic file set in [`cloud-code.md`](cloud-code.md), with `MyModule` /
`MyModuleCCM` becoming `AchievementModule` / `AchievementsCCM`. Every file in that set is
required; the publish profile is the one people leave out, and its absence is reported as a
failure to retrieve the main project.

```csharp
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Unity.Services.CloudCode.Apis;
using Unity.Services.CloudCode.Core;
using Unity.Services.CloudSave.Model;

// Every [CloudCodeFunction] method is an endpoint. IExecutionContext and IGameApiClient
// are supplied by the framework.
public class AchievementModule
{
    const string AchievementsKey = "achievements";

    [CloudCodeFunction("UnlockAchievement")]
    public async Task<AchievementRecord> UnlockAchievement(
        IExecutionContext context, IGameApiClient client, string achievementId)
    {
        var records = await LoadRecordsAsync(context, client);

        var record = records.FirstOrDefault(r => r.Id == achievementId);
        if (record == null)
        {
            record = new AchievementRecord { Id = achievementId, Unlocked = true };
            records.Add(record);
        }
        else
        {
            record.Unlocked = true;
        }

        await SaveRecordsAsync(context, client, records);
        return record;
    }

    [CloudCodeFunction("UpdateAchievementProgress")]
    public async Task<AchievementRecord> UpdateAchievementProgress(
        IExecutionContext context, IGameApiClient client, string achievementId, int count)
    {
        var records = await LoadRecordsAsync(context, client);

        var record = records.FirstOrDefault(r => r.Id == achievementId);
        if (record == null)
        {
            record = new AchievementRecord { Id = achievementId, ProgressCount = count };
            records.Add(record);
        }
        else
        {
            record.ProgressCount += count;
        }

        await SaveRecordsAsync(context, client, records);
        return record;
    }

    [CloudCodeFunction("ResetAchievements")]
    public async Task ResetAchievements(IExecutionContext context, IGameApiClient client)
    {
        // The service token is what makes this write legal where the client's is not.
        await client.CloudSaveData.DeleteProtectedItemAsync(
            context, context.ServiceToken, AchievementsKey,
            context.ProjectId, context.PlayerId!);
    }

    async Task<List<AchievementRecord>> LoadRecordsAsync(
        IExecutionContext context, IGameApiClient client)
    {
        var result = await client.CloudSaveData.GetProtectedItemsAsync(
            context, context.ServiceToken, context.ProjectId,
            context.PlayerId, new List<string> { AchievementsKey });

        var value = result.Data?.Results?.FirstOrDefault()?.Value?.ToString();
        if (string.IsNullOrEmpty(value))
            return new List<AchievementRecord>();

        return JsonConvert.DeserializeObject<List<AchievementRecord>>(value);
    }

    async Task SaveRecordsAsync(
        IExecutionContext context, IGameApiClient client, List<AchievementRecord> records)
    {
        var json = JsonConvert.SerializeObject(records);
        var body = new SetItemBody(AchievementsKey, json);
        await client.CloudSaveData.SetProtectedItemAsync(
            context, context.ServiceToken, context.ProjectId, context.PlayerId, body);
    }
}
```

`count` is the increment, not the new total. The module assigns it on the first write and adds it
thereafter, so a client that sends a running total is right once and double-counts every call
after that — which is why `AddProgressAsync` passes `amount` and keeps `newCount` for its own
local copy.

Note what this module does **not** do: it takes the caller's word for that increment. That is
adequate for achievements, where the worst outcome is a self-awarded badge, and inadequate for
anything convertible into currency — compare the source whitelist in
[`battlepass.md`](battlepass.md).

## Cloud resources

### Packages

The set this feature needs is `core`, `authentication`, `cloudsave`, `cloudcode`,
`remote-config`, `tooling` (for the `.ac`) and `deployment` (for the window). Versions:
[`packages.md`](packages.md). `Newtonsoft.Json` arrives as a transitive dependency and needs no
entry of its own.

### `Assets/Config/Achievements.rc`

Create with **Assets > Create > Services > Remote Config**, name it `Achievements`, and replace
the body:

```json
{
  "$schema": "https://ugs-config-schemas.unity3d.com/v1/remote-config.schema.json",
  "entries": {
    "achievements": [
      {
        "Id": "first_win",
        "Title": "First Win",
        "Description": "Win your first match.",
        "IsHidden": false,
        "ProgressTarget": 0
      },
      {
        "Id": "kill_100_enemies",
        "Title": "Centurion",
        "Description": "Defeat 100 enemies.",
        "IsHidden": false,
        "ProgressTarget": 100
      },
      {
        "Id": "secret_ending",
        "Title": "???",
        "Description": "Find the secret ending.",
        "IsHidden": true,
        "ProgressTarget": 0
      }
    ]
  },
  "types": {
    "achievements": "JSON"
  }
}
```

The `types` block is not optional here — without it the array arrives as a string and
`ToObject<List<AchievementDefinition>>()` fails somewhere that does not mention the config file.

Rules the client relies on: `Id` unique and stable, `ProgressTarget <= 1` meaning single-unlock,
`ProgressTarget > 1` meaning the progress API, `IsHidden` meaning the UI obfuscates title and
description until the record says unlocked.

### `Assets/Config/DenyPlayerCloudSaveWrites.ac`

Create with **Assets > Create > Services > Access Control**:

```json
{
  "$schema": "https://ugs-config-schemas.unity3d.com/v1/project-access-policy.schema.json",
  "statements": [
    {
      "Sid": "DenyPlayerCloudSaveWrites",
      "Action": [
        "Write"
      ],
      "Effect": "Deny",
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**"
    }
  ]
}
```

With it deployed, `m_UseTrustedWrites` must be true — a direct write returns `403`. Without it,
either setting works, which is the right arrangement for a prototype and the wrong one for a
release. A broader deny-then-allow policy that keeps the rest of the client working is in
[`tooling.md`](tooling.md).

## Before you call it done

- The project compiles, aliases present, and `AchievementsCCM` builds on its own.
- Init order holds: `InitializeAsync()`, sign-in, then service calls.
- Read access class matches `m_UseTrustedWrites` — the two are one decision, not two.
- The module solution targets `net9.0` and publishes `linux-x64`.
- The server-side `AchievementRecord` uses properties, not fields.
- The `.ac` file is **deployed**, not merely authored.
- The `"achievements"` key is spelled the same in the `.rc`, in `result.config[...]` and in
  `AchievementsKey`.
- The `"count"` sent to `UpdateAchievementProgress` is the increment, never the running total.
- `.rc`, `.ac` and `.ccmr` all appear in the Deployment Window against the environment you meant.

## Where to go next

- The same shape with real anti-cheat pressure: [`battlepass.md`](battlepass.md)
- The Achievements Building Block, which ships this feature working:
  [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-achievements-341918)
- [Cloud Save](https://docs.unity.com/ugs/en-us/manual/cloud-save/manual) ·
  [Remote Config](https://docs.unity.com/ugs/en-us/manual/remote-config/manual) ·
  [Cloud Code](https://docs.unity.com/ugs/en-us/manual/cloud-code/manual) ·
  [Access Control](https://docs.unity.com/ugs/en-us/manual/access-control/manual)
