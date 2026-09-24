# Purpose: Execute-knob entry point for beeble.ai group nodes (isolated from nuke-fal-ai-tools).

from __future__ import print_function

import beeble_install_help
import beeble_py_compat
import beeble_prerender_core_v1 as prerender_core

UnsavedNukeScriptError = None
ScriptOutputDirError = None

EXECUTE_NODE_GLOBAL = "_beeble_execute_group_node"
_active_execute_group_node = None


def _refresh_prerender_core():
    global prerender_core, UnsavedNukeScriptError, ScriptOutputDirError
    import sys

    mod = sys.modules.get("beeble_prerender_core_v1")
    if mod is not None:
        prerender_core = beeble_py_compat.reload_module(mod)
    UnsavedNukeScriptError = prerender_core.UnsavedNukeScriptError
    ScriptOutputDirError = prerender_core.ScriptOutputDirError


_refresh_prerender_core()


def should_show_success_popup(group_node):
    try:
        knob = group_node.knob("show_success_popup")
        if knob is None:
            return True
        return bool(knob.value())
    except Exception:
        return True


def _show_unsaved_script_message(nuke_module, exc):
    action = "running beeble.ai nodes"
    try:
        if exc.args:
            action = exc.args[0]
    except Exception:
        pass
    try:
        nuke_module.message(prerender_core.unsaved_nuke_script_message(action))
    except Exception:
        pass


def get_execute_group_node(nuke_module, caller_globals=None):
    global _active_execute_group_node
    if _active_execute_group_node is not None:
        return _active_execute_group_node
    if caller_globals is not None:
        try:
            node = caller_globals.get(EXECUTE_NODE_GLOBAL)
            if node is not None:
                return node
        except Exception:
            pass
    return nuke_module.thisNode()


def _run_runner_for_node(node):
    import nuke

    global _active_execute_group_node

    prerender_core.require_saved_nuke_script(nuke)
    prerender_core.reset_to_root_graph(nuke)

    raw_runner = ""
    try:
        raw_runner = node.knob("runner_path").value()
    except Exception:
        pass

    runner = beeble_install_help.require_runner_path(nuke, raw_runner)
    _active_execute_group_node = node
    try:
        beeble_py_compat.exec_script(
            runner,
            {
                "__file__": runner,
                "__name__": "__main__",
                EXECUTE_NODE_GLOBAL: node,
            },
        )
    finally:
        _active_execute_group_node = None
        prerender_core.reset_to_root_graph(nuke)


def execute_this_node():
    import nuke

    _refresh_prerender_core()
    try:
        _run_runner_for_node(nuke.thisNode())
    except UnsavedNukeScriptError as exc:
        _show_unsaved_script_message(nuke, exc)
    except ScriptOutputDirError:
        pass
    except Exception as exc:
        try:
            nuke.message("Execute failed:\n%s" % str(exc))
        except Exception:
            pass
        raise
