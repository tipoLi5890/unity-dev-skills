# Building Blocks and samples — start from one that runs

Unity publishes free Building Block packages on the Asset Store: each is a working vertical slice
with UI, runtime code, Cloud Code modules and the cloud resource files already written. When the
request is "add achievements" or "add leaderboards", importing one and reading it is faster than
assembling the same thing from this skill, and the blueprints in SKILL.md §10 then read as
annotations on something that already runs.

| Building Block | Depends on | Where |
|---|---|---|
| Achievements | `cloudsave`, `remote-config`, `cloudcode`, `tooling`, `deployment`, `analytics`, `authentication` | [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-achievements-341918) |
| Leaderboards | `leaderboards`, `cloudcode`, `tooling`, `deployment`, `authentication` | [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-leaderboards-341926) |
| Player Account | `authentication`, `cloudsave`, `cloudcode`, `deployment` | [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-player-account-341928) |
| Multiplayer Session | `multiplayer` | [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-multiplayer-session-341930) |
| Matchmaker Session | `multiplayer`, `deployment` | [Asset Store](https://assetstore.unity.com/packages/essentials/tutorial-projects/unity-building-block-matchmaker-session-341932) |

The blocks are also described as being bundled in a `com.unity.starter-kits` package, along with
Server Session, Vivox and a platformer starter kit. **That id returns 404 on the public registry**,
the same response a built-in package gives, so do not plan on adding it by id from
`packages.unity.com`: use the Asset Store links above.

## Samples worth cloning

Longer references worth cloning rather than paraphrasing:

| Project | What it shows |
|---|---|
| [Use Case Samples](https://github.com/Unity-Technologies/com.unity.services.samples.use-cases) | Battle pass, virtual shop, daily rewards, starter pack, A/B testing |
| [UGS Samples](https://github.com/Unity-Technologies/com.unity.services.samples) | Authentication flows, Economy, Remote Config, Cloud Code |
| [Boss Room](https://github.com/Unity-Technologies/com.unity.multiplayer.samples.coop) | Authentication and Multiplayer Services in a co-op game |
| [Gem Hunter Match](https://assetstore.unity.com/packages/essentials/tutorial-projects/gem-hunter-match-2d-sample-project-278941) | A full 2D game with progression, hub and store |
