import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from src import bark_notify


class BarkNotifyTests(unittest.TestCase):
    def setUp(self):
        self.completion = {
            "type": "agent-turn-complete",
            "cwd": "/Users/melon/projects/demo",
            "last-assistant-message": "实现和测试均已完成。",
        }
        self.config = {
            "BARK_BASE_URL": "https://example.invalid/device",
            "BARK_TITLE": "codex叫你干活啦",
            "BARK_ICON": "https://example.com/codex.png",
            "BARK_SOUND": "minuet",
            "BARK_TIMEOUT": "8",
            "PREVIOUS_NOTIFY_JSON": "",
        }

    def test_completion_sends_exactly_one_bark(self):
        payload = json.dumps(self.completion, ensure_ascii=False)
        with (
            mock.patch.object(bark_notify, "read_config", return_value=self.config),
            mock.patch.object(bark_notify, "is_user_task", return_value=True),
            mock.patch.object(bark_notify, "send_bark") as send_bark,
            mock.patch.object(bark_notify, "run_previous_notifier") as run_previous,
        ):
            self.assertEqual(bark_notify.main([payload]), 0)

        send_bark.assert_called_once()
        run_previous.assert_called_once_with(self.config, payload)

    def test_non_completion_does_not_send_bark(self):
        payload = json.dumps(
            {"type": "approval-requested", "cwd": "/tmp/demo"},
            ensure_ascii=False,
        )
        with (
            mock.patch.object(bark_notify, "read_config", return_value=self.config),
            mock.patch.object(bark_notify, "send_bark") as send_bark,
            mock.patch.object(bark_notify, "run_previous_notifier") as run_previous,
        ):
            self.assertEqual(bark_notify.main([payload]), 0)

        send_bark.assert_not_called()
        run_previous.assert_called_once_with(self.config, payload)

    def test_subagent_completion_does_not_send_bark(self):
        payload = json.dumps(self.completion, ensure_ascii=False)
        with (
            mock.patch.object(bark_notify, "read_config", return_value=self.config),
            mock.patch.object(bark_notify, "is_user_task", return_value=False),
            mock.patch.object(bark_notify, "send_bark") as send_bark,
            mock.patch.object(bark_notify, "run_previous_notifier") as run_previous,
        ):
            self.assertEqual(bark_notify.main([payload]), 0)

        send_bark.assert_not_called()
        run_previous.assert_called_once_with(self.config, payload)

    def test_session_metadata_distinguishes_subagent_from_user_thread(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            sessions = home / "sessions" / "2026" / "07" / "14"
            sessions.mkdir(parents=True)
            child_id = "019f6082-59b7-7053-b8c1-69a83824a95e"
            root_id = "019f5fab-8b43-7f10-9146-ce55652d1616"
            child_meta = {
                "type": "session_meta",
                "payload": {
                    "id": child_id,
                    "thread_source": "subagent",
                    "source": {
                        "subagent": {
                            "thread_spawn": {"parent_thread_id": root_id, "depth": 1}
                        }
                    },
                },
            }
            root_meta = {
                "type": "session_meta",
                "payload": {
                    "id": root_id,
                    "thread_source": "user",
                    "source": "vscode",
                },
            }
            (sessions / ("rollout-child-" + child_id + ".jsonl")).write_text(
                json.dumps(child_meta) + "\n", encoding="utf-8"
            )
            (sessions / ("rollout-root-" + root_id + ".jsonl")).write_text(
                json.dumps(root_meta) + "\n", encoding="utf-8"
            )

            self.assertFalse(
                bark_notify.is_user_task(
                    {"thread-id": child_id}, home=home
                )
            )
            self.assertTrue(
                bark_notify.is_user_task(
                    {"thread-id": root_id}, home=home
                )
            )

    def test_missing_metadata_is_not_whitelisted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            home = Path(temporary_directory)
            self.assertFalse(
                bark_notify.is_user_task(
                    {"thread-id": "child-thread"},
                    home=home,
                )
            )
            self.assertFalse(
                bark_notify.is_user_task(
                    {"thread-id": "root-thread"},
                    home=home,
                )
            )

    def test_internal_ambient_classifier_completion_does_not_send_bark(self):
        notification = {
            "type": "agent-turn-complete",
            "thread-id": "019f6459-0c04-71c3-a44a-ae961b32cac3",
            "cwd": "/",
            "last-assistant-message": '{"exclude":[]}',
        }
        payload = json.dumps(notification)
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                mock.patch.object(bark_notify, "codex_home", return_value=Path(temporary_directory)),
                mock.patch.dict(bark_notify.os.environ, {}, clear=True),
                mock.patch.object(bark_notify, "read_config", return_value=self.config),
                mock.patch.object(bark_notify, "send_bark") as send_bark,
                mock.patch.object(bark_notify, "run_previous_notifier") as run_previous,
            ):
                self.assertEqual(bark_notify.main([payload]), 0)

        send_bark.assert_not_called()
        run_previous.assert_called_once_with(self.config, payload)

    def test_explicit_verification_payload_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            self.assertTrue(
                bark_notify.is_user_task(
                    {
                        "type": "agent-turn-complete",
                        "codexnotes-test": True,
                    },
                    home=Path(temporary_directory),
                )
            )

    def test_project_name_handles_macos_and_windows_paths(self):
        self.assertEqual(bark_notify.project_name("/Users/melon/projects/demo"), "demo")
        self.assertEqual(bark_notify.project_name(r"C:\Users\melon\projects\demo"), "demo")
        self.assertEqual(
            bark_notify.project_name(r"C:\Users\Melon Laptop\Codex Projects\demo app"),
            "demo app",
        )
        self.assertEqual(bark_notify.project_name(""), "当前项目")

    def test_summary_is_limited_to_220_characters(self):
        summary = bark_notify.compact("x" * 300)
        self.assertEqual(len(summary), 220)
        self.assertTrue(summary.endswith("..."))

    def test_message_contains_project_and_compact_summary(self):
        title, body = bark_notify.build_message(self.completion, self.config)
        self.assertEqual(title, "codex叫你干活啦")
        self.assertIn("项目「demo」已完成", body)
        self.assertIn("实现和测试均已完成。", body)

    def test_bark_url_encodes_icon_sound_and_chinese_text(self):
        url = bark_notify.build_bark_url(self.config, "codex叫你干活啦", "项目已完成")
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        self.assertEqual(params["icon"], ["https://example.com/codex.png"])
        self.assertEqual(params["sound"], ["minuet"])
        self.assertIn("%E9%A1%B9%E7%9B%AE", parsed.path)

    def test_previous_notifier_runs_once_with_original_payload(self):
        payload = json.dumps(self.completion, ensure_ascii=False)
        config = dict(self.config)
        config["PREVIOUS_NOTIFY_JSON"] = json.dumps(["notify-tool", "--done"])
        with mock.patch.object(bark_notify.subprocess, "run") as run:
            bark_notify.run_previous_notifier(config, payload)

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["notify-tool", "--done", payload])

    def test_invalid_or_self_referencing_previous_notifier_is_ignored(self):
        payload = json.dumps(self.completion)
        for value in ("not-json", json.dumps(["python", str(bark_notify.SCRIPT_PATH)])):
            config = dict(self.config)
            config["PREVIOUS_NOTIFY_JSON"] = value
            with mock.patch.object(bark_notify.subprocess, "run") as run:
                bark_notify.run_previous_notifier(config, payload)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
