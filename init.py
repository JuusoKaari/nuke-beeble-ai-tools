# Purpose: Bootstrap nuke-beeble-ai-tools - locate repo root from NUKE_PATH and add nuke/python to sys.path.

from __future__ import print_function

import os
import sys

_MARKER_REL = os.path.join("nuke", "groups", "beeble_switchx_v1.nk")


def _discover_install_root():
    raw = os.environ.get("NUKE_PATH", "") or ""
    if not raw.strip():
        return ""
    sep = ";" if ";" in raw else ":"
    for entry in raw.split(sep):
        entry = (entry or "").strip().strip('"')
        if not entry:
            continue
        root = os.path.normpath(entry).replace("\\", "/")
        if os.path.isfile(os.path.join(root, _MARKER_REL)):
            return root
    return ""


_ROOT = _discover_install_root()
if not _ROOT:
    try:
        import nuke

        nuke.message(
            "nuke-beeble-ai-tools could not find its install root on NUKE_PATH.\n\n"
            "Add the nuke-beeble-ai-tools repo root to NUKE_PATH and restart Nuke.\n"
            "Full steps: docs/INSTALL.md"
        )
    except Exception:
        pass
    raise Exception("nuke-beeble-ai-tools: install root not found on NUKE_PATH")

_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

os.environ["NUKE_BEEBLE_AI_TOOLS_ROOT"] = _ROOT
