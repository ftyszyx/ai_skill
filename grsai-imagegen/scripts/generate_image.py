#!/usr/bin/env python3
"""Generate and save images through the GRS AI GPT Image API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SKILL_DIR / "config.local.json"
DEFAULT_BASE_URL = "https://grsaiapi.com"
GENERATE_PATH = "/v1/draw/completions"
RESULT_PATH = "/v1/draw/result"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TERMINAL_SUCCESS = {"succeeded", "success", "completed"}
TERMINAL_FAILURE = {"failed", "failure", "error", "cancelled", "canceled"}
IMAGE_SIGNATURES = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF", b"BM")


@dataclass(frozen=True)
class ImageResult:
    url: str | None = None
    data: bytes | None = None


class ApiError(RuntimeError):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate images with the GRS AI GPT Image API.")
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Image prompt text.")
    prompt_group.add_argument("--prompt-file", type=Path, help="UTF-8 prompt file.")
    parser.add_argument("--out", type=Path, required=True, help="Output image path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Local JSON config path.")
    parser.add_argument("--base-url", help="API host override.")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key.")
    parser.add_argument("--model", choices=("gpt-image-2", "gpt-image-2-vip"))
    parser.add_argument("--size", "--aspect-ratio", dest="aspect_ratio", default="1024x1024")
    parser.add_argument("--quality", choices=("auto", "low", "medium", "high"), default="auto")
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        help="Reference image path, HTTP(S) URL, base64 value, or data URI. Repeat as needed.",
    )
    parser.add_argument("--count", type=int, default=1, help="Independent variants to generate (1-10).")
    parser.add_argument("--response-mode", choices=("poll", "stream"), help="Completion transport.")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=300.0, help="Overall task timeout in seconds.")
    parser.add_argument("--request-timeout", type=float, default=60.0)
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


def first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def read_prompt(args: argparse.Namespace) -> str:
    value = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8-sig")
    value = value.strip()
    if not value:
        raise SystemExit("Prompt must not be empty.")
    return value


def resolve_api_key(args: argparse.Namespace, config: dict[str, Any]) -> str:
    selected_env = os.environ.get(args.api_key_env, "") if args.api_key_env else ""
    value = first_non_empty(
        config.get("api_key"),
        selected_env,
        os.environ.get("GRSAI_API_KEY"),
        os.environ.get("GRS_API_KEY"),
    )
    if not value:
        raise SystemExit(
            "GRS AI API key is missing. Configure config.local.json or set GRSAI_API_KEY / GRS_API_KEY."
        )
    return value


def normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url:
        raise SystemExit("API base URL must not be empty.")
    if not base_url.startswith(("https://", "http://")):
        raise SystemExit("API base URL must start with http:// or https://.")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    return base_url.rstrip("/")


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url}{path}"


def encode_reference(value: str) -> str:
    value = value.strip()
    if value.startswith(("http://", "https://", "data:image/")):
        return value
    path = Path(value).expanduser()
    if path.is_file():
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
    if value:
        return value
    raise SystemExit("Reference image value must not be empty.")


def build_payload(
    model: str,
    prompt: str,
    aspect_ratio: str,
    quality: str,
    references: list[str],
    response_mode: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "quality": quality,
        "shutProgress": response_mode == "poll",
    }
    if references:
        payload["urls"] = references
    if response_mode == "poll":
        payload["webHook"] = "-1"
    return payload


def safe_error_message(raw: bytes, status: int) -> str:
    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return f"HTTP {status}: {text[:500]}"
    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("msg") or payload.get("message") or payload
    else:
        error = payload
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("type")
        error = message or json.dumps(error, ensure_ascii=False)
    return f"HTTP {status}: {str(error)[:500]}"


def open_request(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    request_timeout: float,
    max_attempts: int,
    accept: str,
) -> BinaryIO:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": accept,
                "User-Agent": "grsai-imagegen/1.0",
            },
        )
        try:
            return urllib.request.urlopen(request, timeout=request_timeout)
        except urllib.error.HTTPError as error:
            message = safe_error_message(error.read(), error.code)
            if error.code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise ApiError(error.code, message) from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt >= max_attempts:
                raise ApiError(None, f"API request failed: {error}") from error
        time.sleep(min(2**attempt, 10))
    raise ApiError(None, "API request failed without a response.")


def post_json(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    request_timeout: float,
    max_attempts: int,
) -> dict[str, Any]:
    with open_request(url, payload, api_key, request_timeout, max_attempts, "application/json") as response:
        raw = response.read()
        status = getattr(response, "status", 200)
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ApiError(status, f"API response was not valid JSON: {raw[:500]!r}") from error
    if not isinstance(value, dict):
        raise ApiError(status, "API response must be a JSON object.")
    return value


def unwrap_task(value: dict[str, Any]) -> dict[str, Any]:
    code = value.get("code")
    if isinstance(code, int) and code != 0:
        message = value.get("msg") or value.get("message") or "Unknown API error"
        raise ApiError(None, f"GRS AI error {code}: {message}")
    data = value.get("data")
    return data if isinstance(data, dict) else value


def task_status(value: dict[str, Any]) -> str:
    status = value.get("status")
    return status.strip().lower() if isinstance(status, str) else ""


def task_failure(value: dict[str, Any]) -> str:
    reason = value.get("failure_reason") or value.get("error") or value.get("msg") or "Unknown failure"
    return str(reason)


def task_id(value: dict[str, Any]) -> str | None:
    task = unwrap_task(value)
    identifier = task.get("id")
    return identifier.strip() if isinstance(identifier, str) and identifier.strip() else None


def decode_image_value(value: str) -> bytes | None:
    marker = ";base64,"
    if value.startswith("data:image/") and marker in value:
        return base64.b64decode(value.split(marker, 1)[1])
    return None


def extract_image_results(value: Any) -> list[ImageResult]:
    results: list[ImageResult] = []

    def collect(item: Any) -> None:
        if isinstance(item, list):
            for nested in item:
                collect(nested)
            return
        if not isinstance(item, dict):
            return
        url = item.get("url")
        if isinstance(url, str) and url.strip():
            data = decode_image_value(url.strip())
            results.append(ImageResult(data=data) if data is not None else ImageResult(url=url.strip()))
        for key in ("results", "images", "data", "output"):
            nested = item.get(key)
            if nested is not None:
                collect(nested)

    collect(value)
    unique: list[ImageResult] = []
    seen: set[tuple[str, bytes | str]] = set()
    for result in results:
        marker = ("data", result.data) if result.data is not None else ("url", result.url or "")
        if marker not in seen:
            seen.add(marker)
            unique.append(result)
    return unique


def wait_for_result(
    base_url: str,
    identifier: str,
    api_key: str,
    timeout: float,
    request_timeout: float,
    max_attempts: int,
    poll_interval: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        response = post_json(
            endpoint_url(base_url, RESULT_PATH),
            {"id": identifier},
            api_key,
            request_timeout,
            max_attempts,
        )
        task = unwrap_task(response)
        status = task_status(task)
        if status in TERMINAL_SUCCESS or extract_image_results(task):
            return task
        if status in TERMINAL_FAILURE:
            raise ApiError(None, f"Image generation failed: {task_failure(task)}")
        if time.monotonic() >= deadline:
            raise ApiError(None, f"Timed out waiting for image task {identifier}.")
        time.sleep(poll_interval)


def stream_json_objects(response: Iterable[bytes]) -> Iterable[dict[str, Any]]:
    for raw_line in response:
        line = raw_line.decode("utf-8-sig", errors="replace").strip()
        if not line or line.startswith("event:") or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def run_stream_request(
    base_url: str,
    payload: dict[str, Any],
    api_key: str,
    request_timeout: float,
    max_attempts: int,
) -> dict[str, Any]:
    last_task: dict[str, Any] | None = None
    with open_request(
        endpoint_url(base_url, GENERATE_PATH),
        payload,
        api_key,
        request_timeout,
        max_attempts,
        "text/event-stream, application/x-ndjson, application/json",
    ) as response:
        for event in stream_json_objects(response):
            task = unwrap_task(event)
            last_task = task
            status = task_status(task)
            if status in TERMINAL_FAILURE:
                raise ApiError(None, f"Image generation failed: {task_failure(task)}")
            if status in TERMINAL_SUCCESS or extract_image_results(task):
                return task
    if last_task is None:
        raise ApiError(None, "Stream ended without a JSON task response.")
    if extract_image_results(last_task):
        return last_task
    raise ApiError(None, "Stream ended before the image task completed.")


def run_poll_request(
    base_url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: float,
    request_timeout: float,
    max_attempts: int,
    poll_interval: float,
) -> dict[str, Any]:
    response = post_json(
        endpoint_url(base_url, GENERATE_PATH),
        payload,
        api_key,
        request_timeout,
        max_attempts,
    )
    initial_task = unwrap_task(response)
    if task_status(initial_task) in TERMINAL_FAILURE:
        raise ApiError(None, f"Image generation failed: {task_failure(initial_task)}")
    if extract_image_results(initial_task):
        return initial_task
    identifier = task_id(response)
    if not identifier:
        raise ApiError(None, "Task submission did not return an id or image result.")
    return wait_for_result(
        base_url,
        identifier,
        api_key,
        timeout,
        request_timeout,
        max_attempts,
        poll_interval,
    )


def download_image(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "image/*", "User-Agent": "grsai-imagegen/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise ApiError(None, f"Failed to download generated image: {error}") from error
    if not content_type.lower().startswith("image/") and not data.startswith(IMAGE_SIGNATURES):
        raise ApiError(None, f"Generated image URL did not return image data: {url}")
    return data


def output_path_for(base_path: Path, index: int) -> Path:
    if index == 0:
        return base_path
    return base_path.with_name(f"{base_path.stem}-{index + 1}{base_path.suffix}")


def save_result(result: ImageResult, path: Path, request_timeout: float) -> Path:
    data = result.data if result.data is not None else download_image(result.url or "", request_timeout)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.resolve()


def dry_run_summary(
    base_url: str,
    response_mode: str,
    model: str,
    prompt: str,
    aspect_ratio: str,
    quality: str,
    references: list[str],
    count: int,
    out: Path,
) -> dict[str, Any]:
    summarized_references = []
    for reference in references:
        if reference.startswith("data:"):
            summarized_references.append(f"data-uri ({len(reference)} chars)")
        else:
            summarized_references.append(reference)
    return {
        "base_url": base_url,
        "endpoint": GENERATE_PATH,
        "response_mode": response_mode,
        "model": model,
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "quality": quality,
        "references": summarized_references,
        "count": count,
        "out": str(out.resolve()),
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 1 <= args.count <= 10:
        parser.error("--count must be between 1 and 10.")
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1.")
    if args.timeout <= 0 or args.request_timeout <= 0 or args.poll_interval <= 0:
        parser.error("Timeouts and --poll-interval must be greater than zero.")

    config = load_config(args.config)
    prompt = read_prompt(args)
    model = first_non_empty(args.model, config.get("model"), "gpt-image-2") or "gpt-image-2"
    if model not in {"gpt-image-2", "gpt-image-2-vip"}:
        raise SystemExit(f"Unsupported model in config: {model}")
    response_mode = args.response_mode or first_non_empty(config.get("response_mode"), "poll") or "poll"
    if response_mode not in {"poll", "stream"}:
        raise SystemExit(f"Unsupported response_mode in config: {response_mode}")
    base_url = normalize_base_url(
        first_non_empty(
            args.base_url,
            config.get("base_url"),
            os.environ.get("GRSAI_BASE_URL"),
            os.environ.get("GRS_BASE_URL"),
            DEFAULT_BASE_URL,
        )
        or DEFAULT_BASE_URL
    )
    references = [encode_reference(value) for value in args.image]

    if args.dry_run:
        print(
            json.dumps(
                dry_run_summary(
                    base_url,
                    response_mode,
                    model,
                    prompt,
                    args.aspect_ratio,
                    args.quality,
                    references,
                    args.count,
                    args.out,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    api_key = resolve_api_key(args, config)
    saved: list[Path] = []
    next_output_index = 0
    for _ in range(args.count):
        payload = build_payload(
            model,
            prompt,
            args.aspect_ratio,
            args.quality,
            references,
            response_mode,
        )
        if response_mode == "poll":
            task = run_poll_request(
                base_url,
                payload,
                api_key,
                args.timeout,
                args.request_timeout,
                args.max_attempts,
                args.poll_interval,
            )
        else:
            task = run_stream_request(base_url, payload, api_key, args.request_timeout, args.max_attempts)
        results = extract_image_results(task)
        if not results:
            raise ApiError(None, "Completed task did not contain an image URL or base64 image.")
        for result in results:
            path = output_path_for(args.out, next_output_index)
            saved.append(save_result(result, path, args.request_timeout))
            next_output_index += 1

    for path in saved:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiError as error:
        raise SystemExit(f"Image generation failed. {error}") from error
