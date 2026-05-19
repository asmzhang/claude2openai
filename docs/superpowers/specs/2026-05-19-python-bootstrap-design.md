# Python Bootstrap Design

**Goal:** Provide a single Python entry point that starts the local fixup proxy and LiteLLM gateway so Claude Code can immediately use the CC Switch profile that points at `http://127.0.0.1:4000`.

## Scope

This addition stays narrow:

- Add one Python bootstrap script for local startup
- Keep the existing PowerShell entry points as lower-level helpers
- Do not modify `C:\Users\Administrator\.claude\settings.json`
- Assume CC Switch manages the Claude-side environment variables

## Constraints

- The workspace is `D:\4\claude2openai`
- This directory is not a git repository
- The real backend key must stay on the local machine and out of checked-in files
- The bootstrap flow must work from Python, not require the user to manually run two PowerShell windows

## Approach

Add a small bootstrap module plus a root `bootstrap_claude_gateway.py` script. The script will accept the backend key from `OPENAI_API_KEY` or a CLI flag, launch the fixup proxy on `8328`, launch LiteLLM on `4000`, wait for both ports to become reachable, then optionally run the existing smoke helpers against the fixup and gateway endpoints.

Runtime process management will be local and file-backed. The script will write logs and pid files under a local runtime directory so repeated runs can reuse healthy processes instead of spawning duplicates. Child processes will inherit only the environment they need: the fixup proxy gets the backend base URL and backend key, while LiteLLM gets the fixup base URL, model mapping, and local gateway key.

## Files

- `bootstrap_claude_gateway.py`: root Python entry point for one-click startup
- `src/claude2openai_gateway/bootstrap.py`: bootstrap helpers for commands, env, health checks, and CC Switch env output
- `tests/test_bootstrap.py`: regression tests for bootstrap configuration helpers
- `README.md`: updated one-click usage instructions

## Success Criteria

The bootstrap flow is considered complete only if:

1. `uv run python bootstrap_claude_gateway.py` starts or reuses the fixup proxy on `8328`
2. The same command starts or reuses LiteLLM on `4000`
3. The script prints the CC Switch environment values that must point Claude Code at `4000`
4. Running `claude` with the existing CC Switch profile works without additional manual startup steps

## Risks

- A stale pid file could point at a dead process, so the bootstrap flow must prefer live health checks over pid files alone
- Port checks prove the services are reachable, but a full smoke run is still the stronger end-to-end verification
- The upstream provider can still substitute `gpt-5.5` with another model; the bootstrap flow only solves local startup and protocol compatibility
