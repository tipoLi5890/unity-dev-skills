# Saying it in the player's language

These are the phrasings the rule in `SKILL.md` §6 produces. They apply to prose the user reads —
questions, plans, summaries. Code and file contents use real type names.

## Asking

| Instead of | Ask |
|---|---|
| "Do you want Lobby for the server list, or Sessions only?" | "Should players see a list of open games and pick one, or only get in through a code or an invite?" |
| "Should this call `QuerySessionsAsync` or `MatchmakeSessionAsync`?" | "Does the game find opponents for the player, or does the player choose a room?" |
| "Do you need Relay, or is direct fine?" | "Two players on different home internet connections, no router setup — does that have to work?" |
| "Do you want host migration enabled?" | "If the player who started the match quits, should the others keep playing, or is the match over?" |

Every question on the right is answerable by someone who has never opened Package Manager. That is
the test.

## Explaining

**Splitting the backend into named products:**

> "We'll use Lobby for the room metadata, Relay for NAT traversal, and Matchmaker for ranked play.
> Sessions wraps Lobby, so you don't need Lobby directly."

Three product names and an architecture lesson, for a reader who asked how their friends join a
game. What they need instead:

> "One system holds the room — who is in it, the map, the rules — and hands the match a working
> connection even when both players are behind home routers. Ranked pairs players up
> automatically; the friends flow uses a code. It is one API, so there is no second room system to
> keep in step."

Same design, no vocabulary the reader has to acquire first.

## When the user names a product themselves

If they write "we're already on Relay", mirror that word — refusing to say it back is its own kind
of noise. What still does not follow is enumerating the rest of the stack they did not ask about,
or explaining which product wraps which, unless they asked for that level.
