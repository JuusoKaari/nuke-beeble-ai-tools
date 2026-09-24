# Purpose: Fail CI if the release ZIP omits install files, ships development
# paths, or extracts to a tree that is not a standalone artist install.
# Run: py -3 -m unittest tests.test_release_zip

from __future__ import print_function

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PACK_SCRIPTS = os.path.join(_ROOT, ".github", "scripts")
if _PACK_SCRIPTS not in sys.path:
    sys.path.insert(0, _PACK_SCRIPTS)

from pack_release import PackError, pack_release_zip

INSTALL_PREFIX = "nuke-beeble-ai-tools/"
INSTALL_ROOT_NAME = "nuke-beeble-ai-tools"

REQUIRED_ZIP_FILES = (
    "nuke-beeble-ai-tools/init.py",
    "nuke-beeble-ai-tools/menu.py",
    "nuke-beeble-ai-tools/requirements-python3.txt",
    "nuke-beeble-ai-tools/README.md",
    "nuke-beeble-ai-tools/LICENSE",
    "nuke-beeble-ai-tools/docs/INSTALL.md",
)

REQUIRED_ZIP_PREFIXES = (
    "nuke-beeble-ai-tools/nuke/groups/",
    "nuke-beeble-ai-tools/nuke/python/",
)

# Relative to the extracted plugin root (the folder that contains init.py).
REQUIRED_EXTRACT_FILES = (
    "init.py",
    "menu.py",
    "requirements-python3.txt",
    "README.md",
    "LICENSE",
    os.path.join("docs", "INSTALL.md"),
)

REQUIRED_EXTRACT_DIRS = (
    os.path.join("nuke", "groups"),
    os.path.join("nuke", "python"),
    "docs",
)

FORBIDDEN_EXTRACT_NAMES = frozenset(
    (
        "tests",
        "dev_tools",
        ".git",
        ".github",
        ".cursor",
        "dist",
        "AGENTS.md",
        "CHANGELOG.md",
        "unattended-todo.json",
        ".gitignore",
        "TODO.md",
    )
)

FORBIDDEN_SEGMENTS = frozenset(
    (
        "tests",
        "dev_tools",
        "planning",
        "unattended-todo.json",
        ".git",
        ".github",
        "__pycache__",
        "dist",
    )
)

# Maintainer docs that must not ship if present in the repo.
FORBIDDEN_ZIP_FILES = (
    "nuke-beeble-ai-tools/docs/RELEASE_CHECK.md",
    "nuke-beeble-ai-tools/docs/RELEASE_CANDIDATE.md",
)

# Helper-side modules that must import without Nuke.
EXTRACT_IMPORT_MODULES = (
    ("extract_repo_urls", os.path.join("nuke", "python", "_beeble_repo_urls.py")),
    ("extract_beeble_py_compat", os.path.join("nuke", "python", "beeble_py_compat.py")),
    ("extract_beeble_install_root", os.path.join("nuke", "python", "_beeble_install_root.py")),
)


def _posix(name):
    return name.replace("\\", "/")


def layout_problems(names):
    """Return human-readable layout failures for ZIP member names."""
    names = [_posix(name) for name in names]
    problems = []
    name_set = set(names)
    for required in REQUIRED_ZIP_FILES:
        if required not in name_set:
            problems.append("missing %s" % required)
    for prefix in REQUIRED_ZIP_PREFIXES:
        if not any(name.startswith(prefix) for name in names):
            problems.append("missing tree %s" % prefix)
    for forbidden in FORBIDDEN_ZIP_FILES:
        if forbidden in name_set:
            problems.append("forbidden %s" % forbidden)
    for name in names:
        for part in name.split("/"):
            if part in FORBIDDEN_SEGMENTS:
                problems.append("forbidden %s in %s" % (part, name))
                break
    return problems


def extract_layout_problems(plugin_root):
    """Return layout failures for an extracted install tree."""
    problems = []
    for rel in REQUIRED_EXTRACT_FILES:
        path = os.path.join(plugin_root, rel)
        if not os.path.isfile(path):
            problems.append("missing file %s" % _posix(rel))
    for rel in REQUIRED_EXTRACT_DIRS:
        path = os.path.join(plugin_root, rel)
        if not os.path.isdir(path):
            problems.append("missing dir %s" % _posix(rel))
    try:
        names = os.listdir(plugin_root)
    except OSError as exc:
        return ["cannot list plugin root: %s" % exc]
    for name in names:
        if name in FORBIDDEN_EXTRACT_NAMES:
            problems.append("dev leftover %s" % name)
    planning = os.path.join(plugin_root, "docs", "planning")
    if os.path.exists(planning):
        problems.append("dev leftover docs/planning")
    for maintainer_doc in ("RELEASE_CHECK.md", "RELEASE_CANDIDATE.md"):
        leftover = os.path.join(plugin_root, "docs", maintainer_doc)
        if os.path.exists(leftover):
            problems.append("dev leftover docs/%s" % maintainer_doc)
    return problems


def compile_extracted_python(plugin_root):
    """Syntax-check every .py under the extract without writing bytecode."""
    failures = []
    for dirpath, dirnames, filenames in os.walk(plugin_root):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                source = handle.read()
            try:
                compile(source, path, "exec")
            except SyntaxError as exc:
                rel = _posix(os.path.relpath(path, plugin_root))
                failures.append("%s: %s" % (rel, exc))
    return failures


def _load_module(mod_name, path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s from %s" % (mod_name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestReleaseZipLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="nuke-beeble-zip-")
        cls._archive = os.path.join(cls._tmpdir, "nuke-beeble-ai-tools-dev.zip")
        pack_release_zip(_ROOT, archive_path=cls._archive, version="dev")
        with zipfile.ZipFile(cls._archive, "r") as zf:
            cls._names = zf.namelist()
            cls._extract = os.path.join(cls._tmpdir, "extract")
            os.makedirs(cls._extract)
            zf.extractall(cls._extract)
        cls._plugin_root = os.path.join(cls._extract, INSTALL_ROOT_NAME)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_packed_archive_matches_install_layout(self):
        self.assertTrue(os.path.isfile(self._archive), self._archive)
        self.assertEqual(layout_problems(self._names), [])
        self.assertIn(INSTALL_PREFIX + "init.py", self._names)
        self.assertIn(INSTALL_PREFIX + "nuke/groups/beeble_switchx_v1.nk", self._names)
        self.assertIn(INSTALL_PREFIX + "nuke/groups/beeble_switchx2_v1.nk", self._names)

    def test_maintainer_release_docs_not_packed_when_absent(self):
        packed_names = [_posix(name) for name in self._names]
        for basename in ("RELEASE_CHECK.md", "RELEASE_CANDIDATE.md"):
            packed = INSTALL_PREFIX + "docs/" + basename
            self.assertNotIn(packed, packed_names)
            self.assertFalse(
                os.path.isfile(
                    os.path.join(self._plugin_root, "docs", basename)
                )
            )

    def test_layout_check_fails_when_maintainer_docs_shipped(self):
        for basename in ("RELEASE_CHECK.md", "RELEASE_CANDIDATE.md"):
            names = list(self._names) + [
                "nuke-beeble-ai-tools/docs/" + basename
            ]
            problems = layout_problems(names)
            self.assertTrue(
                any(basename in item for item in problems),
                problems,
            )

    def test_extracted_tree_is_standalone_install(self):
        self.assertTrue(os.path.isdir(self._plugin_root), self._plugin_root)
        self.assertEqual(extract_layout_problems(self._plugin_root), [])
        extract_names = os.listdir(self._extract)
        self.assertEqual(extract_names, [INSTALL_ROOT_NAME])

    def test_extracted_python_compiles(self):
        failures = compile_extracted_python(self._plugin_root)
        self.assertEqual(failures, [])

    def test_extracted_helper_modules_import(self):
        for mod_name, rel in EXTRACT_IMPORT_MODULES:
            path = os.path.join(self._plugin_root, rel)
            module = _load_module(mod_name, path)
            self.assertIsNotNone(module)

    def test_layout_check_fails_when_tests_shipped(self):
        names = list(self._names) + ["nuke-beeble-ai-tools/tests/test_foo.py"]
        problems = layout_problems(names)
        self.assertTrue(
            any("tests" in item for item in problems),
            problems,
        )

    def test_layout_check_fails_when_init_omitted(self):
        names = [
            name
            for name in self._names
            if _posix(name) != "nuke-beeble-ai-tools/init.py"
        ]
        problems = layout_problems(names)
        self.assertTrue(
            any("init.py" in item for item in problems),
            problems,
        )

    def test_extract_layout_flags_dev_checkout_files(self):
        fake = tempfile.mkdtemp(prefix="nuke-beeble-fake-extract-")
        try:
            open(os.path.join(fake, "init.py"), "w").close()
            os.makedirs(os.path.join(fake, "tests"))
            problems = extract_layout_problems(fake)
            self.assertTrue(
                any("tests" in item for item in problems),
                problems,
            )
        finally:
            shutil.rmtree(fake, ignore_errors=True)

    def test_pack_fails_when_required_install_files_missing(self):
        empty = tempfile.mkdtemp(prefix="nuke-beeble-empty-")
        try:
            archive = os.path.join(empty, "out.zip")
            with self.assertRaises(PackError):
                pack_release_zip(empty, archive_path=archive, version="dev")
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_cli_packer_writes_install_zip(self):
        out_dir = tempfile.mkdtemp(prefix="nuke-beeble-cli-pack-")
        try:
            archive = os.path.join(out_dir, "from-cli.zip")
            script = os.path.join(_ROOT, ".github", "scripts", "pack_release.py")
            subprocess.check_call(
                [
                    sys.executable,
                    script,
                    "--root",
                    _ROOT,
                    "--version",
                    "dev",
                    "--output",
                    archive,
                ]
            )
            with zipfile.ZipFile(archive, "r") as zf:
                names = zf.namelist()
            self.assertEqual(layout_problems(names), [])
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_release_workflow_uses_same_packer(self):
        path = os.path.join(_ROOT, ".github", "workflows", "release.yml")
        with open(path, "r") as handle:
            text = handle.read()
        self.assertIn(".github/scripts/pack_release.py", text)
        self.assertIn("python -m unittest discover -s tests", text)

    def test_gitignore_covers_pack_leftovers(self):
        path = os.path.join(_ROOT, ".gitignore")
        with open(path, "r") as handle:
            lines = [
                line.strip()
                for line in handle.read().replace("\r\n", "\n").split("\n")
            ]
        self.assertIn("dist/", lines)
        self.assertIn("*.zip", lines)
