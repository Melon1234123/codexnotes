#!/usr/bin/env python3
"""Install the Codex Bark notifier without storing a Bark key in Git."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
SOURCE_NOTIFIER = ROOT / "src" / "bark_notify.py"
CONFIG_NAME = "config.toml"
NOTIFIER_NAME = "bark-notify.py"
PRIVATE_CONFIG_NAME = "bark-notify.conf"
STATE_NAME = "bark-notify-install-state.json"
DEFAULT_TITLE = "codex叫你干活啦"
DEFAULT_ICON = (
    "https://wsrv.nl/?url=https%3A%2F%2Fraw.githubusercontent.com%2F"
    "yuriipalam%2Fcodex-status-bar%2Fmain%2FSources%2FCodexBar%2F"
    "Resources%2FcodexColorful.svg&output=png&fit=contain&w=512&h=512"
)


@dataclass(frozen=True)
class NotifySetting:
    present: bool
    command: Optional[List[str]]
    start: int = 0
    end: int = 0
    raw_assignment: Optional[str] = None


@dataclass(frozen=True)
class InstallResult:
    action: str
    codex_home: Path
    backup_path: Optional[Path]
    notify: List[str]
    message: str


def resolve_codex_home(value: Optional[str] = None) -> Path:
    configured = value or os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def serialize_notify(command: Sequence[str]) -> str:
    if not command or not all(isinstance(item, str) and item for item in command):
        raise ValueError("notify must be a non-empty array of non-empty strings")
    return json.dumps(list(command), ensure_ascii=False, separators=(", ", ": "))


def _table_offset(text: str) -> int:
    offset = 0
    table_pattern = re.compile(r"^\s*\[\[?\s*[A-Za-z0-9_'\"-]")
    for line in text.splitlines(keepends=True):
        if table_pattern.match(line):
            return offset
        offset += len(line)
    return len(text)


def _array_end(text: str, start: int) -> int:
    position = start
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text) or text[position] != "[":
        raise ValueError("top-level notify must be a TOML array")

    depth = 0
    quote = ""
    escaped = False
    comment = False
    while position < len(text):
        character = text[position]
        if comment:
            if character in "\r\n":
                comment = False
        elif quote:
            if quote == '"' and escaped:
                escaped = False
            elif quote == '"' and character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
        elif character in "'\"":
            quote = character
        elif character == "#":
            comment = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return position + 1
        position += 1
    raise ValueError("unterminated top-level notify array")


def _decode_basic_string(value: str, position: int) -> Tuple[str, int]:
    output: List[str] = []
    position += 1
    escapes = {
        "b": "\b",
        "t": "\t",
        "n": "\n",
        "f": "\f",
        "r": "\r",
        '"': '"',
        "\\": "\\",
    }
    while position < len(value):
        character = value[position]
        if character == '"':
            return "".join(output), position + 1
        if character in "\r\n":
            raise ValueError("multiline notify strings are not supported")
        if character != "\\":
            output.append(character)
            position += 1
            continue
        position += 1
        if position >= len(value):
            raise ValueError("unterminated escape in notify string")
        escape = value[position]
        if escape in escapes:
            output.append(escapes[escape])
            position += 1
            continue
        if escape in ("u", "U"):
            width = 4 if escape == "u" else 8
            digits = value[position + 1 : position + 1 + width]
            if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                raise ValueError("invalid Unicode escape in notify string")
            output.append(chr(int(digits, 16)))
            position += width + 1
            continue
        raise ValueError("unsupported escape in notify string")
    raise ValueError("unterminated notify string")


def _decode_literal_string(value: str, position: int) -> Tuple[str, int]:
    end = value.find("'", position + 1)
    if end == -1:
        raise ValueError("unterminated literal notify string")
    if "\n" in value[position + 1 : end] or "\r" in value[position + 1 : end]:
        raise ValueError("multiline notify strings are not supported")
    return value[position + 1 : end], end + 1


def _skip_space_and_comments(value: str, position: int) -> int:
    while position < len(value):
        if value[position].isspace():
            position += 1
        elif value[position] == "#":
            newline = value.find("\n", position)
            position = len(value) if newline == -1 else newline + 1
        else:
            break
    return position


def parse_notify_array(value: str) -> List[str]:
    position = _skip_space_and_comments(value, 0)
    if position >= len(value) or value[position] != "[":
        raise ValueError("notify must start with '['")
    position += 1
    command: List[str] = []
    while True:
        position = _skip_space_and_comments(value, position)
        if position >= len(value):
            raise ValueError("unterminated notify array")
        if value[position] == "]":
            position = _skip_space_and_comments(value, position + 1)
            if position != len(value):
                raise ValueError("unexpected content after notify array")
            return command
        if value[position] == '"':
            item, position = _decode_basic_string(value, position)
        elif value[position] == "'":
            item, position = _decode_literal_string(value, position)
        else:
            raise ValueError("notify entries must be TOML strings")
        if not item:
            raise ValueError("notify entries must not be empty")
        command.append(item)
        position = _skip_space_and_comments(value, position)
        if position < len(value) and value[position] == ",":
            position += 1
            continue
        if position < len(value) and value[position] == "]":
            continue
        raise ValueError("notify entries must be separated by commas")


def read_notify_setting(text: str) -> NotifySetting:
    table_offset = _table_offset(text)
    key_pattern = re.compile(r"^\s*notify\s*=", re.MULTILINE)
    matches = [match for match in key_pattern.finditer(text, 0, table_offset)]
    if not matches:
        return NotifySetting(False, None)
    if len(matches) > 1:
        raise ValueError("config.toml contains multiple top-level notify values")

    match = matches[0]
    line_start = text.rfind("\n", 0, match.start()) + 1
    value_start = text.find("=", match.start(), match.end()) + 1
    array_end = _array_end(text, value_start)
    line_end = text.find("\n", array_end)
    line_end = len(text) if line_end == -1 else line_end + 1
    trailing = text[array_end:line_end].strip()
    if trailing and not trailing.startswith("#"):
        raise ValueError("unexpected content after top-level notify array")
    command = parse_notify_array(text[value_start:array_end])
    return NotifySetting(
        True,
        command,
        line_start,
        line_end,
        text[line_start:line_end],
    )


def replace_notify(
    text: str,
    command: Optional[Sequence[str]],
    raw_assignment: Optional[str] = None,
) -> str:
    setting = read_notify_setting(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    if raw_assignment is not None:
        replacement = raw_assignment
    elif command is None:
        replacement = ""
    else:
        replacement = "notify = {}{}".format(serialize_notify(command), newline)

    if setting.present:
        return text[: setting.start] + replacement + text[setting.end :]
    if command is None and raw_assignment is None:
        return text

    offset = _table_offset(text)
    before = text[:offset]
    if before and not before.endswith(("\n", "\r")):
        before += newline
    return before + replacement + text[offset:]


def read_private_config(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    config: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip()
    return config


def _private_config_text(
    existing: Dict[str, str], bark_base_url: str, previous_notify: Optional[List[str]]
) -> str:
    values = {
        "BARK_BASE_URL": bark_base_url,
        "BARK_TITLE": existing.get("BARK_TITLE") or DEFAULT_TITLE,
        "BARK_ICON": existing.get("BARK_ICON") or DEFAULT_ICON,
        "BARK_SOUND": existing.get("BARK_SOUND") or "minuet",
        "BARK_TIMEOUT": existing.get("BARK_TIMEOUT") or "8",
        "PREVIOUS_NOTIFY_JSON": (
            json.dumps(previous_notify, ensure_ascii=False, separators=(",", ":"))
            if previous_notify
            else ""
        ),
        "PREVIOUS_NOTIFY_TIMEOUT": existing.get("PREVIOUS_NOTIFY_TIMEOUT") or "10",
    }
    return "".join("{}={}\n".format(key, value) for key, value in values.items())


def _atomic_write(path: Path, data: bytes, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None and os.name != "nt":
            os.chmod(temporary_path, mode)
        os.replace(str(temporary_path), str(path))
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path: Path, text: str, mode: Optional[int] = None) -> None:
    _atomic_write(path, text.encode("utf-8"), mode)


def _backup_config(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name("{}.bak-bark-{}".format(path.name, timestamp))
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(
            "{}.bak-bark-{}-{}".format(path.name, timestamp, suffix)
        )
        suffix += 1
    shutil.copy2(str(path), str(candidate))
    return candidate


def _is_native_desktop(command: Sequence[str]) -> bool:
    if len(command) < 2 or command[1] != "turn-ended":
        return False
    executable = command[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    return executable in ("skycomputeruseclient", "skycomputeruseclient.exe")


def _split_native_previous(command: Sequence[str]) -> Tuple[List[str], Optional[List[str]]]:
    command = list(command)
    indexes = [index for index, item in enumerate(command) if item == "--previous-notify"]
    if not indexes:
        return command, None
    if len(indexes) != 1 or indexes[0] + 1 >= len(command):
        raise ValueError("desktop notify has an invalid --previous-notify value")
    index = indexes[0]
    try:
        previous = json.loads(command[index + 1])
    except json.JSONDecodeError as error:
        raise ValueError("desktop --previous-notify is not valid JSON") from error
    if not isinstance(previous, list) or not all(
        isinstance(item, str) and item for item in previous
    ):
        raise ValueError("desktop --previous-notify must contain a command array")
    return command[:index] + command[index + 2 :], previous


def _references_notifier(command: Sequence[str], notifier_path: Path) -> bool:
    target = str(notifier_path).replace("\\", "/").lower()
    for item in command:
        if item.replace("\\", "/").lower() == target:
            return True
    if _is_native_desktop(command):
        _, previous = _split_native_previous(command)
        return bool(previous and _references_notifier(previous, notifier_path))
    return False


def _stored_previous(private_path: Path) -> Optional[List[str]]:
    raw = read_private_config(private_path).get("PREVIOUS_NOTIFY_JSON", "")
    if not raw:
        return None
    try:
        command = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(command, list) and all(isinstance(item, str) and item for item in command):
        return command
    return None


def _infer_original_from_existing(
    current: List[str], notifier_path: Path, private_path: Path
) -> Tuple[bool, Optional[List[str]]]:
    previous_before_bark = _stored_previous(private_path)
    if _is_native_desktop(current):
        native, previous = _split_native_previous(current)
        if previous and _references_notifier(previous, notifier_path):
            if previous_before_bark:
                return True, native + [
                    "--previous-notify",
                    json.dumps(previous_before_bark, ensure_ascii=False, separators=(",", ":")),
                ]
            return True, native
    if _references_notifier(current, notifier_path):
        return (previous_before_bark is not None), previous_before_bark
    return True, current


def _build_chain(
    original_present: bool,
    original_notify: Optional[List[str]],
    bark_command: List[str],
) -> Tuple[List[str], Optional[List[str]]]:
    if not original_present or not original_notify:
        return bark_command, None
    if _is_native_desktop(original_notify):
        native, previous = _split_native_previous(original_notify)
        return (
            native
            + [
                "--previous-notify",
                json.dumps(bark_command, ensure_ascii=False, separators=(",", ":")),
            ],
            previous,
        )
    return bark_command, list(original_notify)


def _read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("installed state is unreadable") from error
    if state.get("version") != 1:
        raise RuntimeError("installed state version is unsupported")
    return state


def _validate_bark_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if "\n" in value or "\r" in value or parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Bark base URL must be a complete http(s) device URL")
    return value


def install(
    codex_home: Path,
    bark_base_url: str,
    python_executable: str,
    repair: bool = False,
) -> InstallResult:
    codex_home = Path(codex_home).expanduser()
    bark_base_url = _validate_bark_url(bark_base_url)
    if not python_executable:
        raise ValueError("python executable must not be empty")
    if not SOURCE_NOTIFIER.is_file():
        raise RuntimeError("repository notifier source is missing")

    codex_home.mkdir(parents=True, exist_ok=True)
    config_path = codex_home / CONFIG_NAME
    notifier_path = codex_home / NOTIFIER_NAME
    private_path = codex_home / PRIVATE_CONFIG_NAME
    state_path = codex_home / STATE_NAME
    config_existed = config_path.exists()
    config_text = config_path.read_text(encoding="utf-8") if config_existed else ""
    current = read_notify_setting(config_text)
    bark_command = [python_executable, str(notifier_path)]
    action = "installed"

    if state_path.exists():
        state = _read_state(state_path)
        notify_changed = (
            not current.present or current.command != state.get("installed_notify")
        )
        if notify_changed and not repair:
            raise RuntimeError("notify changed since installation; refusing to overwrite it")
        original_present = bool(state.get("original_notify_present"))
        original_notify = state.get("original_notify")
        original_assignment = state.get("original_notify_assignment")
        original_config_existed = bool(state.get("original_config_existed"))
        backup_raw = state.get("backup_path")
        backup_path = Path(backup_raw) if backup_raw else None
        action = "repaired" if notify_changed else "already-installed"
    else:
        original_config_existed = config_existed
        backup_path = _backup_config(config_path)
        if current.present and current.command is not None and _references_notifier(
            current.command, notifier_path
        ):
            original_present, original_notify = _infer_original_from_existing(
                current.command, notifier_path, private_path
            )
            original_assignment = None
            action = "already-installed"
        else:
            original_present = current.present
            original_notify = current.command
            original_assignment = current.raw_assignment

    if original_notify is not None and (
        not isinstance(original_notify, list)
        or not all(isinstance(item, str) and item for item in original_notify)
    ):
        raise RuntimeError("installed state contains an invalid original notify value")
    installed_notify, previous_notify = _build_chain(
        original_present, original_notify, bark_command
    )

    existing_private = read_private_config(private_path)
    _atomic_write(notifier_path, SOURCE_NOTIFIER.read_bytes(), 0o700)
    atomic_write_text(
        private_path,
        _private_config_text(existing_private, bark_base_url, previous_notify),
        0o600,
    )
    config_mode = config_path.stat().st_mode & 0o777 if config_path.exists() else 0o600
    atomic_write_text(
        config_path,
        replace_notify(config_text, installed_notify),
        config_mode,
    )
    state = {
        "version": 1,
        "original_config_existed": original_config_existed,
        "original_notify_present": original_present,
        "original_notify": original_notify,
        "original_notify_assignment": original_assignment,
        "installed_notify": installed_notify,
        "backup_path": str(backup_path) if backup_path else None,
    }
    atomic_write_text(
        state_path,
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        0o600,
    )
    action_message = {
        "already-installed": "already configured",
        "repaired": "repaired",
        "installed": "installed",
    }[action]
    message = "Bark notifications {} in {}".format(action_message, codex_home)
    return InstallResult(action, codex_home, backup_path, installed_notify, message)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", help="Codex home (default: CODEX_HOME or ~/.codex)")
    parser.add_argument("--bark-base-url", help="Bark device URL; omitted value is read securely")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="restore the recorded notify chain after an external config change",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is required.", file=sys.stderr)
        return 2
    arguments = _arguments()
    codex_home = resolve_codex_home(arguments.codex_home)
    bark_base_url = arguments.bark_base_url or os.environ.get("BARK_BASE_URL")
    if not bark_base_url:
        bark_base_url = read_private_config(codex_home / PRIVATE_CONFIG_NAME).get(
            "BARK_BASE_URL"
        )
    if not bark_base_url:
        bark_base_url = getpass.getpass("Bark device URL (input hidden): ")
    try:
        result = install(
            codex_home,
            bark_base_url,
            arguments.python_executable,
            repair=arguments.repair,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print("Install failed: {}".format(error), file=sys.stderr)
        return 1
    print(result.message)
    if result.backup_path:
        print("Original config backup: {}".format(result.backup_path))
    print("Run verify.py to perform offline verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
