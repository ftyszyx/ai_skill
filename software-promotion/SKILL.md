---
name: software-promotion
description: "当用户要推广软件、独立产品、落地页或开源/商业工具，并希望使用 OpenCLI、浏览器或 GitHub CLI 到知乎、V2EX、掘金、小红书、B站、GitHub 等平台发布草稿、投稿、自荐或创建推广仓库时使用。重点覆盖中文软件推广、多平台草稿制作、登录态检查、封面/素材处理、合规边界和反垃圾发布。"
---

# 软件推广

面向中文软件、独立产品、工具网站和桌面应用的推广执行流程。目标是帮用户把推广内容变成可审核的草稿、合规投稿或自有推广资产，而不是批量制造垃圾信息。

## 基本原则

- 先确认产品落地页、目标受众、允许平台、账号状态、发布方式和是否需要用户审核。
- 用户要求“保存草稿待审核”时，只创建草稿或打开已填好的发布页，不替用户点最终发布。
- 平台未登录时，打开登录页并让用户登录；不要要求用户把账号密码发到聊天里。
- 公开发布、评论、issue、私信、群发都必须看平台规则和上下文；不向无关帖子、无关 issue 或竞品仓库塞广告。
- 明确区分“工具能自动化”和“这个目标是否适合发布”。工具可用不等于允许发。
- 推广文案要真实、克制、可验证。不要夸大功能、伪装成第三方评价，也不要隐藏自荐身份。

## 快速流程

1. 收集基础信息：产品名、官网/落地页、价格/购买页、核心功能、截图/封面图、目标用户、希望投放的平台。
2. 生成平台素材：为每个平台准备标题、正文、摘要、标签、封面建议和落地页链接。
3. 检查工具和登录态：
   - 运行 `opencli list -f json` 确认相关适配器。
   - 对具体平台运行 `opencli <site> --help` 和 `opencli <site> <command> --help`。
   - 需要浏览器登录态时运行 `opencli doctor`，失败则让用户打开对应站点登录。
4. 逐个平台执行：优先创建草稿；如果平台没有草稿能力，则打开已填内容的页面或保存本地草稿给用户手动发布。
5. 每个平台完成后记录结果：草稿地址、已填页面、失败原因、需要用户手动处理的封面/图片路径。
6. GitHub 推广走合规路线：优先自有 repo、README、Release、Discussions、明确接受投稿的周刊/awesome/list 仓库；不在无关项目 issue 里发广告。

## 本地素材目录

在当前产品仓库中创建 `promotion_drafts/`，每个平台一个 Markdown 文件：

```text
promotion_drafts/
├── platform_plan.md
├── zhihu_article.md
├── v2ex_topic.md
├── juejin_article.md
├── xiaohongshu_note.md
├── bilibili_video_script.md
├── github_discussion.md
└── github_<target>_issue.md
```

如果用户给了截图或官网已有截图，优先使用真实产品截图。若要引用本地图片，记录绝对路径；若平台上传受限，明确告诉用户手动选择哪张图。

## 平台处理规则

### 知乎

- 适合长文：问题背景、使用场景、功能清单、截图、注意事项、官网链接。
- 标题不要像硬广，优先围绕真实需求，例如“如何把个人微博内容备份到本地？”
- 若 DraftJS/富文本编辑器无法直接写入，使用浏览器模拟粘贴或 `execCommand('insertText')`；写完必须检查正文是否真的进入编辑器。
- 封面上传经常受浏览器文件输入限制。失败时保留草稿并告知用户手动上传封面图片路径。

### V2EX

- 适合发在 `share`、`create`、`tools` 等合适节点。
- 文案要短，说明“自荐/做了一个工具”、解决什么问题、链接和截图，不要营销腔。
- 用户要求草稿时，只填好页面或保存 Markdown，让用户自己点发布。

### 掘金

- 适合偏技术/产品实现/工具使用教程的长文。
- 写入后必须检查编辑器正文是否为空；有些编辑器仅改 textarea 不会同步内部状态。
- 若正文为空，用编辑器实例、粘贴事件或平台支持的 Markdown 导入方式修正。

### 小红书

- 适合口语化短内容：痛点、结果、截图、标签。
- 自动化可能误触发布或进入审核页；除非用户明确要求立即发布，否则只填草稿并停在确认前。
- 图片/封面优先用真实产品图，标题和正文要避免夸张承诺。

### B站

- 优先准备视频脚本、标题、简介、分镜和标签。
- 如果没有现成视频，不要假装已投稿；输出脚本和发布素材，或等待用户提供视频文件。

### GitHub

GitHub 是开发者可搜索资产，优先做以下合规动作：

- 为产品创建自有 public repo，README 放产品介绍、官网、截图、关键词、免费激活码或试用说明。
- 设置 repo description 和 topics，覆盖中英文关键词。
- 向明确欢迎投稿的仓库提交 issue 或 PR，例如周刊、资源清单、awesome/list；提交前检查 README、CONTRIBUTING、issue 列表和现有投稿格式。
- 如果目标仓库不接受商业/闭源项目，或要求开源项目，不要投。
- 不向微博爬虫、竞品工具、无关开源项目 issue 里发推广。

创建自有推广仓库示例：

```powershell
$repo = "weibo-backup-free-codes"
$dir = "D:\work\github\$repo"
New-Item -ItemType Directory -Path $dir
Set-Location $dir
git init
# 用 apply_patch 写 README.md，包含官网、截图、关键词、激活码
git add README.md
git commit -m "Add product promotion README"
gh repo create "ftyszyx/$repo" --public --source . --remote origin --push --description "微博备份、微博导出、Weibo backup and personal archive tool"
gh api --method PUT "repos/ftyszyx/$repo/topics" -H "Accept: application/vnd.github+json" -f names[]=weibo -f names[]=weibo-backup -f names[]=weibo-archive -f names[]=weibo-export
```

GitHub 投稿 issue 示例标题：

```text
【工具自荐】微博克隆器：把个人微博内容备份到本地的 Windows 工具
```

投稿正文要包含：项目地址、解决的问题、适用场景、当前能力、截图、使用建议。语气保持自荐透明，不伪装路人推荐。

## OpenCLI 使用要点

每次操作前按实时命令为准：

```powershell
opencli list -f json
opencli <site> --help
opencli <site> <command> --help
```

浏览器依赖命令失败时：

```powershell
opencli doctor
opencli browser open "https://目标网站"
```

当适配器行为异常时，不要反复盲试。保存当前素材和错误信息，改用浏览器手动填表、GitHub CLI、或把草稿文件交给用户审核。

## 封面和截图

- 优先使用产品真实截图，不要用无关图。
- 如果已有官网截图 URL，先用 `Invoke-WebRequest -Method Head` 检查是否可访问。
- 如果平台无法自动上传封面，回复用户时给出本地绝对路径和建议选择的图片。
- 对 GitHub README，优先使用可公开访问的图片 URL，例如官网静态图。

## 输出与汇报

每完成一个平台，简短汇报：

- 平台和动作：已创建草稿 / 已打开待提交页面 / 已发布 / 已跳过
- 链接或本地草稿路径
- 需要用户审核或手动补充的事项

遇到不合规目标时，直接说明原因并给替代路线，例如自有 repo、周刊投稿、Discussions 或官方社区展示区。

## 常见故障

- 正文为空：富文本编辑器内部状态未同步，重新用粘贴事件或编辑器 API 写入并检查页面文本。
- 封面未上传：文件输入受限，保留草稿并提供本地图片路径让用户手选。
- GitHub API 超时：先确认 repo 是否已创建和 push；topics/description 可重试，避免重复建仓库。
- 用户给的激活码数量和描述不一致：如实按已给数量发布，并提示可后续追加。
