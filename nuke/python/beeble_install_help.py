# Purpose: Install path resolution and guidance for nuke-beeble-ai-tools (no fal.ai name collisions).

from __future__ import print_function

import os

from _beeble_install_root import discover_install_root
from _repo_urls import GITHUB_RELEASES_URL, GITHUB_REPO_URL

INSTALL_ROOT_PLACEHOLDER = "__INSTALL_ROOT__"

_INSTALL_HINT = (
    "\n\nDownload and install nuke-beeble-ai-tools:\n"
    "  Latest release zip: %s\n"
    "  Or clone: %s\n\n"
    "Extract (or clone) to a stable folder, add that folder to NUKE_PATH, "
    "then restart Nuke.\n"
    "Full steps: docs/INSTALL.md in the install folder."
) % (GITHUB_RELEASES_URL, GITHUB_REPO_URL)


def install_hint():
    return _INSTALL_HINT


def resolve_install_path(path):
    path = (path or "").strip()
    if not path:
        return path

    if os.path.isabs(path):
        return os.path.normpath(path).replace("\\", "/")

    root = discover_install_root()
    if not root:
        return os.path.normpath(path).replace("\\", "/")

    if INSTALL_ROOT_PLACEHOLDER in path:
        path = path.replace(INSTALL_ROOT_PLACEHOLDER, root.replace("\\", "/"))
    else:
        path = os.path.join(root, path)

    return os.path.normpath(path).replace("\\", "/")


def _require_tool_path(nuke_module, raw_path, label):
    path = resolve_install_path((raw_path or "").strip())
    if not path:
        nuke_module.message(
            "%s path is empty. Re-create the node from the beeble.ai menu.%s"
            % (label, _INSTALL_HINT)
        )
        raise Exception("%s_path not set" % label.lower())
    if not os.path.isfile(path):
        nuke_module.message(
            "Missing %s script:\n%s%s" % (label.lower(), path, _INSTALL_HINT)
        )
        raise Exception("%s not found" % label.lower())
    return path


def require_runner_path(nuke_module, raw_path):
    return _require_tool_path(nuke_module, raw_path, "Runner")


def require_helper_path(nuke_module, raw_path):
    return _require_tool_path(nuke_module, raw_path, "Helper")
