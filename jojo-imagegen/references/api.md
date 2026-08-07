# JojoCode Image API

The supplied JojoCode model page shows an OpenAI-compatible service using:

```text
Base URL: https://jojocode.com/v1
Authorization: Bearer <API key>
Model: gpt-image-2
```

Keep endpoint selection and model selection separate in local configuration:

```json
{
  "api_mode": "auto",
  "model": "gpt-image-2"
}
```

The page shows `/chat/completions` in its request example while listing image-generation parameters. The bundled client therefore supports both documented shapes.

## Chat mode

Endpoint:

```text
POST /chat/completions
```

Payload:

```json
{
  "model": "gpt-image-2",
  "messages": [
    {"role": "user", "content": "Image prompt"}
  ],
  "temperature": 0.7
}
```

## Images mode

Endpoint:

```text
POST /images/generations
```

Payload fields shown by the provider:

| Field | Default | Notes |
| --- | --- | --- |
| `prompt` | required | Image description |
| `size` | `1024x1024` | Output dimensions |
| `quality` | `medium` | Live API accepts `auto`, `low`, `medium`, or `high`; legacy `standard` is mapped to `medium` |
| `style` | `vivid` | Visual style |
| `n` | `1` | Image count, 1-10 |
| `response_format` | `url` | `url` or `b64_json` |

## Response compatibility

The client extracts images from common OpenAI-compatible response shapes:

- `data[].url`
- `data[].b64_json`
- `choices[].message.content`
- nested `images`, `image_url`, or `url` fields
- Markdown image links
- `data:image/...;base64,...` URIs

## Authentication

Use the first non-empty key from:

1. `config.local.json` field `api_key`
2. environment variable selected by `--api-key-env`
3. `JOJO_API_KEY`
4. `NEW_API_KEY`
5. `OPENAI_API_KEY`

Never store a real key in `config.example.json` or command output.
