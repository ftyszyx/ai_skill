---
name: grsai-imagegen
description: Generate and save raster images with the GRS AI GPT Image API. Use when Codex needs to create or edit illustrations, icons, mockups, product images, image assets, or prompt variants through grsai.ai / grsaiapi.com, including requests using gpt-image-2 or gpt-image-2-vip, configurable resolution and quality, reference-image URLs or local files, polling, or streaming responses.
---

# GRS AI Imagegen

Use the bundled `scripts/generate_image.py` instead of writing one-off HTTP clients.

## Workflow

1. Turn the request into a concrete production prompt. Add `no text, no watermark` unless text is explicitly requested.
2. Select an output path inside the current workspace, normally `output/imagegen/<descriptive-name>.png`.
3. Check for `config.local.json` in this skill directory or a supported API-key environment variable. Never print or commit the key.
4. Use `--image` for each reference image. Local files are encoded as data URIs; HTTP(S) URLs are passed through.
5. Run the script in `poll` mode unless streaming behavior is specifically needed.
6. Inspect every generated image with an image-viewing tool. Iterate with one targeted prompt change when needed.
7. Report absolute paths for all final images.

## Quick Start

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "A minimal password vault application icon, no text, no watermark" `
  --out E:\path\to\workspace\output\imagegen\vault-icon.png
```

Reference-image generation:

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "Turn this object into a polished studio product photo, no text, no watermark" `
  --image E:\path\to\reference.png `
  --out E:\path\to\workspace\output\imagegen\product.png
```

Generate independent variants of the same prompt:

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "A friendly finance app mascot, no text, no watermark" `
  --out E:\path\to\workspace\output\imagegen\mascot.png `
  --count 3
```

Preview the request without calling the API:

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "test image" `
  --out E:\tmp\test.png `
  --dry-run
```

## Configuration

Copy `config.example.json` to `config.local.json` in this skill directory and fill in the local key, or set `GRSAI_API_KEY` / `GRS_API_KEY`. Do not ask the user to paste a key into chat.

- `poll` mode sends `webHook: "-1"`, receives a task ID, and polls `/v1/draw/result` until completion. This is the default and most reliable mode for saving files.
- `stream` mode consumes JSON, NDJSON, or SSE-style progress responses directly from `/v1/draw/completions`.
- Use `--base-url https://grsai.dakka.com.cn` for the documented China direct host when appropriate. The default is the documented global host `https://grsaiapi.com`.
- Use `--model gpt-image-2-vip` only when the account has access and the user needs that model.

Read `references/api.md` when troubleshooting parameters, response formats, task states, or host selection.

## Constraints

- Keep keys in ignored local configuration or environment variables.
- Do not modify the bundled script for ordinary prompt, reference-image, resolution, quality, count, host, or response-mode selection.
- `--count` creates separate billable tasks because the documented API has no image-count parameter.
- Download returned resources immediately; the provider documents image URLs as valid for two hours.
- Treat HTTP `401` and `403` as configuration or provider-permission failures. Retry only `429` and transient `5xx` responses.
- Do not claim generation succeeded until output files exist and pass visual inspection.
