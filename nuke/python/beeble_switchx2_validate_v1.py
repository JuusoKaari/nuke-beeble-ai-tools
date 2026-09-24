# Purpose:
# - Validate Beeble SwitchX 2.0 video inputs before Product API calls (runs inside Nuke).
# - Reuses the same local limits as legacy SwitchX until a live model input_schema
#   can confirm different frame/resolution caps for switchx-2.0.
# - Aborts the run when validation fails (caller shows nuke.message and raises).

from __future__ import print_function

import beeble_switchx_validate_v1 as _legacy


# Same local guards as legacy SwitchX until live switchx-2.0 schema is available.
MAX_FRAMES = _legacy.MAX_FRAMES
MAX_PIXELS = _legacy.MAX_PIXELS

validate_planned_frame_count = _legacy.validate_planned_frame_count
validate_video_file = _legacy.validate_video_file
validate_reference_image = _legacy.validate_reference_image
validate_switchx_pair = _legacy.validate_switchx_pair


def abort_with_message(nuke_module, message):
    nuke_module.message(message)
    raise Exception("Beeble SwitchX 2.0 input validation failed")
