# Startup Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single managed startup entry point that removes the need for two terminals and makes repeated startup calls reuse healthy services instead of conflicting with existing ones.

**Architecture:** Extend the existing bootstrap module into a small process manager for two known services, keyed by pid files and expected ports. Keep the current detached startup model, but add explicit lifecycle subcommands plus a thin PowerShell wrapper so the default user path is one command instead of two foreground sessions.

**Tech Stack:** Python 3.11, argparse, subprocess, socket, pathlib, httpx, pytest, PowerShell

---

### Task 1: Add red tests for lifecycle behavior

**Files:**
- Modify: `tests/test_bootstrap.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for CLI normalization and service-state classification**
- [ ] **Step 2: Run `uv run pytest tests/test_bootstrap.py -q` and confirm the new tests fail for the missing lifecycle helpers**
- [ ] **Step 3: Add one failing test that proves repeated start reuses a running managed service instead of spawning a duplicate**

### Task 2: Implement bootstrap service management

**Files:**
- Modify: `src/claude2openai_gateway/bootstrap.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Add lifecycle-oriented data structures for managed services and inspected service state**
- [ ] **Step 2: Add pid parsing, stale-pid cleanup, process existence checks, port-closed waits, and managed stop behavior**
- [ ] **Step 3: Add `start`, `stop`, `restart`, and `status` command handling with backward-compatible default-to-`start` behavior**
- [ ] **Step 4: Run `uv run pytest tests/test_bootstrap.py -q` until all lifecycle tests pass**

### Task 3: Add the single PowerShell wrapper

**Files:**
- Create: `manage_gateway.ps1`
- Modify: `README.md`

- [ ] **Step 1: Add a thin wrapper that forwards lifecycle arguments to `bootstrap_claude_gateway.py`, defaulting to `start`**
- [ ] **Step 2: Update the README so this wrapper and the Python bootstrap command are the recommended operational path**

### Task 4: Verify repeat-start and shutdown behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run `uv run pytest tests/test_fixup.py tests/test_bootstrap.py tests/test_smoke.py tests/test_litellm_patch.py -q`**
- [ ] **Step 2: Run `uv run python .\bootstrap_claude_gateway.py start --openai-api-key <real-key>` twice and confirm the second run reuses the existing services**
- [ ] **Step 3: Run `uv run python .\bootstrap_claude_gateway.py status` and confirm both services report as running**
- [ ] **Step 4: Run `uv run python .\bootstrap_claude_gateway.py stop` and confirm both managed services exit cleanly**
