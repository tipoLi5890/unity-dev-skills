# Grounding a recommendation before giving one

Architecture advice that ignores the repo is worse than no advice: it produces a plan the project
cannot adopt without undoing work. Read first, ask second, recommend third.

## The order

1. **What the user already said.** "Two-player co-op", "ranked 5v5", "mobile", "the host keeps
   dropping" — each of those settles a dimension below on its own.
2. **What the project already shows.** `Packages/manifest.json` (which netcode stack, whether the
   multiplayer package is even in), existing networking scripts, a server build target, deployment
   assets under the project. A choice already made in the repo outranks a preference.
3. **One short question.** Only for a dimension that would change the recommendation and that
   neither (1) nor (2) settles. Phrase it as in [`player-language.md`](player-language.md) — about the game, not
   about the SDK.

Map the answers onto the API surface in [`session-api.md`](session-api.md) only once the
requirements are actually clear. Guessing the topology and then presenting the calls for it reads
as confident and is unrecoverable when wrong.

## The six dimensions

| Dimension | What to establish | What it decides internally |
|---|---|---|
| **Player count and topology** | Players per match, and many small matches versus a few large ones. Can one player's machine run the simulation, or does it need a machine nobody is playing on? | Relay versus direct networking; host role versus a dedicated server session; capacity limits on `MaxPlayers` |
| **Casual or competitive** | How much a host-side advantage costs the game. Money, ranking or persistent standing on the line pushes hard toward a server nobody owns | How strongly to push a dedicated server, and how much of the state can be trusted from a client |
| **How matches form** | Codes and invites, a browsable list, or automatic pairing. What the player filters on when browsing | `JoinSessionByCodeAsync` versus `QuerySessionsAsync` versus `MatchmakeSessionAsync`; which session properties need index slots |
| **Connection model and resilience** | Home networks and NAT, whether a dropped player can come back, whether the match survives the host leaving | `WithRelayNetwork` versus `WithDirectNetwork`; `ReconnectToSessionAsync`; `WithHostMigration` and the migration payload |
| **Platforms** | Mobile backgrounding and dropouts, console networking and certification expectations | Match lifetime, reconnect UX, how long a session should hold a slot open |
| **Existing stack and team** | Netcode for GameObjects or Netcode for Entities, and what the team has actually shipped with | Extend what `manifest.json` already has. Introducing a second net model without being asked is a rewrite disguised as a recommendation |

The topology decision itself — what each option costs later, and why it is expensive to reverse —
belongs to `unity-multiplayer`. This file is about establishing which one the project needs; that
skill is about living with it.

## Language

Everything the user reads — questions, plans, summaries, trade-off write-ups — stays in game terms.
Product names (Lobby, Matchmaker, Relay, Sessions) and type names (`ISession`, `QuerySessionsAsync`)
appear in questions only if the user put them there first. Code, file edits and technical reference
material use the real names throughout; nobody benefits from an obfuscated `using` statement. The
before/after pairs are in [`player-language.md`](player-language.md).
