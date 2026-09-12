# Unity import and Animator wiring

Five importer decisions and one controller layout. Automate all of it — see
`reference/editor-templates.md` for the re-runnable Editor scripts.

## 8. Unity import — five things that need automation

1. **Every Mixamo clip is named `mixamo.com`.** All of them. Rename each clip from its file
   name on import, or the Animator cannot tell run from jump.
2. **One FBX = one animation**, and only one carries a mesh. Animation files must set the
   Rig tab to **Copy From Other Avatar**, pointing at the body's Avatar. Otherwise each
   builds its own and **none of them retarget** — symptom: the character **T-poses in
   place** while the Animator reports everything as fine.
3. **Import order is not guaranteed.** Unity may import an animation before the mesh, so
   the Avatar doesn't exist yet and linking fails silently. The Avatar link **must be a
   re-runnable menu command**, not only an `AssetPostprocessor`.
4. **Set `loopPose`, not just `loopTime`.** `loopPose` forces first and last frames to
   match. A run cycle is often **17 frames (0.57 s at 30 fps)** — a one-frame mismatch
   reads as a hitch twice a second, the "something's off but I can't say what" class of bug.
5. **Animator: `applyRootMotion = false`** — belt and braces with In Place, since either
   alone is easy to forget.

Plus the shared prop gotcha: **imported models land on layer 0.** If the camera's culling
mask excludes it, the character **shows in the Scene view and is invisible in the Game
view**. Set the model and all children to the prefab root's layer after parenting
(`unity-3d-models` covers this in full).

**All Editor automation must be re-runnable** — rebuild from a clean state rather than
reconciling with what's there. Re-exports happen constantly.

## 9. Animator structure

**Two run clips (slow + fast) earn a 1D Blend Tree.** Do not time-scale a single clip:
slow down a sprint and the arms still swing like a sprint; speed up a jog and it reads as
cartoon fast-forward. **Blending changes the gait itself.** Drive the blend parameter with
the current speed normalised between minimum and maximum run speed. With one clip only,
fall back to scaling playback rate.

**Upper-body AvatarMask on an override layer** for reactions: a hit plays on torso and arms
while the legs keep running, so the character doesn't stall on every graze. This is the
concrete payoff for **Humanoid over Generic** — the mask is expressed in abstract body
parts, so it needs no bone names and survives a re-rig.
