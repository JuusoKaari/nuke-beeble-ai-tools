# Purpose:
# - Dedicated alpha-mask prerender path for Beeble SwitchX runners.
# - Always normalizes the connected matte to grayscale RGB (alpha or luminance)
#   via temporary Nuke nodes, then encodes an API-compatible MP4.
# - No Read fast-path: Mask channel must be applied before upload.

from __future__ import print_function

import os

from beeble_prerender_video_v1 import render_video_from_node

_MASK_CHANNEL_ALPHA = "alpha"
_MASK_CHANNEL_LUMINANCE = "luminance"
_VALID_MASK_CHANNELS = (_MASK_CHANNEL_ALPHA, _MASK_CHANNEL_LUMINANCE)


def normalize_mask_channel(value):
    """
    Return a canonical mask channel name.
    Unknown / empty values fall back to alpha (safe default for old saved nodes).
    """
    text = (value or "").strip().lower()
    if text in _VALID_MASK_CHANNELS:
        return text
    return _MASK_CHANNEL_ALPHA


def read_mask_channel_knob(group_node):
    """
    Read the group's `mask_channel` knob.
    Missing knob (older saved nodes) -> alpha.
    """
    try:
        kn = group_node.knob("mask_channel")
    except Exception:
        kn = None
    if kn is None:
        return _MASK_CHANNEL_ALPHA
    try:
        return normalize_mask_channel(kn.value())
    except Exception:
        return _MASK_CHANNEL_ALPHA


def _delete_node(nuke_module, node):
    if node is None:
        return
    try:
        nuke_module.delete(node)
    except Exception:
        pass


def _make_alpha_to_rgb_shuffle(nuke_module, src_node):
    """
    Temporary Shuffle: copy input alpha into R, G, and B (grayscale RGB matte).
    Classic Shuffle (not Shuffle2) for older Nuke compatibility.
    """
    sh = nuke_module.nodes.Shuffle()
    try:
        sh["in"].setValue("rgba")
    except Exception:
        pass
    for knob_name in ("red", "green", "blue", "alpha"):
        try:
            sh[knob_name].setValue("alpha")
        except Exception:
            pass
    sh.setInput(0, src_node)
    return sh


def _make_luminance_to_rgb(nuke_module, src_node):
    """
    Temporary Saturation at 0: Nuke writes luminance into R, G, and B.

    Classic Shuffle has no luminance source. Enumeration setValue("luminance")
    returns False and leaves red/green/blue mapped, so do not use Shuffle here.
    Saturation has existed on old Nuke versions and already outputs grayscale RGB.
    """
    sat = nuke_module.nodes.Saturation()
    try:
        sat["saturation"].setValue(0)
    except Exception:
        try:
            sat.knob("saturation").setValue(0)
        except Exception:
            pass
    sat.setInput(0, src_node)
    return sat


def build_mask_normalize_node(nuke_module, src_node, mask_channel):
    """
    Create a temporary processing node that outputs grayscale RGB for the matte.
    Caller owns cleanup (delete the returned node).
    """
    mode = normalize_mask_channel(mask_channel)
    if mode == _MASK_CHANNEL_LUMINANCE:
        return _make_luminance_to_rgb(nuke_module, src_node)
    return _make_alpha_to_rgb_shuffle(nuke_module, src_node)


def prepare_mask_video_input_path(
    nuke_module,
    src_node,
    frame,
    default_first,
    default_last,
    run_dir,
    base_name,
    mask_channel=_MASK_CHANNEL_ALPHA,
):
    """
    Always normalize `src_node` per `mask_channel` and prerender to MP4 under `run_dir`.

    Unlike `prepare_video_input_path`, this never passes through an existing MP4/MOV Read:
    the selected Mask channel must be applied so Beeble receives a predictable grayscale matte.

    Temporary Nuke nodes are deleted even when rendering fails.
    `frame` is accepted for call-site symmetry with other prepare_* helpers (unused here).
    """
    del frame  # mask always uses the planned first..last range

    first = int(default_first)
    last = int(default_last)
    if last < first:
        first, last = last, first

    out_path = os.path.join(run_dir, "%s.mp4" % base_name)

    # Build the normalize node at root, same place render_video_from_node writes.
    # The launcher already resets to root; begin() covers a leaked group context.
    # render_video_from_node creates and deletes its own temporary Write.
    mask_node = None
    entered_root = False
    try:
        try:
            nuke_module.root().begin()
            entered_root = True
        except Exception:
            entered_root = False
        mask_node = build_mask_normalize_node(nuke_module, src_node, mask_channel)
        return render_video_from_node(nuke_module, mask_node, out_path, first, last)
    finally:
        _delete_node(nuke_module, mask_node)
        if entered_root:
            try:
                nuke_module.endGroup()
            except Exception:
                pass
