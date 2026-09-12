# Access Control and Game Overrides — deny wins, and targeting is a separate layer

`com.unity.services.tooling` is Editor-only: it registers two file types with the Deployment
Window and ships no runtime code.

Namespaces: `Unity.Services.Tooling.Editor.AccessControl.Authoring.Core.Model` and
`Unity.Services.Tooling.Editor.GameOverrides.Authoring.Core.Model`.

| File type | Extension | What it does |
|---|---|---|
| Access Control | `.ac` | Permits or denies access to UGS resources by URN, per principal |
| Game Override | `.ugo` | Replaces Remote Config values for a targeted audience |

Both are created from the Project window right-click menu under **Create > Unity Gaming
Services**, and both deploy through **Services > Deployment**.

---

# Access Control

A policy is a list of statements. Each names a resource URN pattern, an action, a principal, and
whether that combination is allowed or denied.

| Field | Values |
|---|---|
| `Effect` | `"Allow"` or `"Deny"` — **`Deny` wins wherever both match** |
| `Action` | `"Read"`, `"Write"`, or `"*"` for both |
| `Principal` | `"Player"` (the end user) or `"ServiceAccount"` (server or admin) |
| `Resource` | `urn:ugs:<service>:/<path>`, with `*` and `**` wildcards |

Deny taking precedence is what makes the whole thing workable: a broad deny cannot be
accidentally re-opened by a specific allow written later, so the policy's floor is stable no
matter how the list grows.

What people reach for it for:

- Forcing every Cloud Save write through Cloud Code by denying the direct path.
- Letting players read Economy currency and inventory, and buy, but never write a balance.
- Restricting which Cloud Code endpoints a client may invoke at all.
- Blocking account deletion and identity unlinking from the client.

## `.ac` format

```json
{
  "$schema": "https://ugs-config-schemas.unity3d.com/v1/project-access-policy.schema.json",
  "statements": [
    {
      "Sid": "DenyPlayerCloudSaveWrites",
      "Effect": "Deny",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**"
    }
  ]
}
```

| Field | Type | |
|---|---|---|
| `Sid` | `string` | Statement id, unique within the file. It is what a review reads, so name the intent |
| `Effect` | `string` | `"Allow"` or `"Deny"` |
| `Action` | `string` or `string[]` | `"Read"`, `"Write"`, `"*"` |
| `Principal` | `string` or `string[]` | `"Player"`, `"ServiceAccount"` |
| `Resource` | `string` or `string[]` | One or more URN patterns |

## URN patterns

```
urn:ugs:<service>:/<path>
```

`*` matches one path segment; `**` matches zero or more, nested included. The `/**/` in the
middle of most patterns below is skipping the environment and version segments that the real
request path carries — which is why the patterns look loose but are not.

### Authentication — `player-auth`

| Pattern | Covers |
|---|---|
| `urn:ugs:player-auth:/*/authentication/anonymous**` | Anonymous sign-up |
| `urn:ugs:player-auth:/*/authentication/external-token**` | Social and platform sign-in |
| `urn:ugs:player-auth:/*/authentication/session-token**` | Returning-player sign-in |
| `urn:ugs:player-auth:/*/authentication/link/**` | Linking an external identity |
| `urn:ugs:player-auth:/*/authentication/unlink/**` | Unlinking |
| `urn:ugs:player-auth:/*/users**` | Player info on Read; account deletion on Write |
| `urn:ugs:player-auth:/.well-known/**` | JWKS public keys |

### Cloud Save — `cloud-save`

| Pattern | Covers |
|---|---|
| `urn:ugs:cloud-save:/**` | Everything |
| `urn:ugs:cloud-save:/**/players/*/keys**` | Listing the player's own keys |
| `urn:ugs:cloud-save:/**/players/*/items**` | Reading and writing the player's own items |
| `urn:ugs:cloud-save:/**/players/*/item-batch**` | Batch writes |
| `urn:ugs:cloud-save:/**/players/query**` | Querying Default data |
| `urn:ugs:cloud-save:/**/players/*/public/keys**` | Another player's public keys |
| `urn:ugs:cloud-save:/**/players/*/public/items**` | Another player's public items |
| `urn:ugs:cloud-save:/**/players/public/query**` | Querying Public data |
| `urn:ugs:cloud-save:/**/custom/*/items**` | Game-wide (Custom) items |

### Economy — `economy`

| Pattern | Covers |
|---|---|
| `urn:ugs:economy:/**/players/*/config**` | The player's economy configuration |
| `urn:ugs:economy:/**/currencies**` | Currency balances |
| `urn:ugs:economy:/**/inventory**` | Inventory |
| `urn:ugs:economy:/**/purchases/virtual**` | Virtual purchases |
| `urn:ugs:economy:/**/purchases/googleplaystore**` | Google Play purchases |
| `urn:ugs:economy:/**/purchases/appleappstore**` | App Store purchases |

### Leaderboards and Cloud Code

| Pattern | Covers |
|---|---|
| `urn:ugs:leaderboards:/**/leaderboards/**` | All leaderboard operations |
| `urn:ugs:cloud-code:/**/modules/**` | Module endpoints |
| `urn:ugs:cloud-code:/**/scripts/**` | Scripts |
| `urn:ugs:cloud-code:/**/subscriptions/tokens/**` | Subscription tokens |

## Deny everything, then allow what the client actually calls

Starting from a blanket deny means a service added next quarter is closed on the day it appears,
rather than on the day somebody notices. The cost is that the allow list has to be complete, and
the list below is roughly what a game using authentication, Cloud Save, Economy, Leaderboards and
Cloud Code needs.

```json
{
  "$schema": "https://ugs-config-schemas.unity3d.com/v1/project-access-policy.schema.json",
  "statements": [
    {
      "Sid": "Deny-all-ugs-access",
      "Effect": "Deny",
      "Action": ["*"],
      "Principal": "Player",
      "Resource": "urn:ugs:*:/**"
    },
    {
      "Sid": "Allow-Anonymous-SignUp",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:player-auth:/*/authentication/anonymous**"
    },
    {
      "Sid": "Allow-External-Token-SignIn",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:player-auth:/*/authentication/external-token**"
    },
    {
      "Sid": "Allow-Session-Token-SignIn",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:player-auth:/*/authentication/session-token**"
    },
    {
      "Sid": "Allow-Link-External-Id",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:player-auth:/*/authentication/link/**"
    },
    {
      "Sid": "Allow-Get-PlayerInfo",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:player-auth:/*/users**"
    },
    {
      "Sid": "Allow-Get-JWKS",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:player-auth:/.well-known/**"
    },
    {
      "Sid": "Allow-Read-Economy-Config",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:economy:/**/players/*/config**"
    },
    {
      "Sid": "Allow-Read-Currencies",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:economy:/**/currencies**"
    },
    {
      "Sid": "Allow-Read-Inventory",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:economy:/**/inventory**"
    },
    {
      "Sid": "Allow-Virtual-Purchases",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:economy:/**/purchases/virtual**"
    },
    {
      "Sid": "Allow-GooglePlay-Purchases",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:economy:/**/purchases/googleplaystore**"
    },
    {
      "Sid": "Allow-AppStore-Purchases",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:economy:/**/purchases/appleappstore**"
    },
    {
      "Sid": "Allow-Read-Leaderboards",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:leaderboards:/**/leaderboards/**"
    },
    {
      "Sid": "Allow-Read-CloudSave-PlayerKeys",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/*/keys**"
    },
    {
      "Sid": "Allow-CloudSave-PlayerItems",
      "Effect": "Allow",
      "Action": ["*"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/*/items**"
    },
    {
      "Sid": "Allow-CloudSave-PlayerItemBatch",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/*/item-batch**"
    },
    {
      "Sid": "Allow-Query-Default-PlayerData",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/query**"
    },
    {
      "Sid": "Allow-Read-Public-PlayerKeys",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/*/public/keys**"
    },
    {
      "Sid": "Allow-Read-Public-PlayerItems",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/*/public/items**"
    },
    {
      "Sid": "Allow-Query-Public-PlayerData",
      "Effect": "Allow",
      "Action": ["Write"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/players/public/query**"
    },
    {
      "Sid": "Allow-Read-GameData",
      "Effect": "Allow",
      "Action": ["Read"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-save:/**/custom/*/items**"
    },
    {
      "Sid": "Allow-CloudCode-Modules",
      "Effect": "Allow",
      "Action": ["*"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-code:/**/modules/**"
    },
    {
      "Sid": "Allow-CloudCode-Scripts",
      "Effect": "Allow",
      "Action": ["*"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-code:/**/scripts/**"
    },
    {
      "Sid": "Allow-Subscription-Tokens",
      "Effect": "Allow",
      "Action": ["*"],
      "Principal": "Player",
      "Resource": "urn:ugs:cloud-code:/**/subscriptions/tokens/**"
    }
  ]
}
```

Read that policy by what is **missing** from the allow list, because the blanket deny is what
handles those:

| Not allowed | Consequence |
|---|---|
| `unlink/**`, and Write on `users**` | A client cannot unlink an identity or delete the account |
| Write on `currencies**` / `inventory**` | Balances change only through a purchase or a Cloud Code grant |
| Any Cloud Save write outside the player's own items | Protected and Custom stay server-only |
| Write on `leaderboards/**` | Scores arrive through Cloud Code, not from the client |

Two operational notes. **A query is a `Write`** in three of these statements, because it is a
POST — surprising, and the reason a query fails under a policy that "obviously" allows reads. And
**deploying this policy breaks any build still writing directly**; it is a client-visible change,
so it ships with a client that already routes through Cloud Code, not before one.

---

# Game Overrides

Overrides replace Remote Config values for an audience — a segment defined in the dashboard.
Remote Config supplies no targeting of its own, so this is where A/B tests, staged rollouts and
time-boxed promotions live.

## `.ugo` format

```json
{
  "GameOverrides": [
    {
      "id": "double-xp-weekend",
      "name": "Double XP Weekend",
      "enabled": true,
      "audiences": ["high_engagement_players"],
      "overrides": [
        {
          "key": "xp_multiplier",
          "value": 2.0
        }
      ]
    }
  ]
}
```

| Field | Type | |
|---|---|---|
| `id` | `string` | Unique, and stable — analytics will be keyed on it |
| `name` | `string` | What a human reads in the dashboard |
| `enabled` | `bool` | Live or not |
| `audiences` | `string[]` | Segment ids from Unity Segmentation |
| `overrides[].key` | `string` | The Remote Config key being replaced |
| `overrides[].value` | any | The replacement |

An active override is invisible from the client's side: `FetchConfigsAsync` returns the overridden
value with nothing marking it as overridden. When a build disagrees with the dashboard, check the
override list before suspecting the fetch.

---

## Editor model types

For a tool that reads these files rather than deploying them.

```csharp
namespace Unity.Services.Tooling.Editor.AccessControl.Authoring.Core.Model
{
    interface IProjectAccessFile
    {
        string Path { get; }
        string Name { get; }
        List<IAccessControlStatement> Statements { get; }
    }

    interface IAccessControlStatement
    {
        string Sid { get; }
        string Effect { get; }           // "Allow" or "Deny"
        List<string> Action { get; }     // "Read", "Write", "*"
        List<string> Principal { get; }  // "Player", "ServiceAccount"
        List<string> Resource { get; }   // URN patterns
    }
}
```

```csharp
namespace Unity.Services.Tooling.Editor.GameOverrides.Authoring.Core.Model
{
    interface IGameOverride
    {
        string Id { get; }
        string Name { get; }
        bool Enabled { get; }
        List<string> Audiences { get; }
        List<OverrideConfig> Overrides { get; }
    }

    class GameOverridesConfigFile
    {
        public List<IGameOverride> GameOverrides { get; }
    }
}
```

Note that `Action`, `Principal` and `Resource` are lists in the model even though the JSON accepts
a bare string for each — a reader must handle both.

The Deployment Window picks both file types up automatically once
`com.unity.services.deployment` is installed.

## Where to go next

- Deploying these files: [`deployment.md`](deployment.md)
- The values an override replaces: [`remote-config.md`](remote-config.md)
- The write path a policy leaves open: [`cloud-code.md`](cloud-code.md)
- [Access Control manual](https://docs.unity.com/ugs/en-us/manual/access-control/manual)
