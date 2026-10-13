# Purpose: Check SwitchX helper failure dialogs, including org-key and credit cases.
# Run: py -3 -m unittest tests.test_switchx2_helper_errors
# Does not require Nuke.

from __future__ import print_function

import os
import sys
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import beeble_common
import beeble_switchx_runner_v1 as switchx_runner
import beeble_switchx2_runner_v1 as runner


_ORG_KEY_LOG = """\
Uploading source video: C:/temp/source_video.mp4
Uploaded beeble_uri=beeble://uploads/upload_x/source_video.mp4
Starting SwitchX 2.0 product job (attempt 1/4)
ERROR: SwitchX 2.0 start request failed.
{
  "detail": "This endpoint requires an organization-bound API key"
}
"""


class Switchx2HelperErrorTests(unittest.TestCase):
    def test_org_bound_key_error_is_explained(self):
        message = runner.helper_failure_message(5, _ORG_KEY_LOG.splitlines())
        self.assertIn("organization-bound API key", message)
        self.assertIn("BEEBLE_API_KEY", message)
        self.assertIn("https://developer.beeble.ai/docs/enterprise/authentication", message)
        self.assertNotIn("exit 5", message)
        self.assertNotIn("Script Editor", message)

    def test_other_helper_failures_keep_exit_code(self):
        lines = [
            "ERROR: SwitchX 2.0 job failed.",
            '{"status": "failed"}',
        ]
        message = runner.helper_failure_message(5, lines)
        self.assertIn("exit 5", message)
        self.assertIn("Script Editor", message)

    def test_budget_exceeded_tells_the_user_credits_are_used_up(self):
        lines = [
            "ERROR: SwitchX 2.0 start request failed.",
            "{",
            '  "detail": {',
            '    "error_code": "BUDGET_EXCEEDED",',
            '    "message": "organization credit balance is empty"',
            "  }",
            "}",
        ]
        message = runner.helper_failure_message(5, lines)
        self.assertIn("Beeble credits are used up", message)
        self.assertIn("https://developer.beeble.ai", message)
        self.assertNotIn("exit 5", message)
        self.assertNotIn("Script Editor", message)

    def test_credit_required_job_status_tells_the_user_credits_are_used_up(self):
        lines = [
            "ERROR: SwitchX 2.0 job failed.",
            '{"status": "credit_required", "error": "credit balance is empty"}',
        ]
        message = runner.helper_failure_message(5, lines)
        self.assertIn("Beeble credits are used up", message)
        self.assertNotIn("exit 5", message)

    def test_legacy_insufficient_balance_uses_the_same_credit_dialog(self):
        lines = [
            "ERROR: SwitchX start request failed.",
            '{"error": {"code": "INSUFFICIENT_BALANCE", "message": "Prepaid account balance is too low"}}',
        ]
        message = switchx_runner.helper_failure_message(5, lines)
        self.assertIn("Beeble credits are used up", message)
        self.assertNotIn("exit 5", message)

    def test_helper_summary_leads_with_the_credit_dialog(self):
        exc = beeble_common.BeebleApiError(
            "HTTP 402 POST failed",
            status_code=402,
            body={
                "detail": {
                    "error_code": "BUDGET_EXCEEDED",
                    "message": "organization credit balance is empty",
                }
            },
        )
        summary = beeble_common.format_beeble_error_summary(exc)
        self.assertTrue(summary.startswith("Beeble credits are used up"))
        self.assertIn("Beeble said: organization credit balance is empty", summary)
        self.assertNotIn("error_code", summary)


if __name__ == "__main__":
    unittest.main()
