import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install
import verify


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.home = Path(self.temporary_directory.name) / ".codex"
        install.install(
            self.home,
            "https://example.invalid/device",
            "/usr/bin/python3",
        )

    def test_default_verification_is_offline(self):
        with mock.patch.object(verify.subprocess, "run") as run:
            result = verify.verify(self.home)

        self.assertTrue(result.ok, result.errors)
        self.assertFalse(result.sent_test)
        run.assert_not_called()

    def test_send_test_invokes_installed_bark_command_once(self):
        completed = mock.Mock(returncode=0)
        with mock.patch.object(verify.subprocess, "run", return_value=completed) as run:
            result = verify.verify(self.home, send_test=True)

        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.sent_test)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/usr/bin/python3", str(self.home / "bark-notify.py")])
        self.assertIn('"type": "agent-turn-complete"', command[-1])
        self.assertIn('"codexnotes-test": true', command[-1])

    def test_blank_private_url_fails_without_sending(self):
        private_path = self.home / "bark-notify.conf"
        text = private_path.read_text(encoding="utf-8")
        private_path.write_text(
            text.replace(
                "BARK_BASE_URL=https://example.invalid/device", "BARK_BASE_URL="
            ),
            encoding="utf-8",
        )

        with mock.patch.object(verify.subprocess, "run") as run:
            result = verify.verify(self.home)

        self.assertFalse(result.ok)
        self.assertTrue(any("BARK_BASE_URL" in error for error in result.errors))
        run.assert_not_called()

    def test_changed_notify_chain_fails_verification(self):
        (self.home / "config.toml").write_text(
            'notify = ["different-tool"]\n', encoding="utf-8"
        )

        result = verify.verify(self.home)

        self.assertFalse(result.ok)
        self.assertTrue(any("notify chain" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
