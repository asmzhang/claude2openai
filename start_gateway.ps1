param(
    [string]$OpenAIBaseUrl = "http://127.0.0.1:8328/v1",
    [string]$GatewayModel = "gpt-5.5",
    [string]$OpenAIModel = "openai/gpt-5.5",
    [string]$GatewayKey = "local-gateway-key",
    [int]$Port = 4000,
    [switch]$LegacyForeground
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $LegacyForeground) {
    Write-Warning "start_gateway.ps1 is now a legacy debug entry point. Delegating to .\\manage_gateway.ps1 start --skip-smoke. Use -LegacyForeground to run only the gateway in the foreground."
    & (Join-Path $root "manage_gateway.ps1") start --skip-smoke
    exit $LASTEXITCODE
}

if (-not $env:OPENAI_API_KEY) {
    throw "Set OPENAI_API_KEY before running start_gateway.ps1."
}

$env:OPENAI_API_BASE = $OpenAIBaseUrl
$env:OPENAI_MODEL = $OpenAIModel
$env:GATEWAY_MODEL = $GatewayModel
$env:LITELLM_MASTER_KEY = $GatewayKey
$env:PYTHONPATH = Join-Path $root "src"

# LiteLLM treats DEBUG as a boolean-like setting. This machine has DEBUG=release,
# which breaks startup unless it is removed for the child process.
Remove-Item Env:DEBUG -ErrorAction SilentlyContinue

uv run litellm --config (Join-Path $root "litellm_config.yaml") --host 127.0.0.1 --port $Port
