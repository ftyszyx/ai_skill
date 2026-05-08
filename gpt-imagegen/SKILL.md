---
name: gpt-imagegen
description: 使用 gpt-image-2 通过 OpenAI Python SDK 和 Images API 流式生成栅格图片，默认 stream=true 且 partial_images=3。适用于用户要求用 gpt-image-2 创建、生成或保存图片，并要求从环境变量读取 API key 与 base URL，将最终图和 partial images 保存为工作区中的 PNG、JPEG 或 WebP 文件时。
---

# GPT Imagegen

## 快速开始

使用 `scripts/generate_image.py` 执行稳定可复用的图片生成流程。脚本会从环境变量读取 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`，不会打印密钥，也不会内置任何固定代理地址。`BASE_URL` 可作为 `OPENAI_BASE_URL` 的兼容别名。

脚本默认使用官方文档里的流式生成方式：`stream=True`，`partial_images=3`。生成过程中会保存 partial images，结束后把最终图写到 `--out`。

依赖 OpenAI Python SDK：

```powershell
python -m pip install --upgrade openai
```

用户需要先在本机配置环境变量：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "你的 API key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "你的 OpenAI 兼容 API base URL", "User")
```

当前 PowerShell 会话需要立即生效时：

```powershell
$env:OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
$env:OPENAI_BASE_URL = [Environment]::GetEnvironmentVariable("OPENAI_BASE_URL", "User")
```

生成图片：

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "一只可爱的毛茸茸小猫坐在阳光照进来的窗边，写实风格，无文字，无水印" `
  --out E:\path\to\output.png
```

脚本默认值：

- `model`: `gpt-image-2`
- `base-url`: 从 `OPENAI_BASE_URL` 读取；兼容 `BASE_URL`
- `api-key`: 从 `OPENAI_API_KEY` 读取
- `background`: `auto`
- `size`: `1024x1024`
- `quality`: `medium`
- `stream`: `true`
- `partial_images`: `3`
- `output-format`: 从 `--out` 后缀推断；无法推断时使用 `png`

## 工作流程

1. 只有在关键信息缺失时才追问用户；否则根据用户请求整理一个清晰、得体的图片 prompt。
2. 在当前工作区中选择输出路径，通常使用 `output/imagegen/<描述性文件名>.png`。
3. 确认用户已在环境变量中配置 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。不要要求用户把 key 发到聊天里，也不要打印 key。
4. 优先使用本 skill 自带脚本和 OpenAI Python SDK，不要重复手写 HTTP 请求代码。
5. 不要把真实 base URL 或 API key 写入 skill、脚本、仓库文件或聊天记录。若必须临时覆盖 base URL，可使用 `--base-url`，但长期配置仍应放在环境变量中。
6. 默认保留流式 partial images：`<输出文件名>-partial-<索引>.<后缀>`。如果用户不需要中间图，可传 `--no-save-partials`。
7. 生成完成后，尽可能用图片查看工具检查输出图片是否正常。
8. 最终回复中给出最终图和 partial images 的绝对路径；如果客户端支持本地图片渲染，同时展示最终图。

## 常用命令

使用环境变量中的 base URL 生成图片：

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "一张高质量写实小猫肖像，小猫坐在窗边，温暖自然光，无文字，无水印" `
  --out E:\opensource\mywork\my_image\output\imagegen\kitten.png
```

指定保存 partial images 的目录：

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "一只小猫坐在窗边，柔和自然光，无文字，无水印" `
  --out E:\opensource\mywork\my_image\output\imagegen\kitten.png `
  --partials-dir E:\opensource\mywork\my_image\output\imagegen\partials
```

使用 prompt 文件生成长提示词图片：

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt-file E:\path\to\prompt.txt `
  --out E:\path\to\image.png `
  --quality high
```

生成透明背景 PNG：

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "一个干净的产品贴纸图标，主体完整居中，无文字，无水印" `
  --background transparent `
  --output-format png `
  --out E:\path\to\sticker.png
```

只预览请求，不真正发送 API 调用：

```powershell
python <skill-dir>\scripts\generate_image.py --prompt "test kitten" --out E:\tmp\kitten.png --dry-run
```

临时关闭流式生成：

```powershell
python <skill-dir>\scripts\generate_image.py --prompt "一只小猫" --out E:\tmp\kitten.png --no-stream
```

如需使用非默认环境变量名：

```powershell
python <skill-dir>\scripts\generate_image.py `
  --api-key-env MY_IMAGE_API_KEY `
  --base-url-env MY_IMAGE_BASE_URL `
  --prompt "一只小猫" `
  --out E:\tmp\kitten.png
```

## Prompt 编写规则

保持 prompt 具体、清晰、适合生产使用：

- 写明主体、风格或媒介、构图、光线、氛围、输出限制和需要避免的元素。
- 除非用户明确要求图片中包含文字，否则加入 `无文字，无水印`。
- 如果用户要求图片里出现特定文字，逐字引用，并要求精确拼写。
- 涉及人物时，避免性化表达；年龄敏感请求必须明确为成年人，并保持非露骨、非性化。
- 如果任务涉及参考图或图片编辑，本脚本不够用；应改用当前可用的图片编辑工作流或 API。

## 故障排查

遇到以下情况时，读取 `references/api-workflow.md`：

- `OPENAI_BASE_URL` 或 `OPENAI_API_KEY` 不可见。
- 缺少或需要升级 `openai` Python 包。
- 代理 base URL 调用失败，或需要确认 endpoint 拼接方式。
- 流式事件没有返回 `b64_json`。
- OpenAI 官方接口和代理支持的模型或参数不一致。

常见修复：

- 如果缺少 `OPENAI_API_KEY` 或 `OPENAI_BASE_URL`，让用户在本机设置环境变量并重启 shell，或为当前进程设置环境变量。
- 如果报缺少 `openai` 包，运行 `python -m pip install --upgrade openai`。
- 如果 PowerShell 的 `Invoke-RestMethod` 出现 TLS send error，优先使用本 skill 的 Python 脚本。
- 如果代理同时支持 `/v1/images/generations` 和 `/images/generations`，优先使用脚本默认的 `/v1` 归一化方式。
