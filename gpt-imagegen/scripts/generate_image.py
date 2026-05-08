#!/usr/bin/env python3
"""Stream image generation with gpt-image-2 through the OpenAI Python SDK."""

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


def normalize_sdk_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return base + "/v1"


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


def load_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "The openai Python package is required for streaming image generation. "
            "Install or upgrade it with: python -m pip install --upgrade openai"
        ) from exc
    return OpenAI


def event_value(event: object, key: str) -> Any:
    if hasattr(event, key):
        return getattr(event, key)
    if isinstance(event, dict):
        return event.get(key)
    if hasattr(event, "model_dump"):
        return event.model_dump().get(key)
    return None


def partial_output_path(out_path: Path, idx: int | str, partials_dir: str | None) -> Path:
    target_dir = Path(partials_dir) if partials_dir else out_path.parent
    suffix = out_path.suffix or ".png"
    return target_dir / f"{out_path.stem}-partial-{idx}{suffix}"


def download_url(url: str, timeout: int) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Image download failed: {exc.reason}") from exc


def response_image_bytes(response: object, timeout: int) -> bytes:
    data = event_value(response, "data")
    if not data:
        raise SystemExit("Response did not include data.")
    item = data[0]
    b64_json = event_value(item, "b64_json")
    if b64_json:
        return base64.b64decode(b64_json)
    url = event_value(item, "url")
    if url:
        return download_url(url, timeout)
    raise SystemExit("Response did not include data[0].b64_json or data[0].url.")


def request_payload(args: argparse.Namespace, prompt: str, output_format: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "background": args.background,
        "size": args.size,
        "quality": args.quality,
        "output_format": output_format,
    }
    if not args.no_stream:
        payload["stream"] = True
        payload["partial_images"] = args.partial_images
    return payload


def stream_image(client: object, payload: dict[str, Any], out_path: Path, partials_dir: str | None, save_partials: bool) -> list[Path]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if partials_dir:
        Path(partials_dir).mkdir(parents=True, exist_ok=True)

    stream = client.images.generate(**payload)
    partial_paths: list[Path] = []
    last_image: bytes | None = None
    final_image: bytes | None = None
    fallback_idx = 0

    for event in stream:
        event_type = event_value(event, "type")
        b64_json = event_value(event, "b64_json")
        if not b64_json:
            continue

        image_bytes = base64.b64decode(b64_json)
        if event_type == "image_generation.partial_image":
            fallback_idx += 1
            idx = event_value(event, "partial_image_index")
            if idx is None:
                idx = fallback_idx
            last_image = image_bytes
            if save_partials:
                path = partial_output_path(out_path, idx, partials_dir)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(image_bytes)
                partial_paths.append(path)
        else:
            final_image = image_bytes

    image_to_write = final_image or last_image
    if image_to_write is None:
        raise SystemExit("Streaming completed without any image bytes.")

    out_path.write_bytes(image_to_write)
    return partial_paths


def generate_image(client: object, payload: dict[str, Any], out_path: Path, timeout: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    response = client.images.generate(**payload)
    out_path.write_bytes(response_image_bytes(response, timeout))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an image with gpt-image-2.")
    parser.add_argument("--prompt", help="Image prompt text.")
    parser.add_argument("--prompt-file", help="UTF-8 text file containing the image prompt.")
    parser.add_argument("--out", required=True, help="Output image path.")
    parser.add_argument("--base-url", help="API base URL override. Prefer configuring an environment variable.")
    parser.add_argument("--base-url-env", default="OPENAI_BASE_URL", help="Environment variable that stores the API base URL.")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--background", choices=["transparent", "opaque", "auto"], default="auto")
    parser.add_argument("--size", choices=["1024x1024", "1024x1536", "1536x1024", "auto"], default="1024x1024")
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], default="medium")
    parser.add_argument("--output-format", choices=["png", "jpeg", "webp"], default=None)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--partial-images", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--partials-dir", help="Directory for streamed partial images. Defaults to the output image directory.")
    parser.add_argument("--no-save-partials", action="store_true", help="Do not write streamed partial images to disk.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming and make a normal image generation request.")
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
    sdk_base_url = normalize_sdk_base_url(base_url)
    payload = request_payload(args, prompt, output_format)

    if args.dry_run:
        preview = dict(payload)
        preview["prompt"] = prompt[:200] + ("..." if len(prompt) > 200 else "")
        print(json.dumps({"base_url": sdk_base_url, "out": str(out_path), "payload": preview}, indent=2))
        return 0

    api_key = get_env(args.api_key_env)
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is missing.")

    OpenAI = load_openai_client()
    client = OpenAI(api_key=api_key, base_url=sdk_base_url, timeout=args.timeout)

    if args.no_stream:
        generate_image(client, payload, out_path, args.timeout)
        partial_paths: list[Path] = []
    else:
        partial_paths = stream_image(client, payload, out_path, args.partials_dir, not args.no_save_partials)

    mime, _ = mimetypes.guess_type(out_path.name)
    print(str(out_path))
    if mime:
        print(mime)
    for path in partial_paths:
        print(f"partial: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
