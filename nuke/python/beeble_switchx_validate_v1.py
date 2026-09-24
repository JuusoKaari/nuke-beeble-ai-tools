# Purpose:
# - Validate Beeble SwitchX video inputs before API calls (runs inside Nuke).
# - Enforces API limits: max 240 frames, max 2,770,000 pixels (width x height).
# - Aborts the run when validation fails (caller shows nuke.message and raises).

from __future__ import print_function

import os

import beeble_read_video_frames_v1 as video_frames

MAX_FRAMES = 240
MAX_PIXELS = 2770000


def _pixel_limit_message(label, width, height, pixels):
    return (
        "%s resolution %dx%d (%d pixels) exceeds the Beeble SwitchX limit of %d pixels."
        % (label, width, height, pixels, MAX_PIXELS)
    )


def _frame_limit_message(label, frame_count):
    return (
        "%s has %d frames, which exceeds the Beeble SwitchX limit of %d frames."
        % (label, frame_count, MAX_FRAMES)
    )


def _require_ffprobe():
    if not video_frames._ffprobe_on_path():
        return (
            "ffprobe is not available on PATH.\n\n"
            "Beeble SwitchX requires ffprobe to validate input video length and resolution before upload.\n"
            "Install ffmpeg (includes ffprobe) and ensure it is on PATH."
        )
    return None


def validate_planned_frame_count(frame_count, label):
    """
    Validate frame count from a planned prerender range (before rendering).
    Returns an error message string, or None if OK.
    """
    try:
        n = int(frame_count)
    except Exception:
        return "%s frame count is invalid." % label
    if n < 1:
        return "%s frame count must be at least 1." % label
    if n > MAX_FRAMES:
        return _frame_limit_message(label, n)
    return None


def _validate_video_pixels(path, label):
    w, h = video_frames.get_video_width_height(path)
    if w is None or h is None:
        return "%s: could not read video resolution with ffprobe.\nFile: %s" % (label, path)
    pixels = int(w) * int(h)
    if pixels > MAX_PIXELS:
        return _pixel_limit_message(label, int(w), int(h), pixels)
    return None


def _validate_video_frames(path, label):
    n = video_frames.get_video_frame_count(path)
    if n is None:
        return "%s: could not read frame count with ffprobe.\nFile: %s" % (label, path)
    if int(n) > MAX_FRAMES:
        return _frame_limit_message(label, int(n))
    return None


def validate_video_file(path, label):
    """
    Validate a local video file for Beeble SwitchX limits.
    Returns an error message string, or None if OK.
    """
    path = os.path.abspath(path or "")
    if not os.path.isfile(path):
        return "%s file not found:\n%s" % (label, path)

    err = _require_ffprobe()
    if err:
        return err

    err = _validate_video_frames(path, label)
    if err:
        return err

    err = _validate_video_pixels(path, label)
    if err:
        return err

    return None


def _validate_image_pixels(path, label):
    w, h = video_frames.get_video_width_height(path)
    if w is None or h is None:
        return "%s: could not read image resolution with ffprobe.\nFile: %s" % (label, path)
    pixels = int(w) * int(h)
    if pixels > MAX_PIXELS:
        return _pixel_limit_message(label, int(w), int(h), pixels)
    return None


def validate_reference_image(path):
    """Validate optional reference still image. Returns error message or None."""
    path = os.path.abspath(path or "")
    if not path:
        return None
    if not os.path.isfile(path):
        return "Reference image file not found:\n%s" % path

    err = _require_ffprobe()
    if err:
        return err

    return _validate_image_pixels(path, "Reference image")


def validate_switchx_pair(source_path, alpha_path):
    """
    Validate source video and custom alpha video for Beeble SwitchX.
    Returns an error message string, or None if OK.
    """
    err = validate_video_file(source_path, "Source video")
    if err:
        return err

    err = validate_video_file(alpha_path, "Alpha mask")
    if err:
        return err

    source_frames = video_frames.get_video_frame_count(source_path)
    alpha_frames = video_frames.get_video_frame_count(alpha_path)
    if source_frames is None or alpha_frames is None:
        return (
            "Could not compare source and alpha frame counts with ffprobe.\n"
            "Source: %s\nAlpha: %s" % (source_path, alpha_path)
        )
    if int(source_frames) != int(alpha_frames):
        return (
            "Source video and alpha mask frame counts must match.\n"
            "Source: %d frames\nAlpha: %d frames" % (int(source_frames), int(alpha_frames))
        )

    sw, sh = video_frames.get_video_width_height(source_path)
    aw, ah = video_frames.get_video_width_height(alpha_path)
    if None in (sw, sh, aw, ah):
        return "Could not compare source and alpha resolution with ffprobe."
    if int(sw) != int(aw) or int(sh) != int(ah):
        return (
            "Source video and alpha mask resolution must match.\n"
            "Source: %dx%d\nAlpha: %dx%d" % (int(sw), int(sh), int(aw), int(ah))
        )

    return None


def abort_with_message(nuke_module, message):
    nuke_module.message(message)
    raise Exception("Beeble SwitchX input validation failed")
