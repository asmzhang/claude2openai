# Claude Code OpenAI Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local LiteLLM-based Anthropic-compatible gateway in `D:\4\claude2openai` and verify Claude Code can talk to the existing OpenAI-style backend through it.

**Architecture:** LiteLLM exposes Anthropic-format endpoints for Claude Code and forwards to the existing `8327` OpenAI-style backend. A small Python helper module builds request payloads and extracts text from backend and gateway responses. PowerShell scripts wrap startup and smoke-test flows.

**Tech Stack:** Python 3.11, LiteLLM proxy, httpx, pytest, PowerShell

---

### Task 1: Project Skeleton and Red Tests

**Files:**
- Create: `D:\4\claude2openai\pyproject.toml`
- Create: `D:\4\claude2openai\tests\test_smoke.py`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run `uv run pytest tests/test_smoke.py -q` and confirm failure because the helper module does not exist yet**

### Task 2: Smoke Helper

**Files:**
- Create: `D:\4\claude2openai\src\claude2openai_gateway\__init__.py`
- Create: `D:\4\claude2openai\src\claude2openai_gateway\smoke.py`

- [ ] **Step 1: Implement request builders and response text extraction with the minimum behavior needed by the tests**
- [ ] **Step 2: Run `uv run pytest tests/test_smoke.py -q` and confirm all tests pass**

### Task 3: Gateway and Wrapper Scripts

**Files:**
- Create: `D:\4\claude2openai\litellm_config.yaml`
- Create: `D:\4\claude2openai\start_gateway.ps1`
- Create: `D:\4\claude2openai\run_smoke.ps1`
- Create: `D:\4\claude2openai\README.md`

- [ ] **Step 1: Add a LiteLLM config that maps a gateway model name to `openai/gpt-5.5` using environment-provided base URL and API key**
- [ ] **Step 2: Add a startup script that requires `OPENAI_API_KEY`, sets gateway env vars, and launches LiteLLM on a local port**
- [ ] **Step 3: Add a smoke-test script that verifies the direct backend, the gateway Anthropic endpoint, and Claude Code custom-model usage**

### Task 4: Integration Verification

**Files:**
- Modify: `D:\4\claude2openai\README.md`

- [ ] **Step 1: Start the gateway locally**
- [ ] **Step 2: Run the smoke script against the real backend**
- [ ] **Step 3: Confirm Claude Code works with `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, and `ANTHROPIC_CUSTOM_MODEL_OPTION=gpt-5.5`**
- [ ] **Step 4: Document the exact commands and observed caveat if the upstream returns `gpt-5.4` instead of `gpt-5.5`**
