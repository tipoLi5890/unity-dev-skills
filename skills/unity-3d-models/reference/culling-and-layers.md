# "It shows in Scene and is invisible in Game"

## The layer / culling gotcha

**Scene view renders every layer; the Game view obeys the camera's culling
mask.** A glTFast model (and any `CreatePrimitive`) lands on **layer 0
(Default)**. If the game camera's culling mask excludes layer 0, the model **shows
in Scene but is invisible in Game.** Fix: set the model + all children to a
layer the camera renders (match the prefab root's layer). That's the `SetLayer`
call in step 5 of `reference/import-and-decimate.md`.
