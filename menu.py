# Purpose: Nuke menu entries for Beeble SwitchX (legacy) and SwitchX 2.0 group nodes.
# Registers under Nodes toolbar and top menubar. Install hints probe GitHub releases,
# then fall back to the repo page when no release exists.

from __future__ import print_function

import os

import nuke

try:
    from _beeble_repo_urls import GITHUB_REPO_URL, install_download_lines
except Exception:
    GITHUB_REPO_URL = "https://github.com/JuusoKaari/nuke-beeble-ai-tools"

    def install_download_lines():
        return "  Repo: %s" % GITHUB_REPO_URL


def _install_hint():
    return (
        "\n\nDownload and install nuke-beeble-ai-tools:\n"
        "%s\n\n"
        "Add the nuke-beeble-ai-tools folder to NUKE_PATH, then restart Nuke.\n"
        "Full steps: docs/INSTALL.md in the install folder."
    ) % install_download_lines()


def _resolve_paths():
    try:
        from _beeble_install_root import discover_install_root
    except Exception:
        discover_install_root = None

    root = ""
    if discover_install_root is not None:
        root = discover_install_root(__file__)
    if not root:
        raw = os.environ.get("NUKE_PATH", "") or ""
        sep = ";" if ";" in raw else ":"
        marker = os.path.join("nuke", "groups", "beeble_switchx_v1.nk")
        for entry in raw.split(sep):
            entry = (entry or "").strip().strip('"')
            if not entry:
                continue
            candidate = os.path.normpath(entry).replace("\\", "/")
            if os.path.isfile(os.path.join(candidate, marker)):
                root = candidate
                break

    group_dir = os.path.join(root, "nuke", "groups").replace("\\", "/")
    return root, group_dir


def _tool_abs_path(root, filename):
    return os.path.join(root, "nuke", "python", filename).replace("\\", "/")


def _create_beeble_node(group_file, helper_py, runner_py):
    root, group_dir = _resolve_paths()
    group_path = os.path.join(group_dir, group_file).replace("\\", "/")
    if not os.path.isfile(group_path):
        nuke.message(
            "Missing group file:\n%s\n\nResolved install root: %s\nNUKE_PATH: %s%s"
            % (group_path, root or "<unknown>", os.environ.get("NUKE_PATH", ""), _install_hint())
        )
        raise Exception("group not found: %s" % group_file)
    node = nuke.createNode(group_path, inpanel=False)
    helper_knob = node.knob("helper_path")
    runner_knob = node.knob("runner_path")
    if helper_knob is None or runner_knob is None:
        nuke.message(
            "Group node is missing helper_path or runner_path knobs:\n%s\n\n"
            "Re-create from Nodes -> beeble.ai or check the group .nk file."
            % group_file
        )
        raise Exception("beeble.ai group missing path knobs: %s" % group_file)
    helper_knob.setValue(_tool_abs_path(root, helper_py))
    runner_knob.setValue(_tool_abs_path(root, runner_py))
    return node


def _make_creator(group_file, helper_py, runner_py):
    def _creator():
        return _create_beeble_node(group_file, helper_py, runner_py)

    return _creator


_SWITCHX_LEGACY = (
    "beeble_switchx_v1.nk",
    "beeble_switchx_helper.py",
    "beeble_switchx_runner_v1.py",
)
_SWITCHX2 = (
    "beeble_switchx2_v1.nk",
    "beeble_switchx2_helper.py",
    "beeble_switchx2_runner_v1.py",
)

_nodes_beeble_menu = nuke.menu("Nodes").addMenu("beeble.ai")
_nodes_beeble_menu.addCommand("SwitchX", _make_creator(*_SWITCHX_LEGACY))
_nodes_beeble_menu.addCommand("SwitchX 2.0", _make_creator(*_SWITCHX2))

_top_beeble_menu = nuke.menu("Nuke").addMenu("beeble.ai")
_top_beeble_menu.addCommand("SwitchX", _make_creator(*_SWITCHX_LEGACY))
_top_beeble_menu.addCommand("SwitchX 2.0", _make_creator(*_SWITCHX2))
