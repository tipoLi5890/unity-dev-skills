# When the backend is somebody else's HTTP API

Not every live feature runs on a games backend. A game that calls an LLM, a translation service,
a weather feed or any other third-party HTTP API from the client has the same three problems as a
UGS integration — a credential, an outbound payload, and a failure path — but arranged
differently, because **the credential may not be yours to ship**.

The worked example throughout is an Android IL2CPP game that sends a per-run summary to a
third-party API: the player pastes their own provider key on a settings sub-screen, the key is
stored on the device, and the APK contains no key at all.

## Who owns the key decides where it lives

| Key | Owner | Where it may live |
|---|---|---|
| Project id, environment name, endpoint host, model id | You | In the repo, in the build. Not secret |
| Your provider account key, billed to you | You | **Server only.** A proxy you run holds it; the build calls the proxy |
| The player's own provider key | The player | **On their device only.** Entered in-app, never in the repo, never in the artifact, never in your logs |

The third row is the one people get wrong, in both directions. Shipping *your* key inside the
build so the feature "just works" makes it public — `strings` on the artifact is enough. Putting
the *player's* key anywhere you can read it — a crash report, an analytics event, an error string
that echoes the request — turns their bill into your incident.

A player-supplied key is a legitimate way to ship a paid-API feature without running a backend,
and it changes the artifact check from "is my key in here" to "is *any* key in here":

```bash
# same toolchain as unity-android-release → reference/artifact-verification.md
strings -a app.apk | grep -Ei "api[_-]?key[\"']?[[:space:]]*[:=]"   # expect: nothing
strings -a app.apk | grep -E 'sk-[A-Za-z0-9]{16,}'                 # whatever prefix your provider uses
strings -a app.apk | grep -F 'api.your-provider.com'               # endpoint is fine; a key beside it is not
```

Once the feature scales past "each player brings their own key", the shape changes to a thin
proxy that holds one key, rate-limits, and never returns it — the same conclusion SKILL.md §2
reaches for anything that authorises a write. (Section numbers below are SKILL.md's.)

## Storage, and what it does not protect

Keep the key where the OS already keeps app-private data — on Android, Unity's per-app preference
store lands there. That is enough to keep it away from other apps on a non-rooted device, and it
is **not** encryption: a rooted device, a debuggable build, or a device backup can still surface
it. Write the residual risk down where the product decisions live rather than implying the value
is protected.

Two rules that cost nothing:

- **The value never enters a log line, an analytics event, or an error message.** Parse failures
  should report the status code and a short truncated prefix of the response body, and nothing
  from the request. Never log request headers.
- **The key is passed to the transport at call time**, from the store, by the caller. No static
  holds it, nothing else in the codebase can reach for it, and the header is written in exactly
  one place.

## Mask it everywhere it is rendered — including the entry field

A device screenshot of the key-entry screen, pasted into a chat during development, carries the
full plaintext key with it. Masking the row that *displays* a stored key is the half everyone
remembers; the field the key was typed into is the half that leaks.

- **Mask at the input field too**, with a reveal the player has to hold or tap. In uGUI that is
  the input field's content type: left on the default `Standard` content type it renders every
  character. Whatever the UI system, the *default* state of a key field is masked.
- **The last four characters are enough** for "yes, that is the key I pasted". Nothing in the UI
  needs the middle.
- **Any screenshot, screen recording, bug report or support log that contains a key is a rotation
  event.** Say so in-product next to the field, so the player knows what to do instead of
  wondering whether it matters. There is no un-sending a screenshot.

## The outbound allow-list, and the test that keeps it honest

§3 asks what the client is not allowed to be *believed* about. A third-party API adds the mirror
question: **what is this build allowed to send off the device?** Answer it with an explicit
allow-list, not by omission.

In the worked example the payload carries derived numbers only — scores, computed indicators,
per-run aggregates, a run timeline — and never a display name, a local profile id, a raw event
stream or captured audio. The local record holds all of those; the payload builder simply never
reads them.

Two rules keep an allow-list an allow-list:

- **One dedicated builder is the only thing that may serialise for the network.** If two places
  can assemble a request body, the allow-list is a convention rather than a boundary.
- **Filter any free-form section through a whitelist of key names**, so a field added to the local
  record later cannot ride along uninvited. The default for a new field must be "not sent".

The test is what makes this a rule rather than an intention — assert on the *serialised string*,
because that is what leaves the device:

```csharp
string json = Payload.Build(record, indicators, /* … */ locale);
StringAssert.DoesNotContain(record.playerName, json);
StringAssert.DoesNotContain(record.profileId, json);
StringAssert.DoesNotContain("\"events\"", json);
StringAssert.DoesNotContain("\"someUnwhitelistedKey\"", json);
Assert.IsNotNull(Json.Parse(json), "payload is still valid JSON");
```

The same assertion is worth repeating one level up, against the body the transport actually
received during a full-flow test — the payload builder being clean does not prove the caller sent
its output rather than something else.

## An injectable transport buys you the whole flow in CI

Put the HTTP call behind an interface with a swappable default:

```csharp
public interface ITransport { IEnumerator Post(string url, string apiKey, string body,
                                               Action<long, string, string> done); }  // status, body, networkError
public static ITransport Transport = new WebTransport();   // tests assign a fake, then restore it
```

The seam buys the feature's whole test coverage with no network and no key:

- **EditMode tests over pure functions** — request body shape, response parsing, error mapping —
  none of which need an editor that can reach the internet.
- **A PlayMode smoke test that walks consent → report** against a fake transport. The fake
  captures the request body, so the "no identity left the device" assertion runs against a send
  the caller actually made, not against the builder's return value.
- **Restore the previous transport, key and consent flag in the same test body**, so a failing
  assertion does not leave a fake transport installed for the rest of the run.

Nothing here requires network access in CI, which is also why it keeps working when the provider
is down or the account has no credit.

## Consent, degradation, and not paying twice

- **A persisted consent gate before the first outbound send.** The first attempt shows what will
  be sent and asks; the answer is stored; later sessions do not re-ask. It is the screen where the
  allow-list above becomes a sentence a player can read. What that sentence must say, and under
  which regime, is a legal question this skill does not answer.
- **The service's prose is never a source of truth for numbers.** Compute every figure locally
  before the call and let the third party write sentences around them. A failed call then still
  leaves the numbers on screen with a retry beside them — §4's "decide what happens when it is
  unreachable", for a feature that is genuinely optional.
- **Cache the response beside the record, keyed by anything that changes it** — the display
  language, for instance, so switching language regenerates while re-opening the same result does
  not. A retry after a call that already succeeded but timed out on the client should read the
  cache, not re-spend the player's money — the billing version of §4's idempotency rule.
- **Pin the endpoint and model as constants covered by a test.** A model id changed by hand in
  three places is how a build starts talking to something nobody priced.
