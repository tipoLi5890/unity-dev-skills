# The Ads Mediation package, and the gate that follows

`SKILL.md` §3 in full: which package, how to tell it is resolved, and what never to do about it.
§4 (native dependencies), §6 and §10 (the version fork) and §7 (initialization) are the router's.


Package Manager lists it as **Ads Mediation** (**Unity Registry**); the project files record
`com.unity.services.levelplay`. Not **Ads IAP Mediation Adaptor** (a separate in-app-purchase package)
nor **Advertisement Legacy** (deprecated Unity Ads; `reference/migration-sdk-9.md` §E). The publisher
installs it, accepting the **Mobile Dependency Resolver** import if offered: `SKILL.md` §4 needs one.

> **The gate: no LevelPlay code until `com.unity.services.levelplay` appears in
> `Packages/packages-lock.json` with a concrete version.** Both files are plain JSON: read them.
>
> - Absent from `manifest.json` → the install never happened. Say so and ask for it.
> - In `manifest.json`, absent from the lock file → not resolved yet (importing, or resolution
>   failed). With no Editor run since the id was added, the lag is expected; re-read after the Editor
>   next opens the project.
>
> Say which you found, and stop. **Never write the entry into `packages-lock.json` by hand**: it is
> Unity's resolution output, and a typed entry is a manufactured pass.

Report the resolved version: the Package Manager window, an earlier turn or a recollection is not
evidence, and `SKILL.md` §6 and §10 branch on it. **Re-read the file at `SKILL.md` §7** even if this gate passed this session; it is
the check most often skipped. **Ads Mediation > Network Manager** adds adapters, checks for updates,
shows the installed SDK version.
