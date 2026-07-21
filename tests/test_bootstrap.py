import argparse
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import bootstrap
import install
import verify


class BootstrapTests(unittest.TestCase):
    def test_raw_key_becomes_official_device_url(self):
        key = "DeviceKey_123-abc"
        self.assertEqual(
            bootstrap.normalize_bark_key(key),
            "https://api.day.app/" + key,
        )

    def test_resolve_accepts_complete_url(self):
        value = "https://example.invalid/device"
        self.assertEqual(
            bootstrap.resolve_bark_url({"BARK_BASE_URL": value}), value
        )

    def test_resolve_rejects_conflicting_inputs_without_echoing_them(self):
        key = "PrivateKey_123"
        with self.assertRaisesRegex(ValueError, "only one") as raised:
            bootstrap.resolve_bark_url(
                {
                    "BARK_KEY": key,
                    "BARK_BASE_URL": "https://example.invalid/device",
                }
            )
        self.assertNotIn(key, str(raised.exception))

    def test_invalid_key_is_rejected_without_echoing_it(self):
        key = "bad/key value"
        with self.assertRaises(ValueError) as raised:
            bootstrap.normalize_bark_key(key)
        self.assertNotIn(key, str(raised.exception))

    def test_missing_environment_uses_hidden_prompt(self):
        prompt = mock.Mock(return_value="PromptKey_123")

        value = bootstrap.resolve_bark_url({}, prompt=prompt)

        self.assertEqual(value, "https://api.day.app/" + "PromptKey_123")
        prompt.assert_called_once_with("Bark key or device URL (input hidden): ")

    def test_offline_verification_precedes_one_test(self):
        calls = []
        home = Path("example-codex-home")

        def install_fn(codex_home, bark_url, python_executable, repair=False):
            calls.append(("install", repair))
            return install.InstallResult("installed", home, None, [], "installed")

        def verify_fn(codex_home, send_test=False):
            calls.append(("verify", send_test))
            return verify.VerificationResult(True, [], [], send_test)

        result = bootstrap.run_bootstrap(
            home,
            "https://example.invalid/device",
            send_test=True,
            install_fn=install_fn,
            verify_fn=verify_fn,
            python_executable="python",
        )

        self.assertEqual(
            calls, [("install", False), ("verify", False), ("verify", True)]
        )
        self.assertTrue(result.sent_test)

    def test_offline_failure_prevents_test_delivery(self):
        calls = []
        home = Path("example-codex-home")

        def install_fn(codex_home, bark_url, python_executable, repair=False):
            calls.append(("install", repair))
            return install.InstallResult("installed", home, None, [], "installed")

        def verify_fn(codex_home, send_test=False):
            calls.append(("verify", send_test))
            return verify.VerificationResult(False, [], ["offline failed"], False)

        with self.assertRaisesRegex(RuntimeError, "offline verification failed"):
            bootstrap.run_bootstrap(
                home,
                "https://example.invalid/device",
                send_test=True,
                install_fn=install_fn,
                verify_fn=verify_fn,
                python_executable="python",
            )

        self.assertEqual(calls, [("install", False), ("verify", False)])

    def test_repair_is_forwarded_only_when_requested(self):
        calls = []
        home = Path("example-codex-home")

        def install_fn(codex_home, bark_url, python_executable, repair=False):
            calls.append(("install", repair))
            return install.InstallResult("repaired", home, None, [], "repaired")

        def verify_fn(codex_home, send_test=False):
            calls.append(("verify", send_test))
            return verify.VerificationResult(True, [], [], False)

        bootstrap.run_bootstrap(
            home,
            "https://example.invalid/device",
            repair=True,
            install_fn=install_fn,
            verify_fn=verify_fn,
            python_executable="python",
        )

        self.assertEqual(calls, [("install", True), ("verify", False)])

    def test_failed_test_delivery_is_reported(self):
        home = Path("example-codex-home")
        installed = install.InstallResult("installed", home, None, [], "installed")
        results = iter(
            [
                verify.VerificationResult(True, [], [], False),
                verify.VerificationResult(False, [], ["test failed"], False),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "test delivery failed"):
            bootstrap.run_bootstrap(
                home,
                "https://example.invalid/device",
                send_test=True,
                install_fn=lambda *args, **kwargs: installed,
                verify_fn=lambda *args, **kwargs: next(results),
                python_executable="python",
            )

    def test_main_output_never_contains_key(self):
        key = "PrivateKey_123"
        home = Path("example-codex-home")
        installed = install.InstallResult("installed", home, None, [], "installed")
        offline = verify.VerificationResult(True, [], [], False)
        test = verify.VerificationResult(True, [], [], True)
        result = bootstrap.BootstrapResult(installed, offline, test)
        arguments = argparse.Namespace(
            codex_home=str(home), send_test=True, repair=False
        )
        stdout = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"BARK_KEY": key}, clear=True),
            mock.patch.object(bootstrap, "_arguments", return_value=arguments),
            mock.patch.object(bootstrap, "run_bootstrap", return_value=result),
            redirect_stdout(stdout),
        ):
            self.assertEqual(bootstrap.main(), 0)

        output = stdout.getvalue()
        self.assertNotIn(key, output)
        self.assertIn("Fully restart Codex", output)

    def test_main_error_never_echoes_invalid_key(self):
        key = "Private Key/123"
        arguments = argparse.Namespace(
            codex_home=None, send_test=True, repair=False
        )
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"BARK_KEY": key}, clear=True),
            mock.patch.object(bootstrap, "_arguments", return_value=arguments),
            redirect_stderr(stderr),
        ):
            self.assertEqual(bootstrap.main(), 1)

        output = stderr.getvalue()
        self.assertNotIn(key, output)
        self.assertIn("Bootstrap failed", output)


if __name__ == "__main__":
    unittest.main()
