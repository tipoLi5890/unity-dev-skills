# Battle pass — one writer, and it is not the client

The same shape as [`achievements.md`](achievements.md) with the stakes raised: this feature grants
things people pay for, so there is no direct-write path at all. Every mutation is a module call.

| Concern | Service | Key |
|---|---|---|
| Pass definitions | Remote Config | `"battle_passes"` |
| Per-player progress | Cloud Save, Protected | `"battle_pass_progress"` |
| Award XP | Cloud Code | `BattlePassModule.AwardXp` |
| Claim a reward | Cloud Code | `BattlePassModule.ClaimReward` |
| Buy the premium track | Cloud Code | `BattlePassModule.PurchasePremium` |

```
Remote Config              Cloud Save (Protected)         Cloud Code
"battle_passes"            "battle_pass_progress"         BattlePassModule
      |                            |                            |
      v                            v                            v
BattlePassDefinition[]     { passId: Progress }             AwardXp
  PassId, Name,            written by the module            ClaimReward
  StartDate, EndDate,      and nothing else                 PurchasePremium
  Tiers[]
      |                            ^                            |
      +------ client reads --------+------ server writes -------+
```

**No `.ac` file is required for this feature.** The Protected bucket is already server-write-only:
a client can read it and cannot modify it. Achievements needed a policy because it offered a
direct path worth closing; there is nothing to close here. A project-wide deny-then-allow policy
([`tooling.md`](tooling.md)) is still a good idea for everything else.

## Two tracks per tier

Every tier carries a free reward and a premium reward. The premium one is **visible to everyone
and claimable only by owners** — showing it locked is the point, since a player who cannot see
what they are missing has no reason to upgrade. The lock is enforced in the module: `ClaimReward`
with `rewardType = "premium"` throws when `HasPremium` is false. A client that hides the button
is a nicety, not a control.

## Several passes at once

- A pass is identified by `PassId` — `"season_03"`, `"easter_2026"`. Passes may overlap in time.
- Progress and premium ownership are tracked **per pass**: the Cloud Save key holds a
  `Dictionary<string, BattlePassProgress>` keyed by `PassId`.
- **Date filtering is client-side.** The client fetches every definition and keeps the ones whose
  window contains now. So a pass can be authored and deployed weeks early; it stays invisible
  until its `StartDate`.
- Expired passes stay in the dictionary and go inert — the client ignores any `PassId` not in the
  active list. A scheduled Cloud Code trigger can prune them if the dictionary ever gets large
  enough to care about.

## Data models

```csharp
[Serializable]
public class BattlePassDefinition
{
    public string PassId;
    public string Name;
    public string StartDate;    // ISO 8601, e.g. "2026-04-01T00:00:00Z"
    public string EndDate;
    public List<BattlePassTier> Tiers;
}

[Serializable]
public class BattlePassTier
{
    public int TierNumber;
    public int XpRequired;      // cumulative, not a delta from the previous tier
    public string FreeRewardId;
    public string PremiumRewardId;
}

[Serializable]
public class BattlePassProgress
{
    public int CurrentXp;
    public int CurrentTier;
    public bool HasPremium;
    public List<string> ClaimedRewards;   // "tier_1_free", "tier_2_premium", …
}

[Serializable]
public class BattlePassTierThreshold   // the slice of a tier the server needs
{
    public int TierNumber;
    public int XpRequired;
}
```

`XpRequired` being cumulative is the single most common authoring mistake in this file format —
tier 3 is not "1200 more", it is "1200 total".

## Namespace aliases

```csharp
using PlayerLoadOptions   = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using PlayerSaveOptions   = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;
using PlayerDeleteOptions = Unity.Services.CloudSave.Models.Data.Player.DeleteOptions;
```

## Reading progress

Always `ProtectedReadAccessClassOptions()`, always the caller's own data — there is no player-id
form and none is wanted here.

> **Plain `LoadOptions` returns nothing.** The module wrote Protected; a default load reads
> Default. No exception, no warning, just an empty dictionary that looks like a player who has
> never played.

The client blueprint further down catches `Exception`, because the failure it guards is `async
void` swallowing a throw. Shipping code catches by type first and branches on the reason: the
`CloudCodeExceptionReason` table in [`cloud-code.md`](cloud-code.md) and the
`CloudSaveExceptionReason` table in [`cloud-save.md`](cloud-save.md) are what turn a failure into
a message. One value is worth wiring a special case for — a `403` on a Cloud Save write from the
client means an Access Control policy is denying the direct path ([`tooling.md`](tooling.md)). It
cannot mean a stray write to the Protected bucket: the client has no Protected write call to
misuse.

## Why the client sends the tier table

`AwardXp` takes a `tiersJson` argument, which reads like a hole until you remember that **Cloud
Code modules cannot reach Remote Config** ([`cloud-code.md`](cloud-code.md)). The server needs the
thresholds to recompute a tier after adding XP, so the client serialises them from the definition
it already loaded and passes them along.

That is safe because the thresholds are not the security boundary. The controls that matter are
the `source` whitelist and the positive-amount check, both server-side. A tampered `tiersJson`
changes only how the player's *own* XP maps to a tier number.

What those controls constrain is the *label* on the XP, not its magnitude: `AwardXp` adds whatever
`amount` it is passed, and in this blueprint the client chooses that number. Deriving it
server-side from state the server already holds — a recorded match result, a completed quest — or
capping it per source is what closes the last hole in this shape.

## The source whitelist

```csharp
static readonly HashSet<string> ValidSources = new()
{
    "match_complete",
    "daily_login",
    "quest_complete"
};
```

An `AwardXp` call naming anything else throws. This is what stops a client inventing an XP source,
and it is the reason the argument exists at all — a call with no `source` would have nothing to
validate. Extend the set as the game grows; keep it in the module, never in config the client
supplies.

## Module functions

| Function | Arguments | What it does |
|---|---|---|
| `AwardXp` | `passId`, `amount`, `source`, `tiersJson` | Rejects an unlisted `source` and a non-positive `amount`, adds the XP, recomputes the tier from the supplied thresholds, writes Protected |
| `ClaimReward` | `passId`, `tierNumber`, `rewardType` | Checks the tier is reached, checks premium ownership when `rewardType` is `"premium"`, refuses a duplicate claim, records `"tier_N_type"`, writes Protected |
| `PurchasePremium` | `passId` | Sets `HasPremium`. **Idempotent** — a repeat call returns the existing progress rather than throwing |

All three return the updated `BattlePassProgress`, so the client never has to guess what the write
did. `PurchasePremium` being idempotent is not a nicety: a purchase retried after a timeout must
not double-charge or double-grant, which is `unity-live-services` §4 in one method.

## Client

```csharp
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Unity.Services.Authentication;
using Unity.Services.CloudCode;
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models;
using Unity.Services.CloudSave.Models.Data.Player;
using PlayerLoadOptions = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using Unity.Services.Core;
using Unity.Services.RemoteConfig;
using UnityEngine;

public class BattlePassManager : MonoBehaviour
{
    public List<BattlePassDefinition> ActivePasses { get; private set; } = new();
    public Dictionary<string, BattlePassProgress> Progress { get; private set; } = new();

    public event Action Loaded;

    async void Start()
    {
        try
        {
            await UnityServices.InitializeAsync();
            if (!AuthenticationService.Instance.IsSignedIn)
                await AuthenticationService.Instance.SignInAnonymouslyAsync();

            await LoadAsync();
            Loaded?.Invoke();
        }
        catch (Exception ex)
        {
            // async void: an unhandled throw here is swallowed, so catch and report.
            Debug.LogError($"[BattlePass] Load failed: {ex.Message}\n{ex.StackTrace}");
        }
    }

    public async Task LoadAsync()
    {
        ActivePasses = await LoadActivePassesAsync();
        Progress     = await LoadProgressAsync();
    }

    struct UserAttributes {}
    struct AppAttributes {}

    async Task<List<BattlePassDefinition>> LoadActivePassesAsync()
    {
        var result = await RemoteConfigService.Instance.FetchConfigsAsync(
            new UserAttributes(), new AppAttributes());

        var token = result.config["battle_passes"];
        if (token == null) return new List<BattlePassDefinition>();

        var allPasses = token.ToObject<List<BattlePassDefinition>>();

        // RoundtripKind keeps the trailing Z meaningful; without it these parse as local time.
        var now = DateTime.UtcNow;
        return allPasses
            .Where(p =>
                DateTime.Parse(p.StartDate, null, DateTimeStyles.RoundtripKind) <= now &&
                DateTime.Parse(p.EndDate,   null, DateTimeStyles.RoundtripKind) >= now)
            .ToList();
    }

    async Task<Dictionary<string, BattlePassProgress>> LoadProgressAsync()
    {
        var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
            new HashSet<string> { "battle_pass_progress" },
            new PlayerLoadOptions(new ProtectedReadAccessClassOptions()));

        if (!result.TryGetValue("battle_pass_progress", out var item))
            return new Dictionary<string, BattlePassProgress>();

        return JsonConvert.DeserializeObject<Dictionary<string, BattlePassProgress>>(
                   item.Value.GetAsString())
               ?? new Dictionary<string, BattlePassProgress>();
    }

    public async Task<BattlePassProgress> AwardXpAsync(string passId, int amount, string source)
    {
        var pass = ActivePasses.FirstOrDefault(p => p.PassId == passId)
            ?? throw new InvalidOperationException(
                $"Pass '{passId}' is not active. Call LoadAsync first.");

        var progress = await CloudCodeService.Instance.CallModuleEndpointAsync<BattlePassProgress>(
            "BattlePassModule", "AwardXp",
            new Dictionary<string, object>
            {
                { "passId",    passId },
                { "amount",    amount },
                { "source",    source },
                { "tiersJson", JsonConvert.SerializeObject(pass.Tiers) }
            });

        Progress[passId] = progress;
        return progress;
    }

    public async Task<BattlePassProgress> ClaimRewardAsync(
        string passId, int tierNumber, string rewardType)
    {
        var progress = await CloudCodeService.Instance.CallModuleEndpointAsync<BattlePassProgress>(
            "BattlePassModule", "ClaimReward",
            new Dictionary<string, object>
            {
                { "passId",     passId },
                { "tierNumber", tierNumber },
                { "rewardType", rewardType }
            });

        Progress[passId] = progress;
        return progress;
    }

    public async Task<BattlePassProgress> PurchasePremiumAsync(string passId)
    {
        var progress = await CloudCodeService.Instance.CallModuleEndpointAsync<BattlePassProgress>(
            "BattlePassModule", "PurchasePremium",
            new Dictionary<string, object> { { "passId", passId } });

        Progress[passId] = progress;
        return progress;
    }
}
```

Each call assigns the returned progress straight into the dictionary, so the client's copy is
whatever the server last said and never a local guess that drifted.

## A smoke test to attach beside it

```csharp
using System.Text;
using UnityEngine;

/// <summary>
/// Sits on the same GameObject as BattlePassManager. Logs the state it loaded, then awards
/// 100 XP to the first active pass through Cloud Code and logs what came back.
/// </summary>
public class BattlePassTester : MonoBehaviour
{
    [SerializeField] BattlePassManager m_Manager;

    void Start()
    {
        if (m_Manager == null)
            m_Manager = GetComponent<BattlePassManager>();
        m_Manager.Loaded += OnLoaded;
    }

    async void OnLoaded()
    {
        LogState("Loaded");

        if (m_Manager.ActivePasses.Count == 0)
        {
            Debug.Log("[BattlePassTester] No active passes — check StartDate/EndDate in the .rc.");
            return;
        }

        var firstPass = m_Manager.ActivePasses[0];
        var result = await m_Manager.AwardXpAsync(firstPass.PassId, 100, "match_complete");

        Debug.Log($"[BattlePassTester] After award — XP={result.CurrentXp}, Tier={result.CurrentTier}");
    }

    void LogState(string label)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"[BattlePassTester] {label} — {m_Manager.ActivePasses.Count} active pass(es):");

        foreach (var pass in m_Manager.ActivePasses)
        {
            m_Manager.Progress.TryGetValue(pass.PassId, out var progress);
            sb.AppendLine($"  [{pass.PassId}] {pass.Name}: " +
                $"XP={progress?.CurrentXp ?? 0}, " +
                $"Tier={progress?.CurrentTier ?? 1}, " +
                $"Premium={progress?.HasPremium ?? false}, " +
                $"Claimed={progress?.ClaimedRewards?.Count ?? 0}");
        }

        Debug.Log(sb.ToString());
    }
}
```

"No active passes" is by far the most common first result, and it almost always means the dates in
the `.rc` do not straddle today rather than that anything is broken.

## The module

Scaffolding per [`cloud-code.md`](cloud-code.md), with `MyModule` / `MyModuleCCM` becoming
`BattlePassModule` / `BattlePassCCM`.

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Unity.Services.CloudCode.Apis;
using Unity.Services.CloudCode.Core;
using Unity.Services.CloudSave.Model;

public class BattlePassModule
{
    const string ProgressKey = "battle_pass_progress";

    static readonly HashSet<string> ValidSources = new()
    {
        "match_complete",
        "daily_login",
        "quest_complete"
    };

    [CloudCodeFunction("AwardXp")]
    public async Task<BattlePassProgress> AwardXp(
        IExecutionContext context, IGameApiClient client,
        string passId, int amount, string source, string tiersJson)
    {
        // Both checks before any read: a rejected call must cost nothing.
        if (!ValidSources.Contains(source))
            throw new Exception(
                $"Invalid XP source: '{source}'. Allowed: {string.Join(", ", ValidSources)}");

        if (amount <= 0)
            throw new Exception("XP amount must be positive.");

        var allProgress = await LoadProgressAsync(context, client);

        if (!allProgress.TryGetValue(passId, out var progress))
            progress = new BattlePassProgress { CurrentTier = 1, ClaimedRewards = new List<string>() };

        progress.CurrentXp += amount;

        var tiers = JsonConvert.DeserializeObject<List<BattlePassTierThreshold>>(tiersJson)
            ?? throw new Exception("tiersJson could not be deserialized.");
        progress.CurrentTier = CalculateTier(progress.CurrentXp, tiers);

        allProgress[passId] = progress;
        await SaveProgressAsync(context, client, allProgress);

        return progress;
    }

    [CloudCodeFunction("ClaimReward")]
    public async Task<BattlePassProgress> ClaimReward(
        IExecutionContext context, IGameApiClient client,
        string passId, int tierNumber, string rewardType)
    {
        if (rewardType != "free" && rewardType != "premium")
            throw new Exception($"Invalid rewardType: '{rewardType}'. Must be 'free' or 'premium'.");

        var allProgress = await LoadProgressAsync(context, client);

        if (!allProgress.TryGetValue(passId, out var progress))
            throw new Exception($"No progress found for pass '{passId}'. Award XP first.");

        if (progress.CurrentTier < tierNumber)
            throw new Exception(
                $"Tier {tierNumber} not yet reached (current tier: {progress.CurrentTier}).");

        if (rewardType == "premium" && !progress.HasPremium)
            throw new Exception("Premium pass not owned. Purchase premium first.");

        var rewardKey = $"tier_{tierNumber}_{rewardType}";
        if (progress.ClaimedRewards.Contains(rewardKey))
            throw new Exception($"Reward '{rewardKey}' already claimed.");

        progress.ClaimedRewards.Add(rewardKey);
        allProgress[passId] = progress;
        await SaveProgressAsync(context, client, allProgress);

        return progress;
    }

    [CloudCodeFunction("PurchasePremium")]
    public async Task<BattlePassProgress> PurchasePremium(
        IExecutionContext context, IGameApiClient client, string passId)
    {
        var allProgress = await LoadProgressAsync(context, client);

        if (!allProgress.TryGetValue(passId, out var progress))
            progress = new BattlePassProgress { CurrentTier = 1, ClaimedRewards = new List<string>() };

        if (progress.HasPremium)
            return progress;   // idempotent: a retried purchase is not an error

        progress.HasPremium = true;
        allProgress[passId] = progress;
        await SaveProgressAsync(context, client, allProgress);

        return progress;
    }

    static int CalculateTier(int currentXp, List<BattlePassTierThreshold> tiers)
    {
        var reached = tiers
            .Where(t => currentXp >= t.XpRequired)
            .OrderByDescending(t => t.TierNumber)
            .FirstOrDefault();

        return reached?.TierNumber ?? 1;
    }

    async Task<Dictionary<string, BattlePassProgress>> LoadProgressAsync(
        IExecutionContext context, IGameApiClient client)
    {
        var result = await client.CloudSaveData.GetProtectedItemsAsync(
            context, context.ServiceToken, context.ProjectId,
            context.PlayerId!, new List<string> { ProgressKey });

        var value = result.Data?.Results?.FirstOrDefault()?.Value?.ToString();
        if (string.IsNullOrEmpty(value))
            return new Dictionary<string, BattlePassProgress>();

        return JsonConvert.DeserializeObject<Dictionary<string, BattlePassProgress>>(value)
            ?? new Dictionary<string, BattlePassProgress>();
    }

    async Task SaveProgressAsync(
        IExecutionContext context, IGameApiClient client,
        Dictionary<string, BattlePassProgress> progress)
    {
        var json = JsonConvert.SerializeObject(progress);
        var body = new SetItemBody(ProgressKey, json);
        await client.CloudSaveData.SetProtectedItemAsync(
            context, context.ServiceToken, context.ProjectId, context.PlayerId!, body);
    }
}
```

Server-side models, in the same file. Properties, not fields — the mismatch is silent:

```csharp
public class BattlePassProgress
{
    public int CurrentXp { get; set; }
    public int CurrentTier { get; set; }
    public bool HasPremium { get; set; }
    public List<string> ClaimedRewards { get; set; } = new();
}

public class BattlePassTierThreshold
{
    public int TierNumber { get; set; }
    public int XpRequired { get; set; }
}
```

Every mutation is load-modify-save on one key, which means two concurrent calls for the same
player can interleave. For a pass driven by one device that is acceptable; if it stops being
acceptable, the mechanism is a write lock ([`cloud-save.md`](cloud-save.md)) applied on the
server side.

## Cloud resources

### `Assets/BattlePasses.rc`

```json
{
  "$schema": "https://ugs-config-schemas.unity3d.com/v1/remote-config.schema.json",
  "entries": {
    "battle_passes": [
      {
        "PassId": "season_03",
        "Name": "Season 3",
        "StartDate": "2024-01-01T00:00:00Z",
        "EndDate": "2099-12-31T23:59:59Z",
        "Tiers": [
          { "TierNumber": 1, "XpRequired": 0,    "FreeRewardId": "item_bronze_badge", "PremiumRewardId": "currency_gold_500" },
          { "TierNumber": 2, "XpRequired": 500,  "FreeRewardId": "item_xp_boost",     "PremiumRewardId": "item_rare_skin_fragment" },
          { "TierNumber": 3, "XpRequired": 1200, "FreeRewardId": "item_silver_badge", "PremiumRewardId": "item_legendary_skin" }
        ]
      },
      {
        "PassId": "easter_2026",
        "Name": "Easter Event 2026",
        "StartDate": "2026-04-01T00:00:00Z",
        "EndDate": "2026-04-21T23:59:59Z",
        "Tiers": [
          { "TierNumber": 1, "XpRequired": 0,   "FreeRewardId": "item_egg_basket", "PremiumRewardId": "item_golden_egg" },
          { "TierNumber": 2, "XpRequired": 300, "FreeRewardId": "item_bunny_ears", "PremiumRewardId": "item_bunny_mount" }
        ]
      }
    ]
  },
  "types": {
    "battle_passes": "JSON"
  }
}
```

Authoring rules, each with a failure attached:

- **`PassId` is permanent.** It keys the progress record, so renaming one after launch orphans
  every player's progress in that pass.
- **`XpRequired` is cumulative**, and **tier 1 must be `0`** or a new player starts below the
  bottom tier and `CalculateTier` falls back to 1 anyway — inconsistently with the table.
- **Reward ids are opaque strings.** The client maps them to names and icons locally; nothing
  server-side interprets them.
- **Deploy a pass before its `StartDate`.** The client filters it out until the window opens, so
  early deployment is the safe order.
- **The window has to contain the day you run.** Filtering is client-side, so a pass whose window
  has closed never reaches `ActivePasses` — `easter_2026` above is that case once its April is
  past, which is why `season_03` is left deliberately open-ended. Set the dates around today
  before a first run, or the first thing you see is an empty list.

### Packages

`core`, `authentication`, `cloudsave`, `cloudcode`, `remote-config`, `tooling`, `deployment`, plus
`com.unity.nuget.newtonsoft-json` for the `JsonConvert` calls above. Floors for the rest:
[`packages.md`](packages.md).

## Before you call it done

- Both projects build: the Unity one and `BattlePassCCM/`.
- Init order holds on every entry path.
- Progress reads use `ProtectedReadAccessClassOptions` — a default load returns nothing.
- The module name in `CallModuleEndpointAsync` matches the `.ccmr` filename.
- No direct client write to `"battle_pass_progress"` exists anywhere.
- The XP `amount` reaching `AwardXp` is derived server-side or capped per source, not whatever the
  client asked for.
- `tiersJson` is serialised from the loaded definition, not reconstructed by hand.
- Date parsing uses `DateTimeStyles.RoundtripKind`, so the `Z` is honoured.
- `PurchasePremium` returns without error when premium is already owned.
- `ClaimReward` checks tier reach, premium ownership and prior claim, in that order.
- `BattlePasses.rc` and `BattlePassModule.ccmr` both appear in the Deployment Window.

## Where to go next

- The lighter version of this shape: [`achievements.md`](achievements.md)
- Real-money purchase of the premium track — receipts, entitlement, store SDKs — is `unity-iap`.
  What is here is the grant that follows a verified purchase, not the purchase.
- [Use Case Samples](https://github.com/Unity-Technologies/com.unity.services.samples.use-cases)
  carries a running battle pass and a virtual shop beside it.
