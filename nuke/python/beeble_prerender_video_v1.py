# Purpose:
# - Video pre-render helper for Nuke Group-node runner scripts (Python 2.7).
# - Renders a connected pipe to a video file by:
#   - Rendering a temp JPEG sequence from Nuke (fast Write, 0.95 quality).
#   - Encoding that sequence to high-quality H.264 mp4 using ffmpeg (4:4:4, no chroma subsampling).
#
# Notes:
# - Must be Python 2.7 compatible (runs inside Nuke).
# - Used by `nuke_prerender_v1.py` as the implementation behind `prepare_video_input_path`.

from __future__ import print_function

import os
import subprocess

from beeble_prerender_core_v1 import ensure_dir, render_sequence_from_node

# High-quality H.264 for SwitchX API upload (lower CRF = higher quality, larger files).
_H264_CRF = "11"
_H264_PRESET = "slow"


def _ffmpeg_exists():
    try:
        p = subprocess.Popen(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        p.communicate()
        return p.returncode == 0
    except Exception:
        return False


def _run_ffmpeg_encode(pattern, first, fps, out_path):
    args = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(float(fps)),
        "-start_number",
        str(int(first)),
        "-i",
        pattern,
        "-c:v",
        "libx264",
        "-preset",
        _H264_PRESET,
        "-crf",
        _H264_CRF,
        "-profile:v",
        "high444",
        "-pix_fmt",
        "yuv444p",
        "-movflags",
        "+faststart",
        out_path,
    ]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = []
    while True:
        line = p.stdout.readline()
        if not line:
            break
        try:
            if isinstance(line, bytes):
                line = line.decode("utf-8", "replace")
        except Exception:
            pass
        try:
            out.append((line or "").rstrip("\r\n"))
        except Exception:
            pass
    p.wait()
    return p.returncode, "\n".join(out[-40:])


def render_video_from_node(nuke_module, src_node, out_path, first, last):
    """
    Render to mp4 by JPEG sequence + ffmpeg encode (requires ffmpeg on PATH).
    """
    out_path = os.path.abspath(out_path)
    ensure_dir(os.path.dirname(out_path))

    if not _ffmpeg_exists():
        raise Exception("ffmpeg was not found on PATH (required for video prerender).")

    pad = 4
    base_name = os.path.splitext(os.path.basename(out_path))[0]
    seq_pattern = os.path.join(
        os.path.dirname(out_path),
        "%s_%%0%dd.jpg" % (base_name, int(pad)),
    )
    render_sequence_from_node(nuke_module, src_node, seq_pattern, first, last)

    try:
        fps = float(nuke_module.root().fps())
    except Exception:
        fps = 25.0

    code, tail = _run_ffmpeg_encode(seq_pattern, first, fps, out_path)
    if code != 0 or (not os.path.isfile(out_path)):
        raise Exception("ffmpeg encode failed (exit %d).\n%s" % (int(code), tail))

    return out_path
