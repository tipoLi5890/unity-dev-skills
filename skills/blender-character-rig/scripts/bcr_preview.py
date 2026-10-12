"""bcr_preview.py — render stills and a frame range to a directory, and put the settings back.

Runs inside Blender; not a command-line script (the stub is in bcr_common.py).

One call must return before the host's tool timeout, so an animation is
rendered a chunk of frames at a time, at a fraction of the output resolution.
Twenty frames per call at 50% is the default to start from; halve it when a
call is slow. The files go where `out_dir` says, as `<prefix><frame:04d>.png`,
and the scene's render path, resolution percentage, file format, camera and
current frame are restored in a `finally`.

    result = bcr_preview.run({
        "out_dir": "/abs/path/preview", "prefix": "f_",
        "frames": [1, 20],            # inclusive; a later call takes [21, 40]
        "percentage": 50,
        "camera": "PreviewCamera",    # optional: render through this camera
    })
    result = bcr_preview.run({"out_dir": "/abs/path/preview", "still": 18, "prefix": "pose_"})

A file left from an earlier run in the same range is deleted first, so a
render that failed cannot pass as this run's picture.

Returns `files`, `frames`, `seconds` and `seconds_per_frame`. Gates: every
frame in the range is on disk, settings restored.
"""
from __future__ import annotations

import os
import time

import bpy

import bcr_common as C


@C.step
def run(params: dict, tracker: C.Tracker) -> dict:
    scene = C.scene_of(params)
    render = scene.render
    out_dir = params["out_dir"]
    prefix = params.get("prefix", "f_")
    os.makedirs(out_dir, exist_ok=True)
    if params.get("still") is not None:
        frames = [int(params["still"])]
    else:
        first, last = params["frames"]
        frames = list(range(int(first), int(last) + 1))
    paths = [os.path.join(out_dir, f"{prefix}{frame:04d}.png") for frame in frames]
    for path in paths:
        if os.path.exists(path):
            os.remove(path)

    saved = (render.filepath, render.resolution_percentage, render.image_settings.file_format,
             scene.camera, scene.frame_current)
    started = time.time()
    try:
        render.resolution_percentage = params.get("percentage", 50)
        render.image_settings.file_format = 'PNG'
        if params.get("camera"):
            scene.camera = bpy.data.objects[params["camera"]]
        for frame, path in zip(frames, paths):
            scene.frame_set(frame)
            render.filepath = path
            bpy.ops.render.render(write_still=True, scene=scene.name)
    finally:
        (render.filepath, render.resolution_percentage, render.image_settings.file_format,
         scene.camera) = saved[:4]
        scene.frame_set(saved[4])
    seconds = time.time() - started

    missing = [p for p in paths if not os.path.exists(p)]
    now = (render.filepath, render.resolution_percentage, render.image_settings.file_format,
           scene.camera, scene.frame_current)
    gates = [
        C.gate("frames_missing", missing, [], not missing),
        C.gate("settings_restored", now == saved, True, now == saved),
    ]
    return C.report(params, gates, files=paths, frames=frames, seconds=seconds,
                    seconds_per_frame=seconds / len(frames), size=[render.resolution_x, render.resolution_y],
                    percentage=params.get("percentage", 50))
