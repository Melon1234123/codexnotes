import json
import tempfile
import unittest
from pathlib import Path

import install
import uninstall


TEST_BARK_URL = "https://example.invalid/device"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.home = Path(self.temporary_directory.name) / ".codex"
        self.python = "/usr/bin/python3"

    def install(self):
        return install.install(self.home, TEST_BARK_URL, self.python)

    def read_notify(self):
        text = (self.home / "config.toml").read_text(encoding="utf-8")
        return install.read_notify_setting(text).command

    def test_missing_config_is_created_and_uninstall_removes_it(self):
        result = self.install()

        self.assertEqual(result.action, "installed")
        self.assertEqual(
            self.read_notify(),
            [self.python, str(self.home / "bark-notify.py")],
        )
        self.assertTrue((self.home / "bark-notify.py").is_file())
        self.assertTrue((self.home / "bark-notify.conf").is_file())
        self.assertTrue((self.home / "bark-notify-install-state.json").is_file())
        self.assertNotIn(TEST_BARK_URL, result.message)

        removed = uninstall.uninstall(self.home)
        self.assertEqual(removed.action, "uninstalled")
        self.assertFalse((self.home / "config.toml").exists())
        self.assertFalse((self.home / "bark-notify.py").exists())
        self.assertFalse((self.home / "bark-notify.conf").exists())

    def test_config_without_notify_keeps_other_settings(self):
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            'model = "gpt-5.6"\n\n[features]\nmemories = true\n',
            encoding="utf-8",
        )

        self.install()

        text = (self.home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('model = "gpt-5.6"', text)
        self.assertIn("[features]", text)
        self.assertEqual(self.read_notify()[0], self.python)

    def test_native_desktop_notifier_stays_outermost(self):
        native = [
            "/Applications/Codex Computer Use.app/Contents/MacOS/SkyComputerUseClient",
            "turn-ended",
        ]
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            "notify = {}\n".format(install.serialize_notify(native)),
            encoding="utf-8",
        )

        self.install()

        command = self.read_notify()
        self.assertEqual(command[:2], native)
        self.assertEqual(command.count("--previous-notify"), 1)
        self.assertEqual(
            json.loads(command[3]),
            [self.python, str(self.home / "bark-notify.py")],
        )

        self.install()
        repeated = self.read_notify()
        self.assertEqual(repeated.count("--previous-notify"), 1)
        self.assertEqual(repeated[:2], native)

    def test_native_desktop_preserves_its_existing_previous_notifier(self):
        previous = ["notify-tool", "--done"]
        native = [
            r"C:\Program Files\Codex\SkyComputerUseClient.exe",
            "turn-ended",
            "--previous-notify",
            json.dumps(previous),
        ]
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            "notify = {}\n".format(install.serialize_notify(native)),
            encoding="utf-8",
        )

        self.install()

        command = self.read_notify()
        self.assertEqual(command[:2], native[:2])
        self.assertEqual(command.count("--previous-notify"), 1)
        private_config = install.read_private_config(
            self.home / "bark-notify.conf"
        )
        self.assertEqual(json.loads(private_config["PREVIOUS_NOTIFY_JSON"]), previous)

        uninstall.uninstall(self.home)
        self.assertEqual(self.read_notify(), native)

    def test_arbitrary_notifier_is_called_by_bark_notifier(self):
        previous = ["notify-tool", "--title", "Codex done"]
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            "notify = {}\n".format(install.serialize_notify(previous)),
            encoding="utf-8",
        )

        self.install()

        self.assertEqual(
            self.read_notify(),
            [self.python, str(self.home / "bark-notify.py")],
        )
        private_config = install.read_private_config(
            self.home / "bark-notify.conf"
        )
        self.assertEqual(json.loads(private_config["PREVIOUS_NOTIFY_JSON"]), previous)

    def test_second_install_is_idempotent_and_reuses_backup(self):
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            'notify = ["notify-tool"]\nmodel = "gpt-5.6"\n', encoding="utf-8"
        )
        first = self.install()
        first_notify = self.read_notify()
        first_state = json.loads(
            (self.home / "bark-notify-install-state.json").read_text(encoding="utf-8")
        )

        second = self.install()
        second_state = json.loads(
            (self.home / "bark-notify-install-state.json").read_text(encoding="utf-8")
        )

        self.assertEqual(second.action, "already-installed")
        self.assertEqual(self.read_notify(), first_notify)
        self.assertEqual(first_state["backup_path"], second_state["backup_path"])
        self.assertEqual(self.read_notify().count("--previous-notify"), 0)
        self.assertEqual(
            json.loads(
                install.read_private_config(self.home / "bark-notify.conf")[
                    "PREVIOUS_NOTIFY_JSON"
                ]
            ),
            ["notify-tool"],
        )
        self.assertIsNotNone(first.backup_path)

    def test_existing_manual_bark_chain_is_adopted_without_duplication(self):
        notifier_path = self.home / "bark-notify.py"
        native = ["/Applications/Codex/SkyComputerUseClient", "turn-ended"]
        bark = [self.python, str(notifier_path)]
        existing = native + ["--previous-notify", json.dumps(bark)]
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(
            "notify = {}\n".format(install.serialize_notify(existing)),
            encoding="utf-8",
        )
        (self.home / "bark-notify.conf").write_text(
            "BARK_BASE_URL={}\nPREVIOUS_NOTIFY_JSON=\n".format(TEST_BARK_URL),
            encoding="utf-8",
        )

        result = self.install()

        self.assertEqual(result.action, "already-installed")
        self.assertEqual(self.read_notify().count("--previous-notify"), 1)
        state = json.loads(
            (self.home / "bark-notify-install-state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["original_notify"], native)

        uninstall.uninstall(self.home)
        self.assertEqual(self.read_notify(), native)

    def test_windows_paths_round_trip_as_single_line_toml(self):
        command = [
            r"C:\Program Files\Python311\python.exe",
            r"C:\Users\Melon Laptop\.codex\bark-notify.py",
        ]

        serialized = install.serialize_notify(command)
        parsed = install.read_notify_setting("notify = {}\n".format(serialized))

        self.assertNotIn("\n", serialized)
        self.assertEqual(parsed.command, command)

    def test_uninstall_restores_original_notify_assignment_exactly(self):
        original = (
            "# user config\n"
            "notify = [ 'notify tool', '--title', 'He said \"done\"' ] # keep me\n"
            'model = "gpt-5.6"\n'
        )
        self.home.mkdir(parents=True)
        (self.home / "config.toml").write_text(original, encoding="utf-8")

        self.install()
        uninstall.uninstall(self.home)

        self.assertEqual(
            (self.home / "config.toml").read_text(encoding="utf-8"), original
        )

    def test_uninstall_refuses_to_overwrite_a_manually_changed_notify(self):
        self.install()
        config_path = self.home / "config.toml"
        config_path.write_text('notify = ["different-tool"]\n', encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "changed since installation"):
            uninstall.uninstall(self.home)

        self.assertTrue((self.home / "bark-notify-install-state.json").exists())


if __name__ == "__main__":
    unittest.main()
