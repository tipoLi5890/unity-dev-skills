# Initialisation, login and tokens

## The package and what comes with it

`com.unity.services.vivox` provides `Unity.Services.Vivox`. Scripts that also drive the UGS side
need `Unity.Services.Core` and `Unity.Services.Authentication`, which the package brings in as
dependencies. Until the package is installed there is no namespace to import, so the failure is a
compile error naming a missing type — read it as "the package is not here", not as a bad `using`.
SKILL.md's *Before you start* has a one-line presence check.

## The bootstrap

One object, one lifetime, four awaits in a fixed order:

```csharp
using UnityEngine;
using Unity.Services.Core;
using Unity.Services.Authentication;
using Unity.Services.Vivox;

public class VoiceBootstrap : MonoBehaviour
{
    async void Start()
    {
        await UnityServices.InitializeAsync();
        await AuthenticationService.Instance.SignInAnonymouslyAsync();
        await VivoxService.Instance.InitializeAsync();

        VivoxService.Instance.LoggedIn  += HandleLoggedIn;
        VivoxService.Instance.LoggedOut += HandleLoggedOut;

        await VivoxService.Instance.LoginAsync(new LoginOptions
        {
            DisplayName = "Bob",
            EnableTTS   = false
        });
    }

    void HandleLoggedIn()  { /* joins and UI enable belong here, not after the await */ }
    void HandleLoggedOut() { /* teardown */ }

    void OnDestroy()
    {
        if (VivoxService.Instance == null) return;
        VivoxService.Instance.LoggedIn  -= HandleLoggedIn;
        VivoxService.Instance.LoggedOut -= HandleLoggedOut;
    }
}
```

The subscriptions sit between init and login on purpose. `LoggedIn` can fire the instant the
login lands — including immediately, on a reconnect — and a handler attached after `LoginAsync`
returns has already missed it.

## The re-init guard

A second `InitializeAsync()` throws `5041 VxErrorAlreadyInitialized`. Any bootstrap living in a
scene that reloads will hit it eventually. Two answers, and the first is better:

```csharp
// Preferred: the bootstrap exists once for the process.
void Awake() => DontDestroyOnLoad(gameObject);

// Or, if the object genuinely must be per-scene:
if (VivoxService.Instance != null && !VivoxService.Instance.IsInitialized)
    await VivoxService.Instance.InitializeAsync();
```

Do not "solve" it with a try/catch around init — swallowing `5041` hides the duplicated
bootstrap that is also duplicating every event subscription behind it.

## `VivoxConfigurationOptions`

`InitializeAsync` takes an optional configuration object covering log level, audio ducking and
server region. Defaults are the right starting point; change one only when a platform note in
the SDK documentation asks for it, and record why in the code, because a region override is
invisible until someone plays from the wrong continent.

## `LoginOptions`

| Field | What it decides |
|---|---|
| `DisplayName` | The string other participants see on `VivoxParticipant.DisplayName`. Session-scoped, not stored, capped at 127 bytes, and not validated by the SDK — uniqueness and profanity are yours to enforce, server-side |
| `EnableTTS` | Text-to-speech injection into channels. Off unless asked for |
| Blocked list | Players this user has already blocked, applied at login rather than after |

Identity is not in this object. The login binds to
`AuthenticationService.Instance.PlayerId`, which is the address other clients use for directed
messages and the id a moderation backend will recognise. Without UGS sign-in that becomes a
per-session GUID: the voice still works, the ban list does not.

## Logging out

```csharp
await VivoxService.Instance.LogoutAsync();   // fires LoggedOut
```

Call it on a deliberate exit — sign-out, returning to a title screen, quitting. The SDK survives
an ungraceful teardown, but an explicit logout releases the server-side session immediately
instead of waiting for a timeout, which is what stops a player's own ghost appearing in the
roster when they rejoin.

## Server-minted access tokens

The UGS path mints access tokens for you; client code never sees one. Switch to server-side
Vivox Access Tokens when:

- identity comes from somewhere other than UGS Authentication;
- an action needs privilege — kick, mute-all, transcription, join-muted;
- entry to a channel must be gated, so that only a client holding a token for that channel name
  can join it.

The minting endpoint lives on a service you run. The signing key stays there: a key shipped in
the client is a key every player has, and it grants precisely the moderation powers it was
introduced for. The SDK documentation carries reference minting implementations in several
languages; treat them as server samples, never as something to port into a `MonoBehaviour`.
