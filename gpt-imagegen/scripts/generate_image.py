#!/usr/bin/env python3
"""Generate an image with gpt-image-2 through an OpenAI-compatible Images API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def read_windows_user_env(name: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value) if value else None
    except OSError:
        return None


def get_env(name: str) -> str | None:
    return os.environ.get(name) or read_windows_user_env(name)


def get_base_url(primary_env: str) -> str | None:
    return get_env(primary_env) or (get_env("BASE_URL") if primary_env != "BASE_URL" else None)


def build_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/images/generations"
    return base + "/v1/images/generations"


def infer_format(out_path: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    suffix = out_path.suffix.lower().lstrip(".")
    if suffix in {"png", "jpeg", "jpg", "webp"}:
        return "jpeg" if suffix == "jpg" else suffix
    return "png"


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt and args.prompt_file:
        raise SystemExit("Use either --prompt or --prompt-file, not both.")
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    raise SystemExit("Missing --prompt or --prompt-file.")


def post_json(url: str, payload: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Response was not JSON: {raw[:500]}") from exc


def download_url(url: str, timeout: int) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Image download failed: {exc.reason}") from exc


def write_image(data: dict[str, Any], out_path: Path, timeout: int) -> None:
    try:
        item = data["data"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit("Unexpected response JSON: " + json.dumps(data)[:1000]) from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if item.get("b64_json"):
        out_path.write_bytes(base64.b64decode(item["b64_json"]))
        return

    if item.get("url"):
        out_path.write_bytes(download_url(item["url"], timeout))
        return

    raise SystemExit("Response did not include data[0].b64_json or data[0].url.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an image with gpt-image-2.")
    parser.add_argument("--prompt", help="Image prompt text.")
    parser.add_argument("--prompt-file", help="UTF-8 text file containing the image prompt.")
    parser.add_argument("--out", required=True, help="Output image path.")
    parser.add_argument("--base-url", help="API base URL override. Prefer configuring an environment variable.")
    parser.add_argument("--base-url-env", default="OPENAI_BASE_URL", help="Environment variable that stores the API base URL.")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", default="medium")
    parser.add_argument("--output-format", choices=["png", "jpeg", "webp"], default=None)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--dry-run", action="store_true", help="Print request metadata without sending.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)
    prompt = read_prompt(args)
    output_format = infer_format(out_path, args.output_format)
    base_url = args.base_url or get_base_url(args.base_url_env)
    if not base_url:
        raise SystemExit(f"{args.base_url_env} is missing. Set it to your OpenAI-compatible API base URL.")
    endpoint = build_endpoint(base_url)

    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "size": args.size,
        "quality": args.quality,
        "output_format": output_format,
    }

    if args.dry_run:
        preview = dict(payload)
        preview["prompt"] = prompt[:200] + ("..." if len(prompt) > 200 else "")
        print(json.dumps({"endpoint": endpoint, "out": str(out_path), "payload": preview}, indent=2))
        return 0

    api_key = get_env(args.api_key_env)
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is missing.")

    data = post_json(endpoint, payload, api_key, args.timeout)
    write_image(data, out_path, args.timeout)

    mime, _ = mimetypes.guess_type(out_path.name)
    print(str(out_path))
    if mime:
        print(mime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
