# Remote Config — the definitions, fetched in one call

`RemoteConfigService.Instance`, namespace `Unity.Services.RemoteConfig`, package
`com.unity.remote-config` (note the id has no `services.` segment, unlike every other UGS
package).

## What it is for

Anything that describes *what exists in the game* and that you want to change without a client
build: the achievement list, battle pass tiers, a shop catalogue, tuning constants, feature flags.
Entries are typed key-value pairs, authored in the dashboard or as `.rc` files under `Assets/` and
pushed through the Deployment Window.

What it is **not** for: per-player state. Config is the same for everyone in an environment,
modulo Game Overrides. Player state belongs in Cloud Save.

## Fetching

One call brings down every entry; there is no per-key fetch.

```csharp
struct UserAttributes {}
struct AppAttributes {}

var result = await RemoteConfigService.Instance.FetchConfigsAsync(
    new UserAttributes(), new AppAttributes());

string val  = result.config.GetString("key");
int    num  = result.config.GetInt("key");
bool   flag = result.config.GetBool("key");

// A JSON entry comes back as a JToken.
var token = result.config["key"];
var obj   = token.ToObject<MyType>();
```

- **The two attribute structs are empty until you use audience targeting.** They are the payload
  a Game Override matches against, so for a project with no overrides they stay as declared here.
- **Results are cached.** A repeat call with the same attributes returns the cached set rather
  than hitting the service, which is why a value changed in the dashboard mid-session does not
  appear until the attributes change or the session restarts.

Supported types: `string`, `bool`, `int`, `float`, `long` and `JSON`.

## `.rc` format

Create one with **Assets > Create > Services > Remote Config** from the Project window
right-click menu, then replace the generated body.

```json
{
  "$schema": "https://ugs-config-schemas.unity3d.com/v1/remote-config.schema.json",
  "entries": {
    "my_string_key": "hello",
    "my_int_key": 42,
    "my_json_key": { "nested": true }
  },
  "types": {
    "my_json_key": "JSON"
  }
}
```

**The `types` block is only for JSON entries.** Scalars are inferred from the literal, so listing
them there is noise; omitting a JSON entry from it is a real bug — the value arrives as a string
and `ToObject<T>()` on it fails at a line that looks nothing like the cause.

Deploy through **Services > Deployment**, which discovers every `.rc` under `Assets/`
([`deployment.md`](deployment.md)).

## Game Overrides do the A/B

Remote Config on its own has **no experiment or targeting mechanism**. Overriding a value for a
segment of players is Game Overrides, which arrive with `com.unity.services.tooling` as `.ugo`
files and sit on top of Remote Config.

The part worth internalising: when an override applies to the calling player, `FetchConfigsAsync`
simply returns the overridden value. There is no second API and no flag in the result saying an
override fired. So a value that reads correctly in the dashboard and wrongly in a build is
usually not a caching problem — it is an override the build's attributes matched.

File shape, fields and audiences: [`tooling.md`](tooling.md).

## Shapes that work

- **A whole definition list under one key**, as a JSON array — the achievement set, the tier
  table. One fetch, one deserialise, and adding an item is a config deploy rather than a release.
- **Feature flags as booleans**, read once at start-up and cached in a settings object, so the
  rest of the game never talks to Remote Config directly.
- **Balance constants** grouped by system rather than scattered, because the person editing them
  is looking for "the economy numbers", not for `xp_multiplier`.

```csharp
using Unity.Services.RemoteConfig;
using Newtonsoft.Json.Linq;

struct UserAttributes {}
struct AppAttributes {}

async Task<List<T>> LoadJsonConfigAsync<T>(string key)
{
    var result = await RemoteConfigService.Instance.FetchConfigsAsync(
        new UserAttributes(), new AppAttributes());

    var token = result.config[key];
    return token.ToObject<List<T>>();
}
```

A missing key returns null from the indexer rather than throwing, so a first fetch against an
environment where nothing has been deployed yields a null token and a `NullReferenceException`
one line later. Guard it, and treat "config is empty" as a state the game has to survive —
`unity-live-services` §4.

## Where to go next

- Overrides, audiences and the `.ugo` file: [`tooling.md`](tooling.md)
- Pushing `.rc` files to an environment: [`deployment.md`](deployment.md)
- Definitions plus per-player state, worked through: [`achievements.md`](achievements.md),
  [`battlepass.md`](battlepass.md)
- [Remote Config manual](https://docs.unity.com/ugs/en-us/manual/remote-config/manual)
