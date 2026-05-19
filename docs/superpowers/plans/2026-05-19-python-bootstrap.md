# Python Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single Python bootstrap command that starts the local fixup proxy and LiteLLM gateway so Claude Code can use the existing CC Switch profile without manual PowerShell startup.

**Architecture:** A new bootstrap helper module will own command construction, environment generation, runtime file paths, and CC Switch env output. A root script will call those helpers, launch the fixup and gateway child processes, wait for readiness, optionally run existing smoke helpers, and print ready-to-use output.

**Tech Stack:** Python 3.11, subprocess, socket, pathlib, httpx, pytest, LiteLLM proxy, uvicorn

---

### Task 1: Bootstrap Helper Red Tests

**Files:**
- Create: `tests/test_bootstrap.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from claude2openai_gateway.bootstrap import (
    build_cc_switch_env,
    build_fixup_launch_spec,
    build_gateway_launch_spec,
)


def test_build_cc_switch_env_points_claude_at_local_gateway():
    assert build_cc_switch_env(
        gateway_url="http://127.0.0.1:4000",
        gateway_key="local-gateway-key",
        gateway_model="gpt-5.5",
    ) == {
        "ANTHROPIC_API_KEY": "local-gateway-key",
        "ANTHROPIC_AUTH_TOKEN": "local-gateway-key",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
        "ANTHROPIC_CUSTOM_MODEL_OPTION": "gpt-5.5",
        "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME": "gpt-5.5",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "gpt-5.5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "gpt-5.5",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "gpt-5.5",
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "gpt-5.5",
    }


def test_build_fixup_launch_spec_uses_backend_key_and_repo_src():
    spec = build_fixup_launch_spec(
        repo_root=Path("D:/4/claude2openai"),
        backend_base_url="http://127.0.0.1:8327/v1",
        backend_api_key="real-key",
        port=8328,
    )

    assert spec.command[-4:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "8328",
    ]
    assert spec.env["BACKEND_API_BASE"] == "http://127.0.0.1:8327/v1"
    assert spec.env["BACKEND_API_KEY"] == "real-key"
    assert spec.env["PYTHONPATH"] == str(Path("D:/4/claude2openai/src"))


def test_build_gateway_launch_spec_points_litellm_at_fixup_proxy():
    spec = build_gateway_launch_spec(
        repo_root=Path("D:/4/claude2openai"),
        openai_base_url="http://127.0.0.1:8328/v1",
        openai_api_key="real-key",
        gateway_model="gpt-5.5",
        openai_model="openai/gpt-5.5",
        gateway_key="local-gateway-key",
        port=4000,
    )

    assert spec.command[-4:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "4000",
    ]
    assert spec.env["OPENAI_API_BASE"] == "http://127.0.0.1:8328/v1"
    assert spec.env["OPENAI_API_KEY"] == "real-key"
    assert spec.env["OPENAI_MODEL"] == "openai/gpt-5.5"
    assert spec.env["GATEWAY_MODEL"] == "gpt-5.5"
    assert spec.env["LITELLM_MASTER_KEY"] == "local-gateway-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bootstrap.py -q`
Expected: FAIL with `ImportError` because `claude2openai_gateway.bootstrap` does not exist yet

- [ ] **Step 3: Commit**

```bash
git add tests/test_bootstrap.py pyproject.toml
git commit -m "test: add bootstrap helper coverage"
```

### Task 2: Bootstrap Helpers

**Files:**
- Create: `src/claude2openai_gateway/bootstrap.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LaunchSpec:
    command: list[str]
    env: dict[str, str]


def build_cc_switch_env(gateway_url: str, gateway_key: str, gateway_model: str) -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": gateway_key,
        "ANTHROPIC_AUTH_TOKEN": gateway_key,
        "ANTHROPIC_BASE_URL": gateway_url,
        "ANTHROPIC_CUSTOM_MODEL_OPTION": gateway_model,
        "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME": gateway_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": gateway_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": gateway_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": gateway_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": gateway_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": gateway_model,
    }
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_bootstrap.py -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/claude2openai_gateway/bootstrap.py tests/test_bootstrap.py
git commit -m "feat: add bootstrap helper module"
```

### Task 3: One-Click Python Entrypoint

**Files:**
- Create: `bootstrap_claude_gateway.py`
- Modify: `README.md`
- Modify: `src/claude2openai_gateway/bootstrap.py`

- [ ] **Step 1: Add bootstrap runtime helpers for logs, pid files, port polling, and detached process launch**
- [ ] **Step 2: Add a root CLI script that reads `OPENAI_API_KEY` or `--openai-api-key`, starts fixup then gateway, waits for readiness, and optionally runs smoke checks**
- [ ] **Step 3: Update `README.md` with the one-click Python command and CC Switch expectations**

### Task 4: Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run `uv run pytest tests/test_smoke.py tests/test_fixup.py tests/test_bootstrap.py -q`**
- [ ] **Step 2: Run `uv run python bootstrap_claude_gateway.py --openai-api-key <real-key>`**
- [ ] **Step 3: Confirm the script reports both local services ready and prints the CC Switch environment block**
- [ ] **Step 4: Run `claude -p --model gpt-5.5 "你好" --output-format json` against the existing CC Switch profile and confirm success**
