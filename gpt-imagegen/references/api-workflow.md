# gpt-image-2 流式图片生成流程

官方文档：https://developers.openai.com/api/docs/guides/tools-image-generation





## 环境变量

必须由用户在本机配置：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "你的 API key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "你的 OpenAI 兼容 API base URL", "User")
```

`BASE_URL` 可作为 `OPENAI_BASE_URL` 的兼容别名。推荐统一使用 `OPENAI_BASE_URL`。

不要把真实 API key 或 base URL 写入 skill、脚本、仓库文件或聊天记录。

## 依赖

流式图片生成使用 OpenAI Python SDK：

```powershell
python -m pip install --upgrade openai
```

## SDK base URL

脚本使用 OpenAI Python SDK：

```python
client = OpenAI(api_key=api_key, base_url=sdk_base_url)
```

脚本会把 base URL 归一化成 SDK 期望的 API 根路径：

- `https://host/path` -> `https://host/path/v1`
- `https://host/path/v1` -> `https://host/path/v1`

如果代理文档明确要求非 `/v1` 路径，需要按代理文档调整脚本或临时传入合适的 `--base-url`。

## 流式请求

除非用户要求不同尺寸、质量或格式，否则使用流式 payload：

```json
{
  "model": "gpt-image-2",
  "prompt": "A concise production-quality image prompt.",
  "background": "auto",
  "size": "1024x1024",
  "quality": "medium",
  "output_format": "png",
  "stream": true,
  "partial_images": 3
}
```

官方文档说明 image generation 支持在最终结果生成前流式返回 partial images，`partial_images` 可设为 1-3。本 skill 默认使用最大值 `3`。

## 图片生成配置项

官方 Images reference 中与本 skill 相关的请求配置和流式事件字段：

| 字段 | 类型/取值 | 用途 |
| --- | --- | --- |
| `background` | `transparent`, `opaque`, `auto` | 请求图片的背景设置。需要透明图时使用 `transparent`，并优先搭配 `output_format=png` 或 `webp`。 |
| `output_format` | `png`, `webp`, `jpeg` | 请求图片的输出格式。脚本可从 `--out` 后缀推断，也可用 `--output-format` 显式指定。 |
| `quality` | `low`, `medium`, `high`, `auto` | 请求图片的质量设置。草图用 `low`，常规结果用 `medium`，最终资产可用 `high` 或 `auto`。 |
| `size` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | 请求图片的尺寸。正方形通常更快；竖图用 `1024x1536`，横图用 `1536x1024`。 |
| `partial_images` | `1`, `2`, `3` | 流式生成时请求返回的 partial image 数量。本 skill 默认 `3`。 |
| `partial_image_index` | number | partial image 的 0-based 索引，来自 `image_generation.partial_image` 事件。 |
| `created_at` | number | 事件创建时的 Unix timestamp，来自流式事件元数据。 |

脚本参数对应关系：

| 脚本参数 | 默认值 |
| --- | --- |
| `--background` | `auto` |
| `--output-format` | 从 `--out` 推断，无法推断时为 `png` |
| `--quality` | `medium` |
| `--size` | `1024x1024` |
| `--partial-images` | `3` |

使用 OpenAI 官方 endpoint 或变更参数时，优先核对当前官方文档：

- `https://platform.openai.com/docs/api-reference/images/create`
- `https://platform.openai.com/docs/guides/image-generation`
- `https://developers.openai.com/api/reference/resources/images`

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

## 流式响应处理

核心事件：

- `image_generation.partial_image`: 包含 `partial_image_index` 和 `b64_json`。

脚本行为：

1. 每收到一个 partial image，就保存为 `<输出文件名>-partial-<索引>.<后缀>`。
2. 如果 SDK 返回非 partial 的 `b64_json` 事件，把它视为最终图。
3. 如果流结束时没有独立最终图事件，则用最后收到的一张图片写入 `--out`，避免没有最终文件。
4. 如果完全没有收到任何图片字节，停止并报错。

`--no-stream` 回退模式仍接受两种常见非流式响应：

- `data[0].b64_json`: base64 解码后写入输出路径。
- `data[0].url`: 下载图片 URL 后写入输出路径。

## 故障排查

`OPENAI_BASE_URL is missing`

用户没有在环境变量中配置 base URL，或当前进程读不到。让用户设置 `OPENAI_BASE_URL`，或确认 Windows 用户环境变量已写入。

`OPENAI_API_KEY is missing`

用户没有在环境变量中配置 API key，或当前进程读不到。让用户在本机设置环境变量，不要让用户把 key 发到聊天里。

`The openai Python package is required`

未安装或版本过旧。运行：

```powershell
python -m pip install --upgrade openai
```

`invalid_api_key`

变量存在，但不是当前 endpoint 或代理认可的有效 key。让用户修复本机环境变量。

PowerShell TLS send error

如果 `Invoke-RestMethod` 报 `The underlying connection was closed`，使用本 skill 的 Python SDK 脚本。

代理路径不确定

优先尝试归一化后的 `/v1/images/generations`。如果代理文档要求非 `/v1` 路由，再按文档调整。

模型不可用

保留用户明确要求的 `gpt-image-2`。如果官方 endpoint 或代理拒绝该模型，报告具体模型错误，并询问是否改用可用图片模型。
