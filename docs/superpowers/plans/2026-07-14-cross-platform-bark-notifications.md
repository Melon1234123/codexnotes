# Cross-Platform Bark Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secret-free, dependency-free package that installs the Codex-to-Bark completion notification flow reproducibly on macOS and Windows.

**Architecture:** A Python notifier consumes Codex's JSON completion payload. A cross-platform installer copies it into the user's Codex home, safely updates the top-level `notify` array, preserves an existing notifier, and records rollback state; verification and uninstall commands complete the lifecycle.

**Tech Stack:** Python 3.9+ standard library, TOML-compatible JSON string arrays, `unittest`, Markdown.

## Global Constraints

- Never commit a Bark key or complete device URL.
- Use no third-party runtime or test dependency.
- Support macOS and Windows paths, including spaces and backslashes.
- Send Bark only for root `agent-turn-complete` events; suppress subagent completions and never send during default verification.
- Preserve an existing notifier exactly once and make repeated installation idempotent.
- Write only under the repository and the explicitly selected Codex home.

---

### Task 1: Notifier behavior

**Files:**
- Create: `tests/test_bark_notify.py`
- Create: `src/bark_notify.py`
- Create: `config/bark-notify.conf.example`

**Interfaces:**
- Consumes: one JSON payload argument and key/value configuration from `$CODEX_HOME/bark-notify.conf`.
- Produces: `main(arguments: list[str]) -> int`, one Bark request for `agent-turn-complete`, and an optional previous notifier invocation.

- [ ] Write tests asserting one Bark call for root `agent-turn-complete`, zero calls for `approval-requested` and subagent completion, correct macOS/Windows project names, a 220-character summary limit, encoded icon and `minuet`, and previous-notifier dispatch exactly once.
- [ ] Run `python3 -m unittest tests.test_bark_notify -v`; expect failures because `src.bark_notify` does not exist.
- [ ] Implement the notifier with Python standard-library modules only; resolve `thread-id` against rollout `session_meta`, fall back to `CODEX_THREAD_ID`, and do not add third-party dependencies.
- [ ] Re-run `python3 -m unittest tests.test_bark_notify -v`; expect all notifier tests to pass.

### Task 2: Idempotent installation and rollback

**Files:**
- Create: `tests/test_install.py`
- Create: `install.py`
- Create: `uninstall.py`

**Interfaces:**
- Produces: `install.install(codex_home: Path, bark_base_url: str, python_executable: str) -> InstallResult` and `uninstall.uninstall(codex_home: Path, keep_config: bool = False) -> UninstallResult`.
- Persists: `$CODEX_HOME/bark-notify-install-state.json` with the original notifier and backup path.

- [ ] Write tests for missing config, no notifier, native `SkyComputerUseClient turn-ended`, arbitrary notifier preservation, a second idempotent install, Windows path serialization, and exact uninstall restoration.
- [ ] Run `python3 -m unittest tests.test_install -v`; expect failures because installer functions do not exist.
- [ ] Implement safe top-level `notify` parsing, JSON-compatible TOML array serialization, atomic file replacement, timestamped backup, state persistence, and rollback.
- [ ] Re-run `python3 -m unittest tests.test_install -v`; expect all installer tests to pass.

### Task 3: Verification and reproducibility documentation

**Files:**
- Create: `verify.py`
- Create: `AGENTS.md`
- Replace: `README.md`

**Interfaces:**
- `verify.py` performs offline checks by default and sends a synthetic completion payload only with `--send-test`.
- `README.md` and `AGENTS.md` expose the same install, verify, test, and uninstall commands.

- [ ] Implement verifier checks for Python version, installed files, non-empty private URL, notify-chain membership, file permissions, and optional test delivery.
- [ ] Write exact macOS and Windows commands, Python prerequisite recovery, expected output, security rules, troubleshooting, and rollback steps.
- [ ] Run `python3 -m unittest discover -s tests -v`; expect all tests to pass.
- [ ] Run an integration install and uninstall against temporary Codex homes for direct, native, and arbitrary notifier scenarios; expect exact restoration.
- [ ] Run `rg -n 'https://api\.day\.app/[A-Za-z0-9_-]{10,}' .`; expect no matches.
- [ ] Run `python3 verify.py --codex-home /tmp/codexnotes-verify-home` against an installed fixture; expect offline verification to pass without a network request.

### Task 4: Publish

**Files:**
- Modify: none beyond prior tasks.

**Interfaces:**
- Produces: verified commits on `main` and a matching `origin/main`.

- [ ] Review `git diff --check`, `git status --short`, and the full changed-file list.
- [ ] Commit documentation and implementation with scoped commit messages.
- [ ] Push `main`; if HTTPS authentication is unavailable, verify SSH and switch `origin` to `git@github.com:Melon1234123/codexnotes.git`.
- [ ] Verify `git status --short --branch` reports `main...origin/main` with no ahead count.
