# Purpose: Static checks for Mask channel knobs, mask prerender routing, and docs.
# Run: py -3 -m unittest tests.test_mask_channel_logic
# Does not require Nuke.

from __future__ import print_function

import ast
import importlib.util
import os
import sys
import tempfile
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
_GROUPS_DIR = os.path.join(_ROOT, "nuke", "groups")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import beeble_prerender_mask_v1 as mask_prerender
import beeble_prerender_v1 as prerender


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeKnob(object):
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value


class _FakeNode(object):
    def __init__(self, class_name="NoOp"):
        self._class = class_name
        self._knobs = {}
        self._input0 = None
        self.deleted = False

    def Class(self):
        return self._class

    def knob(self, name):
        return self._knobs.get(name)

    def knobs(self):
        return self._knobs

    def __getitem__(self, name):
        if name not in self._knobs:
            self._knobs[name] = _FakeKnob(None)
        return self._knobs[name]

    def setInput(self, index, node):
        if index == 0:
            self._input0 = node


class _FakeNodes(object):
    def __init__(self, created):
        self._created = created

    def Shuffle(self):
        node = _FakeNode("Shuffle")
        self._created.append(node)
        return node

    def Saturation(self):
        node = _FakeNode("Saturation")
        self._created.append(node)
        return node

    def Write(self):
        node = _FakeNode("Write")
        self._created.append(node)
        return node


class _FakeRoot(object):
    def begin(self):
        return None

    def fps(self):
        return 24.0


class _FakeNuke(object):
    def __init__(self):
        self.created = []
        self.deleted = []
        self.end_group_calls = 0
        self.nodes = _FakeNodes(self.created)
        self._root = _FakeRoot()

    def root(self):
        return self._root

    def endGroup(self):
        self.end_group_calls += 1

    def delete(self, node):
        node.deleted = True
        self.deleted.append(node)

    def execute(self, write_node, first, last):
        return None

    def filename(self, read_node, frame):
        kn = read_node.knob("file")
        return kn.value() if kn is not None else ""


class _GroupWithKnob(object):
    def __init__(self, knobs):
        self._knobs = knobs

    def knob(self, name):
        return self._knobs.get(name)


class TestNormalizeMaskChannel(unittest.TestCase):
    def test_valid_values(self):
        self.assertEqual(mask_prerender.normalize_mask_channel("alpha"), "alpha")
        self.assertEqual(mask_prerender.normalize_mask_channel("Luminance"), "luminance")
        self.assertEqual(mask_prerender.normalize_mask_channel(" ALPHA "), "alpha")

    def test_fallback_to_alpha(self):
        self.assertEqual(mask_prerender.normalize_mask_channel(""), "alpha")
        self.assertEqual(mask_prerender.normalize_mask_channel(None), "alpha")
        self.assertEqual(mask_prerender.normalize_mask_channel("rgba"), "alpha")


class TestReadMaskChannelKnob(unittest.TestCase):
    def test_reads_knob(self):
        group = _GroupWithKnob({"mask_channel": _FakeKnob("luminance")})
        self.assertEqual(mask_prerender.read_mask_channel_knob(group), "luminance")

    def test_missing_knob_falls_back_to_alpha(self):
        group = _GroupWithKnob({})
        self.assertEqual(mask_prerender.read_mask_channel_knob(group), "alpha")

    def test_wrapper_export(self):
        group = _GroupWithKnob({})
        self.assertEqual(prerender.read_mask_channel_knob(group), "alpha")


class TestNkMaskChannelKnob(unittest.TestCase):
    def test_both_groups_have_mask_channel_default_alpha(self):
        for name in ("beeble_switchx_v1.nk", "beeble_switchx2_v1.nk"):
            text = _read(os.path.join(_GROUPS_DIR, name))
            self.assertIn('addUserKnob {4 mask_channel l "Mask channel"', text)
            self.assertIn("M {alpha luminance \"\"}", text)
            self.assertIn("mask_channel alpha", text)
            self.assertIn("Choose which channel is used as the Beeble matte", text)


class TestRunnerMaskRouting(unittest.TestCase):
    def _runner_source(self, filename):
        return _read(os.path.join(_PYTHON_DIR, filename))

    def test_runners_call_prepare_mask_not_generic_for_alpha(self):
        for filename in ("beeble_switchx_runner_v1.py", "beeble_switchx2_runner_v1.py"):
            text = self._runner_source(filename)
            self.assertIn("prepare_mask_video_input_path", text)
            self.assertIn("read_mask_channel_knob", text)
            # Alpha path must not use the generic video prepare helper.
            self.assertNotIn('base_name="alpha_mask",\n        )', text.replace("\r\n", "\n"))
            # Source video still uses the generic path.
            self.assertIn("prepare_video_input_path", text)
            self.assertIn('base_name="source_video"', text)
            # Alpha mask must not skip planned-frame validation via video fast path.
            self.assertIn('(alpha_node, "Alpha mask", False)', text)

    def test_runners_importable_without_nuke(self):
        # Importing runners pulls Nuke only inside main(); module load must succeed.
        for filename, mod_name in (
            ("beeble_switchx_runner_v1.py", "beeble_switchx_runner_v1_test"),
            ("beeble_switchx2_runner_v1.py", "beeble_switchx2_runner_v1_test"),
        ):
            path = os.path.join(_PYTHON_DIR, filename)
            module = _load_module(mod_name, path)
            self.assertTrue(hasattr(module, "main"))


class TestPrepareMaskAlwaysPrerenders(unittest.TestCase):
    def test_alpha_mode_builds_shuffle_and_deletes_it(self):
        fake_nuke = _FakeNuke()
        src = _FakeNode("Read")
        created_before = len(fake_nuke.created)

        original_render = mask_prerender.render_video_from_node
        calls = []

        def _fake_render(nuke_module, src_node, out_path, first, last):
            calls.append((src_node, out_path, first, last))
            # Write a tiny file so callers that check existence would succeed.
            with open(out_path, "wb") as handle:
                handle.write(b"fake")
            return out_path

        mask_prerender.render_video_from_node = _fake_render
        try:
            with tempfile.TemporaryDirectory() as td:
                out = mask_prerender.prepare_mask_video_input_path(
                    fake_nuke,
                    src,
                    frame=1,
                    default_first=10,
                    default_last=12,
                    run_dir=td,
                    base_name="alpha_mask",
                    mask_channel="alpha",
                )
                self.assertTrue(out.endswith("alpha_mask.mp4"))
                self.assertEqual(len(calls), 1)
                rendered_src, _, first, last = calls[0]
                self.assertEqual(first, 10)
                self.assertEqual(last, 12)
                self.assertEqual(rendered_src.Class(), "Shuffle")
                self.assertEqual(rendered_src["red"].value(), "alpha")
                self.assertEqual(rendered_src["green"].value(), "alpha")
                self.assertEqual(rendered_src["blue"].value(), "alpha")
                self.assertTrue(rendered_src.deleted)
        finally:
            mask_prerender.render_video_from_node = original_render

        self.assertGreater(len(fake_nuke.created), created_before)

    def test_luminance_uses_saturation_zero(self):
        fake_nuke = _FakeNuke()
        src = _FakeNode("Constant")
        calls = []

        def _fake_render(nuke_module, src_node, out_path, first, last):
            calls.append(src_node)
            with open(out_path, "wb") as handle:
                handle.write(b"fake")
            return out_path

        original_render = mask_prerender.render_video_from_node
        mask_prerender.render_video_from_node = _fake_render
        try:
            with tempfile.TemporaryDirectory() as td:
                mask_prerender.prepare_mask_video_input_path(
                    fake_nuke,
                    src,
                    frame=1,
                    default_first=1,
                    default_last=2,
                    run_dir=td,
                    base_name="alpha_mask",
                    mask_channel="luminance",
                )
        finally:
            mask_prerender.render_video_from_node = original_render

        self.assertEqual(len(calls), 1)
        rendered_src = calls[0]
        self.assertEqual(rendered_src.Class(), "Saturation")
        self.assertEqual(rendered_src["saturation"].value(), 0)
        self.assertTrue(rendered_src.deleted)
        self.assertEqual(fake_nuke.end_group_calls, 1)

    def test_mask_path_never_passes_through_mp4_read(self):
        # prepare_video_input_path would return a Read mp4; mask path must not.
        tree = ast.parse(_read(os.path.join(_PYTHON_DIR, "beeble_prerender_mask_v1.py")))
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        self.assertIn("prepare_mask_video_input_path", func_names)
        source = _read(os.path.join(_PYTHON_DIR, "beeble_prerender_mask_v1.py"))
        self.assertIn("never passes through an existing mp4/mov read", source.lower())
        self.assertIn("no read fast-path", source.lower())


class TestPrepareVideoUnchanged(unittest.TestCase):
    def test_prepare_video_still_has_mp4_fast_path(self):
        source = _read(os.path.join(_PYTHON_DIR, "beeble_prerender_v1.py"))
        self.assertIn("_is_valid_video_extension", source)
        self.assertIn("resolve_read_file_at_frame", source)
        self.assertIn("Do not use this for alpha_mask", source)


class TestDocsDescribeGraphInputs(unittest.TestCase):
    def test_readme_and_install(self):
        readme = _read(os.path.join(_ROOT, "README.md"))
        install = _read(os.path.join(_ROOT, "docs", "INSTALL.md"))
        for text in (readme, install):
            self.assertIn("Any Nuke image/video pipe", text)
            self.assertIn("Any Nuke matte pipe", text)
            self.assertIn("Mask channel", text)
            self.assertIn("always", text.lower())
            self.assertIn("normalized", text.lower())


if __name__ == "__main__":
    unittest.main()
