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
    $command = $GatewayArgs[0]
    $remainingArgs = @()
    if ($GatewayArgs.Count -gt 1) {
        $remainingArgs = $GatewayArgs[1..($GatewayArgs.Count - 1)]
    }

    switch ($command) {
        "on" {
            $forwardArgs = @("start") + $remainingArgs
        }
        "off" {
            $forwardArgs = @("stop") + $remainingArgs
        }
        "start" {
            throw "Legacy command '$command' is no longer supported. Use 'on'/'off' instead."
        }
        "stop" {
            throw "Legacy command '$command' is no longer supported. Use 'on'/'off' instead."
        }
        default {
            $forwardArgs = $GatewayArgs
        }
    }
}

uv run python .\bootstrap_claude_gateway.py @forwardArgs
