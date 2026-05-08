#!/usr/bin/env python3
"""Convert Markdown/plain article text to WeChat-friendly inline HTML."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


STYLE = {
    "article": "font-size:16px;line-height:1.9;color:#2b2f36;letter-spacing:.02em;",
    "p": "margin:0 0 18px 0;line-height:1.9;font-size:16px;color:#2b2f36;letter-spacing:.02em;",
    "h2": "margin:34px 0 16px;padding-left:12px;border-left:4px solid #0f7cff;font-size:20px;line-height:1.45;color:#111827;font-weight:700;",
    "blockquote": "margin:18px 0;padding:12px 16px;border-left:4px solid #d0d7de;background:#f6f8fa;color:#4b5563;line-height:1.8;",
    "ul": "margin:0 0 18px 0;padding-left:1.2em;",
    "li": "margin:0 0 8px;",
    "hr": "margin:30px auto;border:0;border-top:1px solid #e5e7eb;",
    "strong": "font-weight:700;color:#111827;",
    "img": "display:block;width:100%;height:auto;margin:18px auto;border-radius:6px;",
    "callout": "margin:18px 0;padding:14px 16px;border-left:4px solid #0f7cff;background:#f5f8ff;color:#374151;border-radius:4px;line-height:1.8;",
    "code": "margin:16px 0;padding:14px 16px;background:#1f2937;color:#e5e7eb;border-radius:6px;font-size:13px;line-height:1.7;font-family:Consolas,Monaco,'Courier New',monospace;white-space:pre-wrap;word-break:break-word;",
    "inline_code": "background:#f3f4f6;color:#d97706;padding:1px 4px;border-radius:3px;font-family:Consolas,Monaco,'Courier New',monospace;",
}


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", rf'<strong style="{STYLE["strong"]}">\1</strong>', text)
    text = re.sub(r"`([^`]+)`", rf'<code style="{STYLE["inline_code"]}">\1</code>', text)
    return text


def render_callout(lines: list[str], emoji: str = "") -> str:
    text = "<br/>".join(inline(line.strip()) for line in lines if line.strip())
    prefix = f"{html.escape(emoji)} " if emoji else ""
    return f'<section style="{STYLE["callout"]}">{prefix}{text}</section>'


def render_code(lines: list[str]) -> str:
    escaped = "<br/>".join(html.escape(line) for line in lines)
    return f'<section style="{STYLE["code"]}">{escaped}</section>'


def render_blocks(markdown: str, drop_first_title: bool = False, drop_first_image: bool = False) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    callout: list[str] | None = None
    callout_emoji = ""
    code: list[str] | None = None
    list_open = False
    first_title_dropped = False
    first_image_dropped = False

    def close_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = "<br/>".join(inline(part.strip()) for part in paragraph if part.strip())
            if text:
                out.append(f'<section style="{STYLE["p"]}">{text}</section>')
        paragraph = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    for raw in lines:
        line = raw.strip()

        if code is not None:
            if line.startswith("```"):
                out.append(render_code(code))
                code = None
            else:
                code.append(raw.rstrip("\n"))
            continue

        if callout is not None:
            if line.startswith("</callout"):
                out.append(render_callout(callout, callout_emoji))
                callout = None
                callout_emoji = ""
            elif line:
                callout.append(line)
            continue

        if line.startswith("```"):
            close_paragraph()
            close_list()
            code = []
            continue

        callout_match = re.match(r"<callout\b([^>]*)>", line)
        if callout_match:
            close_paragraph()
            close_list()
            emoji_match = re.search(r'emoji="([^"]+)"', callout_match.group(1))
            callout_emoji = emoji_match.group(1) if emoji_match else ""
            callout = []
            continue

        if not line:
            close_paragraph()
            close_list()
            continue

        image_match = re.match(r"!\[[^\]]*\]\(([^)]+)\)", line)
        if image_match:
            close_paragraph()
            close_list()
            if drop_first_image and not first_image_dropped:
                first_image_dropped = True
                continue
            src = html.escape(image_match.group(1), quote=True)
            out.append(f'<img src="{src}" style="{STYLE["img"]}"/>')
            continue

        if line.startswith("# "):
            if drop_first_title and not first_title_dropped:
                first_title_dropped = True
                continue
            close_paragraph()
            close_list()
            out.append(f'<h1 style="font-size:24px;line-height:1.4;margin:0 0 22px;color:#111827;">{inline(line[2:].strip())}</h1>')
            continue

        if line.startswith("## "):
            close_paragraph()
            close_list()
            out.append(f'<h2 style="{STYLE["h2"]}">{inline(line[3:].strip())}</h2>')
            continue

        if line.startswith("> "):
            close_paragraph()
            close_list()
            out.append(f'<blockquote style="{STYLE["blockquote"]}">{inline(line[2:].strip())}</blockquote>')
            continue

        if line in {"---", "***", "___"}:
            close_paragraph()
            close_list()
            out.append(f'<hr style="{STYLE["hr"]}"/>')
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            close_paragraph()
            if not list_open:
                out.append(f'<ul style="{STYLE["ul"]}">')
                list_open = True
            out.append(f'<li style="{STYLE["li"]}">{inline(bullet.group(1))}</li>')
            continue

        paragraph.append(line)

    close_paragraph()
    close_list()
    if code is not None:
        out.append(render_code(code))
    if callout is not None:
        out.append(render_callout(callout, callout_emoji))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Markdown to inline-styled WeChat HTML.")
    parser.add_argument("input", help="Input Markdown/text file")
    parser.add_argument("output", help="Output HTML file")
    parser.add_argument("--drop-first-title", action="store_true", help="Drop the first # title from body")
    parser.add_argument("--drop-first-image", action="store_true", help="Drop the first Markdown image from body when using --cover-image")
    args = parser.parse_args()

    source = Path(args.input)
    target = Path(args.output)
    markdown = source.read_text(encoding="utf-8-sig")
    body = render_blocks(markdown, args.drop_first_title, args.drop_first_image)
    target.write_text(f'<section style="{STYLE["article"]}">\n{body}\n</section>\n', encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
