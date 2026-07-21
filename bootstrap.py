#!/usr/bin/env python3
"""Install and verify Codex Bark notifications in one explicit operation."""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

import install
import verify


KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class BootstrapResult:
    install_result: install.InstallResult
    offline_result: verify.VerificationResult
    test_result: Optional[verify.VerificationResult]

    @property
    def sent_test(self) -> bool:
        return bool(self.test_result and self.test_result.sent_test)


def normalize_bark_key(value: str) -> str:
    key = value.strip()
    if not key or not KEY_PATTERN.fullmatch(key):
        raise ValueError(
            "Bark key must contain only letters, digits, underscores, or hyphens"
        )
    return "https://api.day.app/" + key


def resolve_bark_url(
    environ: Optional[Mapping[str, str]] = None,
    prompt: Callable[[str], str] = getpass.getpass,
) -> str:
    values = os.environ if environ is None else environ
    key = values.get("BARK_KEY", "").strip()
    base_url = values.get("BARK_BASE_URL", "").strip()
    if key and base_url:
        raise ValueError("Set only one of BARK_KEY or BARK_BASE_URL")
    if key:
        return normalize_bark_key(key)
    if base_url:
        return install._validate_bark_url(base_url)
    hidden = prompt("Bark key or device URL (input hidden): ").strip()
    if hidden.startswith(("http://", "https://")):
        return install._validate_bark_url(hidden)
    return normalize_bark_key(hidden)


def _verification_error(
    label: str, result: verify.VerificationResult
) -> RuntimeError:
    details = "; ".join(result.errors) or "unknown verification error"
    return RuntimeError("{}: {}".format(label, details))


def run_bootstrap(
    codex_home: Path,
    bark_url: str,
    send_test: bool = False,
    repair: bool = False,
    install_fn=install.install,
    verify_fn=verify.verify,
    python_executable: str = sys.executable,
) -> BootstrapResult:
    installed = install_fn(
        codex_home, bark_url, python_executable, repair=repair
    )
    offline = verify_fn(codex_home, send_test=False)
    if not offline.ok:
        raise _verification_error("offline verification failed", offline)
    tested = None
    if send_test:
        tested = verify_fn(codex_home, send_test=True)
        if not tested.ok or not tested.sent_test:
            raise _verification_error("test delivery failed", tested)
    return BootstrapResult(installed, offline, tested)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home")
    parser.add_argument("--send-test", action="store_true")
    parser.add_argument("--repair", action="store_true")
    return parser.parse_args()


def main() -> int:
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is required.", file=sys.stderr)
        return 2
    arguments = _arguments()
    try:
        bark_url = resolve_bark_url()
        codex_home = install.resolve_codex_home(arguments.codex_home)
        result = run_bootstrap(
            codex_home,
            bark_url,
            send_test=arguments.send_test,
            repair=arguments.repair,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print("Bootstrap failed: {}".format(error), file=sys.stderr)
        return 1
    print(result.install_result.message)
    print("Offline verification passed.")
    if result.sent_test:
        print("One Bark test push was delivered successfully.")
    print("Fully restart Codex before testing task-completion notifications.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
