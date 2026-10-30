#!/usr/bin/env python3
"""Run every shipped script's selftest; the exit code is the verdict.

Each row of SELFTESTS below is one script: how its selftest is called and what it needs.
A row whose dependency is missing prints `SKIP (missing dep: ...)` and does not count as a
failure; a row that runs passes on exit 0 and fails on anything else (or a timeout). A
script under skills/ that defines a selftest but has no row fails the run too, so a new
selftest cannot be left out by accident.

Dependencies: stdlib, numpy, pillow, cv2 and torch must import in this interpreter;
ffmpeg must be on PATH; bpy rows run inside Blender, and only when --blender PATH is given
(`blender -b --factory-startup -P SCRIPT -- ARGS`).

  python3 tools/run-selftests.py                          # every row this machine can run
  python3 tools/run-selftests.py --only codex-visual      # rows whose path contains this
  python3 tools/run-selftests.py --blender /path/to/blender

Exit codes: 0 every row that ran passed; 1 a row failed, a selftest has no row, or a
usage error. Standard library only.
"""
import argparse
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

TIMEOUT = 900

# path (under skills/), argv, dependencies. Keep it sorted by path.
SELFTESTS = [
    ('art-asset-registry/scripts/registry.py', ['selftest'], ['stdlib']),
    ('art-asset-registry/scripts/registry_adopt.py', ['selftest'], ['stdlib']),
    ('art-asset-registry/scripts/registry_ingest.py', ['selftest'], ['stdlib']),
    ('blender-retarget/scripts/bakeoff_report.py', ['selftest'], ['stdlib']),
    ('blender-retarget/scripts/clip_metrics.py', ['selftest'], ['numpy']),
    ('blender-retarget/scripts/motion_metrics.py', ['--selftest'], ['numpy']),
    ('character-autorig/scripts/arp_markers.py', ['--selftest'], ['numpy']),
    ('character-autorig/scripts/arp_markers.py', ['--selftest'], ['bpy', 'numpy']),
    ('character-autorig/scripts/autorig.py', ['--selftest'], ['stdlib']),
    ('character-autorig/scripts/deform_gate.py', ['--selftest'], ['bpy', 'numpy']),
    ('character-autorig/scripts/mesh_check.py', ['--selftest'], ['numpy']),
    ('codex-visual/scripts/audit_3d_source.py', ['--selftest'], ['numpy', 'pillow']),
    ('codex-visual/scripts/audit_frames.py', ['--selftest'], ['numpy', 'pillow']),
    ('codex-visual/scripts/breathe.py', ['--selftest'], ['numpy', 'pillow']),
    ('codex-visual/scripts/contact_sheet.py', ['--selftest'], ['pillow']),
    ('codex-visual/scripts/key_unmix.py', ['--selftest'], ['numpy', 'pillow']),
    ('codex-visual/scripts/overview_sheet.py', ['--selftest'], ['pillow']),
    ('codex-visual/scripts/pick_key.py', ['--selftest'], ['numpy', 'pillow']),
    ('codex-visual/scripts/pixel_ops.py', ['--selftest'], ['numpy', 'pillow']),
    ('codex-visual/scripts/sheet_to_frames.py', ['--selftest'], ['numpy', 'pillow']),
    ('comfyui-asset-generation/scripts/camera_gate.py', ['selftest'], ['numpy', 'pillow']),
    ('comfyui-asset-generation/scripts/graph_diff.py', ['--selftest'], ['stdlib']),
    ('comfyui-asset-generation/scripts/layout_map.py', ['selftest'], ['numpy', 'pillow']),
    ('humanoid-motion/scripts/bvh_io.py', ['--selftest'], ['numpy']),
    ('humanoid-motion/scripts/contact_bake.py', ['--selftest'], ['numpy']),
    ('humanoid-motion/scripts/contact_bake.py', ['--selftest-blender'], ['bpy', 'numpy']),
    ('humanoid-motion/scripts/twocam/blender/apply_motion.py', ['--selftest'], ['bpy', 'numpy']),
    ('humanoid-motion/scripts/twocam/blender/prepare_rig.py', ['--selftest'], ['bpy', 'numpy']),
    ('humanoid-motion/scripts/twocam/blender/render_baked.py', ['--selftest'], ['bpy', 'numpy']),
    ('humanoid-motion/scripts/twocam/blender/render_dataset.py', ['--selftest'], ['bpy', 'numpy']),
    ('humanoid-motion/scripts/twocam/blender/render_ref.py', ['--selftest'], ['bpy', 'numpy']),
    ('humanoid-motion/scripts/twocam/detect.py', ['--selftest'], ['numpy', 'cv2', 'torch']),
    ('humanoid-motion/scripts/twocam/exam.py', ['--selftest'], ['numpy']),
    ('humanoid-motion/scripts/twocam/film.py', ['--selftest'], ['numpy', 'cv2']),
    ('humanoid-motion/scripts/twocam/layout.py', ['--selftest'], ['numpy']),
    ('humanoid-motion/scripts/twocam/make_prompt.py', ['--selftest'], ['numpy']),
    ('humanoid-motion/scripts/twocam/skeleton.py', ['--selftest'], ['numpy']),
    ('humanoid-motion/scripts/twocam/solve.py', ['--selftest'], ['numpy', 'torch']),
    ('humanoid-motion/scripts/twocam/train.py', ['--selftest'], ['numpy', 'cv2', 'torch']),
    ('humanoid-motion/scripts/twocam/twocam.py', ['--selftest'], ['numpy']),
    ('sprite-from-video/scripts/video_canvas.py', ['--selftest'], ['numpy', 'pillow']),
    ('sprite-from-video/scripts/video_frames.py', ['--selftest'], ['numpy', 'pillow', 'ffmpeg']),
    ('sprite-from-video/scripts/video_loop.py', ['--selftest'], ['numpy', 'pillow']),
    ('unity-2d-level/scripts/level_validate.py', ['selftest'], ['stdlib']),
    ('unity-audio/scripts/spectrum_check.py', ['selftest'], ['numpy']),
    ('unity-debug/scripts/merge_results.py', ['selftest'], ['stdlib']),
    ('unity-game-brief/scripts/examples/courier_run_preview.py', ['selftest'], ['numpy', 'pillow', 'ffmpeg']),
    ('unity-game-brief/scripts/preview_compose.py', ['selftest'], ['numpy', 'pillow', 'ffmpeg']),
    ('unity-game-brief/scripts/preview_reel.py', ['selftest'], ['numpy', 'pillow', 'ffmpeg']),
    ('unity-game-feel/scripts/screen_smoothness.py', ['selftest'], ['stdlib']),
    ('unity-gameplay/scripts/jump_report.py', ['selftest'], ['stdlib']),
    ('unity-new-project/scripts/pure_tests.py', ['selftest'], ['stdlib']),
    ('unity-play-harness/scripts/journey_report.py', ['selftest'], ['stdlib']),
    ('unity-profiling/scripts/compare_windows.py', ['selftest'], ['stdlib']),
    ('unity-rigged-character/scripts/contract_map.py', ['selftest'], ['numpy']),
]

MODULES = {'numpy': 'numpy', 'pillow': 'PIL', 'cv2': 'cv2', 'torch': 'torch'}
HAS_SELFTEST = re.compile(r'^def (?:selftest|cmd_selftest|selftest_host)\(', re.M)


def run(cmd: list, timeout: int) -> tuple:
    """(exit code, stdout + stderr) of cmd; the code is None on a timeout. Reuses check-registry's run()."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    try:
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f'timed out after {timeout}s'
    return r.returncode, r.stdout + r.stderr


def tail(out: str, n: int = 15) -> str:
    lines = out.rstrip().splitlines()[-n:]
    return ''.join(f'\n    {line}' for line in lines)


def missing_deps(deps: list, blender: str | None) -> list:
    missing = []
    for dep in deps:
        if dep == 'stdlib':
            continue
        if dep == 'ffmpeg':
            ok = shutil.which('ffmpeg') is not None
        elif dep == 'bpy':
            ok = bool(blender)
        else:
            ok = importlib.util.find_spec(MODULES[dep]) is not None
        if not ok:
            missing.append('bpy (no --blender)' if dep == 'bpy' else dep)
    return missing


def unlisted() -> list:
    """Scripts that define a selftest but have no row."""
    listed = {path for path, _, _ in SELFTESTS}
    out = []
    for f in sorted((ROOT / 'skills').rglob('*.py')):
        if '__pycache__' in f.parts:
            continue
        rel = f.relative_to(ROOT / 'skills').as_posix()
        if rel not in listed and HAS_SELFTEST.search(f.read_text(encoding='utf-8', errors='replace')):
            out.append(rel)
    return out


class UsageParser(argparse.ArgumentParser):
    def error(self, message):   # a usage error is exit 1, like a failed row
        self.print_usage(sys.stderr)
        self.exit(1, f'{self.prog}: error: {message}\n')


def main() -> int:
    ap = UsageParser(description=__doc__.split('\n')[0])
    ap.add_argument('--blender', metavar='PATH', help='a Blender executable: also run the bpy rows')
    ap.add_argument('--only', metavar='TEXT', help='only the rows whose path contains TEXT')
    ap.add_argument('--timeout', type=int, default=TIMEOUT, help=f'seconds per script (default {TIMEOUT})')
    a = ap.parse_args()
    if a.blender and not (os.path.isfile(a.blender) or shutil.which(a.blender)):
        print(f'--blender {a.blender}: no such executable')
        return 1

    considered = ran = passed = skipped = 0
    failures = []
    for path, argv, deps in SELFTESTS:
        if a.only and a.only not in path:
            continue
        considered += 1
        label = f'{path} {" ".join(argv)}' + (' (Blender)' if 'bpy' in deps else '')
        script = ROOT / 'skills' / path
        if not script.is_file():
            failures.append(label)
            print(f'FAIL {label}: the script is missing')
            continue
        missing = missing_deps(deps, a.blender)
        if missing:
            skipped += 1
            print(f'SKIP (missing dep: {", ".join(missing)}) {label}')
            continue
        if 'bpy' in deps:
            cmd = [a.blender, '-b', '--factory-startup', '-P', str(script), '--', *argv]
        else:
            cmd = [sys.executable, str(script), *argv]
        ran += 1
        start = time.monotonic()
        code, out = run(cmd, a.timeout)
        took = time.monotonic() - start
        if code == 0:
            passed += 1
            print(f'PASS {label} ({took:.1f}s)')
        else:
            failures.append(label)
            print(f'FAIL {label}: exit {code} ({took:.1f}s){tail(out)}')

    missing_rows = [] if a.only else unlisted()
    for rel in missing_rows:
        print(f'FAIL skills/{rel}: defines a selftest but has no row in tools/run-selftests.py')
    print(f'{considered} selftests: {ran} ran, {passed} passed, {len(failures)} failed, {skipped} skipped'
          + (f'; {len(missing_rows)} without a row' if missing_rows else ''))
    return 1 if failures or missing_rows else 0


if __name__ == '__main__':
    sys.exit(main())
