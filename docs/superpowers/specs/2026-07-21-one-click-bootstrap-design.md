# One-Click Codex Bark Bootstrap Design

## Goal

Let a human configure Codex completion notifications by giving an agent only two values: this repository URL and a Bark key. The agent must complete installation, offline verification, and one live test push without asking for repeated approvals when the human explicitly requests the one-click workflow.

The workflow must support Windows and macOS, preserve the repository's current notification defaults, and reuse the existing installer and verifier rather than reimplementing their behavior.

## User Experience

The README will provide one copy-ready prompt:

```text
请按仓库的一站式流程安装 Codex Bark 通知。
仓库：https://github.com/Melon1234123/codexnotes.git
Bark Key：<your key>
使用仓库默认配置，完成安装、离线验证并发送一次测试通知；除非失败或需要 repair，不要再向我确认。
```

This explicit request authorizes the following actions as one operation:

1. Clone or update the repository in a temporary or agent-managed directory.
2. Install the notifier into the resolved user-level Codex home.
3. Run offline verification.
4. Send exactly one live test push after offline verification succeeds.

On success, the agent reports the installed Codex home and tells the human to fully restart Codex. The agent does not restart Codex itself because doing so could terminate the active task. The current task is not expected to emit a completion push when Codex loaded its configuration before installation.

## Bootstrap Interface

Add `bootstrap.py` as a standard-library-only orchestration entry point. It accepts configuration through environment variables so a Bark key does not need to appear in command arguments:

- `BARK_KEY`: a raw Bark device key.
- `BARK_BASE_URL`: a complete Bark device URL, retained for compatibility with `install.py`.

Exactly one of these values must resolve to a usable URL. If `BARK_KEY` is set, the bootstrap constructs `https://api.day.app/<key>` after validating that the key contains only ASCII letters, digits, underscores, or hyphens. If neither environment variable is available, interactive execution may use a hidden prompt. The bootstrap never prints either input.

Command-line options:

- `--codex-home PATH`: pass an explicit Codex home through to installation and verification.
- `--send-test`: authorize one live test push after offline verification passes.
- `--repair`: explicitly authorize repair of an externally changed notification chain.

The agent contract requires `--send-test` for the copy-ready one-click request. The bootstrap itself does not silently infer network authorization from the presence of a key.

## Components And Data Flow

`bootstrap.py` imports and calls the existing modules in this order:

1. Resolve and validate the key or URL without printing it.
2. Call `install.install(...)` with `sys.executable`, the resolved Codex home, and the explicit repair flag.
3. Call `verify.verify(codex_home, send_test=False)` and stop if any offline check fails.
4. When `--send-test` is present, call `verify.verify(codex_home, send_test=True)` exactly once.
5. Print a concise non-secret summary and the restart requirement.

`install.py` remains responsible for backups, atomic writes, private configuration, notifier composition, idempotence, and repair protection. `verify.py` remains responsible for installation auditing and test delivery. `src/bark_notify.py` remains responsible for runtime filtering and Bark delivery.

The bootstrap must expose small functions for input normalization and orchestration so tests can inject installer and verifier callables without touching the real user home or network.

## Agent Contract

Update `AGENTS.md` with a one-click procedure. When a human supplies a repository URL, a Bark key or URL, and explicitly asks for the one-click installation, an agent must:

- treat the request as authorization to clone or update the repository, install, verify offline, and request one test push;
- use the provided key only through `BARK_KEY` or `BARK_BASE_URL` in the child process environment;
- run `bootstrap.py --send-test` with the platform's Python 3.9+ interpreter;
- avoid repeating design, installation, test-push, or secret-handling confirmations;
- stop and ask only when `--repair` would be required or an external blocker prevents progress;
- never echo, log, commit, or quote the key in the final response.

The contract will include Windows PowerShell and macOS shell command shapes using placeholder values only. It will not contain a real device key or complete device URL.

## Defaults

The one-click path keeps all current repository defaults:

- title `codex叫你干活啦`;
- colorful Codex icon;
- Bark `minuet` sound;
- project directory and compact final-response summary in the body;
- one push only for a confirmed root `agent-turn-complete` event;
- no push for subagents, internal classifiers, submissions, approvals, waiting, or unknown events;
- existing native or arbitrary notifiers preserved exactly once.

## Error Handling

- Missing or unsupported Python is an external blocker and must be reported without changing Codex configuration.
- Invalid or ambiguous key input fails before installation.
- Installation errors return a nonzero status and a non-secret message.
- Offline verification errors prevent the live test from running.
- A changed installed notification chain fails closed. Repair requires an explicit `--repair` request and must never be inferred from the one-click prompt.
- Test-delivery failure returns a nonzero status while leaving the valid local installation intact.
- Repeated successful execution remains idempotent and requests at most one test push per invocation.

## Testing

Add `tests/test_bootstrap.py` using `unittest` and temporary directories or injected callables. Cover:

- raw key normalization;
- complete URL compatibility;
- invalid, missing, and conflicting inputs;
- install followed by offline verification;
- offline failure preventing a test push;
- `--send-test` producing exactly one test-verification call;
- `--repair` forwarding only when explicitly supplied;
- success and failure output containing no key or complete Bark URL;
- success output including the resolved Codex home and restart instruction.

Keep the existing install, notifier, and verifier tests unchanged except where a public helper must be exposed. Run the full standard-library test suite, byte compilation, `git diff --check`, and the repository secret scan.

## Acceptance Criteria

- A new agent can complete the workflow from only the repository URL, Bark key, and copy-ready one-click request without additional confirmation.
- The same bootstrap works with Python 3.9+ on Windows and macOS.
- Offline verification always precedes any live test push.
- A successful invocation sends at most one test push and tells the human to restart Codex.
- Existing notifiers and repeated-install behavior remain correct.
- No real Bark key or complete device URL appears in repository files, command output, logs, or commits.
