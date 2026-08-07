#!/usr/bin/env python3
"""Generate images through the JojoCode OpenAI-compatible API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_DIR / "config.local.json"
DEFAULT_BASE_URL = "https://jojocode.com/v1"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
DATA_URI_PATTERN = re.compile(r"data:image/[^;]+;base64,([A-Za-z0-9+/=\r\n]+)")
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


@dataclass(frozen=True)
class ImageResult:
    data: bytes | None = None
    url: str | None = None


class ApiError(RuntimeError):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate images with the JojoCode gpt-image-2 API.")
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Image prompt text.")
    prompt_group.add_argument("--prompt-file", type=Path, help="UTF-8 prompt file.")
    parser.add_argument("--out", type=Path, required=True, help="Output image path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Local JSON config path.")
    parser.add_argument("--base-url", help="API base URL override.")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key.")
    parser.add_argument("--api-mode", choices=("auto", "chat", "images"), help="API endpoint mode.")
    parser.add_argument("--model", help="Model override. Defaults to config or gpt-image-2.")
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", default="medium")
    parser.add_argument("--style", default="vivid")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--response-format", choices=("url", "b64_json"), default="url")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"Config must be a JSON object: {path}")
    return value


def read_prompt(args: argparse.Namespace) -> str:
    value = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8-sig")
    value = value.strip()
    if not value:
        raise SystemExit("Prompt must not be empty.")
    return value


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_api_key(args: argparse.Namespace, config: dict[str, Any]) -> str:
    selected_env = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    value = first_non_empty(
        config.get("api_key"),
        selected_env,
        os.environ.get("JOJO_API_KEY"),
        os.environ.get("NEW_API_KEY"),
        os.environ.get("OPENAI_API_KEY"),
    )
    if not value:
        raise SystemExit(
            "JojoCode API key is missing. Configure config.local.json or set JOJO_API_KEY / NEW_API_KEY."
        )
    return value


def normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url:
        raise SystemExit("API base URL must not be empty.")
    if not base_url.endswith("/v1"):
        base_url += "/v1"
    return base_url + "/"


def endpoint_url(base_url: str, path: str) -> str:
    return urljoin(base_url, path.lstrip("/"))


def chat_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    return {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": args.temperature,
    }


def images_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    quality = "medium" if args.quality == "standard" else args.quality
    return {
        "model": args.model,
        "prompt": prompt,
        "size": args.size,
        "quality": quality,
        "style": args.style,
        "n": args.n,
        "response_format": args.response_format,
    }


def safe_error_message(raw: bytes, status: int) -> str:
    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return f"HTTP {status}: {text[:500]}"
    error = payload.get("error", payload) if isinstance(payload, dict) else payload
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("type")
        return f"HTTP {status}: {message or json.dumps(error, ensure_ascii=False)[:500]}"
    return f"HTTP {status}: {str(error)[:500]}"


def post_json(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: float,
    max_attempts: int,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "jojo-imagegen/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
                if not isinstance(value, dict):
                    raise ApiError(response.status, "API response must be a JSON object.")
                return value
        except urllib.error.HTTPError as error:
            message = safe_error_message(error.read(), error.code)
            if error.code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise ApiError(error.code, message) from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt >= max_attempts:
                raise ApiError(None, f"API request failed: {error}") from error
        time.sleep(min(2 ** attempt, 10))
    raise ApiError(None, "API request failed without a response.")


def append_string_result(value: str, results: list[ImageResult]) -> None:
    for match in DATA_URI_PATTERN.finditer(value):
        results.append(ImageResult(data=base64.b64decode(match.group(1))))
    markdown_urls = MARKDOWN_IMAGE_PATTERN.findall(value)
    for url in markdown_urls:
        results.append(ImageResult(url=url))
    if markdown_urls:
        return
    stripped = value.strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        results.append(ImageResult(url=stripped))
        return
    for url in URL_PATTERN.findall(value):
        results.append(ImageResult(url=url.rstrip(".,;)]}")))


def collect_image_results(value: Any, results: list[ImageResult]) -> None:
    if isinstance(value, str):
        append_string_result(value, results)
        return
    if isinstance(value, list):
        for item in value:
            collect_image_results(item, results)
        return
    if not isinstance(value, dict):
        return

    b64_value = value.get("b64_json")
    if isinstance(b64_value, str) and b64_value:
        results.append(ImageResult(data=base64.b64decode(b64_value)))

    for key in ("url", "image_url"):
        nested = value.get(key)
        if isinstance(nested, str):
            append_string_result(nested, results)
        elif isinstance(nested, (dict, list)):
            collect_image_results(nested, results)

    for key in ("data", "images", "image", "choices", "message", "content", "output"):
        nested = value.get(key)
        if nested is not None:
            collect_image_results(nested, results)


def extract_image_results(response: dict[str, Any]) -> list[ImageResult]:
    results: list[ImageResult] = []
    collect_image_results(response, results)
    unique: list[ImageResult] = []
    seen: set[tuple[str, bytes | str]] = set()
    for result in results:
        marker = ("data", result.data) if result.data is not None else ("url", result.url or "")
        if marker not in seen:
            seen.add(marker)
            unique.append(result)
    return unique


def download_image(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "image/*", "User-Agent": "jojo-imagegen/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        data = response.read()
    if not content_type.lower().startswith("image/") and not data.startswith((b"\x89PNG", b"\xff\xd8\xff", b"RIFF")):
        raise ApiError(None, f"Generated image URL did not return image data: {url}")
    return data


def output_path_for(base_path: Path, index: int) -> Path:
    if index == 0:
        return base_path
    return base_path.with_name(f"{base_path.stem}-{index + 1}{base_path.suffix}")


def save_results(results: list[ImageResult], out_path: Path, count: int, timeout: float) -> list[Path]:
    if not results:
        raise ApiError(None, "The API response did not contain an image URL or base64 image.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for index, result in enumerate(results[:count]):
        data = result.data if result.data is not None else download_image(result.url or "", timeout)
        path = output_path_for(out_path, index)
        path.write_bytes(data)
        saved.append(path.resolve())
    return saved


def request_modes(mode: str) -> tuple[str, ...]:
    if mode == "auto":
        return ("chat", "images")
    return (mode,)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 1 <= args.n <= 10:
        parser.error("--n must be between 1 and 10.")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1.")

    config = load_config(args.config)
    prompt = read_prompt(args)
    args.model = first_non_empty(args.model, config.get("model"), "gpt-image-2") or "gpt-image-2"
    base_url = normalize_base_url(
        first_non_empty(
            args.base_url,
            config.get("base_url"),
            os.environ.get("JOJO_BASE_URL"),
            DEFAULT_BASE_URL,
        )
        or DEFAULT_BASE_URL
    )
    mode = args.api_mode or first_non_empty(config.get("api_mode"), "auto") or "auto"
    if mode not in {"auto", "chat", "images"}:
        raise SystemExit(f"Unsupported api_mode in config: {mode}")

    if args.dry_run:
        print(json.dumps({
            "base_url": base_url,
            "api_mode": mode,
            "model": args.model,
            "prompt": prompt,
            "size": args.size,
            "quality": args.quality,
            "style": args.style,
            "n": args.n,
            "response_format": args.response_format,
            "out": str(args.out.resolve()),
        }, ensure_ascii=False, indent=2))
        return 0

    api_key = resolve_api_key(args, config)
    errors: list[str] = []
    for endpoint_mode in request_modes(mode):
        endpoint = "chat/completions" if endpoint_mode == "chat" else "images/generations"
        payload = chat_payload(args, prompt) if endpoint_mode == "chat" else images_payload(args, prompt)
        try:
            response = post_json(endpoint_url(base_url, endpoint), payload, api_key, args.timeout, args.max_attempts)
            results = extract_image_results(response)
            saved = save_results(results, args.out, args.n, args.timeout)
            for path in saved:
                print(path)
            return 0
        except ApiError as error:
            errors.append(f"{endpoint_mode}: {error}")
            if mode != "auto" or error.status in {401, 403, 429}:
                break

    raise SystemExit("Image generation failed. " + " | ".join(errors))


if __name__ == "__main__":
    raise SystemExit(main())
