# GRS AI GPT Image API

This reference summarizes the provider documentation at:

```text
https://grsai.ai/zh/dashboard/documents/gpt-image
```

## Hosts and authentication

| Purpose | Value |
| --- | --- |
| Global host | `https://grsaiapi.com` |
| China direct host | `https://grsai.dakka.com.cn` |
| Header | `Authorization: Bearer <API key>` |
| Content type | `application/json` |

## Submit an image task

```text
POST /v1/draw/completions
```

Documented request:

```json
{
  "model": "gpt-image-2",
  "prompt": "Describe the image to generate",
  "aspectRatio": "1024x1024",
  "quality": "auto",
  "urls": ["https://example.com/reference.png"],
  "webHook": "-1",
  "shutProgress": true
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `model` | yes | `gpt-image-2` or `gpt-image-2-vip` |
| `prompt` | yes | Image prompt |
| `aspectRatio` | no | Pixel dimensions such as `1024x1024`; the provider says current pixel values are generally supported |
| `quality` | no | `auto`, `low`, `medium`, or `high` |
| `urls` | no | Reference-image URLs or base64 values; multiple images are supported |
| `webHook` | no | Callback URL, or `-1` to return a task ID immediately for polling |
| `shutProgress` | no | Suppress progress events and return only the final result; defaults to `false` |

The documentation lists these `gpt-image-2` sizes in its generator UI: `auto`, `1024x1024`, `1672x941`, `941x1672`, `1443x1090`, `1090x1443`, `1536x1024`, `1024x1536`, `1408x1120`, `1120x1408`, `1920x832`, `832x1920`, `1792x896`, and `896x1792`. The API documentation points to the provider's newer resolution document for the broader supported set.

## Poll a task

```text
POST /v1/draw/result
```

Request:

```json
{"id": "task-id"}
```

Response:

```json
{
  "code": 0,
  "data": {
    "id": "task-id",
    "progress": 100,
    "status": "succeeded",
    "failure_reason": "",
    "error": "",
    "results": [
      {"url": "https://example.com/generated.png"}
    ]
  },
  "msg": "success"
}
```

`code: -22` means the task does not exist.

## Task states and failures

- `running`: generation is in progress.
- `succeeded`: generation completed.
- `failed`: generation failed.
- `failure_reason: output_moderation`: generated output was rejected.
- `failure_reason: input_moderation`: input was rejected.
- `failure_reason: error`: another provider error occurred; the documentation says a retry can help with transient system instability.

The provider states failed tasks return consumed credits. Retry only transient HTTP or provider-system failures; do not retry moderation failures without changing the prompt or reference images.

## Result lifetime

The provider documents returned image URLs as valid for two hours. Download them immediately or configure the provider's storage integration outside this skill.
