# One-Click Codex Bark Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one cross-platform command that installs, verifies, and optionally tests Codex Bark notifications when an agent receives only the repository URL and Bark key.

**Architecture:** Add a standard-library `bootstrap.py` orchestrator over the existing `install.install` and `verify.verify` APIs. Preserve the existing modules' ownership boundaries, make explicit test delivery report network/API rejection without changing runtime failure isolation, and document an agent contract that treats the copy-ready one-click prompt as authorization for installation plus one test push.

**Tech Stack:** Python 3.9+ standard library, `unittest`, Codex user-level `notify`, Bark HTTP API, GitHub

## Global Constraints

- Support Windows and macOS with the same Python entry point.
- Never print, log, commit, or quote a real Bark key or complete device URL.
- Accept a raw key through `BARK_KEY` or a complete URL through `BARK_BASE_URL`, but reject conflicting inputs.
- Run offline verification before any live test push.
- Require explicit `--send-test` and `--repair` flags for those actions.
- Preserve the default title `codex叫你干活啦`, colorful Codex icon, `minuet` sound, root-task filtering, previous notifier, and idempotent installation.
- Keep ordinary completion delivery failures non-fatal to Codex.

---

### Task 1: Make Explicit Test Delivery Observable

**Files:**
- Modify: `src/bark_notify.py:168-240`
- Test: `tests/test_bark_notify.py`

**Interfaces:**
- Consumes: Bark HTTP response bodies and the existing `codexnotes-test` payload marker.
- Produces: `send_bark(config, title, body) -> bool`; `main(arguments) -> 1` only when an explicit test payload cannot be delivered, while ordinary notifications still return 0.

- [ ] **Step 1: Add failing tests for Bark response status and explicit test failure**

Add tests that mock `urlopen` and `send_bark`:

```python
    def test_send_bark_reports_api_rejection(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"code":400,"message":"invalid"}'
        )
        with (
            mock.patch.object(bark_notify, "urlopen", return_value=response),
            mock.patch.object(bark_notify, "log_error") as log_error,
        ):
            delivered = bark_notify.send_bark(self.config, "title", "body")

        self.assertFalse(delivered)
        log_error.assert_called_once_with("Bark delivery failed: response rejected")

    def test_send_bark_accepts_success_response(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"code":200,"message":"success"}'
        )
        with mock.patch.object(bark_notify, "urlopen", return_value=response):
            self.assertTrue(bark_notify.send_bark(self.config, "title", "body"))

    def test_explicit_test_delivery_failure_returns_nonzero(self):
        notification = dict(self.completion, **{"codexnotes-test": True})
        payload = json.dumps(notification, ensure_ascii=False)
        with (
            mock.patch.object(bark_notify, "read_config", return_value=self.config),
            mock.patch.object(bark_notify, "is_user_task", return_value=True),
            mock.patch.object(bark_notify, "send_bark", return_value=False),
            mock.patch.object(bark_notify, "run_previous_notifier"),
        ):
            self.assertEqual(bark_notify.main([payload]), 1)

    def test_regular_delivery_failure_remains_nonfatal(self):
        payload = json.dumps(self.completion, ensure_ascii=False)
        with (
            mock.patch.object(bark_notify, "read_config", return_value=self.config),
            mock.patch.object(bark_notify, "is_user_task", return_value=True),
            mock.patch.object(bark_notify, "send_bark", return_value=False),
            mock.patch.object(bark_notify, "run_previous_notifier"),
        ):
            self.assertEqual(bark_notify.main([payload]), 0)
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```powershell
python -m unittest tests.test_bark_notify.BarkNotifyTests.test_send_bark_reports_api_rejection tests.test_bark_notify.BarkNotifyTests.test_send_bark_accepts_success_response tests.test_bark_notify.BarkNotifyTests.test_explicit_test_delivery_failure_returns_nonzero tests.test_bark_notify.BarkNotifyTests.test_regular_delivery_failure_remains_nonfatal -v
```

Expected: the response tests fail because `send_bark` returns `None`, and the explicit-test test fails because `main` returns 0.

- [ ] **Step 3: Return delivery status and propagate it only for explicit tests**

Replace `send_bark` and update `main` with this behavior:

```python
def send_bark(config: Dict[str, str], title: str, body: str) -> bool:
    request = Request(
        build_bark_url(config, title, body),
        headers={"User-Agent": "Codex-Bark-Notifier/1.0"},
    )
    try:
        with urlopen(request, timeout=float(config.get("BARK_TIMEOUT", "8"))) as response:
            payload = response.read()
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            result = None
        if isinstance(result, dict) and result.get("code") not in (None, 200):
            log_error("Bark delivery failed: response rejected")
            return False
        return True
    except (OSError, URLError, ValueError) as error:
        log_error("Bark delivery failed: {}".format(type(error).__name__))
        return False


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
```

- [ ] **Step 4: Run notifier and verifier tests**

Run:

```powershell
python -m unittest tests.test_bark_notify tests.test_verify -v
```

Expected: all notifier and verifier tests pass, including the existing rule that normal completion failures do not fail Codex.

- [ ] **Step 5: Commit the explicit-test behavior**

```powershell
git add src/bark_notify.py tests/test_bark_notify.py
git commit -m "fix: report Bark test delivery failures"
```

### Task 2: Add The Cross-Platform Bootstrap

**Files:**
- Create: `bootstrap.py`
- Create: `tests/test_bootstrap.py`

**Interfaces:**
- Consumes: `BARK_KEY`, `BARK_BASE_URL`, `--codex-home`, `--send-test`, and `--repair`.
- Produces: `normalize_bark_key(value: str) -> str`, `resolve_bark_url(environ, prompt) -> str`, `run_bootstrap(...) -> BootstrapResult`, and a secret-safe CLI exit status.

- [ ] **Step 1: Write failing unit tests for input normalization and orchestration**

Create `tests/test_bootstrap.py` with tests that:

```python
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
                {"BARK_KEY": key, "BARK_BASE_URL": "https://example.invalid/device"}
            )
        self.assertNotIn(key, str(raised.exception))

    def test_missing_environment_uses_hidden_prompt(self):
        prompt = mock.Mock(return_value="PromptKey_123")

        value = bootstrap.resolve_bark_url({}, prompt=prompt)

        self.assertEqual(value, "https://api.day.app/" + "PromptKey_123")
        prompt.assert_called_once_with("Bark key or device URL (input hidden): ")

    def test_invalid_key_is_rejected_without_echoing_it(self):
        key = "bad/key value"
        with self.assertRaises(ValueError) as raised:
            bootstrap.normalize_bark_key(key)
        self.assertNotIn(key, str(raised.exception))

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
```

- [ ] **Step 2: Run bootstrap tests and confirm the module is missing**

Run:

```powershell
python -m unittest tests.test_bootstrap -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bootstrap'`.

- [ ] **Step 3: Implement the bootstrap orchestrator**

Create `bootstrap.py` with these public units and CLI behavior:

```python
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
        raise ValueError("Bark key must contain only letters, digits, underscores, or hyphens")
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


def _verification_error(label: str, result: verify.VerificationResult) -> RuntimeError:
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
```

- [ ] **Step 4: Run bootstrap tests and full integration tests**

Run:

```powershell
python -m unittest tests.test_bootstrap -v
python -m unittest discover -s tests -v
```

Expected: all bootstrap tests and the complete suite pass.

- [ ] **Step 5: Commit the bootstrap**

```powershell
git add bootstrap.py tests/test_bootstrap.py
git commit -m "feat: add one-click Bark bootstrap"
```

### Task 3: Document The One-Click Agent Contract

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: repository URL plus either a raw Bark key or complete Bark URL supplied by the human.
- Produces: one copy-ready Chinese prompt and deterministic Windows/macOS agent procedures that require no repeated confirmation.

- [ ] **Step 1: Add the one-click README section**

Insert a section before manual installation that states:

````markdown
## 交给 Codex 一站式安装

把下面内容发给 Codex，并替换最后一行的 Key：

```text
请按仓库的一站式流程安装 Codex Bark 通知。
仓库：https://github.com/Melon1234123/codexnotes.git
Bark Key：在这里粘贴你的 Key
使用仓库默认配置，完成安装、离线验证并发送一次测试通知；除非失败或需要 repair，不要再向我确认。
```

这段请求授权 Codex 克隆或更新仓库、安装、离线验证并发送一次测试通知。成功后需要完全退出并重新打开 Codex；安装前已经启动的任务不会补发完成通知。
````

Document direct commands using placeholder environment values only:

```powershell
$secureKey = Read-Host "Bark Key" -AsSecureString
$env:BARK_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
python bootstrap.py --send-test
Remove-Item Env:BARK_KEY
$secureKey = $null
```

```bash
read -rs BARK_KEY && export BARK_KEY
python3 bootstrap.py --send-test
unset BARK_KEY
```

- [ ] **Step 2: Add the machine-readable one-click procedure to AGENTS.md**

Add a `One-click agent procedure` section that defines the prompt as authorization for clone/update, install, offline verify, and exactly one test push; requires `BARK_KEY` or `BARK_BASE_URL` child-process environment input; forbids repeated confirmation; and permits a new question only for `--repair` or an external blocker.

Add `bootstrap.py` to the implementation map and to byte-compilation validation:

```text
python3 -m py_compile bootstrap.py install.py uninstall.py verify.py src/bark_notify.py
```

- [ ] **Step 3: Run documentation and secret checks**

Run:

```powershell
rg -n "一站式流程|bootstrap.py --send-test|BARK_KEY|--repair" README.md AGENTS.md
rg -n 'https://api\.day\.app/[A-Za-z0-9_-]{10,}' .
git diff --check
```

Expected: the first command finds the documented protocol, the secret scan finds zero matches, and `git diff --check` exits 0.

- [ ] **Step 4: Commit the documentation**

```powershell
git add README.md AGENTS.md
git commit -m "docs: add one-click Codex install workflow"
```

### Task 4: Final Validation And Publication

**Files:**
- Verify: all tracked project files

**Interfaces:**
- Consumes: the completed feature branch.
- Produces: a pushed branch and draft pull request against `main`.

- [ ] **Step 1: Run the complete validation suite**

```powershell
python -m unittest discover -s tests -v
python -m py_compile bootstrap.py install.py uninstall.py verify.py src\bark_notify.py
git diff --check origin/main...HEAD
rg -n 'https://api\.day\.app/[A-Za-z0-9_-]{10,}' .
```

Expected: all tests pass, compilation and diff checks exit 0, and the secret scan returns no matches.

- [ ] **Step 2: Review the branch scope**

```powershell
git status --short --branch
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: the branch contains only the design, implementation plan, notifier test-status change, bootstrap, tests, README, and AGENTS updates.

- [ ] **Step 3: Push and open a draft PR**

Follow the repository publishing workflow to push `feat/one-click-bootstrap` and open a draft pull request targeting `main`. The PR must summarize the one-click agent interface, test-delivery observability, documentation, and validation results without including a Bark key or URL.
