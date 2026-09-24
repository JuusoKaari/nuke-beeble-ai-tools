# Purpose: Beeble install hints keep using this plugin's URL module when another
# plugin has already loaded a different module named _repo_urls.
# Run: py -3 -m unittest tests.test_repo_url_isolation
# Does not require Nuke.

from __future__ import print_function

import os
import sys
import types
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
_FAL_PYTHON_DIR = os.path.normpath(
    os.path.join(_ROOT, "..", "nuke-fal-ai-tools", "nuke", "python")
)


class RepoUrlIsolationTest(unittest.TestCase):
    def setUp(self):
        self._saved_modules = {}
        for name in ("_repo_urls", "_beeble_repo_urls", "beeble_install_help"):
            self._saved_modules[name] = sys.modules.get(name)
            sys.modules.pop(name, None)
        self._saved_path = list(sys.path)
        if _PYTHON_DIR not in sys.path:
            sys.path.insert(0, _PYTHON_DIR)

    def tearDown(self):
        sys.path[:] = self._saved_path
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_install_help_ignores_foreign_repo_urls(self):
        foreign = types.ModuleType("_repo_urls")
        foreign.GITHUB_REPO_URL = "https://github.com/example/not-beeble"
        sys.modules["_repo_urls"] = foreign

        import beeble_install_help
        from _beeble_repo_urls import GITHUB_REPO_URL, install_download_lines

        self.assertIs(beeble_install_help.install_download_lines, install_download_lines)
        self.assertIn("nuke-beeble-ai-tools", GITHUB_REPO_URL)
        self.assertNotIn("not-beeble", GITHUB_REPO_URL)

    def test_fal_repo_urls_does_not_satisfy_beeble_import(self):
        if not os.path.isfile(os.path.join(_FAL_PYTHON_DIR, "_repo_urls.py")):
            self.skipTest("nuke-fal-ai-tools is not checked out beside this repo")
        if _FAL_PYTHON_DIR not in sys.path:
            sys.path.insert(0, _FAL_PYTHON_DIR)

        import _repo_urls as fal_urls

        self.assertFalse(hasattr(fal_urls, "install_download_lines"))
        self.assertIn("nuke-fal-ai-tools", fal_urls.GITHUB_REPO_URL)

        import beeble_install_help
        from _beeble_repo_urls import GITHUB_REPO_URL

        self.assertIn("nuke-beeble-ai-tools", GITHUB_REPO_URL)
        self.assertEqual(
            beeble_install_help.install_download_lines.__module__,
            "_beeble_repo_urls",
        )


if __name__ == "__main__":
    unittest.main()
