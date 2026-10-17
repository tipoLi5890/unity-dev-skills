#!/usr/bin/env python3
"""make_tree.py — build the courier-run project that manifest_courier.md describes.

  python3 make_tree.py DEST

writes DEST/tree/: the files below as empty placeholders, and manifest_courier.md copied to
DEST/tree/ArtDirection/manifest.md. Adopt reads names and hashes, never pixels, so nothing here
is a real image. Two differences from the manifest are on purpose:
  ArtDirection/sheets/runner_jump.png   named by a row, left out: adopt records it missing
  ArtDirection/sheets/runner_wave.png   on disk, named by no row: adopt reports an orphan

registry_adopt.py's selftest runs this in a temporary directory. Standard library only.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

TREE = (
    "ArtDirection/anchors/master.png",
    "ArtDirection/anchors/runner.png",
    "ArtDirection/anchors/runner_v1.png",
    "ArtDirection/prompts/master.txt",
    "ArtDirection/prompts/runner_sheets.txt",
    "ArtDirection/sheets/runner_run.png",
    "ArtDirection/sheets/runner_idle.png",
    "ArtDirection/sheets/runner_run_v1.png",
    "ArtDirection/sheets/runner_wave.png",
    "ArtDirection/frames/runner_run/run_1.png",
    "ArtDirection/frames/runner_run/run_2.png",
    "ArtDirection/frames/runner_run/run_3.png",
    "ArtDirection/frames/runner_run/run_4.png",
    "ArtDirection/frames/runner_run/run_5.png",
    "ArtDirection/frames/runner_run/run_6.png",
    "ArtDirection/turnarounds/mallet_front.png",
    "ArtDirection/turnarounds/mallet_side.png",
    "ArtDirection/previews/runner_run.gif",
    "ArtDirection/raw/3d/Mallet/mallet_raw.glb",
    "ArtDirection/sources/runner_rig_v1.blend",
    "ArtDirection/sources/runner_rig_v1.fbx",
    "ArtDirection/sources/Runner.blend",
    "Assets/Models/HeroProp/Mallet/Mallet.glb",
    "Assets/Models/Character/Runner/Runner.fbx",
    "Assets/Models/Character/Runner/Runner@GateLatchSwing.fbx",
    "Assets/Models/Character/Runner/Runner@Run.fbx",
)


def build(dest):
    root = os.path.join(dest, "tree")
    for rel in TREE:
        full = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "wb").close()
    shutil.copyfile(os.path.join(HERE, "manifest_courier.md"),
                    os.path.join(root, "ArtDirection", "manifest.md"))
    return root


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: make_tree.py DEST")
    print(build(sys.argv[1]))
