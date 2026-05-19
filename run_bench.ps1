param(
    [string]$BackendBaseUrl = "http://127.0.0.1:8327/v1",
    [string]$FixupBaseUrl = "http://127.0.0.1:8328/v1",
    [string]$GatewayUrl = "http://127.0.0.1:4000",
    [string]$GatewayModel = "gpt-5.5",
    [string]$BackendKey = $env:OPENAI_API_KEY,
    [string]$GatewayKey = "local-gateway-key",
    [string]$Prompt = "请只回答数字：1+1=",
    [int]$Repeats = 5,
    [int]$Warmup = 1
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONUTF8 = "1"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $BackendKey) {
    throw "Set OPENAI_API_KEY or pass -BackendKey before running run_bench.ps1."
}

uv run python -m claude2openai_gateway.smoke bench `
    --backend-base-url $BackendBaseUrl `
    --fixup-base-url $FixupBaseUrl `
    --gateway-base-url $GatewayUrl `
    --backend-api-key $BackendKey `
    --gateway-api-key $GatewayKey `
    --model $GatewayModel `
    --prompt $Prompt `
    --repeats $Repeats `
    --warmup $Warmup
