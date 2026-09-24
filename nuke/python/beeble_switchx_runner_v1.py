# Purpose:
# - Runner script for the Nuke Group node `Beeble_SwitchX_v1` (executes inside Nuke).
# - Accepts source video, custom alpha mask video, and optional reference image inputs.
# - Validates Beeble API limits before upload; aborts if inputs are out of spec.
# - Calls external Python 3 helper `beeble_switchx_helper.py` and spawns a result Read node.
#
# Notes:
# - Must be Python 2.7 / 3.x compatible (runs inside Nuke).
# - Network/API calls run in the external helper (Python 3), not inside Nuke.

from __future__ import print_function

import os

import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import beeble_install_help
import beeble_runner_launcher

import beeble_prerender_v1 as prerender
import beeble_read_video_frames_v1 as video_frames
import beeble_spawn_read_position_v1 as spawn_pos
import beeble_switchx_validate_v1 as switchx_validate


def _norm_slashes(p):
    return (p or "").replace("\\", "/")


def _split_cmd(cmd):
    return prerender.split_cmd(cmd)


def _get_frame_range_from_knobs(group_node, nuke_module):
    try:
        mode = (group_node.knob("frame_range").value() or "root").strip().lower()
    except Exception:
        mode = "root"

    if mode == "current":
        f = int(nuke_module.frame())
        return f, f

    if mode == "custom":
        try:
            start = int(float((group_node.knob("custom_start").value() or "1").strip()))
            end = int(float((group_node.knob("custom_end").value() or "1").strip()))
            if end < start:
                start, end = end, start
            return start, end
        except Exception:
            pass

    try:
        start = int(nuke_module.root().firstFrame())
        end = int(nuke_module.root().lastFrame())
    except Exception:
        start = 1
        end = 1
    if end < start:
        start, end = end, start
    return start, end


def _will_use_read_video_fast_path(nuke_module, src_node, frame):
    if not prerender.is_read_node(src_node):
        return False
    try:
        pat = (src_node.knob("file").value() or "").strip()
    except Exception:
        pat = ""
    if prerender.looks_like_sequence_pattern(pat):
        return False
    if not prerender._is_valid_video_extension(pat):
        return False
    p = prerender.resolve_read_file_at_frame(nuke_module, src_node, frame)
    return bool(p and os.path.isfile(p))


def _validate_planned_prerenders(nuke_module, nodes_and_labels, frame, first, last):
    planned = int(last) - int(first) + 1
    if planned < 1:
        switchx_validate.abort_with_message(
            nuke_module,
            "Invalid frame range: end must be >= start.",
        )

    for src_node, label in nodes_and_labels:
        if _will_use_read_video_fast_path(nuke_module, src_node, frame):
            continue
        err = switchx_validate.validate_planned_frame_count(planned, label)
        if err:
            switchx_validate.abort_with_message(
                nuke_module,
                "%s\n\nPlanned prerender range: %d-%d (%d frames)." % (err, first, last, planned),
            )


def main():
    import nuke

    g = beeble_runner_launcher.get_execute_group_node(nuke, caller_globals=globals())
    frame = int(nuke.frame())

    src_video_node = g.input(0)
    if not src_video_node:
        switchx_validate.abort_with_message(nuke, "Input 0 (source_video) is not connected.")

    alpha_node = g.input(1)
    if not alpha_node:
        switchx_validate.abort_with_message(nuke, "Input 1 (alpha_mask) is not connected.")

    ref_node = g.input(2)

    default_first, default_last = _get_frame_range_from_knobs(g, nuke)

    _validate_planned_prerenders(
        nuke,
        [
            (src_video_node, "Source video"),
            (alpha_node, "Alpha mask"),
        ],
        frame,
        default_first,
        default_last,
    )

    prompt = (g.knob("prompt").value() or "").strip()
    has_ref_input = ref_node is not None
    if not prompt and not has_ref_input:
        switchx_validate.abort_with_message(
            nuke,
            "Prompt is empty and no reference_image input is connected.\n"
            "Beeble SwitchX requires at least one of prompt or reference image.",
        )

    try:
        max_resolution = int(g.knob("max_resolution").value())
    except Exception:
        max_resolution = 1080
    if max_resolution not in (720, 1080):
        switchx_validate.abort_with_message(
            nuke,
            "max_resolution must be 720 or 1080.",
        )

    seed = (g.knob("seed").value() or "").strip()

    temp_dir, out_dir, ts = prerender.make_run_dirs(
        nuke_module=nuke,
        prefix="beeble_switchx",
    )

    try:
        video_path = prerender.prepare_video_input_path(
            nuke_module=nuke,
            src_node=src_video_node,
            frame=frame,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="source_video",
        )
    except Exception as e:
        switchx_validate.abort_with_message(nuke, "Failed to prepare source video:\n%s" % str(e))

    try:
        alpha_path = prerender.prepare_video_input_path(
            nuke_module=nuke,
            src_node=alpha_node,
            frame=frame,
            default_first=default_first,
            default_last=default_last,
            run_dir=temp_dir,
            base_name="alpha_mask",
        )
    except Exception as e:
        switchx_validate.abort_with_message(nuke, "Failed to prepare alpha mask:\n%s" % str(e))

    ref_path = None
    if has_ref_input:
        try:
            ref_path = prerender.prepare_still_input_path(
                nuke_module=nuke,
                src_node=ref_node,
                frame=frame,
                run_dir=temp_dir,
                base_name="reference_image",
            )
        except Exception as e:
            switchx_validate.abort_with_message(nuke, "Failed to prepare reference image:\n%s" % str(e))

    err = switchx_validate.validate_switchx_pair(video_path, alpha_path)
    if err:
        switchx_validate.abort_with_message(nuke, err)

    if ref_path:
        err = switchx_validate.validate_reference_image(ref_path)
        if err:
            switchx_validate.abort_with_message(nuke, err)

    out_path = os.path.join(out_dir, "beeble_switchx_%s.mp4" % ts)
    out_path_nk = _norm_slashes(out_path)

    python3_cmd = (g.knob("python3_cmd").value() or "").strip() or "py -3"
    helper_path = beeble_install_help.require_helper_path(
        nuke,
        (g.knob("helper_path").value() or "").strip(),
    )

    py_parts = _split_cmd(python3_cmd) or ["py", "-3"]
    args = list(py_parts) + [
        helper_path,
        "--video",
        video_path,
        "--alpha",
        alpha_path,
        "--out",
        out_path,
        "--max-resolution",
        str(max_resolution),
        "--verbose",
    ]

    if prompt:
        args += ["--prompt", prompt]
    if ref_path:
        args += ["--reference-image", ref_path]
    if seed:
        args += ["--seed", seed]

    env = prerender.helper_subprocess_env()
    api_knob = (g.knob("BEEBLE_API_KEY").value() or "").strip()
    if api_knob and ("insert your secret" not in api_knob.lower()):
        env.update({"BEEBLE_API_KEY": api_knob})

    try:
        returncode, _stdout_lines = prerender.run_helper_subprocess(
            args,
            env=env,
            title="Beeble SwitchX",
        )
    except prerender.BeebleProgressCancelled:
        switchx_validate.abort_with_message(nuke, "Beeble SwitchX request cancelled.")

    if returncode != 0:
        switchx_validate.abort_with_message(
            nuke,
            "Beeble SwitchX helper failed (exit %d). Check the Script Editor output for details." % returncode,
        )

    xpos = int(g.xpos())
    ypos = int(g.ypos())

    nuke.root().begin()
    try:
        fx, fy = spawn_pos.resolve_spawn_xy(nuke, xpos, ypos + 140)
        r = nuke.nodes.Read(file=out_path_nk)
        try:
            r.setName("%s_result_%s" % (g.name(), ts), unique=True)
        except Exception:
            pass
        try:
            r.knob("label").setValue("Beeble SwitchX\n%s" % out_path_nk)
        except Exception:
            pass
        r.setXpos(fx)
        r.setYpos(fy)
        try:
            video_frames.set_read_frame_range_from_video_file(r, out_path)
        except Exception:
            pass
    finally:
        nuke.endGroup()

    if beeble_runner_launcher.should_show_success_popup(g):
        nuke.message("Beeble SwitchX output created:\n%s" % out_path_nk)


if __name__ == "__main__":
    main()
