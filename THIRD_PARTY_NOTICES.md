# Third-party notices

This repository is released under the licence in [LICENSE](LICENSE). The files below contain code
ported from other projects and carry those projects' licences.

## Real-PixelArt

- **File:** `skills/codex-visual/scripts/pixel_ops.py` — the cut-line fit, the per-cell colour
  recovery, the Lab / CIEDE2000 colour distance and the palette selection. The functions ported are
  listed in that file's header.
- **Source:** <https://github.com/Bocchi-The-Glock/Real-PixelArt>, commit
  `17ce487597dbc6c04c630226a0f499108a0e20ac`
- **Licence:** MIT

```
MIT License

Copyright (c) 2026 Sixiang Wang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## sprite-gen

- **Files:** each file's header lists the functions it ports, by upstream file.
  - `tools/shared-blocks/chroma_unmix.py` — the canonical copy of the `chroma_unmix` shared block,
    pasted into `skills/codex-visual/scripts/key_unmix.py` and
    `skills/sprite-from-video/scripts/video_frames.py`. From `frames/extract.py`: the key channel
    split, the key tint score and field, the key distance field, `despill_color` and
    `unmix_key_blend`, the key-family and border-candidate signatures with the painted-key lean,
    the Chebyshev and bounded grows, `detect_background_key_rgb` (the painted key read from the
    border), `hard_key_mask`, and the classification, depth-ring un-mix and trapped-spill despill
    passes of `remove_chroma_background` (`--edge tint`).
  - `skills/codex-visual/scripts/pick_key.py` — from `gen/prepare.py`: the chroma candidates, the
    border ring, `detect_reference_background`, the background mask and its flood fill, the
    subject pixels with the speck test, `analyze_reference`, the scoring and eligibility rule of
    `choose_chroma_key`, and their constants.
  - `skills/codex-visual/scripts/sheet_to_frames.py` — from `frames/extract.py`: `fit_scale`
    (`--scale reach`) and the band rule of the `foot-centroid` mode (the bottom fifth of the
    content rows, at least two, the whole frame when that band is empty; `--align foot`); from `util/resample.py`: `resize_cell` behind `--resample split`.
  - `skills/codex-visual/scripts/sprite_ops.py` — from `util/resample.py`: `MIX_SUPPORT`,
    `support_bounds`, `mix_windows`, `window_extrema` and `resize_cell` (here `resize_split`).
  - `skills/codex-visual/scripts/audit_frames.py` — from `frames/extract.py`:
    `chroma_adjacent_count` and its thresholds (the residual gate), `alpha_nonzero_count` and the
    sparse-frame error of `inspect_frames`; from `spec/subject.py`: `SUBJECT_FLOOR_RATIOS`,
    `_ceil_ratio_sqrt` and `default_min_used_pixels` (the sparse floor).
  - `skills/codex-visual/scripts/breathe.py` — from `effects/breathe.py`: the wave, smoothstep,
    envelope, appendage protection, row strain, the pixel-mode warp (row accumulation, the
    monotone column map about a fixed axis column, the outline-end copy, the off-canvas refusal),
    the per-row strain refusal, the integer-folded phases and the defaults; from
    `effects/anatomy.py`: the axis column, centre runs, width profile, bottleneck prominences, the
    neck bottleneck search, torso metrics, the rigid and basis rows and the appendage test.
  - `skills/sprite-from-video/scripts/video_canvas.py` — from `video/canvas.py`: the canvas
    profiles and the per-state canvas table (with the wide overrides), the corner tolerance, the
    corner key, key resolution, key normalisation and the square / tall / wide placement of
    `pad_canvas`.
  - `skills/sprite-from-video/scripts/video_frames.py` — from `video/frames.py`: probe and
    extract, speck removal, the edge bands, edge-contact classification and its two refusal
    messages, the keyed / refused hand-over and their constants; plus the `chroma_unmix` block
    above.
  - `skills/sprite-from-video/scripts/video_loop.py` — from `video/loop.py`: the analysis size,
    seam, periodicity, one-shot and half-step constants, the per-state loop profiles and windows,
    the small-feature distance matrix, repeat context, `detect_cycle`, the periodicity floor,
    `detect_one_shot`, the body and foot centres, the body wrap offset and drift ramp, the cycle
    subsampling and the seam gate's re-read on moved cells; from `video/period.py`: the divisors,
    the near and exact returns, local minima, the pose measure, the verdict and the screen.
  - `skills/blender-retarget/scripts/motion_metrics.py` — its loop search (the period, periodicity,
    seam and gait-double constants and the cut search) follows `video_loop.py` above, with joint
    distance in place of pixel distance.
- **Source:** <https://github.com/aldegad/sprite-gen>, commit
  `dddcc1013f7b5587a5eabd8609a5b42dd8aa7c26`
- **Licence:** Apache License 2.0. Each of the files above states its changes from the upstream code
  in its header, as §4(b) asks.

```
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions.

   "License" shall mean the terms and conditions for use, reproduction,
   and distribution as defined by Sections 1 through 9 of this document.

   "Licensor" shall mean the copyright owner or entity authorized by
   the copyright owner that is granting the License.

   "Legal Entity" shall mean the union of the acting entity and all
   other entities that control, are controlled by, or are under common
   control with that entity. For the purposes of this definition,
   "control" means (i) the power, direct or indirect, to cause the
   direction or management of such entity, whether by contract or
   otherwise, or (ii) ownership of fifty percent (50%) or more of the
   outstanding shares, or (iii) beneficial ownership of such entity.

   "You" (or "Your") shall mean an individual or Legal Entity
   exercising permissions granted by this License.

   "Source" form shall mean the preferred form for making modifications,
   including but not limited to software source code, documentation
   source, and configuration files.

   "Object" form shall mean any form resulting from mechanical
   transformation or translation of a Source form, including but
   not limited to compiled object code, generated documentation,
   and conversions to other media types.

   "Work" shall mean the work of authorship, whether in Source or
   Object form, made available under the License, as indicated by a
   copyright notice that is included in or attached to the work
   (an example is provided in the Appendix below).

   "Derivative Works" shall mean any work, whether in Source or Object
   form, that is based on (or derived from) the Work and for which the
   editorial revisions, annotations, elaborations, or other modifications
   represent, as a whole, an original work of authorship. For the purposes
   of this License, Derivative Works shall not include works that remain
   separable from, or merely link (or bind by name) to the interfaces of,
   the Work and Derivative Works thereof.

   "Contribution" shall mean any work of authorship, including
   the original version of the Work and any modifications or additions
   to that Work or Derivative Works thereof, that is intentionally
   submitted to Licensor for inclusion in the Work by the copyright owner
   or by an individual or Legal Entity authorized to submit on behalf of
   the copyright owner. For the purposes of this definition, "submitted"
   means any form of electronic, verbal, or written communication sent
   to the Licensor or its representatives, including but not limited to
   communication on electronic mailing lists, source code control systems,
   and issue tracking systems that are managed by, or on behalf of, the
   Licensor for the purpose of discussing and improving the Work, but
   excluding communication that is conspicuously marked or otherwise
   designated in writing by the copyright owner as "Not a Contribution."

   "Contributor" shall mean Licensor and any individual or Legal Entity
   on behalf of whom a Contribution has been received by Licensor and
   subsequently incorporated within the Work.

2. Grant of Copyright License. Subject to the terms and conditions of
   this License, each Contributor hereby grants to You a perpetual,
   worldwide, non-exclusive, no-charge, royalty-free, irrevocable
   copyright license to reproduce, prepare Derivative Works of,
   publicly display, publicly perform, sublicense, and distribute the
   Work and such Derivative Works in Source or Object form.

3. Grant of Patent License. Subject to the terms and conditions of
   this License, each Contributor hereby grants to You a perpetual,
   worldwide, non-exclusive, no-charge, royalty-free, irrevocable
   (except as stated in this section) patent license to make, have made,
   use, offer to sell, sell, import, and otherwise transfer the Work,
   where such license applies only to those patent claims licensable
   by such Contributor that are necessarily infringed by their
   Contribution(s) alone or by combination of their Contribution(s)
   with the Work to which such Contribution(s) was submitted. If You
   institute patent litigation against any entity (including a
   cross-claim or counterclaim in a lawsuit) alleging that the Work
   or a Contribution incorporated within the Work constitutes direct
   or contributory patent infringement, then any patent licenses
   granted to You under this License for that Work shall terminate
   as of the date such litigation is filed.

4. Redistribution. You may reproduce and distribute copies of the
   Work or Derivative Works thereof in any medium, with or without
   modifications, and in Source or Object form, provided that You
   meet the following conditions:

   (a) You must give any other recipients of the Work or
       Derivative Works a copy of this License; and

   (b) You must cause any modified files to carry prominent notices
       stating that You changed the files; and

   (c) You must retain, in the Source form of any Derivative Works
       that You distribute, all copyright, patent, trademark, and
       attribution notices from the Source form of the Work,
       excluding those notices that do not pertain to any part of
       the Derivative Works; and

   (d) If the Work includes a "NOTICE" text file as part of its
       distribution, then any Derivative Works that You distribute must
       include a readable copy of the attribution notices contained
       within such NOTICE file, excluding those notices that do not
       pertain to any part of the Derivative Works, in at least one
       of the following places: within a NOTICE text file distributed
       as part of the Derivative Works; within the Source form or
       documentation, if provided along with the Derivative Works; or,
       within a display generated by the Derivative Works, if and
       wherever such third-party notices normally appear. The contents
       of the NOTICE file are for informational purposes only and
       do not modify the License. You may add Your own attribution
       notices within Derivative Works that You distribute, alongside
       or as an addendum to the NOTICE text from the Work, provided
       that such additional attribution notices cannot be construed
       as modifying the License.

   You may add Your own copyright statement to Your modifications and
   may provide additional or different license terms and conditions
   for use, reproduction, or distribution of Your modifications, or
   for any such Derivative Works as a whole, provided Your use,
   reproduction, and distribution of the Work otherwise complies with
   the conditions stated in this License.

5. Submission of Contributions. Unless You explicitly state otherwise,
   any Contribution intentionally submitted for inclusion in the Work
   by You to the Licensor shall be under the terms and conditions of
   this License, without any additional terms or conditions.
   Notwithstanding the above, nothing herein shall supersede or modify
   the terms of any separate license agreement you may have executed
   with Licensor regarding such Contributions.

6. Trademarks. This License does not grant permission to use the trade
   names, trademarks, service marks, or product names of the Licensor,
   except as required for reasonable and customary use in describing the
   origin of the Work and reproducing the content of the NOTICE file.

7. Disclaimer of Warranty. Unless required by applicable law or
   agreed to in writing, Licensor provides the Work (and each
   Contributor provides its Contributions) on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
   implied, including, without limitation, any warranties or conditions
   of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
   PARTICULAR PURPOSE. You are solely responsible for determining the
   appropriateness of using or redistributing the Work and assume any
   risks associated with Your exercise of permissions under this License.

8. Limitation of Liability. In no event and under no legal theory,
   whether in tort (including negligence), contract, or otherwise,
   unless required by applicable law (such as deliberate and grossly
   negligent acts) or agreed to in writing, shall any Contributor be
   liable to You for damages, including any direct, indirect, special,
   incidental, or consequential damages of any character arising as a
   result of this License or out of the use or inability to use the
   Work (including but not limited to damages for loss of goodwill,
   work stoppage, computer failure or malfunction, or any and all
   other commercial damages or losses), even if such Contributor
   has been advised of the possibility of such damages.

9. Accepting Warranty or Additional Liability. While redistributing
   the Work or Derivative Works thereof, You may choose to offer,
   and charge a fee for, acceptance of support, warranty, indemnity,
   or other liability obligations and/or rights consistent with this
   License. However, in accepting such obligations, You may act only
   on Your own behalf and on Your sole responsibility, not on behalf of
   any other Contributor, and only if You agree to indemnify,
   defend, and hold each Contributor harmless for any liability
   incurred by, or claims asserted against, such Contributor by reason
   of your accepting any such warranty or additional liability.

END OF TERMS AND CONDITIONS

APPENDIX: How to apply the Apache License to your work.

   To apply the Apache License to your work, attach the following
   boilerplate notice, with the fields enclosed by brackets "[]"
   replaced with your own identifying information. (Don\'t include
   the brackets!)  The text should be enclosed in the appropriate
   comment syntax for the file format. We also recommend that a
   file or class name and description of purpose be included on the
   same "printed page" as the copyright notice for easier
   identification within third-party archives.

Copyright [yyyy] [name of copyright owner]

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

### sprite-gen's NOTICE, reproduced as §4(d) requires

Of the parts this NOTICE credits to other projects, the projection segmentation, the YCbCr matting,
the run-length pitch estimator and the RIFE code are not ported into this repository. Nor is
the `alpha-centroid` alignment this NOTICE credits to perfectpixel-studio, or the helper sprite-gen
computes it with: `sheet_to_frames.py --align foot` takes only the band of sprite-gen's
`foot-centroid` mode and reads it with that script's own alpha-weighted centroid.

```
sprite-gen
Copyright 2026 Alex Kim

This project is inspired by the Apache-2.0 licensed hatch-pet component-row
workflow. sprite-gen targets generic game sprite atlases and does not include
Codex pet assets, pet packages, or hatch-pet visual assets.

The `align_x: "alpha-centroid"` frame alignment (sprite_gen/extract.py) is a
port of the alpha-weighted mass-centroid alignment from perfectpixel-studio
(https://github.com/gykim80/perfectpixel-studio, internal/sprite/extract.go),
Copyright Andrew Kim (gykim80), MIT License.

The `segmentation: "projection"` frame separation (sprite_gen/segment.py) is a
port of the projection-profile + DP optimal-cut segmentation from
perfectpixel-studio (https://github.com/gykim80/perfectpixel-studio,
internal/sprite/segment.go), Copyright Andrew Kim (gykim80), MIT License.

The opt-in `chroma.mode: "ycbcr"` background matting (sprite_gen/extract.py) is
a port of the chrominance-plane matting — CbCr border-mode key detection,
Hermite soft matte, key-direction despill, border flood fill and the pure-key
rematte self-diagnostic — from perfectpixel-studio
(https://github.com/gykim80/perfectpixel-studio, internal/sprite/chroma.go),
Copyright Andrew Kim (gykim80), MIT License.

The estimation-only `estimate_pixel_grid_runlen` pitch estimator
(sprite_gen/extract.py) is a port of the unfake same-color run-length mode
block-size estimation from perfectpixel-studio
(https://github.com/gykim80/perfectpixel-studio, internal/sprite/pixelize.go),
Copyright Andrew Kim (gykim80), MIT License.

RIFE's torch backend (sprite_gen/video/rife_torch.py) writes again the IFNet of
rife-v4.6 — its structure and parameter names, and its warp — from Practical-RIFE
(https://github.com/hzwer/Practical-RIFE, commit f6b5132, train_log/IFNet_HDv3.py
and model/warplayer.py), Copyright (c) 2021 hzwer, MIT License.

Its test-time augmentation — the pair turned eight ways and run both ways in time,
the flows averaged at every level — follows rife-ncnn-vulkan 20221029
(https://github.com/nihui/rife-ncnn-vulkan, src/rife.cpp RIFE::process_v4 and its
rife_*_tta shaders), Copyright (c) 2020 nihui, MIT License. It reads its weights
from that release's rife-v4.6 model, which sprite-gen does not ship.
```

## anymove

- **Files:** under `skills/humanoid-motion/scripts/twocam/`; each file's header names the upstream file
  it ports and what changed.
  - `layout.py` — from `mocap/layout.py` and the layout half of `blender/common.py`: the two-view frame,
    `compose`, `split`, `project`, `unproject_front`, `unproject_side`; from `tools/compose_ref.py`: the
    reference frame composition.
  - `model.py` — from `mocap/model.py`: `JointReader` (DINOv2 with registers and the upsampling head),
    `square`, `decode`; from `mocap/train.py`: `heatmaps`.
  - `train.py` — from `mocap/train.py`: `backdrop`, `photometric`, the `Views` sample (framing jitter,
    divider, square, warp), the held-out split, the optimiser, schedule, loss and validation.
  - `detect.py` — from `mocap/detect.py`: `read_frames`, `calibrate` (the ECC affine fit), `prep`, the
    batched read, `load`, `overlay`.
  - `solve.py` — from `mocap/solve.py`: `fix_swaps`, `height_features`, `align_views` (the time warp),
    `paw_agreement`, `sync_report`, `euler_xyz`, `axis_angle`, `Rig`, `project`, `triangulate`,
    `root_from_triangulation`, `euler_from_matrix`, `rot_between`, `ik_init`, `fit`, `to_quat` and the
    stage order of `main`.
  - `exam.py` — from `mocap/exam.py`: `make`, `qmul`, `video`, `score` and its groups.
  - `skeleton.py` — replaces `blender/common.py`'s `load_rig`, `mirror`, `write_rig_info`, `LEG_BONES` and
    `LEG_COLORS`, and the limb names of `mocap/solve.py` (`LEGS`, the paw prefixes), with the humanoid
    contract; the rig_info.json fields are upstream's.
  - `make_prompt.py` — from `tools/make_prompt.py`: the template and `prompt`, `check`.
  - `film.py` — replaces `mocap/generate.py` and `mocap/fal.py`, keeping the output folder layout.
  - `twocam.py` — from `tools/_env.sh`, `tools/dataset.sh`, `tools/train.sh`, `tools/film.sh` and
    `tools/capture.sh`, rewritten in Python.
  - `blender/bcommon.py` — from `blender/common.py`: `cameras`, `camera_json`, `studio`, `render_views`,
    `srgb_to_linear`, `paint_legs` (here `paint_limbs`).
  - `blender/prepare_rig.py` — from `blender/build_rig.py`: the rig_info and paint writing and the save.
  - `blender/render_ref.py`, `blender/render_dataset.py`, `blender/apply_motion.py` — from the files of the
    same names in `blender/` (`apply_motion.py` without the fur springs).
  Not ported: `mocap/fal.py`, `mocap/lora.py`, `mocap/generate.py`, `mocap/mirror.py`,
  `mocap/showcase.py`, `tools/build_lora_set.py`, the mesh, rig and fur tools, the assets and prompts.
- **Source:** <https://github.com/patch-gg/anymove>, commit
  `7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e`. The two-camera method is @CanItCode's; the H3 LoRA idea,
  not ported here, is @Graalitoo's (credited in `skills/humanoid-motion/reference/two-camera.md`).
- **Licence:** Apache License 2.0, the text reproduced in the sprite-gen section above. Each of the files
  above states its changes from the upstream code in its header, as §4(b) asks. anymove ships no NOTICE
  file. Its licence does not cover the Patch name and marks, which are not used here; MiniMax H3's weights
  and outputs carry their own community licence, and hosted H3 on fal goes through fal's terms.
