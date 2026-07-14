#!/usr/bin/env python3
"""Uninstall the Codex Bark notifier and restore the previous notify value."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import install as installer


@dataclass(frozen=True)
class UninstallResult:
    action: str
    codex_home: Path
    message: str


def uninstall(codex_home: Path, keep_config: bool = False) -> UninstallResult:
    codex_home = Path(codex_home).expanduser()
    state_path = codex_home / installer.STATE_NAME
    if not state_path.exists():
        return UninstallResult(
            "not-installed", codex_home, "Bark notifications are not installed"
        )

    state = installer._read_state(state_path)
    config_path = codex_home / installer.CONFIG_NAME
    if not config_path.exists():
        raise RuntimeError("config.toml changed since installation; refusing to overwrite it")
    config_text = config_path.read_text(encoding="utf-8")
    current = installer.read_notify_setting(config_text)
    if not current.present or current.command != state.get("installed_notify"):
        raise RuntimeError("notify changed since installation; refusing to overwrite it")

    original_present = bool(state.get("original_notify_present"))
    original_notify = state.get("original_notify") if original_present else None
    raw_assignment = state.get("original_notify_assignment") if original_present else None
    restored = installer.replace_notify(config_text, original_notify, raw_assignment)
    if not state.get("original_config_existed") and not restored.strip():
        config_path.unlink()
    else:
        mode = config_path.stat().st_mode & 0o777
        installer.atomic_write_text(config_path, restored, mode)

    (codex_home / installer.NOTIFIER_NAME).unlink(missing_ok=True)
    if not keep_config:
        (codex_home / installer.PRIVATE_CONFIG_NAME).unlink(missing_ok=True)
    state_path.unlink()
    message = "Bark notifications uninstalled from {}".format(codex_home)
    return UninstallResult("uninstalled", codex_home, message)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", help="Codex home (default: CODEX_HOME or ~/.codex)")
    parser.add_argument(
        "--keep-config",
        action="store_true",
        help="keep the private Bark configuration file",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        result = uninstall(
            installer.resolve_codex_home(arguments.codex_home), arguments.keep_config
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print("Uninstall failed: {}".format(error), file=sys.stderr)
        return 1
    print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
