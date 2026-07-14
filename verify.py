#!/usr/bin/env python3
"""Verify a Codex Bark installation; network delivery is opt-in."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import install as installer


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    checks: List[str]
    errors: List[str]
    sent_test: bool


def _normalized_path(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").lower()


def _bark_commands(
    command: Sequence[str], notifier_path: Path, depth: int = 0
) -> List[List[str]]:
    if depth > 4:
        return []
    target = _normalized_path(str(notifier_path))
    reference_count = sum(_normalized_path(item) == target for item in command)
    if reference_count:
        return [list(command) for _ in range(reference_count)]
    if installer._is_native_desktop(command):
        try:
            _, previous = installer._split_native_previous(command)
        except ValueError:
            return []
        if previous:
            return _bark_commands(previous, notifier_path, depth + 1)
    return []


def _private_permissions_are_restricted(path: Path) -> bool:
    if os.name == "nt":
        return True
    return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def verify(codex_home: Path, send_test: bool = False) -> VerificationResult:
    codex_home = Path(codex_home).expanduser()
    checks: List[str] = []
    errors: List[str] = []
    sent_test = False
    config_path = codex_home / installer.CONFIG_NAME
    notifier_path = codex_home / installer.NOTIFIER_NAME
    private_path = codex_home / installer.PRIVATE_CONFIG_NAME
    state_path = codex_home / installer.STATE_NAME

    if sys.version_info < (3, 9):
        errors.append("Python 3.9 or newer is required")
    else:
        checks.append("Python version is supported")

    required = [config_path, notifier_path, private_path, state_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        errors.append("missing installed files: {}".format(", ".join(missing)))
        return VerificationResult(False, checks, errors, sent_test)
    checks.append("installed files are present")

    try:
        state = installer._read_state(state_path)
    except RuntimeError as error:
        errors.append(str(error))
        return VerificationResult(False, checks, errors, sent_test)
    checks.append("install state is readable")

    private_config = installer.read_private_config(private_path)
    bark_base_url = private_config.get("BARK_BASE_URL", "")
    if not bark_base_url:
        errors.append("BARK_BASE_URL is blank in the private configuration")
    else:
        try:
            installer._validate_bark_url(bark_base_url)
        except ValueError as error:
            errors.append(str(error))
        else:
            checks.append("private Bark URL is configured")

    try:
        setting = installer.read_notify_setting(
            config_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        errors.append("config.toml notify chain is unreadable: {}".format(error))
        setting = installer.NotifySetting(False, None)
    installed_notify = state.get("installed_notify")
    if not setting.present or setting.command != installed_notify:
        errors.append("config.toml notify chain changed after installation")
    else:
        checks.append("config.toml notify chain matches install state")

    bark_commands = (
        _bark_commands(setting.command, notifier_path) if setting.command else []
    )
    if len(bark_commands) != 1:
        errors.append(
            "notify chain must contain exactly one Bark command; found {}".format(
                len(bark_commands)
            )
        )
    else:
        checks.append("notify chain contains exactly one Bark command")

    if notifier_path.read_bytes() != installer.SOURCE_NOTIFIER.read_bytes():
        errors.append("installed Bark notifier differs from the repository version")
    else:
        checks.append("installed notifier matches the repository version")

    for private_file in (private_path, state_path):
        if not _private_permissions_are_restricted(private_file):
            errors.append("private file permissions are too broad: {}".format(private_file))
    if not any("permissions" in error for error in errors):
        checks.append("private file permissions are restricted")

    if send_test and not errors:
        payload = json.dumps(
            {
                "type": "agent-turn-complete",
                "cwd": str(Path.cwd()),
                "last-assistant-message": "Bark 跨平台通知测试成功。",
            },
            ensure_ascii=False,
        )
        try:
            completed = subprocess.run(
                bark_commands[0] + [payload],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            errors.append("test push command failed: {}".format(type(error).__name__))
        else:
            if completed.returncode != 0:
                errors.append(
                    "test push command exited with code {}".format(completed.returncode)
                )
            else:
                sent_test = True
                checks.append("test push command completed")

    return VerificationResult(not errors, checks, errors, sent_test)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", help="Codex home (default: CODEX_HOME or ~/.codex)")
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="send one real Bark test push after offline checks pass",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    result = verify(
        installer.resolve_codex_home(arguments.codex_home), arguments.send_test
    )
    for check in result.checks:
        print("OK: {}".format(check))
    for error in result.errors:
        print("ERROR: {}".format(error), file=sys.stderr)
    if result.ok and not arguments.send_test:
        print("Offline verification passed. No Bark push was sent.")
    elif result.ok and result.sent_test:
        print("Verification passed and one Bark test push was requested.")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
