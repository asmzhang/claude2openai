# Claude Code OpenAI Gateway Design

**Goal:** Run Claude Code against a local Anthropic-compatible gateway that forwards requests to the existing OpenAI-compatible backend at `http://127.0.0.1:8327/v1`.

## Scope

This setup is intentionally narrow:

- Run a local LiteLLM gateway on the machine
- Expose Anthropic-compatible endpoints required by Claude Code
- Keep OpenAI credentials out of checked-in files
- Provide repeatable smoke tests for the backend, gateway, and Claude Code

## Constraints

- The target workspace is `D:\4\claude2openai`
- There is no git repository in that directory
- The current upstream backend responds to OpenAI-style requests, not Anthropic Messages requests
- Earlier testing showed upstream requests for `gpt-5.5` can be fulfilled as `gpt-5.4`, so the gateway can solve protocol compatibility but not upstream model substitution

## Approach

Use LiteLLM as a local Anthropic-compatible gateway. Claude Code will point at LiteLLM using `ANTHROPIC_BASE_URL`, and LiteLLM will forward requests to the existing `8327` OpenAI-style backend using environment-provided `OPENAI_API_BASE` and `OPENAI_API_KEY`.

Add a small Python helper module for smoke testing so the setup is easy to verify without manual curl editing. Wrap common tasks with PowerShell scripts so the setup is runnable from the target folder.

## Files

- `pyproject.toml`: local Python project and dependencies
- `litellm_config.yaml`: gateway model mapping and auth settings
- `src/claude2openai_gateway/smoke.py`: helper functions and CLI for smoke tests
- `tests/test_smoke.py`: regression tests for request building and response parsing
- `start_gateway.ps1`: starts LiteLLM with environment-driven configuration
- `run_smoke.ps1`: verifies backend, gateway, and Claude Code
- `README.md`: local usage instructions

## Verification

The setup is considered usable only if all three checks succeed:

1. Direct OpenAI-style call to `8327` returns text
2. Anthropic-style call through LiteLLM returns text
3. Claude Code call through LiteLLM with `ANTHROPIC_CUSTOM_MODEL_OPTION` returns text

## Risks

- LiteLLM can satisfy the Claude Code protocol requirements, but it cannot prevent the upstream provider from swapping `gpt-5.5` to another model
- If the local `8327` backend does not support the OpenAI Responses API consistently, the backend smoke test may need to fall back to chat completions
