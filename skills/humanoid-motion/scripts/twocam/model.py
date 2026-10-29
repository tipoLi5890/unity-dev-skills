"""model.py — the joint reader: DINOv2 (ViT-B/14 with registers) plus a small upsampling head, one heatmap per joint.

Ported from patch-gg/anymove (https://github.com/patch-gg/anymove), mocap/model.py, commit
7a82a0a8fadffddd5c24fabf0697d9b6c814ce6e, Apache License 2.0. Changes from upstream: torch and transformers are
imported when a reader is built, not when the module is imported, so the CLIs answer --help and compile without
them; the backbone may be passed as a module (the selftests use a small stand-in instead of downloading DINOv2);
`heatmaps` (the Gaussian training targets) moved here from train.py so train and the selftests share it;
`device_and_autocast` picks the device and turns on bf16 autocast only on CUDA; the backbone is loaded with
PyTorch's scaled-dot-product attention when the installed transformers offers it (the eager attention otherwise).
The network, the square padding and the sub-pixel decode are upstream's.

Both views go through the same network one at a time. A view is padded to a square with the backdrop grey, centred,
and resized to 448 x 448 (32 x 32 patches); heatmaps come out at 128 x 128.
The backbone facebook/dinov2-with-registers-base (Apache-2.0) downloads on first use.
"""
from __future__ import annotations

import contextlib

import numpy as np

BACKBONE = "facebook/dinov2-with-registers-base"
SIZE, HM, PATCH = 448, 128, 14
MEAN_RGB, STD_RGB = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
_cls = None


def reader_class():
    """The JointReader nn.Module class (built once, on first use)."""
    global _cls
    if _cls is not None:
        return _cls
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class JointReader(nn.Module):
        def __init__(self, n_joints, backbone=BACKBONE):
            super().__init__()
            if isinstance(backbone, str):
                backbone = load_backbone(backbone)
            self.backbone = backbone
            self.n_reg = getattr(self.backbone.config, "num_register_tokens", 0)
            c = self.backbone.config.hidden_size
            self.register_buffer("mean", torch.tensor(MEAN_RGB).view(1, 3, 1, 1), persistent=False)
            self.register_buffer("std", torch.tensor(STD_RGB).view(1, 3, 1, 1), persistent=False)

            def block(i, o):
                return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.GroupNorm(16, o), nn.GELU())

            self.neck = block(c, 256)
            self.up1 = block(256, 128)
            self.up2 = block(128, 128)
            self.out = nn.Conv2d(128, n_joints, 1)

        def forward(self, x):
            b = x.shape[0]
            tokens = self.backbone(pixel_values=(x - self.mean.to(x)) / self.std.to(x)).last_hidden_state
            g = SIZE // PATCH
            f = tokens[:, 1 + self.n_reg:].transpose(1, 2).reshape(b, -1, g, g)
            f = self.neck(f)
            f = self.up1(F.interpolate(f, scale_factor=2, mode="bilinear", align_corners=False))
            f = self.up2(F.interpolate(f, size=(HM, HM), mode="bilinear", align_corners=False))
            return self.out(f)

    _cls = JointReader
    return _cls


def load_backbone(name: str):
    """A Hugging Face backbone with SDPA attention when this transformers version accepts it, else its default."""
    from transformers import AutoModel
    try:
        return AutoModel.from_pretrained(name, attn_implementation="sdpa")
    except (TypeError, ValueError, ImportError):
        return AutoModel.from_pretrained(name)


def stub_backbone(hidden=32, registers=4):
    """A tiny stand-in with DINOv2's interface (patch tokens behind a class token and registers), for selftests."""
    import types
    import torch
    import torch.nn as nn

    class Stub(nn.Module):
        def __init__(self):
            super().__init__()
            self.config = types.SimpleNamespace(hidden_size=hidden, num_register_tokens=registers)
            self.embed = nn.Conv2d(3, hidden, PATCH, stride=PATCH)
            self.extra = nn.Parameter(torch.zeros(1, 1 + registers, hidden))

        def forward(self, pixel_values):
            t = self.embed(pixel_values).flatten(2).transpose(1, 2)
            return types.SimpleNamespace(last_hidden_state=torch.cat([self.extra.expand(len(t), -1, -1), t], 1))

    return Stub()


def device_and_autocast(name: str | None):
    """(device, autocast context factory). bf16 autocast on CUDA only; MPS and CPU run in float32."""
    import torch
    if name in (None, "auto"):
        name = "cuda" if torch.cuda.is_available() else "cpu"
    if name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda but CUDA is not available")
    if name == "mps" and not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
        raise RuntimeError("--device mps but MPS is not available")
    if name == "cuda":
        return name, (lambda: torch.autocast("cuda", dtype=torch.bfloat16))
    return name, contextlib.nullcontext


def square(img, fill):
    """Pad an H x W x 3 view to a centred square; return it and the (offset_x, offset_y) of the view inside."""
    h, w = img.shape[:2]
    s = max(h, w)
    out = np.empty((s, s, 3), img.dtype)
    out[:] = fill
    ox, oy = (s - w) // 2, (s - h) // 2
    out[oy:oy + h, ox:ox + w] = img
    return out, ox, oy, s


def heatmaps(kp, sigma=2.0):
    """Gaussian targets at HM resolution for keypoints given in SIZE pixels."""
    import torch
    b, j, _ = kp.shape
    g = (kp * HM / SIZE).view(b, j, 1, 1, 2)
    ys, xs = torch.meshgrid(torch.arange(HM, device=kp.device), torch.arange(HM, device=kp.device), indexing="ij")
    d2 = (xs - g[..., 0]) ** 2 + (ys - g[..., 1]) ** 2
    return torch.exp(-d2 / (2 * sigma ** 2))


def decode(hm):
    """Heatmaps (B, J, 128, 128) to sub-pixel peaks in heatmap units and peak values."""
    import torch
    b, j, h, w = hm.shape
    flat = hm.reshape(b, j, -1)
    conf, idx = flat.max(-1)
    y, x = (idx // w).float(), (idx % w).float()
    # quadratic refinement from the neighbours of the peak
    xi, yi = x.long().clamp(1, w - 2), y.long().clamp(1, h - 2)
    gather = lambda dy, dx: hm.gather(-1, (xi + dx).view(b, j, 1, 1).expand(b, j, h, 1)).squeeze(-1) \
        .gather(-1, (yi + dy).view(b, j, 1)).squeeze(-1)
    c, l, r, u, d = gather(0, 0), gather(0, -1), gather(0, 1), gather(-1, 0), gather(1, 0)
    dx = 0.5 * (r - l) / (2 * c - l - r).clamp(min=1e-6)
    dy = 0.5 * (d - u) / (2 * c - u - d).clamp(min=1e-6)
    x = x + dx.clamp(-0.5, 0.5)
    y = y + dy.clamp(-0.5, 0.5)
    return torch.stack([x, y], -1), conf
