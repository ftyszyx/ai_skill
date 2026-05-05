---
name: wechat-article
version: 1.0.0
description: "微信公众号文章发布：将飞书文档等内容迁移到微信公众号草稿箱，支持图片上传、代码块格式化、富文本排版。当用户需要将内容发布到微信公众号、编辑公众号文章、插入代码块/图片到公众号编辑器时触发。"
---

# 微信公众号文章发布

本技能指导如何通过 Chrome DevTools MCP 操作微信公众号后台编辑器，实现文章内容的完整迁移和发布。

## 前置条件

- Chrome DevTools MCP 已连接
- 已登录微信公众号后台（https://mp.weixin.qq.com）
- 如需迁移飞书文档，需安装 lark-cli 并完成认证

## 编辑器架构

微信公众号使用 **ProseMirror** 作为富文本编辑器。编辑器位于 `.ProseMirror` DOM 节点内。

### 关键行为

- ProseMirror 会 sanitize 通过 `execCommand('insertHTML')` 插入的 HTML
- 全局变量：`__MpEditor`（React 组件类）、`$EDITORUI`、`editorVarGlobal`
- 正文字数显示在 `uid` 对应 "正文字数" 的 StaticText 节点
- 草稿 ID 即 URL 中的 `appmsgid` 参数

### HTML 标签存活表

| 标签 | 是否保留 | 说明 |
|------|---------|------|
| `<h2>`, `<h3>` | ✅ 保留 | heading 标签存活，但 `<h1>` 不推荐使用 |
| `<p>` | ✅ 保留 | 行内 style 样式生效 |
| `<blockquote>` | ✅ 保留 | 引用块 |
| `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>` | ✅ 保留 | 表格完整存活 |
| `<div>` | ✅ 保留 | 行内 style 样式生效（用于代码块） |
| `<span>` | ✅ 保留 | 行内样式存活（用于代码高亮） |
| `<a>` | ✅ 保留 | 链接；会被加上 `class="normal_text_link"` |
| `<img>` | ✅ 保留 | `style` 属性保留；自动添加 `contenteditable="false"` |
| `<code>` | ✅ 保留 | 行内代码样式存活 |
| `<br>` | ✅ 保留 | 代码块换行必须用 `<br>` |
| `<strong>`, `<b>` | ✅ 保留 | 加粗 |
| `<ul>`, `<ol>`, `<li>` | ⚠️ 合并 | 相邻的 `<ul>` 会被 ProseMirror 合并为一个列表 |
| `<pre>` | ❌ 丢失 | 换行符被吃掉，改用 `<div>` + `<br>` |

### CSS 规则

- **仅行内 CSS 生效**：必须使用 `style="..."` 属性
- **外部/内嵌样式表不生效**：`<style>` 标签和外部 CSS 文件会被过滤
- **样式属性限制**：部分 CSS 属性可能被过滤，建议只用基础属性

## 内容插入

### 基本方法

通过 `execCommand('insertHTML')` 插入 HTML 内容：

```javascript
const pm = document.querySelector('.ProseMirror');
pm.focus();
document.execCommand('insertHTML', false, htmlString);
```

### 清空编辑器

```javascript
const pm = document.querySelector('.ProseMirror');
pm.focus();
const range = document.createRange();
range.selectNodeContents(pm);
const sel = window.getSelection();
sel.removeAllRanges();
sel.addRange(range);
document.execCommand('delete', false, null);
```

### 插入策略

1. **整篇文章一次性插入**：推荐使用单次 `insertHTML` 插入完整 HTML，避免多次调用导致的列表合并等问题
2. **避免 `<ul>/<li>`**：用 `<p style="padding-left:20px;">• 内容</p>` 替代，防止相邻列表被错位合并
3. **先验证 HTML**：可以用小段测试 HTML 验证标签存活情况后再完整插入

## 代码块

ProseMirror 会丢弃 `<pre><code>` 内的换行符，必须使用 `<div>` + `<br>` 方案：

```html
<div style="background:#282c34;color:#abb2bf;padding:16px;border-radius:8px;
  font-family:Consolas,Monaco,Courier New,monospace;font-size:13px;
  line-height:1.7;overflow-x:auto;margin:12px 0;">
<span style="color:#98c379;"># 注释</span><br>
命令内容<br>
</div>
```

颜色方案参考：
- 背景：`#282c34`（One Dark 风格）
- 注释：`#98c379`（绿色）
- 关键字：`#c678dd`（紫色）
- 字符串：`#98c379`（绿色）
- 函数/属性：`#56b6c2`（青色）
- 数值：`#d19a66`（橙色）

## 标题和排版

### 二级标题

```html
<h2 style="color:#1a73e8;border-bottom:2px solid #1a73e8;
  padding-bottom:8px;margin-top:24px;">标题文本</h2>
```

### 三级标题

```html
<h3 style="color:#333;margin-top:20px;">子标题</h3>
```

### 引用块

```html
<blockquote style="border-left:4px solid #1a73e8;padding:8px 16px;
  margin:12px 0;background:#f0f7ff;color:#555;">引用内容</blockquote>
```

### 正文段落

```html
<p style="color:#444;line-height:1.8;">正文内容</p>
```

### 行内代码

```html
<code style="background:#f0f0f0;padding:1px 4px;border-radius:3px;">code</code>
```

## 表格

ProseMirror 保留完整表格结构，支持 `<thead>` / `<tbody>` 语义标签：

```html
<table style="border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;">
  <thead>
    <tr style="background:#e8f0fe;">
      <th style="border:1px solid #ddd;padding:10px 12px;text-align:left;">列名</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="border:1px solid #ddd;padding:10px 12px;">数据</td>
    </tr>
  </tbody>
</table>
```

## 图片上传

### 上传机制

微信公众号使用隐藏的文件输入框上传图片到 `mmbiz.qpic.cn` CDN：

```javascript
// 找到隐藏的 file input
const fi = document.querySelector('input[type="file"][name="file"]');
```

### 上传流程

1. 点击编辑器工具栏的"图片"按钮，打开图片选择器
2. 使用 Chrome DevTools MCP 的 `upload_file` 工具将图片设置到隐藏的 file input
3. 派发 `change` 事件触发上传：

```javascript
const fi = document.querySelector('input[type="file"][name="file"]');
// upload_file MCP 工具设置文件后
fi.dispatchEvent(new Event('change', { bubbles: true }));
```

4. 等待上传完成（ProseMirror 自动插入图片节点）
5. 从 ProseMirror 中获取 CDN URL：

```javascript
const imgs = document.querySelectorAll('.ProseMirror img.rich_pages.wxw-img');
const urls = Array.from(imgs).map(img => img.src);
```

### 图片定位策略

每次点击"图片"按钮上传后，图片出现在光标位置。由于重复点击图片按钮比较繁琐，推荐采用 **"先上传收集 URL，再一次性 rebuild"** 策略：

1. 依次上传所有图片（每次需先点击工具栏"图片"按钮）
2. 记录每次上传后的 CDN URL（ProseMirror 中最新出现的 img）
3. 清空编辑器
4. 用 `<img>` 标签在正确位置引用 CDN URL，一次性插入完整 HTML

### 从飞书文档导出图片

```bash
# 1. 获取文档内容，提取 image token
lark-cli docs +fetch --doc "https://xxx.feishu.cn/wiki/Dg6R..." --format json

# 2. 下载图片到本地
lark-cli docs +media-download --token <image_token> --output ./img_name.png
```

图片 token 在飞书文档 markdown 中以 `<image token="QEFlbd..."/>` 形式出现。

## 完整发布工作流

### 1. 打开目标文章

导航到微信公众号后台的文章编辑页：
```
https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&appmsgid=<draft_id>&type=77&lang=zh_CN
```

### 2. 准备图片（如从飞书迁移）

```bash
# 获取文档 markdown，提取所有 image token
lark-cli docs +fetch --doc "https://xxx.feishu.cn/wiki/..." --format json

# 下载每张图片
lark-cli docs +media-download --token <token1> --output ./img1.png
lark-cli docs +media-download --token <token2> --output ./img2.png
```

### 3. 上传图片到微信 CDN

采用 CDN URL 收集策略（详见"图片上传"章节）：
1. 点击工具栏"图片"按钮 → upload_file → dispatchEvent('change') → 等待上传
2. 获取最新的 CDN URL
3. 重复直到所有图片上传完毕

### 4. 构建并插入文章 HTML

根据内容构建完整 HTML（遵循"内容插入"和"代码块"章节的格式规则），一次性插入：

```javascript
const pm = document.querySelector('.ProseMirror');
pm.focus();
// 清空
const range = document.createRange();
range.selectNodeContents(pm);
window.getSelection().removeAllRanges();
window.getSelection().addRange(range);
document.execCommand('delete', false, null);

// 构建并插入完整 HTML
const html = '<p style="text-align:center;"><img src="'+cdnUrl+'" ...></p>' +
  '<h2 style="color:#1a73e8;border-bottom:2px solid #1a73e8;...">标题</h2>' +
  // ... 完整文章
  '';
document.execCommand('insertHTML', false, html);
```

### 5. 保存草稿

点击"保存为草稿"按钮（uid 对应 "保存为草稿"），等待出现"已保存"提示。

### 6. 设置封面图（可选）

页面顶部的"编辑封面"区域需要单独上传封面图。封面图与正文内联图片是不同的上传入口。

### 7. 预览和发表

- **预览**：点击"预览"按钮，输入微信号发送到手机查看效果
- **发表**：确认无误后点击"发表"

## 常见问题

### 代码块没有换行

**原因**：ProseMirror 解析 `<pre><code>` 时会丢弃 `\n` 换行符。

**解决**：使用 `<div>` + `<br>` 替代。详见"代码块"章节。

### 子弹列表位置错乱

**原因**：ProseMirror 会合并相邻的 `<ul>` 元素，导致不同章节的列表项混在一起。

**解决**：用 `<p style="padding-left:20px;">• 内容</p>` 模拟列表，避免使用 `<ul>/<li>`。

### 标题样式不显示

**原因**：`<h1>` 标签可能被 ProseMirror 过滤。

**解决**：使用 `<h2>` 和 `<h3>`，并确保 style 属性是标准 CSS（用分号分隔，属性名无前缀）。

### 图片上传后出现重复

**原因**：微信的图片上传 handler 可能为每次上传生成 2 个 ProseMirror image 节点。

**解决**：上传阶段容忍重复；最终通过 `selectAll` + `delete` + 完整 HTML 重建来清理。

### 正文字数显示 0

**原因**：字数统计可能有延迟。

**解决**：保存草稿后会自动刷新；也可点击编辑器触发更新。

## 参考

- [ProseMirror 文档](https://prosemirror.net/docs/guide/)
- [微信公众号后台](https://mp.weixin.qq.com)
- 飞书文档迁移配合 [`lark-doc`](https://github.com/anthropics/claude-code) Skills
