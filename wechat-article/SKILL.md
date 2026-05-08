---
name: wechat-article
description: "当需要通过 OpenCLI 处理微信公众号文章时使用：从本地 Markdown/HTML 或飞书/Lark 文档创建带样式的 mp.weixin.qq.com 草稿、上传前转换为公众号友好的 HTML、下载公众号文章、查看草稿、设置封面图，以及排查 OpenCLI 浏览器登录、桥接和 HTML 样式丢失问题。"
---

# 微信公众号文章

使用 `opencli weixin` 处理微信公众号文章。当前流程只创建或检查草稿，不执行群发/发表。

上传文章前，必须先把正文转换成公众号友好的 HTML，并优化内联样式。除非用户明确要求纯文本草稿，否则不要直接上传原始 Markdown。

## 先检查命令

不要假设本机安装的适配器版本，先看实时 help：

```bash
opencli weixin create-draft --help
opencli weixin create-draft-html --help
opencli weixin download --help
opencli weixin drafts --help
```

如果缺少 `create-draft-html`，从本 skill 安装本地适配器：

```powershell
powershell -ExecutionPolicy Bypass -File .\wechat-article\scripts\install_create_draft_html_adapter.ps1
opencli validate weixin/create-draft-html
```

内置的 `opencli weixin create-draft` 会用 `insertText` 插入正文，HTML 标签可能变成纯文本。带样式草稿优先使用 `create-draft-html`。

`create-draft-html` 必须通过富文本粘贴路径写入微信的 ProseMirror 编辑器：派发 `ClipboardEvent('paste')`，同时携带 `text/html` 和 `text/plain`，让 ProseMirror 自己解析 HTML。不要把裸 `document.execCommand('insertHTML')` 当主上传路径；它可能让编辑器看起来填上了内容，但保存后重新打开会变成没有可靠换行和样式的一整段纯文本。

## 前置条件

创建或查看草稿前，先检查浏览器桥接：

```bash
opencli doctor
```

如果扩展未连接，让用户打开 Chrome 并启用/连接 OpenCLI 扩展，然后重跑 `opencli doctor`。

如果创建草稿失败并提示 `Could not extract session token`，打开微信公众号后台让用户登录：

```bash
opencli browser open "https://mp.weixin.qq.com" --focus
opencli browser get url
```

登录后的 URL 应包含 `token=<number>`。

## 转换为带样式 HTML

先准备本地 Markdown 正文，再转换：

```powershell
python .\wechat-article\scripts\md_to_wechat_html.py `
  .\wechat-article-content.md `
  .\wechat-article-content.html `
  --drop-first-title `
  --drop-first-image
```

当标题已经通过 `--title` 传给公众号草稿时，使用 `--drop-first-title`。
当同一张图已经通过 `--cover-image` 作为封面上传时，使用 `--drop-first-image`，避免正文重复出现封面图。

转换器会输出带内联 CSS 的 `<section>` 结构，适配微信编辑器：正文有字号和行高，标题、引用、列表、图片、分隔线、加粗等都有基础样式。

段落优先使用 `<section style="...">`，不要只依赖弱样式的 `<p>`。每个段落块都应显式包含 `line-height`、`font-size`、`color`、`margin` 等内联样式，微信编辑器更容易保留。

## 创建带样式草稿

优先把生成的 HTML 文件传给 `opencli weixin create-draft-html`：

```powershell
opencli weixin create-draft-html `
  --title "Title" `
  --summary "Summary" `
  --cover-image ".\cover.png" `
  -f json `
  "@.\wechat-article-content.html"
```

使用 `@path` 传 HTML 文件，避免命令行引号、换行和长度问题。

`create-draft-html` 的返回结果应包含非零的富文本指标，例如 `blocks=68, styled=67`。只有 `draft saved` 但没有块数量和样式数量，不足以证明样式上传成功。

## 纯文本兜底

只有在 `create-draft-html` 不可用或明确要纯文本时，才使用内置 `create-draft`：

```bash
opencli weixin create-draft "<content>" \
  --title "Title" \
  --author "Author" \
  --summary "Summary" \
  --cover-image ".\cover.png" \
  -f json
```

注意：

- `--title` 必填，最长 64 字符。
- `--author` 可选，用户未提供时不要自行编造。
- `--summary` 可选。
- `--cover-image` 必须是真实存在的本地图片路径。适配器会先把它上传到正文，再从正文图片中设为封面。
- 这个兜底路径会用 `insertText` 插入正文，Markdown 或 HTML 可能变成纯文本。创建后必须检查微信编辑器。

## 从飞书/Lark 文档创建草稿

源文档是飞书/Lark 时，先用 `lark-doc` 拉取 Markdown：

```bash
lark-cli docs +fetch --api-version v2 \
  --doc "<feishu-doc-or-wiki-url>" \
  --doc-format markdown \
  --detail simple
```

推荐流程：

1. 提取 `data.document.content`。
2. 保存为本地 `.md` 文件，避免命令行转义和长度问题。
3. 用 `scripts/md_to_wechat_html.py` 转成带样式 `.html`。
4. 如果同时传 `--cover-image`，转换时加 `--drop-first-image`，避免正文重复封面图。
5. 把 HTML 文件传给 `opencli weixin create-draft-html`。

PowerShell 示例：

```powershell
$json = lark-cli docs +fetch --api-version v2 --doc "<feishu-url>" --doc-format markdown --detail simple | ConvertFrom-Json
$content = $json.data.document.content
Set-Content -Encoding UTF8 .\wechat-article-content.md $content

python .\wechat-article\scripts\md_to_wechat_html.py `
  .\wechat-article-content.md `
  .\wechat-article-content.html `
  --drop-first-title `
  --drop-first-image

opencli weixin create-draft-html `
  --title "Title" `
  --cover-image ".\cover.png" `
  -f json `
  "@.\wechat-article-content.html"
```

## 下载已有公众号文章

用 `opencli weixin download` 把已有公众号文章导出为 Markdown：

```bash
opencli weixin download --url "https://mp.weixin.qq.com/s/..." --output ".\weixin-articles" --download-images true -f json
```

迁移旧文章时，可把下载得到的 Markdown 作为重新创建草稿的来源。

## 验证结果

创建草稿后，先查看草稿箱：

```bash
opencli weixin drafts --limit 5 -f json
```

向用户报告草稿标题和更新时间。

对样式敏感的 HTML 草稿，必须重新打开最新草稿，在微信编辑器里检查 `.ProseMirror`：

```bash
opencli browser eval "(()=>({blocks:document.querySelector('.ProseMirror')?.querySelectorAll('p,section,h1,h2,h3,blockquote,li').length||0,styled:document.querySelector('.ProseMirror')?.querySelectorAll('[style]').length||0,text:document.querySelector('.ProseMirror')?.innerText.slice(0,200)||''}))()"
```

健康的带样式文章重新打开后，应该有较多 block 节点和较多带 `style` 的节点。如果 `.ProseMirror.innerText` 有整篇文章，但 `blocks` 或 `styled` 接近 0，说明上传实际上变成了纯文本；应使用修复后的 `create-draft-html` 重新创建草稿。

## 常见故障

- `Browser Bridge extension not connected`：运行 `opencli doctor`；用户需要连接 OpenCLI Chrome 扩展。
- `Unknown command create-draft-html`：运行 `scripts/install_create_draft_html_adapter.ps1`，再执行 `opencli validate weixin/create-draft-html`。
- `Could not extract session token`：用户未登录 `mp.weixin.qq.com`；用 `opencli browser open "https://mp.weixin.qq.com" --focus` 打开后台登录。
- `Image not found`：检查当前工作目录下的 `--cover-image` 路径是否存在。
- HTML 标签直接显示在正文里：使用了纯文本 `create-draft`；改用 `create-draft-html` 重新创建。
- 上传后没有换行或没有样式：HTML 可能通过裸 `insertHTML` 或 `insertText` 插入，而不是 ProseMirror 富文本粘贴。重新安装 `scripts/install_create_draft_html_adapter.ps1`，重新生成 HTML，重新创建草稿，并验证重新打开后的 `blocks>1` 和 `styled>1`。
- `Article editor did not load`：登录可能过期；手动打开微信公众号后台后重试。
