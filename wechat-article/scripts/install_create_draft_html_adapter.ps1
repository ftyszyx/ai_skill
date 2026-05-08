param(
  [string]$OpenCliHome = "$env:USERPROFILE\.opencli"
)

$siteDir = Join-Path $OpenCliHome "clis\weixin"
New-Item -ItemType Directory -Force -Path $siteDir | Out-Null
$target = Join-Path $siteDir "create-draft-html.js"

@'
import { cli, Strategy } from '@jackwener/opencli/registry';
import { CommandExecutionError } from '@jackwener/opencli/errors';
import fs from 'node:fs';
import path from 'node:path';

const WEIXIN_DOMAIN = 'mp.weixin.qq.com';
const WEIXIN_HOME = 'https://mp.weixin.qq.com/';

async function getToken(page) {
  return page.evaluate(`(window.location.href.match(/token=(\\d+)/)||[])[1]`);
}

async function navigateToEditor(page) {
  await page.goto(WEIXIN_HOME);
  await page.wait(3);
  const token = await getToken(page);
  if (!token) throw new CommandExecutionError('Could not extract session token. Please log in to mp.weixin.qq.com');
  await page.goto(`https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&token=${token}&lang=zh_CN`);
  await page.wait(4);
  const hasTitle = await page.evaluate('!!document.querySelector("textarea#title")');
  if (!hasTitle) throw new CommandExecutionError('Article editor did not load. Session may have expired');
}

async function fillField(page, selector, value) {
  return page.evaluate(`(() => {
    var el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return { ok: false, reason: 'not found: ' + ${JSON.stringify(selector)} };
    el.focus();
    var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value');
    if (setter && setter.set) setter.set.call(el, ${JSON.stringify(value)});
    else el.value = ${JSON.stringify(value)};
    el.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${JSON.stringify(value)} }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.blur();
    return { ok: true };
  })()`);
}

async function fillHtmlContent(page, html) {
  return page.evaluate(`(async () => {
    function plainTextFromHtml(source) {
      var root = document.createElement('div');
      root.innerHTML = source;
      root.querySelectorAll('br').forEach(function(br) {
        br.replaceWith(document.createTextNode('\\n'));
      });
      root.querySelectorAll('p,section,div,h1,h2,h3,blockquote,li').forEach(function(el) {
        el.appendChild(document.createTextNode('\\n'));
      });
      return root.textContent.replace(/\\n{3,}/g, '\\n\\n').trim();
    }

    function editorMetrics(editor) {
      return {
        blocks: editor.querySelectorAll('p,section,h1,h2,h3,blockquote,li').length,
        sections: editor.querySelectorAll('section').length,
        paragraphs: editor.querySelectorAll('p').length,
        styled: editor.querySelectorAll('[style]').length,
        textLength: (editor.innerText || '').trim().length,
        htmlPreview: editor.innerHTML.slice(0, 500)
      };
    }

    var editors = Array.from(document.querySelectorAll('div[contenteditable="true"]'));
    var editor = editors.find(function(el) { return el.classList.contains('ProseMirror'); }) || editors[editors.length - 1];
    if (!editor) return { ok: false, reason: 'content editor not found' };
    editor.focus();
    var range = document.createRange();
    range.selectNodeContents(editor);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);

    var dt = new DataTransfer();
    dt.setData('text/html', ${JSON.stringify(html)});
    dt.setData('text/plain', plainTextFromHtml(${JSON.stringify(html)}));
    var pasteEvent = new ClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true
    });
    editor.dispatchEvent(pasteEvent);
    await new Promise(function(resolve) { setTimeout(resolve, 500); });

    var metrics = editorMetrics(editor);
    if (metrics.blocks < 2 || metrics.textLength === 0) {
      editor.focus();
      selection.removeAllRanges();
      range = document.createRange();
      range.selectNodeContents(editor);
      selection.addRange(range);
      document.execCommand('delete', false, null);
      document.execCommand('insertHTML', false, ${JSON.stringify(html)});
      editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertFromPaste' }));
      await new Promise(function(resolve) { setTimeout(resolve, 500); });
      metrics = editorMetrics(editor);
      metrics.fallback = 'execCommand';
    } else {
      metrics.fallback = '';
    }
    return { ok: metrics.textLength > 0 && metrics.blocks >= 2, metrics };
  })()`);
}

async function uploadContentImage(page, imagePath) {
  const absPath = path.resolve(imagePath);
  if (!fs.existsSync(absPath)) throw new CommandExecutionError(`Image not found: ${absPath}`);
  if (!page.setFileInput) throw new CommandExecutionError('Image upload requires Browser Bridge with CDP support');
  await page.evaluate(`(() => document.querySelector('#js_editor_insertimage')?.click())()`);
  await page.wait(1);
  await page.evaluate(`(() => {
    var items = document.querySelectorAll('.js_img_dropdown_menu .tpl_dropdown_menu_item');
    if (items[0]) items[0].click();
  })()`);
  await page.wait(1);
  await page.setFileInput([absPath], 'input[type="file"][name="file"]');
  await page.wait(8);
  const cdnCount = await page.evaluate(`(() => {
    var editor = document.querySelector('.ProseMirror') || document.querySelector('#ueditor_0');
    return editor ? editor.querySelectorAll('img[src*="mmbiz"]').length : 0;
  })()`);
  if (cdnCount === 0) throw new CommandExecutionError('Image did not upload to WeChat CDN');
}

async function selectCoverFromContent(page) {
  await page.evaluate('document.querySelector("#js_cover_description_area")?.scrollIntoView()');
  await page.wait(1);
  await page.evaluate('document.querySelector(".js_cover_btn_area")?.click()');
  await page.wait(1);
  await page.evaluate(`(() => {
    var target = '\\u4ece\\u6b63\\u6587\\u9009\\u62e9';
    var links = document.querySelectorAll('a.pop-opr__button');
    for (var i = 0; i < links.length; i++) {
      if ((links[i].textContent || '').trim() === target) { links[i].click(); return; }
    }
  })()`);
  await page.wait(2);
  await page.evaluate(`(() => {
    var img = document.querySelector('.weui-desktop-dialog_img-picker .appmsg_content_img');
    if (img) img.click();
  })()`);
  await page.wait(1);
  await page.evaluate(`(() => {
    var target = '\\u4e0b\\u4e00\\u6b65';
    var btns = document.querySelectorAll('.weui-desktop-dialog_img-picker button');
    for (var i = 0; i < btns.length; i++) {
      if ((btns[i].textContent || '').trim() === target && !btns[i].disabled) { btns[i].click(); return; }
    }
  })()`);
  for (let attempt = 0; attempt < 8; attempt++) {
    await page.wait(2);
    const ready = await page.evaluate(`(() => {
      var target = '\\u786e\\u8ba4';
      var btns = document.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) {
        if ((btns[i].textContent || '').trim() === target && btns[i].offsetHeight > 0 && !btns[i].disabled) return true;
      }
      return false;
    })()`);
    if (ready) break;
  }
  await page.evaluate(`(() => {
    var target = '\\u786e\\u8ba4';
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      if ((btns[i].textContent || '').trim() === target && btns[i].offsetHeight > 0 && !btns[i].disabled) { btns[i].click(); return; }
    }
  })()`);
  await page.wait(2);
}

async function clickSaveDraft(page) {
  const result = await page.evaluate(`(() => {
    var target = '\\u4fdd\\u5b58\\u4e3a\\u8349\\u7a3f';
    var btns = document.querySelectorAll('span, button, a');
    for (var i = 0; i < btns.length; i++) {
      if ((btns[i].textContent || '').trim() === target) { btns[i].click(); return { ok: true }; }
    }
    return { ok: false };
  })()`);
  if (!result?.ok) throw new CommandExecutionError('Save draft button not found');
  for (let attempt = 0; attempt < 5; attempt++) {
    await page.wait(2);
    const saved = await page.evaluate(`(() => {
      var el = document.querySelector('#js_save_success');
      if (el && window.getComputedStyle(el).display !== 'none') return true;
      return document.body.innerText.indexOf('\\u5df2\\u4fdd\\u5b58') >= 0;
    })()`);
    if (saved) return true;
  }
  return false;
}

cli({
  site: 'weixin',
  name: 'create-draft-html',
  description: '创建微信公众号图文草稿（正文使用 HTML 富文本插入）',
  domain: WEIXIN_DOMAIN,
  strategy: Strategy.COOKIE,
  browser: true,
  navigateBefore: false,
  timeoutSeconds: 180,
  args: [
    { name: 'html', required: true, positional: true, help: '文章 HTML 正文或 @html 文件路径' },
    { name: 'title', required: true, help: '文章标题 (最长64字)' },
    { name: 'author', help: '作者名 (最长8字)' },
    { name: 'cover-image', help: '封面图片路径 (会先上传到正文再设为封面)' },
    { name: 'summary', help: '文章摘要' },
  ],
  columns: ['status', 'detail'],
  func: async (page, kwargs) => {
    await navigateToEditor(page);
    const titleResult = await fillField(page, 'textarea#title', kwargs.title);
    if (!titleResult?.ok) throw new CommandExecutionError('Failed to fill title');
    if (kwargs.author) {
      const authorResult = await fillField(page, 'input#author', kwargs.author);
      if (!authorResult?.ok) throw new CommandExecutionError('Failed to fill author');
    }
    let html = kwargs.html;
    if (typeof html === 'string' && html.startsWith('@')) html = fs.readFileSync(path.resolve(html.slice(1)), 'utf8');
    const contentResult = await fillHtmlContent(page, html);
    if (!contentResult?.ok) throw new CommandExecutionError('Failed to fill HTML content');
    if (kwargs['cover-image']) {
      await uploadContentImage(page, kwargs['cover-image']);
      await selectCoverFromContent(page);
    }
    if (kwargs.summary) await fillField(page, 'textarea#js_description', kwargs.summary);
    const success = await clickSaveDraft(page);
    const metrics = contentResult.metrics || {};
    const metricText = `blocks=${metrics.blocks ?? 0}, styled=${metrics.styled ?? 0}${metrics.fallback ? ', fallback=' + metrics.fallback : ''}`;
    return [{ status: success ? 'draft saved' : 'save attempted, check browser to confirm', detail: `"${kwargs.title}" (html${kwargs['cover-image'] ? ', with cover' : ''}; ${metricText})` }];
  },
});
'@ | Set-Content -Encoding UTF8 $target

Write-Output $target
