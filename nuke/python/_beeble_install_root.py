# Purpose: Resolve nuke-beeble-ai-tools install root when Nuke passes a relative __file__.

from __future__ import print_function

import os

_MARKER_REL = os.path.join("nuke", "groups", "beeble_switchx_v1.nk")


def _norm_root(path):
    return os.path.normpath(path or "").replace("\\", "/")


def _has_marker(root):
    root = _norm_root(root)
    if not root:
        return False
    return os.path.isfile(os.path.join(root, _MARKER_REL))


def _iter_nuke_path_entries():
    raw = os.environ.get("NUKE_PATH", "") or ""
    if not raw.strip():
        return
    sep = ";" if ";" in raw else ":"
    for entry in raw.split(sep):
        entry = (entry or "").strip().strip('"')
        if entry:
            yield entry


def discover_install_root(caller_file=None):
    """
    Return the nuke-beeble-ai-tools repo root.

    Resolution order:
    1. NUKE_PATH entries that contain beeble_switchx_v1.nk
    2. NUKE_BEEBLE_AI_TOOLS_ROOT if it contains the marker
    3. Absolute dirname of caller_file if it contains the marker
    4. Scan parents of caller_file for the marker
    """
    for entry in _iter_nuke_path_entries():
        root = _norm_root(entry)
        if _has_marker(root):
            return root

    env_root = _norm_root(os.environ.get("NUKE_BEEBLE_AI_TOOLS_ROOT", ""))
    if _has_marker(env_root):
        return env_root

    paths_to_try = []
    if caller_file:
        caller_file = (caller_file or "").strip()
        if caller_file:
            paths_to_try.append(os.path.abspath(caller_file))
            if not os.path.isabs(caller_file):
                paths_to_try.append(os.path.join(os.getcwd(), caller_file))

    for path in paths_to_try:
        root = _norm_root(os.path.dirname(path))
        if _has_marker(root):
            return root
        walk = root
        for _ in range(6):
            parent = _norm_root(os.path.dirname(walk))
            if parent == walk:
                break
            if _has_marker(parent):
                return parent
            walk = parent

    if paths_to_try:
        return _norm_root(os.path.dirname(paths_to_try[0]))
    return env_root
