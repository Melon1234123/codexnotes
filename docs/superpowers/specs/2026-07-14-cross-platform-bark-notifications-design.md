# Cross-Platform Bark Notifications Design

## Goal

Reproduce the working Codex-to-Bark completion notification flow on macOS and Windows from this repository. The repository must be usable by both humans and coding agents, and it must never contain the user's Bark key.

## Codex integration

This project uses Codex's user-level `notify` configuration, not MCP, hooks, or scheduled automations. Codex appends one JSON payload to the configured command when an `agent-turn-complete` event occurs. The notifier accepts that payload, ignores other event types, derives a short project-aware message, and sends it to Bark.

The installer writes only to the selected Codex home directory: `CODEX_HOME` when set, otherwise `~/.codex`. It copies the notifier and private configuration there, creates a timestamped backup of `config.toml`, and updates the top-level `notify` value.

## Cross-platform behavior

The implementation requires Python 3.9 or newer and uses only the standard library. Humans run `python3` on macOS and `py -3` or `python` on Windows. The installer uses `sys.executable` in the generated Codex command, so paths with spaces and Windows backslashes are encoded correctly.

Codex's legacy notification payload does not identify internal work directly. Before sending Bark, the notifier resolves the payload's `thread-id` to the matching rollout `session_meta` under `CODEX_HOME` and permits only confirmed user threads. Subagents, internal classifiers, and unknown records without rollout metadata are suppressed. The verifier uses an explicit local test marker for opt-in test delivery. Existing desktop or arbitrary notifiers still receive the original event once.

The installer supports three existing states:

1. No notifier: install the Bark notifier directly.
2. Codex desktop `SkyComputerUseClient turn-ended`: preserve it as the outer desktop notifier and set Bark as its `--previous-notify` command.
3. Any other notifier: store that command in the private Bark config and call it once after processing the Codex payload.

Repeated installation is idempotent. It must not add another Bark command, another desktop notifier call, or another previous-notifier layer.

## Repository structure

- `README.md`: exact human installation, verification, troubleshooting, and uninstall steps for macOS and Windows.
- `AGENTS.md`: machine-oriented contract with commands, invariants, and completion criteria.
- `src/bark_notify.py`: event filtering, message construction, Bark request, and optional previous notifier dispatch.
- `install.py`: cross-platform installation and `config.toml` patching.
- `verify.py`: offline verification by default and an explicit opt-in test push.
- `uninstall.py`: restore the original `notify` setting and remove installed files.
- `config/bark-notify.conf.example`: secret-free configuration template.
- `tests/`: standard-library unit and integration tests.

## Security

`BARK_BASE_URL` is blank in Git. Installation accepts it from `--bark-base-url`, the `BARK_BASE_URL` environment variable, or an interactive prompt. The installer never prints the complete key and writes the installed config with user-only permissions where supported.

The repository must not contain the current Bark key, a complete `api.day.app` device URL, copied local authentication files, or generated private configuration.

## Notification policy

- Send exactly one Bark push for `agent-turn-complete`.
- Send no Bark push for thread-spawned subagent completions.
- Send no Bark push for Codex internal classifiers or unknown threads without user metadata.
- Send no Bark push for submission, approval, waiting, or unknown events.
- Keep the title `codex叫你干活啦`.
- Include the project directory and final assistant message, truncated to 220 characters.
- Use the verified Codex cloud-terminal icon and the `minuet` sound.
- Bark failures must not fail the completed Codex turn.
- Verification must not send a real push unless `--send-test` is provided.

## Acceptance criteria

- All unit tests pass with Python 3.9+ and no third-party packages.
- Installation into a temporary Codex home works with an empty, missing, native, arbitrary, and already-installed `notify` configuration.
- User-thread metadata permits Bark delivery while subagent metadata suppresses it without suppressing the existing notifier.
- Windows paths serialize to valid single-line TOML arrays.
- Offline verification confirms one Bark command and no duplicate desktop call.
- Repository secret scans find no Bark key or non-placeholder device URL.
- README and AGENTS.md contain copy-paste commands for install, verify, test push, and uninstall.
