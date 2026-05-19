param(
    [string]$OpenAIBaseUrl = "http://127.0.0.1:8327/v1",
    [string]$FixupBaseUrl = "http://127.0.0.1:8328/v1",
    [string]$GatewayUrl = "http://127.0.0.1:4000",
    [string]$GatewayModel = "gpt-5.5",
    [string]$GatewayKey = "local-gateway-key",
    [switch]$SkipClaudeCode
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $env:OPENAI_API_KEY) {
    throw "Set OPENAI_API_KEY before running run_smoke.ps1."
}

Write-Host "== Direct backend smoke =="
uv run python -m claude2openai_gateway.smoke backend --base-url $OpenAIBaseUrl --api-key $env:OPENAI_API_KEY --model $GatewayModel --prompt "你好"

Write-Host ""
Write-Host "== Fixup smoke =="
uv run python -m claude2openai_gateway.smoke backend --base-url $FixupBaseUrl --api-key $env:OPENAI_API_KEY --model $GatewayModel --prompt "你好"

Write-Host ""
Write-Host "== Anthropic gateway smoke =="
uv run python -m claude2openai_gateway.smoke gateway --base-url $GatewayUrl --api-key $GatewayKey --model $GatewayModel --prompt "你好"

if (-not $SkipClaudeCode) {
    Write-Host ""
    Write-Host "== Claude Code smoke =="
    $env:ANTHROPIC_BASE_URL = $GatewayUrl
    $env:ANTHROPIC_AUTH_TOKEN = $GatewayKey
    $env:ANTHROPIC_API_KEY = $GatewayKey
    $env:ANTHROPIC_CUSTOM_MODEL_OPTION = $GatewayModel
    $env:ANTHROPIC_CUSTOM_MODEL_OPTION_NAME = $GatewayModel
    claude -p --model $GatewayModel "你好" --output-format json
}
