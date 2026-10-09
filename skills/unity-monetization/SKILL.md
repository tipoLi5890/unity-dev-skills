---
name: unity-monetization
description: >-
  Where in-app purchases and ads collide with shipping a Unity build. Load
  when adding IAP or ad mediation to a game, when purchases work in the
  editor and not on the device, when adding an ad SDK changes the APK's
  permissions or breaks the Gradle or CocoaPods build, when preparing a
  store submission that declares purchases or advertising ID, or when
  deciding whether receipts are validated on the client or on a server.
  Covers sandbox behaviour in a release build, what an ad or IAP SDK adds to
  the merged manifest and to the Gradle/CocoaPods build, the store
  declarations that follow, and idempotent grants. Store-listing work and
  the artifact itself are unity-android-release.
---

# unity-monetization — the seam between an SDK and a shippable build

> **Integrating the SDK is the easy half.** The half that costs a rejected submission is what the
> SDK does to the merged manifest, to the Gradle or CocoaPods build, and to what the store
> requires you to declare.

## Symptom → where to look

| Symptom | Go to |
|---|---|
| Purchases work in the editor, not on device | §1 |
| Adding an ad SDK broke the Android build | §2 |
| Permissions appeared in the APK that nobody added | §2 |
| Store submission rejected over data disclosure or advertising ID | §3 |
| Deciding where receipts are validated | §4 |
| A tester was granted an item they did not buy | §4 |

**When to jump.** This skill owns the seam — what an SDK does to the artifact, what the store then
makes you declare, and where a grant is allowed to be decided. The call-by-call SDK work lives next
door: `unity-iap` for connecting to a store, the catalogue and the purchase flow,
`unity-ads-levelplay` for the mediation SDK and its ad units. Go there to write the integration,
come back here before the build.

## 1. Sandbox is a different code path

The editor stubs the store. A device talks to a real one, in one of three modes — sandbox, an
internal/closed test track, or production — **and they behave differently from each other**, not
just from the editor.

- **A purchase never completes in the editor in a way that proves anything.** Verify on a device,
  on a track, with a test account, before believing the flow works.
- **Test accounts are per-store configuration, not per-build.** A build that works for you and
  fails for a tester is usually the account, not the code.
- **Restore purchases is mandatory on iOS and is the path nobody tests.** It must work on a fresh
  install with no local state, because that is exactly when a player needs it.
- **Pending purchases must survive the app being killed mid-transaction.** Confirm the grant only
  after it is durable; a purchase acknowledged before the grant is written is a lost purchase and
  a refund request.

Two properties of the purchasing package decide how the code around that has to be shaped.
`unity-iap` carries them in full; test both in a store sandbox.

- **An unconfirmed purchase is replayed the moment you connect,** including one made in a session
  that ended days ago. A handler registered after the connect call therefore misses exactly the
  purchase that most needs granting: subscribe first, connect second. That replay is also what
  makes the durability rule above affordable — key the grant on the transaction id and the repeat
  delivery costs nothing instead of granting twice.
- **Once a consumable is confirmed the store stops mentioning it.** Refetching purchases returns
  non-consumables and subscriptions; a coin pack that was granted and confirmed is simply absent.
  The only record that it happened is the one you wrote yourself, before confirming — which is why
  §4's idempotent grant is a save-side concern rather than a store-side one.

## 2. What an SDK does to your build

This is the direct seam with `unity-android-release`.

- **An ad or IAP SDK adds permissions via manifest merge.** They will not appear in any setting
  you edited. **Read them back off the artifact** —
  `unity-android-release` → `reference/artifact-verification.md`. `com.google.android.gms.permission.AD_ID`
  is the one that surprises people, and it is the one the store asks about.
- **Two SDKs pulling different versions of the same transitive dependency is the classic Gradle
  failure.** The error names a class, not the conflict. Resolve versions explicitly rather than
  removing whichever SDK you added most recently.
- **Native `.aar` dependencies must carry every ABI you ship.** A missing `arm64-v8a` builds
  cleanly and crashes on launch — the ABI gate in `unity-android-release`'s
  `templates/build-android.sh`, installed at `Tools/`, covers this, and an ad SDK is exactly what
  trips it.
- **Adding an SDK is a size event.** Record the artifact size before and after; if it moved more
  than expected, `unity-android-release` → `reference/size-and-stripping.md`.
- **SDKs use reflection, so managed stripping can remove their callbacks.** Symptom: initialises
  fine, no callback ever arrives, no exception. `[Preserve]` or `link.xml`.

## 3. What the store makes you declare

Adding monetisation changes the submission, not just the build:

- **Data safety / privacy nutrition labels** must match what the SDKs actually collect. An ad
  mediation SDK collects more than the game does, and the declaration is about the shipped
  binary, not your intent.
- **Advertising ID** must be declared on Android when present, and it is present as soon as an ad
  SDK is linked — see §2.
- **iOS ATT**: if the SDK requests tracking, the prompt and its usage-description string are
  required, and the string is reviewed by a person.
- **A build that contains an ad SDK but ships with ads disabled still declares everything the SDK
  brings.** "We turned it off in config" is not a defence at review.

Gate these in the release script rather than in a checklist —
`unity-android-release` → `reference/store-submission.md`.

## 4. Where a receipt is validated

| Validated | Good enough when | Not good enough when |
|---|---|---|
| On the client (Google Play only — on Apple the client check does nothing, `unity-iap` §5) | Purchases unlock local content only, and a cheater only cheats themselves | Anything else, and anything on Apple |
| On a server | Currency, anything tradeable, anything competitive, anything a support agent may have to reverse | — |

> **A client-validated receipt is an unsigned assertion by an untrusted process.** If the grant
> touches a balance or another player, it needs server validation and the grant needs to happen
> server-side. `unity-live-services` §3.

Grants must be **idempotent**: a retry after a timeout must not grant twice. Use a purchase
token as the operation key.

## Verification

- Buy, kill the app mid-transaction, relaunch — the item is granted exactly once.
- Fresh install, restore purchases — entitlements return with no local state.
- `aapt dump permissions` on the artifact matches what was declared to the store.
- Artifact size and ABI list recorded before and after adding the SDK.

## Scope — what this skill does NOT do

The SDK surface itself. `unity-iap` owns the v5 purchase flow, the product catalogue, the receipt
and entitlement APIs and the migrations into them; `unity-ads-levelplay` owns the mediation SDK
integration, ad unit wiring and the privacy-consent APIs. Also out: pricing and monetisation design,
and server-side entitlement (`unity-live-services`).
