---
name: jojo-imagegen
description: Generate and save raster images with the JojoCode OpenAI-compatible gpt-image-2 API. Use when Codex needs to create image assets, illustrations, icons, mockups, or image variants through jojocode.com, including requests that need configurable size, quality, style, count, URL/base64 responses, or compatibility with chat/completions and images/generations endpoints.
---

# Jojo Imagegen

Use the bundled `scripts/generate_image.py` instead of writing one-off HTTP clients.

## Workflow

1. Turn the user's request into a concrete production prompt. Add `no text, no watermark` unless text is explicitly requested.
2. Select an output path inside the current workspace, normally `output/imagegen/<descriptive-name>.png`.
3. Check for `config.local.json` in this skill directory or a supported API-key environment variable. Never print or commit the key.
4. Run the script in `auto` mode unless the user or provider documentation requires a specific endpoint.
5. Inspect every generated image with an image-viewing tool. Iterate with one targeted prompt change when needed.
6. Report absolute paths for all final images.

## Quick Start

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "A minimal password vault application icon, no text, no watermark" `
  --out E:\path\to\workspace\output\imagegen\vault-icon.png
```

Multiple images:

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "Three polished product illustration variants" `
  --out E:\path\to\workspace\output\imagegen\product.png `
  --n 3
```

Preview the request without calling the API:

```powershell
python <skill-dir>\scripts\generate_image.py `
  --prompt "test image" `
  --out E:\tmp\test.png `
  --dry-run
```

## Configuration

Copy `config.example.json` to `config.local.json` in this skill directory and fill in the local key, or set `JOJO_API_KEY` / `NEW_API_KEY`. Do not ask the user to paste a key into chat.

Endpoint modes:

- `auto`: call `/chat/completions` first, then fall back to `/images/generations` when the response does not contain an image or the endpoint is unsupported.
- `chat`: use the JojoCode chat example exactly.
- `images`: use OpenAI-compatible image generation parameters.

Read `references/api.md` when troubleshooting endpoint behavior or response formats.

## Constraints

- Keep keys in ignored local configuration or environment variables.
- Do not modify the bundled script for ordinary prompt, size, style, count, or endpoint selection.
- Use one API request per distinct prompt. Use `--n` only for variants of the same prompt.
- Treat HTTP `401` and `403` as configuration or provider-permission failures. Retry only `429` and transient `5xx` responses.
- Do not claim generation succeeded until output files exist and pass visual inspection.
