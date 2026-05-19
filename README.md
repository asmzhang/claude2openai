# claude2openai

用于让 Claude Code 通过本地 Anthropic 兼容网关访问现有 OpenAI 风格后端 `http://127.0.0.1:8327/v1` 的本地包装层。

## 当前状态

当前本地链路已经可以端到端工作：

- `fixup_server.py` 会修正 `8327` 上不标准的 `OpenAI /responses` 返回
- `litellm_proxy.py` 会在启动代理前应用一层本地 LiteLLM 兼容补丁
- Claude Code 可以通过本地 Anthropic 兼容网关 `http://127.0.0.1:4000` 正常调用
- 当前主入口是 Python 启动脚本，不再需要手动守着两个前台终端

CLI 验收已经通过，且验证的是 Claude Code 本身，不只是原始 HTTP 烟测：

```powershell
claude -p --model gpt-5.5 "在吗" --output-format json
```

期望返回大致如下：

```json
{
  "subtype": "success",
  "is_error": false,
  "result": "在。有什么要我处理的？"
}
```

## 文件说明

- `start_fixup.ps1`：仅用于调试的旧前台 fixup 启动脚本
- `start_gateway.ps1`：仅用于调试的旧前台 gateway 启动脚本
- `bootstrap_claude_gateway.py`：一条命令拉起 fixup + gateway + smoke 的 Python 主入口
- `claude2openai.ps1`：对 `bootstrap_claude_gateway.py` 的薄 PowerShell 包装
- `run_smoke.ps1`：验证直连后端、Anthropic gateway 和 Claude Code
- `litellm_config.yaml`：LiteLLM 模型映射配置
- `src/claude2openai_gateway/bootstrap.py`：后台进程启停与生命周期管理
- `src/claude2openai_gateway/smoke.py`：烟测辅助逻辑与 CLI
- `src/claude2openai_gateway/fixup_server.py`：规范化异常 `/responses` 返回
- `src/claude2openai_gateway/litellm_proxy.py`：本地 LiteLLM 启动器与补丁挂钩
- `src/claude2openai_gateway/litellm_patch.py`：LiteLLM 的 Anthropic 日志兼容补丁
- `tests/test_smoke.py`：smoke 辅助测试
- `tests/test_fixup.py`：fixup 回归测试
- `tests/test_bootstrap.py`：bootstrap 启停与命令构造测试
- `tests/test_litellm_patch.py`：LiteLLM 补丁回归测试

## 前置条件

- Python 3.11+
- `uv`
- 仓库根目录中的 `gateway_config.toml`
  - 默认已提交 `proxy-key`
  - Python 主入口会优先读取这个文件
  - 如需临时覆盖，仍可使用 `BACKEND_API_KEY` / `OPENAI_API_KEY` 或 CLI 参数
  - 旧调试脚本的前台模式仍然要求 `OPENAI_API_KEY`

## 快速开始

正常使用时，不要再分别启动 `start_fixup.ps1` 和 `start_gateway.ps1`。

直接使用 Python 主入口：

```powershell
Set-Location D:\4\claude2openai
uv run python .\bootstrap_claude_gateway.py start
```

这条命令会：

- 启动或复用 `8328` 上的 fixup proxy
- 启动或复用 `4000` 上的 LiteLLM gateway
- 默认执行 smoke check，除非传入 `--skip-smoke`
- 默认打印精简摘要
- 传入 `--verbose` 时打印 smoke 详情和 Claude / CC Switch 环境变量块

如果你只是更习惯 PowerShell，也可以用包装脚本：

```powershell
Set-Location D:\4\claude2openai
.\claude2openai.ps1 start
```

常用生命周期命令：

```powershell
uv run python .\bootstrap_claude_gateway.py status
uv run python .\bootstrap_claude_gateway.py start --verbose
uv run python .\bootstrap_claude_gateway.py restart --skip-smoke
uv run python .\bootstrap_claude_gateway.py stop
```

对应的 PowerShell 包装命令：

```powershell
.\claude2openai.ps1 status
.\claude2openai.ps1 restart --skip-smoke
.\claude2openai.ps1 stop
```

重复执行 `start` 是安全的：

- 如果两个托管服务都已健康运行，会直接复用
- 如果 `pid` 文件已经失效，会自动清理后重启
- 如果 `4000` 或 `8328` 被未知进程占用，会明确报冲突，而不是重复拉起实例

## 旧调试脚本

底层 PowerShell 脚本仍然保留用于单层调试，但默认不再走旧的双终端工作流。

默认会转发到：

```powershell
.\claude2openai.ps1 start --skip-smoke
```

只有显式传入 `-LegacyForeground`，才会回到旧的前台调试模式。

## Python 主入口细节

如果你已经通过 CC Switch 管理 Claude 侧环境变量，最短路径仍然是 Python 主入口：

```powershell
Set-Location D:\4\claude2openai
uv run python .\bootstrap_claude_gateway.py start
```

默认配置文件内容如下：

```toml
[backend]
api_key = "proxy-key"
base_url = "http://127.0.0.1:8327/v1"

[gateway]
key = "local-gateway-key"
model = "gpt-5.5"
openai_model = "openai/gpt-5.5"

[ports]
fixup = 8328
gateway = 4000
```

这个脚本按如下顺序解析后端 key：

1. `--openai-api-key`
2. `BACKEND_API_KEY`
3. `OPENAI_API_KEY`
4. `gateway_config.toml` 中的 `[backend].api_key`

如果你不想先设置环境变量，可以直接传参数：

```powershell
uv run python .\bootstrap_claude_gateway.py start --openai-api-key "your-key"
```

## 旧调试模式：只起 fixup

在一个 PowerShell 会话里执行：

```powershell
$env:OPENAI_API_KEY = "your-key"
Set-Location D:\4\claude2openai
.\start_fixup.ps1 -LegacyForeground
```

这会在 `http://127.0.0.1:8328` 启动 OpenAI fixup proxy。

## 旧调试模式：只起 gateway

在一个 PowerShell 会话里执行：

```powershell
$env:OPENAI_API_KEY = "your-key"
Set-Location D:\4\claude2openai
.\start_gateway.ps1 -GatewayKey "local-gateway-key" -LegacyForeground
```

这会在 `http://127.0.0.1:4000` 启动 LiteLLM。

只有在你明确需要旧前台调试流时才建议这样做。

## 运行 smoke 测试

在另一个 PowerShell 会话里执行：

```powershell
$env:OPENAI_API_KEY = "your-key"
Set-Location D:\4\claude2openai
uv run pytest tests/test_smoke.py -q
uv run pytest tests/test_fixup.py -q
.\run_smoke.ps1 -GatewayKey "local-gateway-key"
```

## Claude Code 环境变量

如果要直接用 CLI 测本地 gateway：

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:4000"
$env:ANTHROPIC_AUTH_TOKEN = "local-gateway-key"
$env:ANTHROPIC_CUSTOM_MODEL_OPTION = "gpt-5.5"
$env:ANTHROPIC_CUSTOM_MODEL_OPTION_NAME = "gpt-5.5"
claude -p --model gpt-5.5 "你好" --output-format json
```

如果你使用 CC Switch，把地址指向 `http://127.0.0.1:4000`，key 用 `local-gateway-key`。启动脚本也会打印完整环境变量块。

## 故障排查

### Claude settings 报错：`cleanupPeriodDays`

较新的 Claude Code 不接受 `C:\Users\Administrator\.claude\settings.json` 中的 `cleanupPeriodDays: 0`。

请改成大于等于 `1` 的值，例如：

```json
{
  "cleanupPeriodDays": 3650
}
```

如果你想完全关闭会话持久化，可以去掉 `cleanupPeriodDays`，然后这样启动 Claude Code：

```powershell
claude --no-session-persistence
```

### 重复启动冲突或必须守着终端

使用托管入口：

```powershell
uv run python .\bootstrap_claude_gateway.py start
```

或者：

```powershell
.\claude2openai.ps1 start
```

这会替代旧的“两窗口常驻”方式。

常用管理命令：

```powershell
uv run python .\bootstrap_claude_gateway.py status
uv run python .\bootstrap_claude_gateway.py restart
uv run python .\bootstrap_claude_gateway.py stop
```

包装脚本对应命令：

```powershell
.\claude2openai.ps1 status
.\claude2openai.ps1 restart
.\claude2openai.ps1 stop
```

如果 `status` 显示 `conflict`，说明 `4000` 或 `8328` 被其他进程占用，管理器不会直接帮你强杀未知进程。

### LiteLLM 警告：`/responses/input_tokens` 返回 `404`

LiteLLM 可能会打印类似警告：

```text
Provider token counting failed (404). Falling back to local tokenizer.
```

这目前不阻塞使用。因为 `8327` 后端没有实现 `/v1/responses/input_tokens`，LiteLLM 会回退到本地 tokenizer，Claude Code 请求仍然可以成功。

### Anthropic logging 校验错误

本地 LiteLLM 启动器就是为了绕开这类错误：

```text
LiteLLM.Success_Call Error: validation error for AnthropicResponse
```

如果这个错误再次出现，先确认 gateway 是通过下面的方式启动的：

```powershell
uv run python .\bootstrap_claude_gateway.py start
```

或者通过仓库里的启动脚本启动，而不是直接调用 `litellm.exe`。

## 已知限制

这套方案解决的是两个独立兼容性问题：

1. 当前后端返回了不标准的 OpenAI `responses` 结构
2. Claude Code 需要 Anthropic 兼容端点

它仍然无法阻止上游提供方替换你请求的模型。当前对 `8327` 的直连测试里，请求的是 `gpt-5.5`，但实际返回过 `gpt-5.4`。
