# Five questions, one page

> Part of the `unity-game-brief` skill. Read this the moment someone says "I want to make a game
> where…". It is the only part of the first hour where the agent mostly asks and mostly does not
> build.

A one-line idea contains an experience that the person can already see and cannot yet write down.
Five questions get it onto a page. More than five and the person is designing by interview; fewer
and the brief has holes that the architecture will quietly fill with a guess.

**Ask one at a time.** A numbered list of five questions comes back as five one-word answers. Each
answer changes what the next question is worth asking about, and the point of asking at all is
that the answers interact.

---

## The five

**1 · What is the player doing, in verbs?**

Push for verbs, not nouns and not genre. "A courier game" is a noun. "Launch a runner down one of
three lanes and get it through the gate before the sentry closes it" is three verbs and a stake.
Take at most three verbs forward: three is what a first version can be built and tuned around, and
the fourth verb is the first line of the "not in the first version" list.

*If the answer is a genre*, ask what the player's hands are doing during the ten seconds the person
is picturing.

**2 · Describe three moments: before, during, after.**

Not a feature list — three pictures. What is on screen just before the action starts, what the
screen looks like at the peak, what happens in the two seconds after it resolves. These become the
three things the visual direction is judged against and the three things the first screenshot walk
has to photograph.

*If a moment cannot be described*, that part of the game does not exist yet, and building it first
is how a first version dies.

**3 · Where is it played?**

Device, viewing distance, aspect, input hardware, session length — as numbers. This question feels
like logistics and is the one that forces the most architecture. Played 2–3 m from a propped-up
tablet with a gamepad that has three physical buttons: that single sentence sets the type sizes,
kills hover states, caps the number of simultaneous choices at three, and decides that the game is
readable at a glance or not at all.

*If the answer is "everywhere"*, ask which one the person will be playing it on this week.

**4 · What must never break?**

The non-negotiables. Push every answer toward a sentence with a number in it, because that is the
difference between a value and a test. "It has to feel fast" becomes "a run is 20–40 seconds from
launch to gate". "The player must always have an out" becomes "every hazard row leaves at least one
lane open". Six shapes these sentences come in: `reference/invariants.md`.

*If nothing comes*, offer the failure instead: "what would make you delete the build?"

**5 · What are you willing to cut?**

Asked last, because it only has an answer once the first four exist. Everything named here goes in
"Not in the first version" **by name** — menus, saving, audio, a second enemy type, difficulty
levels. A reader assumes anything unmentioned is included, and that assumption is what turns a
one-week first version into a three-week one.

---

## Write the answers back as sentences with numbers

The brief is not a transcript. Each answer gets rewritten as a line the project can be checked
against, and read back to the person for a yes:

| They said | Write |
|---|---|
| "It should feel fast" | A run is 20–40 s from launch to the gate. |
| "You should always have a way out" | Every hazard row leaves at least one of the three lanes open. |
| "I want to be able to replay a run" | The same seed produces the same track and the same run. |
| "You have to see it coming" | The runner, the next hazard row and the gate are on screen together at all times. |
| "It's played on the sofa" | Readable at 2–3 m on a propped-up tablet; three physical buttons, no hover, no text under the size the brief sets. |

The rewrite is where most disagreements surface, and they are cheap here. A person who says "no,
20 seconds is too long" has just saved the tuning pass.

---

## Refuse your own brief

Before writing the file, check it against this list. A brief that fails any line is not ready, and
the failure is always cheaper now:

- **The experience sentence has no verb and no stake.** It is a category, not an experience.
- **There are more than three verbs.** Cut to three; the rest are the cut list.
- **A non-negotiable has no number.** It is a preference. Either find the number or move it.
- **"Where it is played" has no distance or input hardware.** Two of the most expensive constraints
  are missing, and the architecture will be derived from air.
- **The cut list is empty.** Nobody has agreed to anything yet, they have only agreed to everything.
- **It is longer than one page.** Something in it is a feature list. The page is the constraint, not
  a formatting preference.
- **It describes how it is built.** Assemblies, managers, state machines and pooling belong in the
  proposal, which is derived from this page — putting them here removes the derivation.

Then fill `templates/GAME_BRIEF.md` and stop. The visual direction and the architecture are the
next two sections of the skill, and both are worse if written before the human has said yes to
this page.

---

## The new-feature variant

An existing game asking for a new feature runs the same five questions, scoped down, plus one:

- **Question 0 — what does this feature change about a moment that already exists?** Name the
  moment. A feature that does not change one of the game's existing moments is a second game
  wearing the first one's assets.
- Verbs: does it add one, or change what an existing one costs? Adding a fourth verb to a
  three-verb game is a bigger change than it looks, and it is worth saying so out loud.
- Non-negotiables: **the existing invariants are inherited**, and the new feature has to hold them
  too. Write the inherited IDs into the feature brief rather than restating them, so a later change
  cannot quietly drop one.
- Cut list: the feature's own, plus anything the feature makes obsolete. A feature that replaces
  something should say what it replaces, or the game keeps both.

The output is the same one page, filed next to the original brief rather than replacing it.
