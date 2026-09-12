# Authentication — identity, and the signatures people get wrong

`AuthenticationService.Instance` (`IAuthenticationService`), namespace `Unity.Services.Authentication`,
assembly `Unity.Services.Authentication`. `UnityServices.InitializeAsync()` from
`com.unity.services.core` must have completed first. Floors: [`packages.md`](packages.md).

## Wrong → Correct

Half of the compile errors in an authentication integration are one of these six. The pattern is
consistent: the async-looking method is synchronous, and the one-argument social overload is the
deprecated one.

| Wrong | Correct |
|---|---|
| `await ...SignOutAsync()` | `SignOut(bool clearCredentials = false)` — synchronous `void`, there is no async form |
| `await ...SwitchProfileAsync(name)` | `SwitchProfile(string)` — synchronous `void` |
| `await ...ClearSessionTokenAsync()` | `ClearSessionToken()` — synchronous `void` |
| `SignInWithSteamAsync(ticket)` | `SignInWithSteamAsync(ticket, identity)` — the one-argument overload carries `[Obsolete]`. Same for `LinkWithSteamAsync` |
| `SignInWithOculusAsync(nonce)` | `SignInWithOculusAsync(nonce, userId)` — both required. Same for `LinkWithOculusAsync` |
| `if (service.IsAnonymous)` | No such property on the service. Inspect `PlayerInfo.Identities` to see what is linked |
| `await ...UnlinkUsernamePasswordAsync()` | Does not exist — username/password cannot be unlinked once added |

## Sign-in methods

```csharp
// Anonymous. Signs in silently with a cached session token if one exists, otherwise
// creates a new player.
Task SignInAnonymouslyAsync(SignInOptions options = default)

// Token-based social providers.
Task SignInWithGoogleAsync(string idToken, SignInOptions options = default)
Task SignInWithGooglePlayGamesAsync(string authCode, SignInOptions options = default)
Task SignInWithAppleAsync(string idToken, SignInOptions options = default)
Task SignInWithAppleGameCenterAsync(string signature, string teamPlayerId, string publicKeyURL,
    string salt, ulong timestamp, SignInOptions options = default)
Task SignInWithFacebookAsync(string accessToken, SignInOptions options = default)

// Steam: identity is required. The one-argument overload is deprecated.
[Obsolete] Task SignInWithSteamAsync(string sessionTicket, SignInOptions options = default)
Task SignInWithSteamAsync(string sessionTicket, string identity, SignInOptions options = default)
// Sub-apps (PlayTest, Demo) take the appId as well:
Task SignInWithSteamAsync(string sessionTicket, string identity, string appId,
    SignInOptions options = default)

// Oculus: nonce and userId are both required.
Task SignInWithOculusAsync(string nonce, string userId, SignInOptions options = default)

// Generic OIDC provider, configured by name in the dashboard.
Task SignInWithOpenIdConnectAsync(string idProviderName, string idToken,
    SignInOptions options = default)

// Unity Player Accounts — the token comes from PlayerAccountService (see player-account.md).
Task SignInWithUnityAsync(string token, SignInOptions options = default)

// Username/password: registration and sign-in are separate calls, and neither takes options.
Task SignUpWithUsernamePasswordAsync(string username, string password)
Task SignInWithUsernamePasswordAsync(string username, string password)

// Device code flow: show a code on the constrained device, confirm it elsewhere.
Task<SignInCodeInfo> GenerateSignInCodeAsync(string identifier = default)
Task SignInWithCodeAsync(bool usePolling = false, CancellationToken cancellationToken = default)
Task<SignInCodeInfo> GetSignInCodeInfoAsync(string code)
Task ConfirmCodeAsync(string code, string idProvider = default, string externalToken = default)

// Synchronous. Not async.
void SignOut(bool clearCredentials = false)

// Deletes the Authentication record only — read the warning at the end of this file.
Task DeleteAccountAsync()
```

## State properties

| Property | Type | Meaning |
|---|---|---|
| `IsSignedIn` | `bool` | A token exists in memory — **expired or not** |
| `IsAuthorized` | `bool` | A token exists **and** has not expired: calls will be accepted |
| `IsExpired` | `bool` | A token exists but has expired; the SDK is attempting refresh |
| `PlayerId` | `string` | Stable player identifier, available as soon as sign-in returns |
| `PlayerName` | `string` | Display name; may be null until fetched |
| `AccessToken` | `string` | JWT used for service calls |
| `Profile` | `string` | Active profile name |
| `SessionTokenExists` | `bool` | A session token is cached on this device |

The three-way distinction matters because the obvious guard is the wrong one: `IsSignedIn` stays
true through expiry, so a retry gated on it retries with a dead token. Gate on `IsAuthorized`,
and let the `Expired` → `SignInFailed` pair tell you when refresh has genuinely given up.

## Events

| Event | Signature | Fires when |
|---|---|---|
| `SignedIn` | `Action` | Any sign-in method succeeds |
| `SignedOut` | `Action` | The player signs out |
| `Expired` | `Action` | The access token expired. The SDK now tries to refresh — this is not yet a failure |
| `SignInFailed` | `Action<RequestFailedException>` | Sign-in, or a refresh, failed. This is the one that means re-authenticate |
| `SignInCodeReceived` | `Action<SignInCodeInfo>` | Device code flow: a code was issued |
| `SignInCodeExpired` | `Action` | Device code flow: the code timed out |
| `PlayerNameChanged` | `Action<string>` | Name updated, carries the new name |
| `PlayerIdChanged` | `Action<string>` | Player id changed, carries the new id |
| `PlayerInfoChanged` | `Action<PlayerInfo>` | Player info updated |

```csharp
AuthenticationService.Instance.Expired += () =>
    Debug.Log("Token expired; the SDK is refreshing. Not an error yet.");

AuthenticationService.Instance.SignInFailed += ex =>
    Debug.LogError($"Refresh gave up — send the player back to sign-in: {ex.Message}");
```

## Player info and name

```csharp
Task<PlayerInfo> GetPlayerInfoAsync()
Task<string> GetPlayerNameAsync(bool autoGenerate = true)
Task<string> UpdatePlayerNameAsync(string name)
```

`PlayerInfo` carries `Id`, `Username` (nullable), `Identities` (`List<Identity>` — the linked
providers), `CreatedAt` and `LastPasswordUpdate` (both `DateTime?`). Rather than reading
`Identities` by hand it exposes one accessor per provider: `GetGoogleId()`, `GetAppleId()`,
`GetFacebookId()`, `GetSteamId()`, `GetOculusId()`, `GetGooglePlayGamesId()`,
`GetAppleGameCenterId()`, `GetUnityId()`, `GetOpenIdConnectId(providerName)`, `GetCustomId()` and
`GetOpenIdConnectIdProviders()`.

## Linking and unlinking

Every `Link*` method takes an optional `LinkOptions`, whose only member is `ForceLink`.

```csharp
Task LinkWithGoogleAsync(string idToken, LinkOptions options = default)
Task LinkWithGooglePlayGamesAsync(string authCode, LinkOptions options = default)
Task LinkWithAppleAsync(string idToken, LinkOptions options = default)
Task LinkWithAppleGameCenterAsync(string signature, string teamPlayerId, string publicKeyURL,
    string salt, ulong timestamp, LinkOptions options = default)
Task LinkWithFacebookAsync(string accessToken, LinkOptions options = default)
[Obsolete] Task LinkWithSteamAsync(string sessionTicket, LinkOptions options = default)
Task LinkWithSteamAsync(string sessionTicket, string identity, LinkOptions options = default)
Task LinkWithSteamAsync(string sessionTicket, string identity, string appId,
    LinkOptions options = default)
Task LinkWithOculusAsync(string nonce, string userId, LinkOptions options = default)
Task LinkWithOpenIdConnectAsync(string idProviderName, string idToken,
    LinkOptions options = default)
Task LinkWithUnityAsync(string token, LinkOptions options = default)

Task UnlinkGoogleAsync()
Task UnlinkGooglePlayGamesAsync()
Task UnlinkAppleAsync()
Task UnlinkAppleGameCenterAsync()
Task UnlinkFacebookAsync()
Task UnlinkSteamAsync()
Task UnlinkOculusAsync()
Task UnlinkOpenIdConnectAsync(string idProviderName)
Task UnlinkUnityAsync()
```

The list is asymmetric on purpose: **there is no unlink for username/password.** Once a player
adds those credentials they stay.

```csharp
try
{
    await AuthenticationService.Instance.LinkWithGoogleAsync(googleIdToken);
}
catch (AuthenticationException ex)
    when (ex.ErrorCode == AuthenticationErrorCodes.AccountAlreadyLinked)
{
    // 10003 — that Google account already belongs to a different player.
    // ForceLink steals the link from the other player. Ask first; it is not reversible.
    await AuthenticationService.Instance.LinkWithGoogleAsync(
        googleIdToken, new LinkOptions { ForceLink = true });
}
```

## Profiles

```csharp
void SwitchProfile(string profile)      // synchronous; must precede sign-in
void ClearSessionToken()                // synchronous; clears the active profile's cache
void ProcessAuthenticationTokens(string accessToken, string sessionToken = default)
```

A profile is a separate credential cache on one device, which is how two accounts share a phone
or how a test rig keeps fixtures apart. The ordering is strict — sign out, switch, sign in:

```csharp
AuthenticationService.Instance.SignOut();
AuthenticationService.Instance.SwitchProfile("ProfileB");
await AuthenticationService.Instance.SignInAnonymouslyAsync();
```

## Username and password rules

| Field | Constraint |
|---|---|
| Username length | 3–20 characters |
| Username characters | `A-Z`, `a-z`, `0-9`, `.`, `-`, `@`, `_` |
| Username case | Case-insensitive, stored lowercase |
| Password length | 8–30 characters |
| Password content | At least one lowercase, one uppercase, one digit and one symbol |

Validate against this table on the client before the call: a rejection round trip is the same
error code as several other problems, so local validation is what makes the message specific.

```csharp
// Add credentials to an account that already exists (typically an anonymous one).
Task AddUsernamePasswordAsync(string username, string password)

// Changing the password signs the player out of every other device.
Task UpdatePasswordAsync(string currentPassword, string newPassword)
```

## Option types

| Type | Member | Default | Effect |
|---|---|---|---|
| `SignInOptions` | `CreateAccount` | `true` | `false` signs in only if the credentials already map to a player, instead of creating one |
| `LinkOptions` | `ForceLink` | `false` | `true` removes the link from whichever player currently holds it |
| `SignInCodeInfo` | `SignInCode`, `Identifier`, `Expiration` | — | The code to display, its identifier, and when it dies |

## Identity providers

| Provider | Configured in the dashboard with | The SDK wants | Method |
|---|---|---|---|
| Anonymous | nothing | nothing | `SignInAnonymouslyAsync()` |
| Google | Client ID, Client Secret | ID token | `SignInWithGoogleAsync(idToken)` |
| Google Play Games | Client ID, Client Secret | Auth code | `SignInWithGooglePlayGamesAsync(authCode)` |
| Apple | Client ID, Client Secret | ID token | `SignInWithAppleAsync(idToken)` |
| Apple Game Center | Client ID, Client Secret | Signature bundle | `SignInWithAppleGameCenterAsync(...)` |
| Facebook | Client ID, Client Secret | Access token | `SignInWithFacebookAsync(accessToken)` |
| Steam | Publisher Web API Key | Session ticket + identity | `SignInWithSteamAsync(ticket, identity)` |
| Oculus | App ID, App Secret | Nonce + user id | `SignInWithOculusAsync(nonce, userId)` |
| OpenID Connect | Client ID, Client Secret, Issuer URL | ID token | `SignInWithOpenIdConnectAsync(name, idToken)` |
| Unity Player Accounts | enable it | Access token | `SignInWithUnityAsync(token)` |
| Username / password | enable it | Username + password | `SignInWithUsernamePasswordAsync(u, p)` |

Providers live in the dashboard under the project's Authentication product, Identity Providers.
There is no local file for them, which is why an integration that compiles can still fail with
`InvalidProvider` — the provider was never enabled in the environment the build is bound to.

## Templates

Initialise and sign in — the shape every other snippet in this skill assumes:

```csharp
using Unity.Services.Core;
using Unity.Services.Authentication;

async Task InitAndSignIn()
{
    await UnityServices.InitializeAsync();

    // Covers both cases: a cached session token signs in silently, no token creates a player.
    if (!AuthenticationService.Instance.IsSignedIn)
        await AuthenticationService.Instance.SignInAnonymouslyAsync();

    Debug.Log($"Signed in as {AuthenticationService.Instance.PlayerId}");
}
```

Account management:

```csharp
var info    = await AuthenticationService.Instance.GetPlayerInfoAsync();
var name    = await AuthenticationService.Instance.GetPlayerNameAsync();
var updated = await AuthenticationService.Instance.UpdatePlayerNameAsync("NewName");

await AuthenticationService.Instance.AddUsernamePasswordAsync(username, password);
await AuthenticationService.Instance.UpdatePasswordAsync(currentPassword, newPassword);
await AuthenticationService.Instance.DeleteAccountAsync();
```

## Errors

`AuthenticationException` extends `RequestFailedException`. Catch the specific one first and
compare `ex.ErrorCode` against `AuthenticationErrorCodes`; the general one then catches network
and service faults.

```csharp
try
{
    await AuthenticationService.Instance.SignInAnonymouslyAsync();
}
catch (AuthenticationException ex)
{
    Debug.LogError($"Auth failed: {ex.Message} (code: {ex.ErrorCode})");
}
catch (RequestFailedException ex)
{
    Debug.LogError($"Request failed: {ex.Message}");
}
```

| Constant | Value | Meaning |
|---|---|---|
| `ClientInvalidUserState` | 10000 | The operation is not valid from the current state |
| `ClientNoActiveSession` | 10001 | No active session |
| `InvalidParameters` | 10002 | Bad input |
| `AccountAlreadyLinked` | 10003 | The external id already belongs to another player |
| `AccountLinkLimitExceeded` | 10004 | Too many linked accounts for this provider type |
| `ClientUnlinkExternalIdNotFound` | 10005 | Nothing to unlink |
| `ClientInvalidProfile` | 10006 | Invalid profile name |
| `InvalidSessionToken` | 10007 | Session token invalid or expired |
| `InvalidProvider` | 10008 | Unknown provider — usually one not enabled in this environment |
| `BannedUser` | 10009 | The player is banned |
| `EnvironmentMismatch` | 10010 | The cached session token belongs to a different environment |

`EnvironmentMismatch` is the one worth recognising on sight: it means the build changed
environments while a token from the old one was still cached. `unity-live-services` §1 is about
making that visible rather than diagnosable.

Error bodies follow RFC 7807. Branch on `status` and `title`; **`detail` is prose and may change**,
so matching on it produces handling that breaks silently on a service update.

## Three ways to lose an account

- **Consoles do not auto-refresh.** On Xbox, PlayStation and Switch, expiry means re-signing in
  by hand. A game that assumes the mobile behaviour looks fine in testing and logs players out
  mid-session in the wild.
- **`ClearSessionToken()` or `SignOut(clearCredentials: true)` on an anonymous-only account
  destroys it.** There is no recovery: no provider is linked, so nothing identifies the player.
  Offer that button only once at least one provider is linked.
- **`DeleteAccountAsync()` deletes the Authentication record and nothing else.** Cloud Save,
  Economy and Leaderboards data survive it. The App Store requires account deletion for any app
  offering account creation, so this call is not optional — but satisfying that requirement means
  deleting the other services' data first, and that ordering is yours to write.

## Where to go next

- Browser-based Unity sign-in, the second assembly it needs, and the event that actually signals
  completion: [`player-account.md`](player-account.md)
- Storing anything per player once signed in: [`cloud-save.md`](cloud-save.md)
- Locking down what a signed-in player may call: [`tooling.md`](tooling.md)
- [Authentication manual](https://docs.unity.com/ugs/en-us/manual/authentication/manual)
