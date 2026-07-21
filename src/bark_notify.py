#!/usr/bin/env python3
"""Send one Bark push when Codex reports an agent-turn-complete event."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from http.client import HTTPException
from pathlib import Path, PureWindowsPath
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


EVENT_TYPE = "agent-turn-complete"
MAX_BARK_RESPONSE_BYTES = 64 * 1024
USER_THREAD_SOURCES = {"cli", "vscode", "exec", "mcp", "custom", "unknown"}
DEFAULT_TITLE = "codex叫你干活啦"
DEFAULT_ICON = (
    "https://wsrv.nl/?url=https%3A%2F%2Fraw.githubusercontent.com%2F"
    "yuriipalam%2Fcodex-status-bar%2Fmain%2FSources%2FCodexBar%2F"
    "Resources%2FcodexColorful.svg&output=png&fit=contain&w=512&h=512"
)
SCRIPT_PATH = Path(__file__).resolve()


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def config_path() -> Path:
    return codex_home() / "bark-notify.conf"


def log_path() -> Path:
    return codex_home() / "bark-notify.log"


def read_config(path: Optional[Path] = None) -> Dict[str, str]:
    source = path or config_path()
    config: Dict[str, str] = {}
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip()
    return config


def find_notification(arguments: List[str]) -> Optional[Tuple[dict, str]]:
    for argument in reversed(arguments):
        try:
            value = json.loads(argument)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value, argument
    return None


def _rollout_candidates(home: Path, thread_id: str) -> Iterable[Path]:
    pattern = "*{}*.jsonl".format(thread_id)
    sessions = home / "sessions"
    archived_sessions = home / "archived_sessions"
    try:
        if sessions.is_dir():
            yield from sessions.rglob(pattern)
        if archived_sessions.is_dir():
            yield from archived_sessions.glob(pattern)
    except OSError:
        return


def _session_metadata(home: Path, thread_id: str) -> Optional[dict]:
    for path in _rollout_candidates(home, thread_id):
        try:
            with path.open("r", encoding="utf-8") as handle:
                record = json.loads(handle.readline())
        except (OSError, json.JSONDecodeError):
            continue
        payload = record.get("payload") if isinstance(record, dict) else None
        if (
            record.get("type") == "session_meta"
            and isinstance(payload, dict)
            and payload.get("id") == thread_id
        ):
            return payload
    return None


def is_user_task(
    notification: dict,
    home: Optional[Path] = None,
) -> bool:
    if notification.get("codexnotes-test") is True:
        return True

    thread_id = str(notification.get("thread-id") or "").strip()
    if not thread_id:
        return False
    metadata = _session_metadata(home or codex_home(), thread_id)
    if metadata is None:
        return False

    thread_source = str(metadata.get("thread_source") or "").strip().lower()
    if thread_source:
        return thread_source == "user"
    source = metadata.get("source")
    return isinstance(source, str) and source.strip().lower() in USER_THREAD_SOURCES


def compact(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def project_name(cwd: str) -> str:
    if not cwd:
        return "当前项目"
    if re.match(r"^[A-Za-z]:[\\/]", cwd) or cwd.startswith("\\\\"):
        name = PureWindowsPath(cwd).name
    else:
        name = Path(cwd).name
    return name or cwd or "当前项目"


def build_message(notification: dict, config: Dict[str, str]) -> Tuple[str, str]:
    project = project_name(str(notification.get("cwd") or ""))
    summary = compact(str(notification.get("last-assistant-message") or ""))
    body = "项目「{}」已完成".format(project)
    if summary:
        body += "：{}".format(summary)
    return config.get("BARK_TITLE") or DEFAULT_TITLE, body


def build_bark_url(config: Dict[str, str], title: str, body: str) -> str:
    base_url = config["BARK_BASE_URL"].rstrip("/")
    params = {"icon": config.get("BARK_ICON") or DEFAULT_ICON}
    sound = config.get("BARK_SOUND")
    if sound:
        params["sound"] = sound
    return "{}/{}/{}?{}".format(
        base_url,
        quote(title, safe=""),
        quote(body, safe=""),
        urlencode(params),
    )


def log_error(message: str) -> None:
    destination = log_path()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
        if os.name != "nt":
            os.chmod(destination, 0o600)
    except OSError:
        pass


def send_bark(config: Dict[str, str], title: str, body: str) -> bool:
    request = Request(
        build_bark_url(config, title, body),
        headers={"User-Agent": "Codex-Bark-Notifier/1.0"},
    )
    try:
        with urlopen(request, timeout=float(config.get("BARK_TIMEOUT", "8"))) as response:
            payload = response.read(MAX_BARK_RESPONSE_BYTES + 1)
        if len(payload) > MAX_BARK_RESPONSE_BYTES:
            log_error("Bark delivery failed: response too large")
            return False
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            result = None
        if isinstance(result, dict) and result.get("code") not in (None, 200):
            log_error("Bark delivery failed: response rejected")
            return False
        return True
    except (OSError, URLError, HTTPException, ValueError) as error:
        log_error("Bark delivery failed: {}".format(type(error).__name__))
        return False


def _references_this_script(command: List[str]) -> bool:
    for argument in command:
        if not argument.lower().endswith(".py"):
            continue
        try:
            if Path(argument).expanduser().resolve() == SCRIPT_PATH:
                return True
        except OSError:
            continue
    return False


def run_previous_notifier(config: Dict[str, str], payload: str) -> None:
    raw_command = config.get("PREVIOUS_NOTIFY_JSON", "").strip()
    if not raw_command:
        return
    try:
        command = json.loads(raw_command)
    except json.JSONDecodeError:
        return
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
        or _references_this_script(command)
    ):
        return
    try:
        subprocess.run(
            command + [payload],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=float(config.get("PREVIOUS_NOTIFY_TIMEOUT", "10")),
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        log_error("Previous notifier failed: {}".format(type(error).__name__))


def main(arguments: List[str]) -> int:
    found = find_notification(arguments)
    if found is None:
        return 0
    notification, raw_payload = found
    test_delivery_failed = False
    try:
        config = read_config()
        if (
            notification.get("type") == EVENT_TYPE
            and is_user_task(notification)
            and config.get("BARK_BASE_URL")
        ):
            title, body = build_message(notification, config)
            delivered = send_bark(config, title, body)
            test_delivery_failed = (
                notification.get("codexnotes-test") is True and not delivered
            )
        run_previous_notifier(config, raw_payload)
    except (OSError, KeyError, ValueError) as error:
        log_error("Notifier setup failed: {}".format(type(error).__name__))
        test_delivery_failed = notification.get("codexnotes-test") is True
    return 1 if test_delivery_failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
