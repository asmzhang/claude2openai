# Startup Lifecycle Design

**Goal:** Replace the fragile "two foreground terminals" workflow with a single managed entry point that can start, stop, restart, and report status for the local fixup proxy and LiteLLM gateway.

## Scope

- Keep the existing fixup proxy on `8328`
- Keep the existing LiteLLM gateway on `4000`
- Make the Python bootstrap entry point the primary control surface
- Add explicit lifecycle commands: `start`, `stop`, `restart`, `status`
- Default repeated `start` calls to reuse healthy managed services
- Detect and report unknown port conflicts instead of silently starting duplicates

## Constraints

- The workspace is `D:\4\claude2openai`
- This directory is not a git repository
- Existing lower-level PowerShell scripts may still be useful for debugging, but should stop being the recommended path
- The startup flow must stay local and file-backed; no external service manager is introduced

## Approach

The bootstrap module will own lightweight service management for two managed processes: `fixup` and `gateway`. Each service keeps its log file and pid file under `.runtime`. The manager will inspect pid files, test whether the recorded pid still exists, and check whether the expected port is listening.

Repeated startup behavior will be deterministic:

1. If a managed pid exists and the expected port is open, treat the service as already running and reuse it
2. If the pid exists but the process is gone, treat the pid file as stale, remove it, and start fresh
3. If the expected port is open without a live managed pid, treat it as an external conflict and fail with a clear error
4. If a managed process exists but is still warming up, wait for the port instead of starting a duplicate

Lifecycle operations stay conservative. `stop` and `restart` only terminate processes that were started and recorded by this bootstrap flow. They do not blindly kill any process bound to `4000` or `8328`; unknown listeners are reported as conflicts for the user to resolve intentionally.

## Files

- `bootstrap_claude_gateway.py`: root CLI entry point with lifecycle subcommands
- `src/claude2openai_gateway/bootstrap.py`: service inspection, lifecycle management, and CLI behavior
- `manage_gateway.ps1`: thin PowerShell wrapper for the Python entry point
- `tests/test_bootstrap.py`: regression coverage for CLI normalization, state classification, and repeat-start behavior
- `README.md`: updated single-entry usage and troubleshooting guidance

## Success Criteria

1. `uv run python .\bootstrap_claude_gateway.py start` starts or reuses both local services
2. Running the same command again does not spawn duplicates or require extra terminals
3. `uv run python .\bootstrap_claude_gateway.py status` clearly reports whether each service is running, stale, stopped, starting, or in conflict
4. `uv run python .\bootstrap_claude_gateway.py stop` shuts down only managed services and cleans up stale pid files
5. `manage_gateway.ps1` provides the same lifecycle commands without requiring the user to remember the Python invocation

## Risks

- Pid reuse is theoretically possible, so pid files are only one signal; port state is still checked
- A service may be in a short startup window where the process exists but the port is not open yet; this must be treated as "starting" rather than as a conflict
- Unknown listeners on `4000` or `8328` are intentionally not auto-killed, so the failure mode must be explicit and actionable
