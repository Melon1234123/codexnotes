# Reproduction Contract

This repository installs one user-level Codex `notify` integration that sends root task completions to Bark on macOS and Windows. Treat this file as the machine-readable execution contract.

## Non-negotiable invariants

- Never write or commit a real Bark key or complete device URL in this repository.
- `config/bark-notify.conf.example` must keep `BARK_BASE_URL=` blank.
- Use Python 3.9+ and standard-library modules only.
- Install only under the selected `CODEX_HOME`; resolution order is `--codex-home`, `CODEX_HOME`, then `~/.codex`.
- Send Bark exactly once for a root `agent-turn-complete` event.
- Do not send Bark for subagent, internal classifier, submission, approval, waiting, or unknown events.
- Preserve an existing notifier exactly once. Keep native `SkyComputerUseClient turn-ended` as the outer notifier.
- Repeated installation must be idempotent.
- External notify changes must fail closed unless the human explicitly authorizes `install.py --repair`.
- `verify.py` must remain offline unless the human explicitly requests `--send-test`.
- Do not print the Bark URL in output, errors, tests, or logs.

## Human-secret boundary

For a first install, obtain the Bark device URL only through one of these channels:

1. Hidden interactive prompt from `bootstrap.py` or `install.py`.
2. A human-provided `BARK_BASE_URL` environment variable.
3. A human-provided raw key in the `BARK_KEY` environment variable when using `bootstrap.py`.
4. Explicit `--bark-base-url` input when the human accepts command-history/process-list exposure.

Do not search the repository, shell history, session logs, or another machine for the key. An existing local `~/.codex/bark-notify.conf` may be reused by `install.py` for an idempotent upgrade. Never relay its value in a response.

## One-click agent procedure

When a human provides this repository URL, a Bark key or device URL, and explicitly asks for the one-click installation, that single request authorizes all of the following actions:

1. Clone or fast-forward this repository in a temporary or agent-managed directory.
2. Select Python 3.9 or newer for the current platform.
3. Run `bootstrap.py --send-test` with the human value supplied only through the child process environment.
4. Install into the resolved Codex home, verify offline, and request exactly one live test push.

Use `BARK_KEY` for a raw key or `BARK_BASE_URL` for a complete device URL. Remove the process-scoped value immediately after the bootstrap command exits. Do not place the value in a command argument, repository file, generated plan, response, log, or commit.

Do not repeat design, installation, secret-handling, or test-push confirmation after the human makes the explicit one-click request. Ask a new question only when an externally changed notification chain requires explicit `--repair` authorization or when an external blocker prevents progress. Never infer `--repair` from the one-click request.

On success, report the resolved Codex home and tell the human to fully restart Codex. Do not restart Codex during the active task, and do not promise that a task started before installation will emit a completion push.

Windows agents use a process-scoped environment value and always clear it:

```powershell
$env:BARK_KEY = $humanProvidedKey
try { python bootstrap.py --send-test } finally { Remove-Item Env:BARK_KEY -ErrorAction SilentlyContinue }
```

macOS agents use the equivalent child-process environment without writing the value to shell history:

```bash
BARK_KEY="$human_provided_key" python3 bootstrap.py --send-test
unset human_provided_key
```

The variables in these examples are placeholders for values already supplied directly by the human. Agents must not print them while preparing the environment.

## macOS procedure

```bash
python3 --version
python3 install.py
python3 verify.py
```

Expected final verification line:

```text
Offline verification passed. No Bark push was sent.
```

Only after explicit human authorization:

```bash
python3 verify.py --send-test
```

Uninstall:

```bash
python3 uninstall.py
```

## Windows PowerShell procedure

```powershell
py -3 --version
py -3 install.py
py -3 verify.py
```

Use `python` instead of `py -3` only when `python --version` reports 3.9 or newer.

Only after explicit human authorization:

```powershell
py -3 verify.py --send-test
```

Uninstall:

```powershell
py -3 uninstall.py
```

## Implementation map

- `bootstrap.py`: raw-key normalization and one-click install, offline verification, optional test delivery, and restart handoff.
- `src/bark_notify.py`: payload parsing, subagent suppression, message construction, Bark delivery, and previous-notifier dispatch.
- `install.py`: constrained TOML `notify` parsing, backup, atomic install, native/previous notifier composition, private config, and state recording.
- `uninstall.py`: exact previous assignment restoration with changed-config protection.
- `verify.py`: offline installation audit and explicit test delivery.
- `config/bark-notify.conf.example`: secret-free defaults for title, icon, sound, and timeouts.
- `tests/`: unit and temporary-home integration coverage.

The legacy Codex notify payload does not directly identify internal work. The notifier resolves `thread-id` against the matching rollout `session_meta` under `CODEX_HOME` and allows only confirmed user threads. Missing metadata fails closed because Codex ambient-suggestion classifiers can emit `agent-turn-complete` from `cwd=/` without a rollout. Existing desktop/arbitrary notifiers still receive the original event once. `verify.py --send-test` uses the dedicated `codexnotes-test` marker.

## Required validation

Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bootstrap.py install.py uninstall.py verify.py src/bark_notify.py
git diff --check
```

Run the secret scan and require zero matches:

```bash
rg -n 'https://api\.day\.app/[A-Za-z0-9_-]{10,}' .
```

Also install, verify, reinstall, and uninstall against temporary Codex homes for direct, native desktop, arbitrary previous-notifier, and Windows-path fixtures. Do not use the real user home for destructive tests.

## Completion criteria

- All tests pass on Python 3.9+.
- Offline verification performs no subprocess or network delivery.
- A temporary install contains one Bark command and preserves any previous notifier.
- A second install contains the same single Bark command and reuses the original backup/state.
- Uninstall restores the exact original top-level `notify` assignment or removes the generated config when none existed.
- Subagent metadata produces zero Bark calls while root metadata produces one.
- The repository secret scan has zero matches.
- `main` is pushed and matches `origin/main`.
