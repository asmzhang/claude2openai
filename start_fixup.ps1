param(
    [string]$BackendBaseUrl = "http://127.0.0.1:8327/v1",
    [int]$Port = 8328,
    [switch]$LegacyForeground
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $LegacyForeground) {
    Write-Warning "start_fixup.ps1 is now a legacy debug entry point. Delegating to .\\manage_gateway.ps1 start --skip-smoke. Use -LegacyForeground to run fixup only in the foreground."
    & (Join-Path $root "manage_gateway.ps1") start --skip-smoke
    exit $LASTEXITCODE
}

if (-not $env:OPENAI_API_KEY) {
    throw "Set OPENAI_API_KEY before running start_fixup.ps1."
}

$env:BACKEND_API_BASE = $BackendBaseUrl
$env:BACKEND_API_KEY = $env:OPENAI_API_KEY
$env:PYTHONPATH = Join-Path $root "src"

uv run uvicorn claude2openai_gateway.fixup_server:app --host 127.0.0.1 --port $Port
