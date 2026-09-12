# Player accounts — three ways in, and the assembly nobody references

SKILL.md §10's "client-direct data" shape: sign the player in, give them an identity, and store
the non-sensitive half of their profile straight from the client. No Cloud Code in the path,
because nothing here is worth cheating over.

| Concern | Service | Call |
|---|---|---|
| Anonymous sign-in | Authentication | `SignInAnonymouslyAsync()` |
| Unity sign-in through a browser | Player Accounts, then Authentication | `StartSignInAsync()` → `SignInWithUnityAsync(AccessToken)` |
| Username and password | Authentication | `SignUpWithUsernamePasswordAsync` / `SignInWithUsernamePasswordAsync` |
| Identity | Authentication | `PlayerId`, `PlayerName`, `UpdatePlayerNameAsync` |
| Per-player data | Cloud Save | `CloudSaveService.Instance.Data.Player` |

```
UnityServices.InitializeAsync()
            |
            v
  AuthenticationService.Instance
            |
   +--------+------------+
   |        |            |
  anon   Unity        password
   |    (browser)        |
   |        |            |
   |  PlayerAccountService.Instance.StartSignInAsync()
   |        |   (returns when the browser OPENS)
   |   SignedIn event fires   <- this is the completion signal
   |        |
   |   SignInWithUnityAsync(AccessToken)
   |        |            |
   +--------+------------+
            |
      PlayerId / PlayerName
            |
      CloudSaveService.Instance.Data.Player
        |          |           |
     Default    Public     Protected
   owner r/w   anyone r,   owner r,
               owner w     server w
```

## The two things that cost an afternoon

> **`Unity.Services.Authentication.PlayerAccounts` is a separate assembly** that ships inside the
> `com.unity.services.authentication` package. An `.asmdef` referencing only
> `Unity.Services.Authentication` cannot see `PlayerAccountService`, and the error is a plain
> unresolved type — which reads like a missing package rather than a missing reference and sends
> people to reinstall something already installed.

> **`StartSignInAsync()` returns when the browser opens, not when the player signs in.** Awaiting
> it and then reading `AccessToken` gets you nothing. The completion signal is the `SignedIn`
> event, and it has to be subscribed **before** the call.

## Assemblies

| Assembly | Package | For |
|---|---|---|
| `Unity.Services.Core` | `com.unity.services.core` | `UnityServices.InitializeAsync()` |
| `Unity.Services.Authentication` | `com.unity.services.authentication` | `AuthenticationService.Instance` |
| `Unity.Services.Authentication.PlayerAccounts` | same package, **different assembly** | `PlayerAccountService.Instance` |
| `Unity.Services.CloudSave` | `com.unity.services.cloudsave` | `CloudSaveService.Instance.Data.Player` |

```json
{
    "name": "MyGame.PlayerAccount",
    "rootNamespace": "",
    "references": [
        "Unity.Services.Core",
        "Unity.Services.Authentication",
        "Unity.Services.Authentication.PlayerAccounts",
        "Unity.Services.CloudSave",
        "Unity.Services.CloudCode"
    ],
    "includePlatforms": [],
    "excludePlatforms": [],
    "allowUnsafeCode": false,
    "overrideReferences": false,
    "precompiledReferences": [],
    "autoReferenced": true,
    "defineConstraints": [],
    "versionDefines": [],
    "noEngineReferences": false
}
```

`Unity.Services.CloudCode` is only needed if this feature also touches Protected or Custom data;
drop it otherwise. Package versions: [`packages.md`](packages.md).

## Access classes for a profile

Default, Public and Protected — who reads, who writes, what goes there — are the table in SKILL.md
§3. **The class used to save decides the class that must be used to load**, and a mismatch returns
an empty result rather than an error ([`cloud-save.md`](cloud-save.md)).

## Anonymous

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;
using UnityEngine;

async Task SignInAnonymously()
{
    await UnityServices.InitializeAsync();

    if (!AuthenticationService.Instance.IsSignedIn)
        await AuthenticationService.Instance.SignInAnonymouslyAsync();

    Debug.Log($"Signed in as {AuthenticationService.Instance.PlayerId}");
}
```

One call covers returning and new players (SKILL.md §2); the `IsSignedIn` guard is what stops a
scene reload from turning it into an error.

## Unity account, through the browser

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;
using Unity.Services.Authentication.PlayerAccounts;
using UnityEngine;

void Start()
{
    // Subscribe before anything can fire it.
    PlayerAccountService.Instance.SignedIn += OnPlayerAccountSignedIn;
}

async Task StartSignInWithUnityAsync()
{
    await UnityServices.InitializeAsync();

    if (PlayerAccountService.Instance.IsSignedIn)
    {
        // Already through Player Accounts; go straight on to Authentication.
        OnPlayerAccountSignedIn();
        return;
    }

    // Opens the system browser and returns. Sign-in has not happened yet.
    await PlayerAccountService.Instance.StartSignInAsync();
}

async void OnPlayerAccountSignedIn()
{
    try
    {
        await AuthenticationService.Instance.SignInWithUnityAsync(
            PlayerAccountService.Instance.AccessToken);
        Debug.Log($"Signed in as {AuthenticationService.Instance.PlayerId}");
    }
    catch (AuthenticationException ex)
    {
        Debug.LogError($"Unity sign-in failed: {ex.Message}");
    }
    catch (RequestFailedException ex)
    {
        Debug.LogError($"Request failed: {ex.Message}");
    }
}
```

Two services, in sequence: Player Accounts authenticates the *Unity account* and hands back a
token; Authentication exchanges that token for a *UGS player*. Anything other than anonymous
sign-in also needs the matching identity provider enabled under **Project Settings > Services >
Authentication > Identity Providers**, which is a dashboard setting with no local file — so it
fails at run time on a build that compiled cleanly.

### `PlayerAccountService`

Namespace `Unity.Services.Authentication.PlayerAccounts`; the interface is `IPlayerAccountService`.

| Member | Type | |
|---|---|---|
| `StartSignInAsync(bool isSigningUp = false)` | `Task` | Opens the browser. Completes on **open**, not on sign-in |
| `SignOut()` | `void` | Signs out and revokes the token. Synchronous |
| `RefreshTokenAsync()` | `Task` | Refreshes the access token |
| `AccessToken` | `string` | What `SignInWithUnityAsync` wants |
| `IdToken` | `string` | The ID token |
| `IdTokenClaims` | `IdToken` | Parsed claims — email, subject |
| `IsSignedIn` | `bool` | Signed in to Player Accounts (not the same as signed in to UGS) |
| `AccountPortalUrl` | `string` | The player's account portal |
| `SignedIn` | `event Action` | Browser sign-in completed |
| `SignedOut` | `event Action` | Signed out |
| `SignInFailed` | `event Action<RequestFailedException>` | Sign-in failed |

`PlayerAccountService.Instance.IsSignedIn` and `AuthenticationService.Instance.IsSignedIn` are
different states, and a UI reading the wrong one shows a signed-in player a sign-in button.

## Username and password

Registration and sign-in are separate calls; there is no "sign in, creating if needed".

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;
using UnityEngine;

async Task SignUpWithPasswordAsync(string username, string password)
{
    await UnityServices.InitializeAsync();

    try
    {
        await AuthenticationService.Instance.SignUpWithUsernamePasswordAsync(username, password);
    }
    catch (AuthenticationException ex)
        when (ex.ErrorCode == AuthenticationErrorCodes.AccountAlreadyLinked)
    {
        // 10003 on a sign-up means the username is taken — by this player or another.
        await AuthenticationService.Instance.SignInWithUsernamePasswordAsync(username, password);
    }
    catch (AuthenticationException ex)
    {
        Debug.LogError($"Sign-up failed: {ex.Message} (code: {ex.ErrorCode})");
    }
}
```

Falling through to a sign-in on 10003 is convenient and worth thinking about: it turns a
"username taken" into a login attempt, which will fail on a wrong password with a different code.
If the UI needs to distinguish those two for the player, do not collapse them here.

Username and password constraints: [`authentication.md`](authentication.md), § Username and
password rules.

## Identity

| Member | Type | |
|---|---|---|
| `PlayerId` | `string` | Available as soon as sign-in returns |
| `PlayerName` | `string` | May be null until fetched |
| `IsSignedIn` | `bool` | A token exists |
| `SignedIn` / `SignedOut` | `event Action` | |
| `Expired` | `event Action` | Token expired; the SDK is refreshing |

There is no `IsAnonymous` on the service. Whether an account is still anonymous is a question about
what is linked to it, and the answer is in `PlayerInfo` — `Identities`, or the per-provider
accessors ([`authentication.md`](authentication.md), § Player info and name).

```csharp
string name    = await AuthenticationService.Instance.GetPlayerNameAsync(autoGenerate: true);
string updated = await AuthenticationService.Instance.UpdatePlayerNameAsync("NewDisplayName");

AuthenticationService.Instance.SignOut();
// AuthenticationService.Instance.SignOut(clearCredentials: true);  // see the warning below
```

**`SignOut` is `void`.** Awaiting it is a compile error, and reaching for a `SignOutAsync` that
does not exist is the usual first move. `PlayerAccountService.SignOut()` is likewise synchronous.

And the warning: `clearCredentials: true` on an account whose only identity is anonymous
**destroys it** — nothing remains to identify the player. Offer that only once a provider is
linked ([`authentication.md`](authentication.md)).

## Cloud Save for a profile

```csharp
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models;
using Unity.Services.CloudSave.Models.Data.Player;
using PlayerLoadOptions    = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using PlayerLoadAllOptions = Unity.Services.CloudSave.Models.Data.Player.LoadAllOptions;
using PlayerSaveOptions    = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;
```

The aliases are not decoration — `SaveOptions` and `LoadOptions` exist at two namespace levels and
importing both without aliasing is an ambiguous-reference error.

```csharp
// Default: private to the player. No options needed.
var data = new Dictionary<string, object>
{
    { "settings_volume", 0.8f },
    { "settings_difficulty", "hard" },
    { "last_login", DateTime.UtcNow.ToString("o") }
};
await CloudSaveService.Instance.Data.Player.SaveAsync(data);

// Public: other players can read it.
var publicData = new Dictionary<string, object>
{
    { "display_name", "Hero123" },
    { "avatar_id", 42 }
};
await CloudSaveService.Instance.Data.Player.SaveAsync(
    publicData, new PlayerSaveOptions(new PublicWriteAccessClassOptions()));
```

```csharp
// Default read.
var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
    new HashSet<string> { "settings_volume", "settings_difficulty" });

if (result.TryGetValue("settings_volume", out var volumeItem))
{
    float volume = volumeItem.Value.GetAs<float>();
    Debug.Log($"Volume {volume}");
}

// Own public data.
var mine = await CloudSaveService.Instance.Data.Player.LoadAsync(
    new HashSet<string> { "display_name", "avatar_id" },
    new PlayerLoadOptions(new PublicReadAccessClassOptions()));

// Someone else's public data — the player id is the only difference.
var theirs = await CloudSaveService.Instance.Data.Player.LoadAsync(
    new HashSet<string> { "display_name", "avatar_id" },
    new PlayerLoadOptions(new PublicReadAccessClassOptions(otherPlayerId)));

// Everything in one bucket.
var allItems = await CloudSaveService.Instance.Data.Player.LoadAllAsync(
    new PlayerLoadAllOptions(new DefaultReadAccessClassOptions()));
```

`GetAsString()` returns the plain string for a value saved as one, and the JSON for a complex
object; `GetAs<T>()` deserialises. Values arrive as `IDeserializable`, never as the type you saved.

## When the client should not be the writer

Default and Public are client-writable, which is right for preferences and a display name. Two
cases are not:

- **Data no player owns** — guild records, shared level configuration, global state. It belongs in
  the Custom bucket, which has no client write path at all
  ([`cloud-code.md`](cloud-code.md), [`apis.md`](apis.md)).
- **Data a player would benefit from forging** — XP, currency, unlocks. Protected bucket, written
  by a module. This is a design decision rather than a rule: decide per key whether an arbitrary
  value would matter, and `unity-live-services` §3 is the framing.

Reading Protected from the client is ordinary, and it is the read that people get wrong:

```csharp
var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
    new HashSet<string> { "player_level", "currency" },
    new PlayerLoadOptions(new ProtectedReadAccessClassOptions()));
```

Plain `LoadOptions` here returns an empty dictionary, because those keys are in a bucket that a
default load does not look at.

## Client

```csharp
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Unity.Services.Authentication;
using Unity.Services.Authentication.PlayerAccounts;
using Unity.Services.CloudSave;
using Unity.Services.CloudSave.Models.Data.Player;
using Unity.Services.Core;
using UnityEngine;
using PlayerLoadOptions    = Unity.Services.CloudSave.Models.Data.Player.LoadOptions;
using PlayerLoadAllOptions = Unity.Services.CloudSave.Models.Data.Player.LoadAllOptions;
using PlayerSaveOptions    = Unity.Services.CloudSave.Models.Data.Player.SaveOptions;

public class PlayerAccountManager : MonoBehaviour
{
    public string PlayerId   => AuthenticationService.Instance.PlayerId;
    public string PlayerName => AuthenticationService.Instance.PlayerName;
    public bool   IsSignedIn => AuthenticationService.Instance.IsSignedIn;

    public event Action SignedIn;

    async void Start()
    {
        await UnityServices.InitializeAsync();

        AuthenticationService.Instance.SignedIn += () => SignedIn?.Invoke();

        // Wired before any StartSignInAsync call can fire it.
        PlayerAccountService.Instance.SignedIn += OnPlayerAccountSignedIn;
    }

    // --- sign-in ---

    public async Task SignInAnonymouslyAsync()
    {
        if (AuthenticationService.Instance.IsSignedIn) return;
        await AuthenticationService.Instance.SignInAnonymouslyAsync();
    }

    /// <summary>
    /// Opens the browser for Unity sign-in. The returned Task completes when the browser
    /// opens; wait on SignedIn to know the player actually got through.
    /// </summary>
    public async Task StartSignInWithUnity()
    {
        if (PlayerAccountService.Instance.IsSignedIn)
        {
            OnPlayerAccountSignedIn();
            return;
        }

        await PlayerAccountService.Instance.StartSignInAsync();
    }

    async void OnPlayerAccountSignedIn()
    {
        try
        {
            await AuthenticationService.Instance.SignInWithUnityAsync(
                PlayerAccountService.Instance.AccessToken);
        }
        catch (AuthenticationException ex)
        {
            Debug.LogError($"Unity sign-in failed: {ex.Message}");
        }
        catch (RequestFailedException ex)
        {
            Debug.LogError($"Request failed: {ex.Message}");
        }
    }

    public async Task SignUpWithPasswordAsync(string username, string password)
    {
        try
        {
            await AuthenticationService.Instance.SignUpWithUsernamePasswordAsync(username, password);
        }
        catch (AuthenticationException ex)
            when (ex.ErrorCode == AuthenticationErrorCodes.AccountAlreadyLinked)
        {
            Debug.LogWarning("That username is taken — sign in instead.");
            throw;
        }
    }

    public Task SignInWithPasswordAsync(string username, string password)
        => AuthenticationService.Instance.SignInWithUsernamePasswordAsync(username, password);

    public void SignOut()
    {
        AuthenticationService.Instance.SignOut();
        // PlayerAccountService.Instance.SignOut();  // also drop the Unity account session
    }

    // --- identity ---

    public Task<string> GetPlayerNameAsync()
        => AuthenticationService.Instance.GetPlayerNameAsync(autoGenerate: true);

    public Task<string> UpdatePlayerNameAsync(string newName)
        => AuthenticationService.Instance.UpdatePlayerNameAsync(newName);

    // --- Cloud Save: Default ---

    public Task SaveDefaultAsync(string key, object value)
        => CloudSaveService.Instance.Data.Player.SaveAsync(
            new Dictionary<string, object> { { key, value } });

    public async Task<string> LoadDefaultAsync(string key)
    {
        var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
            new HashSet<string> { key });
        return result.TryGetValue(key, out var item) ? item.Value.GetAsString() : null;
    }

    // --- Cloud Save: Public ---

    public Task SavePublicAsync(string key, object value)
        => CloudSaveService.Instance.Data.Player.SaveAsync(
            new Dictionary<string, object> { { key, value } },
            new PlayerSaveOptions(new PublicWriteAccessClassOptions()));

    public async Task<string> LoadPublicAsync(string key)
    {
        var result = await CloudSaveService.Instance.Data.Player.LoadAsync(
            new HashSet<string> { key },
            new PlayerLoadOptions(new PublicReadAccessClassOptions()));
        return result.TryGetValue(key, out var item) ? item.Value.GetAsString() : null;
    }

    public async Task<List<string>> LoadAllDefaultKeysAsync()
    {
        var result = await CloudSaveService.Instance.Data.Player.LoadAllAsync(
            new PlayerLoadAllOptions(new DefaultReadAccessClassOptions()));
        return new List<string>(result.Keys);
    }
}
```

## A smoke test to attach beside it

```csharp
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;

/// <summary>
/// Sits on the same GameObject as PlayerAccountManager. Signs in anonymously, logs the
/// identity it got, round-trips one value through the Default bucket, then lists the keys.
/// </summary>
public class PlayerAccountTester : MonoBehaviour
{
    [SerializeField] PlayerAccountManager m_Manager;

    async void Start()
    {
        if (m_Manager == null)
            m_Manager = GetComponent<PlayerAccountManager>();

        m_Manager.SignedIn += OnSignedIn;
        await m_Manager.SignInAnonymouslyAsync();
    }

    async void OnSignedIn()
    {
        LogIdentity("Signed in");

        // PlayerName is often still null right after an anonymous sign-in.
        await m_Manager.GetPlayerNameAsync();
        LogIdentity("After name fetch");

        const string key = "tester_probe";
        const string expected = "ok";
        await m_Manager.SaveDefaultAsync(key, expected);
        var loaded = await m_Manager.LoadDefaultAsync(key);

        Debug.Log($"[PlayerAccountTester] round-trip: " +
            $"{(loaded == expected ? "OK" : $"MISMATCH (got '{loaded}')")}");

        LogKeys(await m_Manager.LoadAllDefaultKeysAsync());
    }

    void LogIdentity(string label)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"[PlayerAccountTester] {label}:");
        sb.AppendLine($"  PlayerId   : {m_Manager.PlayerId ?? "<null>"}");
        sb.AppendLine($"  PlayerName : {(string.IsNullOrEmpty(m_Manager.PlayerName) ? "<none>" : m_Manager.PlayerName)}");
        sb.AppendLine($"  IsSignedIn : {m_Manager.IsSignedIn}");
        Debug.Log(sb.ToString());
    }

    void LogKeys(List<string> keys)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"[PlayerAccountTester] Default bucket keys ({keys.Count}):");
        foreach (var k in keys)
            sb.AppendLine($"  {k}");
        Debug.Log(sb.ToString());
    }
}
```

A save-then-load probe is worth keeping past the first day: it fails the moment an access class
stops matching, which is otherwise the hardest thing in this file to notice.

## Errors

`AuthenticationException` and `PlayerAccountsException` both extend `RequestFailedException`, so
catch the specific one first and let the general one take network faults.

| `AuthenticationErrorCodes` | Value | |
|---|---|---|
| `ClientInvalidUserState` | 10000 | Not valid from the current state |
| `InvalidParameters` | 10002 | Bad input |
| `AccountAlreadyLinked` | 10003 | Username taken on sign-up, or the external id belongs to another player |

| `PlayerAccountsErrorCodes` | Value | |
|---|---|---|
| `InvalidState` | 10101 | Already signed in |
| `MissingClientId` | 10102 | Client id not configured in the dashboard |

`MissingClientId` is a dashboard problem wearing a code error's clothes — nothing in the project
can fix it.

Cloud Save has its own hierarchy; order the catches specific first:

```csharp
try
{
    await CloudSaveService.Instance.Data.Player.SaveAsync(data);
}
catch (CloudSaveValidationException ex)
{
    foreach (var d in ex.Details)
        Debug.LogError($"Validation: {d.Field} {string.Join(", ", d.Messages)}");
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

## Before you call it done

- Every namespace resolves, aliases included.
- `InitializeAsync()` precedes every `*.Instance` touch, on every entry path.
- The `.asmdef` references **both** authentication assemblies.
- `PlayerAccountService.Instance.SignedIn` is subscribed before `StartSignInAsync()` runs.
- Each key is loaded with the access class it was saved with.
- Nothing awaits `SignOut()` on either service.

## Where to go next

- Linking providers, profiles, the full error table: [`authentication.md`](authentication.md)
- Buckets, write locks and queries: [`cloud-save.md`](cloud-save.md)
- Server-written player state: [`achievements.md`](achievements.md)
- The Player Account Building Block, which ships this working:
  [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-player-account-341928)
