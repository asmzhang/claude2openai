param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GatewayArgs
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$forwardArgs = @()
if ($GatewayArgs.Count -eq 0) {
    $forwardArgs = @("start")
} else {
    $forwardArgs = $GatewayArgs
}

uv run python .\bootstrap_claude_gateway.py @forwardArgs
