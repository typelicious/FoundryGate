# FoundryGate API Reference

FoundryGate keeps the client-facing surface intentionally small: OpenAI-compatible paths for chat and image workloads, plus a compact operator API for health, routing introspection, and updates.

## Core OpenAI-Compatible Endpoints

### `GET /v1/models`

Returns the virtual `auto` model plus one entry for every provider that actually loaded at startup.

```bash
curl -fsS http://127.0.0.1:8090/v1/models
```

### `POST /v1/chat/completions`

Routes OpenAI-style chat requests.

- `model: "auto"` runs the normal routing flow
- `model: "<provider-id>"` routes directly to a loaded provider
- request size is bounded by `security.max_json_body_bytes`

```bash
curl -fsS http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Summarize the benefits of a local AI gateway."}
    ],
    "max_tokens": 128
  }'
```

### `POST /v1/images/generations`

Routes image-generation requests to providers with `capabilities.image_generation: true`.

- validates `prompt`, `n`, and `size` before any provider call
- supports image-policy hints via `metadata.image_policy` or `X-FoundryGate-Image-Policy`

```bash
curl -fsS http://127.0.0.1:8090/v1/images/generations \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "prompt": "An architectural diagram of a local AI gateway, blueprint style",
    "size": "1024x1024"
  }'
```

### `POST /v1/images/edits`

Routes image-editing requests to providers with `capabilities.image_editing: true`.

- expects `multipart/form-data`
- currently supports one required `image` and one optional `mask`
- rejects uploads above `security.max_upload_bytes`
- accepts image-policy hints via `image_policy`, `metadata.image_policy`, or `X-FoundryGate-Image-Policy`

```bash
curl -fsS http://127.0.0.1:8090/v1/images/edits \
  -F 'model=auto' \
  -F 'prompt=Remove the background and keep the subject centered' \
  -F 'image=@input.png' \
  -F 'mask=@mask.png'
```

## Operator Endpoints

### `GET /health`

Returns overall service status, provider summary, and capability coverage.

Each provider entry includes health, failure counters, average latency, last error, contract, backend, tier, capabilities, and image metadata.

```bash
curl -fsS http://127.0.0.1:8090/health
```

### `GET /api/providers`

Returns the loaded provider inventory plus the same capability-coverage summary used by the dashboard.

- optional `capability=<name>`
- optional `healthy=true|false`

```bash
curl -fsS 'http://127.0.0.1:8090/api/providers?capability=image_generation'
```

### `GET /api/stats`

Returns aggregate request counters, token usage, per-client breakdowns, aggregate client totals, client highlight summaries, cost data, and operator-action summaries.

```bash
curl -fsS http://127.0.0.1:8090/api/stats
```

### `GET /api/recent`

Returns recent request records with optional filters for provider, client tag, layer, and success state.

```bash
curl -fsS 'http://127.0.0.1:8090/api/recent?limit=20'
```

### `GET /api/traces`

Returns detailed route traces including requested model, decision reason, attempt order, client profile, and selected provider.

```bash
curl -fsS 'http://127.0.0.1:8090/api/traces?limit=20'
```

### `GET /api/update`

Returns current release information plus update guardrails such as alert level, rollout ring, release age eligibility, maintenance-window state, and verification hints.

```bash
curl -fsS http://127.0.0.1:8090/api/update
```

### `GET /api/operator-events`

Returns helper-driven operator actions such as update checks and auto-update attempts.

```bash
curl -fsS 'http://127.0.0.1:8090/api/operator-events?limit=20'
```

### `POST /api/route`

Dry-runs chat routing and returns the selected provider, routing layer, decision reason, profile resolution, and attempt order.

```bash
curl -fsS http://127.0.0.1:8090/api/route \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Plan a low-latency response path for a CLI agent."}
    ]
  }'
```

### `POST /api/route/image`

Dry-runs image-generation or image-editing routing without calling an upstream provider.

```bash
curl -fsS http://127.0.0.1:8090/api/route/image \
  -H 'Content-Type: application/json' \
  -d '{
    "operation": "generation",
    "model": "auto",
    "prompt": "A clean dashboard screenshot mockup",
    "size": "1024x1024"
  }'
```

### `GET /dashboard`

Serves the built-in no-build operator dashboard.

```bash
open http://127.0.0.1:8090/dashboard
```

## Response Headers

Non-streaming chat completions include:

- `X-FoundryGate-Provider`
- `X-FoundryGate-Layer`
- `X-FoundryGate-Rule`

These are intentionally bounded and sanitized before they leave the gateway.
