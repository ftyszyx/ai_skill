# gpt-image-2 图片生成流程

## 环境变量

必须由用户在本机配置：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "你的 API key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "你的 OpenAI 兼容 API base URL", "User")
```

`BASE_URL` 可作为 `OPENAI_BASE_URL` 的兼容别名。推荐统一使用 `OPENAI_BASE_URL`。

不要把真实 API key 或 base URL 写入 skill、脚本、仓库文件或聊天记录。

## Endpoint

使用 OpenAI 兼容的 Images generation endpoint：

```text
POST <base-url>/v1/images/generations
```

脚本会归一化 base URL：

- `https://host/path` -> `https://host/path/v1/images/generations`
- `https://host/path/v1` -> `https://host/path/v1/images/generations`

如果代理文档明确要求非 `/v1` 路径，需要按代理文档调整脚本或临时传入合适的 `--base-url`。

## Payload

除非用户要求不同尺寸、质量或格式，否则使用最小 payload：

```json
{
  "model": "gpt-image-2",
  "prompt": "A concise production-quality image prompt.",
  "size": "1024x1024",
  "quality": "medium",
  "output_format": "png"
}
```

常用参数：

- `quality`: `low`, `medium`, `high`, `auto`
- `output_format`: `png`, `jpeg`, `webp`
- `size`: `1024x1024` 等正方形尺寸通常更快、更稳

使用 OpenAI 官方 endpoint 或变更参数时，优先核对当前官方文档：

- `https://platform.openai.com/docs/api-reference/images/create`
- `https://platform.openai.com/docs/guides/image-generation`

## 认证

从 `OPENAI_API_KEY` 读取 key。

不要：

- 打印 key。
- 要求用户把 key 发到聊天里。
- 把 key 写入或提交到文件。

Windows 用户级环境变量可能不会自动进入当前父进程。脚本会检查 `os.environ` 和 `HKEY_CURRENT_USER\Environment`，所以用下面命令设置的值也能被读取：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://your-proxy.example.com/path", "User")
```

当前会话立即生效：

```powershell
$env:OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
$env:OPENAI_BASE_URL = [Environment]::GetEnvironmentVariable("OPENAI_BASE_URL", "User")
```

## 响应处理

接受两种常见响应：

- `data[0].b64_json`: base64 解码后写入输出路径。
- `data[0].url`: 下载图片 URL 后写入输出路径。

如果两者都不存在，输出简短响应摘要并停止。

## 故障排查

`OPENAI_BASE_URL is missing`

用户没有在环境变量中配置 base URL，或当前进程读不到。让用户设置 `OPENAI_BASE_URL`，或确认 Windows 用户环境变量已写入。

`OPENAI_API_KEY is missing`

用户没有在环境变量中配置 API key，或当前进程读不到。让用户在本机设置环境变量，不要让用户把 key 发到聊天里。

`invalid_api_key`

变量存在，但不是当前 endpoint 或代理认可的有效 key。让用户修复本机环境变量。

PowerShell TLS send error

如果 `Invoke-RestMethod` 报 `The underlying connection was closed`，使用本 skill 的 Python 脚本。

代理路径不确定

优先尝试归一化后的 `/v1/images/generations`。如果代理文档要求非 `/v1` 路由，再按文档调整。

模型不可用

保留用户明确要求的 `gpt-image-2`。如果官方 endpoint 或代理拒绝该模型，报告具体模型错误，并询问是否改用可用图片模型。
