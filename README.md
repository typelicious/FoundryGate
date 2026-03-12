# FoundryGate

[![repo-safety](https://github.com/typelicious/FoundryGate/actions/workflows/repo-safety.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/repo-safety.yml)
[![CI](https://github.com/typelicious/FoundryGate/actions/workflows/ci.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/ci.yml)
[![CodeQL](https://github.com/typelicious/FoundryGate/actions/workflows/codeql.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/typelicious/FoundryGate?display_name=tag)](https://github.com/typelicious/FoundryGate/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![OpenAI-compatible](https://img.shields.io/badge/OpenAI-compatible-0ea5e9.svg)](./README.md#api)
[![OpenClaw-friendly](https://img.shields.io/badge/OpenClaw-friendly-111827.svg)](https://openclaw.ai/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](./Dockerfile)
[![PyPI](https://img.shields.io/badge/pypi-workflow%20ready-3775A9?logo=pypi&logoColor=white)](./RELEASES.md)
[![Publish Dry Run](https://github.com/typelicious/FoundryGate/actions/workflows/publish-dry-run.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/publish-dry-run.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](./pyproject.toml)

## Quick Navigation

- [Quickstart](#quickstart)
- [Docs](#docs)
- [How It Works](#how-it-works)
- [API](#api)
- [Model Aliases And Routing](#model-aliases-and-routing)
- [Policy Routing](#policy-routing)
- [Client Profiles](#client-profiles)
- [Request Hooks](#request-hooks)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Helper Scripts](#helper-scripts)
- [Update Checks](#update-checks)
- [Publishing](#publishing)
- [Community And Security](#community-and-security)
- [Repo Safety And CI](#repo-safety-and-ci)
- [Workflow](#workflow)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Releases](#releases)

Local OpenAI-compatible AI gateway for 🦞 [OpenClaw](https://openclaw.ai/) and other AI-native clients.

FoundryGate is a local OpenAI-compatible router/proxy for OpenClaw and other clients. Point your client at a single local endpoint, and FoundryGate routes each request to the configured upstream provider and model, applies fallbacks on failures, and exposes health and usage data for operations.

## Why FoundryGate

- OpenAI-compatible API: expose `/v1/models` and `/v1/chat/completions` to OpenClaw or any OpenAI-style client.
- Modality growth path: the runtime now includes OpenAI-compatible image generation and image editing paths for providers marked as image-capable.
- Single endpoint, multiple providers: clients call one local base URL while FoundryGate chooses the upstream provider.
- Multi-provider routing: use `auto` for routing or target a provider directly by model id.
- Multi-dimensional routing: score providers across locality, context headroom, token limits, cache metadata, latency, and recent failure state during provider selection.
- Robust fallback behavior: provider errors, timeouts, and connection failures fall through the configured fallback chain.
- Useful observability: `/health` reports provider status, capability coverage, consecutive failures, last error, and average latency.
- Hardened extension seam: request hooks are sanitized, can fail closed, and expose hook errors in dry-run and completion responses.
- Safe database path handling: metrics use `FOUNDRYGATE_DB_PATH`, so the SQLite database does not need to live in the repo checkout.

## Who Is This For?

- OpenClaw users who want one local endpoint instead of wiring every upstream model into the client
- Agent stacks that already speak the OpenAI chat completions API
- Operators who want local routing, failover, and lightweight request/cost visibility
- Developers who want a small FastAPI service instead of a larger gateway stack

## Quickstart

The fastest path is a local Python run using the stock `config.yaml`.

1. Clone the repo and create your environment file.
2. Set at least one provider API key in `.env`.
3. Override `FOUNDRYGATE_DB_PATH` to a writable path outside the repo if you are not using the systemd unit.
4. Install dependencies and run the app.

```bash
git clone https://github.com/typelicious/FoundryGate.git foundrygate
cd foundrygate
cp .env.example .env
mkdir -p "$HOME/.local/state/foundrygate"
printf '\nFOUNDRYGATE_DB_PATH=%s\n' "$HOME/.local/state/foundrygate/foundrygate.db" >> .env
$EDITOR .env
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m foundrygate
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8090/v1/models
```

If you want the fastest local bootstrap, use the generic helpers first:

```bash
./scripts/foundrygate-bootstrap
$EDITOR .env
./scripts/foundrygate-doctor
```

If you prefer the Linux service path instead of a manual Python run, jump to [Helper Scripts](#helper-scripts) and use `./scripts/foundrygate-install`.

If you install the project as a package, the `foundrygate` and `foundrygate-stats` console scripts are available.

If every configured provider API key is empty, FoundryGate still starts, but it skips those providers at startup and `v1/models` will only expose the virtual `auto` model.

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Integrations](./docs/INTEGRATIONS.md)
- [Onboarding](./docs/ONBOARDING.md)
- [Publishing](./docs/PUBLISHING.md)
- [Troubleshooting](./docs/TROUBLESHOOTING.md)
- [Roadmap](./docs/FOUNDRYGATE-ROADMAP.md)

## How It Works

```text
Client (OpenClaw or any OpenAI-style client)
  |
  v
http://127.0.0.1:8090/v1
  |
  +--> Layer 0: optional policy rules
  +--> Layer 1: static rules
  +--> Layer 2: heuristic rules
  +--> Layer 3: optional request hooks
  +--> Layer 4: optional client profile defaults
  +--> Layer 5: optional LLM classifier
  |
  +--> chosen provider
         |- deepseek-chat
         |- deepseek-reasoner
         |- gemini-flash-lite
         |- gemini-flash
         `- openrouter-fallback
```

Routing decisions happen in order:

1. Optional policy rules for client-specific, governance, or local/cloud constraints
2. Static rules for known patterns such as heartbeat, explicit model hints, and sub-agent traffic
3. Heuristic rules for user-message content, tools, and rough token size
4. Optional request hooks that can add per-request routing hints or profile overrides
5. Optional client profile defaults for callers such as OpenClaw, n8n, or CLI wrappers
6. An optional LLM classifier if you enable it in `config.yaml`

Every candidate provider is also checked and ranked against configured context windows, token limits, cache metadata, locality hints, health, latency, and recent failures before FoundryGate commits to the final route or fallback.

Important implementation detail: heuristic keyword scoring only evaluates user messages, not the system prompt. This avoids over-routing to expensive tiers because of long system prompts.

For OpenClaw specifically, both one-agent and many-agent traffic use the same OpenAI-compatible endpoint. The built-in rules and presets can distinguish sub-agent traffic through `x-openclaw-source` when that header is present.

## API

These endpoints are implemented today in [foundrygate/main.py](./foundrygate/main.py).

### `GET /health`

Returns overall service status, provider summary, capability coverage, and one object per loaded provider. Each provider entry includes:

- `healthy`
- `consecutive_failures`
- `avg_latency_ms`
- `last_error`
- `contract`
- `backend`
- `tier`
- `capabilities`
- `image`

```bash
curl -fsS http://127.0.0.1:8090/health
```

### `GET /api/providers`

Returns the loaded provider inventory plus the same capability-coverage summary used by the dashboard.

- optional `capability=<name>` filter
- optional `healthy=true|false` filter

```bash
curl -fsS 'http://127.0.0.1:8090/api/providers?capability=image_generation'
```

### `GET /v1/models`

Returns an OpenAI-compatible model list. It always includes the virtual `auto` model, plus one entry for every provider that actually loaded at startup.

```bash
curl -fsS http://127.0.0.1:8090/v1/models
```

### `POST /v1/chat/completions`

OpenAI-compatible chat completions endpoint.

- `model: "auto"` routes through FoundryGate
- `model: "<provider-id>"` routes directly to that loaded provider

For non-streaming responses, FoundryGate also adds these response headers:

- `X-FoundryGate-Provider`
- `X-FoundryGate-Layer`
- `X-FoundryGate-Rule`

```bash
curl -fsS http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Summarize the benefits of a local LLM gateway."}
    ],
    "max_tokens": 128
  }'
```

### `POST /v1/images/generations`

OpenAI-compatible image generation endpoint.

- `model: "auto"` selects the best loaded provider with `capabilities.image_generation: true`
- `model: "<provider-id>"` routes directly to a loaded image-capable provider
- validates `prompt`, `n`, and `size` before any provider call
- optional image-policy hints can be passed via `metadata.image_policy` or `X-FoundryGate-Image-Policy`

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

OpenAI-compatible image editing endpoint.

- expects `multipart/form-data`
- currently supports one required `image` upload plus an optional `mask`
- `model: "auto"` selects the best loaded provider with `capabilities.image_editing: true`
- `model: "<provider-id>"` routes directly to a loaded image-edit-capable provider
- validates scalar fields such as `prompt`, `n`, and `size` before any provider call
- optional image-policy hints can be passed via form field `image_policy`, `metadata.image_policy`, or `X-FoundryGate-Image-Policy`

```bash
curl -fsS http://127.0.0.1:8090/v1/images/edits \
  -F 'model=auto' \
  -F 'prompt=Remove the background and keep the subject centered' \
  -F 'image=@input.png' \
  -F 'mask=@mask.png' \
  -F 'size=1024x1024'
```

### Additional Stable Operational Endpoints

- `POST /api/route`
- `POST /api/route/image`
- `GET /api/providers`
- `GET /api/update`
- `GET /api/operator-events`
- `GET /api/stats`
- `GET /api/recent?limit=50`
- `GET /api/traces?limit=50`
- `GET /dashboard`

```bash
curl -fsS http://127.0.0.1:8090/api/route \
  -H 'Content-Type: application/json' \
  -H 'X-FoundryGate-Profile: local-only' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Route this without sending it upstream."}
    ]
  }'

curl -fsS http://127.0.0.1:8090/api/route/image \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "capability": "image_editing",
    "prompt": "Remove the background and keep the subject centered."
  }'

curl -fsS http://127.0.0.1:8090/api/stats
curl -fsS http://127.0.0.1:8090/api/update
curl -fsS http://127.0.0.1:8090/api/operator-events
curl -fsS 'http://127.0.0.1:8090/api/providers?healthy=true'
curl -fsS 'http://127.0.0.1:8090/api/recent?limit=10'
curl -fsS 'http://127.0.0.1:8090/api/traces?limit=10'
curl -fsS 'http://127.0.0.1:8090/api/stats?provider=local-worker&client_tag=codex&modality=chat'
```

`POST /api/route` is a dry-run endpoint. It uses the same routing logic as `POST /v1/chat/completions` but does not call an upstream provider. The response includes the resolved client profile, the routing decision, candidate ranking details where applicable, hook errors, and the fallback attempt order.

`POST /api/route/image` is the matching dry-run endpoint for image-generation and image-editing requests. Use `capability: "image_generation"` or `capability: "image_editing"` to preview modality-specific routing without calling an upstream image provider.

If request hooks are enabled, `POST /api/route` also shows the applied hook names and the effective request metadata after hook processing.

`GET /api/providers` returns the current provider inventory, including capability flags and optional image metadata such as `max_outputs`, `max_side_px`, and `supported_sizes`.

For image-capable providers, `image.policy_tags` can be used as lightweight presets such as `quality`, `cost`, `balanced`, `batch`, or `editing`. When a request carries `metadata.image_policy` or `X-FoundryGate-Image-Policy`, routing prefers providers whose `image.policy_tags` match that hint.

`GET /api/stats`, `GET /api/recent`, and `GET /api/traces` also accept optional `provider`, `modality`, `client_profile`, `client_tag`, `layer`, and `success` filters. The built-in dashboard uses the same filtered endpoints.

`GET /api/operator-events` returns recent operator-side update checks and apply attempts. The built-in dashboard now shows both a recent operator-action summary card and an operator-action breakdown table.

`GET /api/traces` returns recent enriched routing records from the metrics store, including requested model, modality, resolved client profile, client tag, decision reason, confidence, and attempt order.

`GET /api/update` returns the cached release-check result for the running service, including the current version, latest known tag, update availability, update type (`patch`, `minor`, `major`), alert level, recommended action, and the release URL when GitHub lookups succeed.

## Model Aliases And Routing

FoundryGate itself exposes:

- `auto` as the virtual routing model
- direct provider ids such as `deepseek-chat`, `deepseek-reasoner`, `gemini-flash-lite`, `gemini-flash`, and `openrouter-fallback` when those providers are loaded

The stock routing rules also understand short explicit model hints:

- `r1`, `reasoner`, `think` -> `deepseek-reasoner`
- `flash`, `gemini`, `vision` -> `gemini-flash`
- `ds`, `chat`, `default` -> `deepseek-chat`

If you use OpenClaw, the recommended client-side aliases live in [openclaw-integration.jsonc](./openclaw-integration.jsonc):

- `auto`
- `ds`
- `r1`
- `lite`
- `flash`
- `or`

Those aliases are defined on the OpenClaw side. FoundryGate only sees the resulting `model` value and routes accordingly.

## Policy Routing

FoundryGate now supports an optional `routing_policies` layer for `auto` requests. This sits in front of the existing static and heuristic rules and is meant for constraints that are broader than a single keyword rule, for example:

- prefer local providers for private or LAN-only traffic
- keep a client or workflow on a subset of allowed providers
- require capabilities such as `tools` before a request is sent
- prefer one provider order while still falling through to another eligible provider

Each rule has:

- `match`: request conditions such as `header_contains`, `model_requested`, `has_tools`, `estimated_tokens`, or `message_keywords`
- `select`: provider filters and preference order via `allow_providers`, `deny_providers`, `prefer_providers`, `prefer_tiers`, `require_capabilities`, and `capability_values`

Minimal example:

```yaml
routing_policies:
  enabled: true
  rules:
    - name: local-only-profile
      match:
        header_contains:
          x-foundrygate-profile: ["local-only"]
      select:
        capability_values:
          local: true
        prefer_tiers: ["local"]
```

## Client Profiles

FoundryGate also supports optional `client_profiles` for caller-aware defaults. Profiles are resolved from request headers and apply routing hints only when policy, static, and heuristic layers did not already pick a provider.

This is useful for giving different default behavior to:

- OpenClaw
- n8n workflows
- local/private-only callers
- future CLI wrappers or other automation clients

Profile rules can match on:

- `header_present`
- `header_contains`

Profile hints use the same selector keys as policy rules, for example `prefer_tiers`, `allow_providers`, `require_capabilities`, or `capability_values`.

FoundryGate also ships built-in presets for common callers:

- `openclaw`
- `n8n`
- `cli`

Enable them via `client_profiles.presets`. Presets add a default profile and header-matching rule, and you can still override the generated profile or rule explicitly in your own config.

Example:

```yaml
client_profiles:
  enabled: true
  default: generic
  presets: ["openclaw", "n8n", "cli"]
  profiles:
    generic: {}
  rules:
    - profile: cli
      match:
        header_contains:
          x-foundrygate-client: ["codex"]
```

## Request Hooks

FoundryGate also supports optional `request_hooks` as a narrow pre-routing extension seam.

The current built-in hooks are:

- `prefer-provider-header` for `x-foundrygate-prefer-provider`
- `locality-header` for `x-foundrygate-locality: local-only | cloud-only`
- `profile-override-header` for `x-foundrygate-profile`

Hooks run after policy, static, and heuristic routing, but before client-profile defaults. They are request-scoped and meant for controlled extensions such as context, memory, or CLI optimization layers without baking that logic into the core gateway.

Hook behavior is intentionally narrow:

- body updates are limited to known request fields such as `model`, `messages`, `tools`, `metadata`, and `max_tokens`
- unsupported routing hints are ignored instead of widening the routing surface accidentally
- `request_hooks.on_error` can be set to `fail` to reject the request instead of continuing on hook errors

Example:

```yaml
request_hooks:
  enabled: true
  on_error: continue
  hooks:
    - prefer-provider-header
    - locality-header
    - profile-override-header
```

Dry-run example:

```bash
curl -fsS http://127.0.0.1:8090/api/route \
  -H 'Content-Type: application/json' \
  -H 'X-FoundryGate-Prefer-Provider: local-worker' \
  -H 'X-FoundryGate-Locality: local-only' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Keep this on the local worker."}
    ]
  }'
```

## Configuration

FoundryGate loads configuration from:

- `config.yaml`
- `.env` via `python-dotenv`

String values in `config.yaml` support `${ENV_VAR}` and `${ENV_VAR:-default}` expansion.

### Provider Routing Metadata

The runtime now also understands these optional provider fields:

- `context_window`: total context budget used for route-fit checks
- `limits.max_input_tokens`: reject providers that cannot accept the estimated input size
- `limits.max_output_tokens`: reject providers that cannot satisfy the requested output size
- `cache.mode`: `none`, `implicit`, or `explicit`
- `cache.read_discount`: whether cache reads are cheaper than fresh input

These fields are exposed back through `/health` and `/v1/models`, and they are used by the routing engine when it ranks or rejects candidates.

The ranking logic intentionally prefers providers that both fit the request and leave enough safe headroom, rather than simply preferring the largest context window.

### Core Environment Variables

| Variable | What it does | Notes |
| --- | --- | --- |
| `FOUNDRYGATE_DB_PATH` | Path to the metrics SQLite database | Stock `config.yaml` defaults to `/var/lib/foundrygate/foundrygate.db` (not `./foundrygate.db`) |
| `DEEPSEEK_API_KEY` | Enables the default DeepSeek providers | Used by `deepseek-chat` and `deepseek-reasoner` |
| `GEMINI_API_KEY` | Enables the default Gemini providers | Used by `gemini-flash-lite` and `gemini-flash` |
| `OPENROUTER_API_KEY` | Enables the default OpenRouter fallback provider | Optional |
| `DEEPSEEK_BASE_URL` | Overrides the DeepSeek base URL | Optional |
| `GEMINI_BASE_URL` | Overrides the Gemini base URL | Optional |
| `OPENROUTER_BASE_URL` | Overrides the OpenRouter base URL | Optional |

### Additional Provider Key Variables Referenced In The Stock Config

The stock `config.yaml` ships many commented provider stanzas. If you uncomment one, its `api_key` field expects one of these variables:

- Cloud APIs: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENCODE_API_KEY`, `ZAI_API_KEY`, `AI_GATEWAY_API_KEY`, `KILOCODE_API_KEY`, `XAI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `COPILOT_GITHUB_TOKEN`, `HUGGINGFACE_HUB_TOKEN`, `MOONSHOT_API_KEY`, `KIMI_API_KEY`, `VOLCANO_ENGINE_API_KEY`, `BYTEPLUS_API_KEY`, `SYNTHETIC_API_KEY`, `MINIMAX_API_KEY`
- Local/OpenAI-compatible proxies: `OLLAMA_API_KEY`, `VLLM_API_KEY`, `LMSTUDIO_API_KEY`, `LITELLM_API_KEY`

Only providers whose `api_key` resolves to a non-empty value are initialized at startup.

Today, the runtime code implements:

- `openai-compat`
- `google-genai`

The stock config also includes commented templates for a wider provider catalog. Enable only the providers that match the backends implemented by your current FoundryGate runtime.

### Timeout Notes

The stock `config.yaml` includes per-provider `timeout` stanzas for documentation and future tuning, but the current runtime uses one shared `httpx` client timeout:

- connect timeout: `10s`
- read/response timeout: `120s`

Timeouts and connection errors still participate in fallback behavior and health tracking.

### Update Check Settings

FoundryGate can also cache release-update metadata for operators. The runtime surface stays read-only; optional helper-driven updates remain explicit and opt-in.

Supported fields in `update_check`:

- `enabled`
- `repository`
- `api_base`
- `timeout_seconds`
- `check_interval_seconds`

Example:

```yaml
update_check:
  enabled: true
  repository: "typelicious/FoundryGate"
  api_base: "https://api.github.com"
  timeout_seconds: 5
  check_interval_seconds: 21600
```

The status is exposed through `GET /api/update`, the dashboard, and the helper script `foundrygate-update-check`.
Recent operator-side update checks and apply attempts are exposed through `GET /api/operator-events`.

FoundryGate also supports an optional `auto_update` policy block for controlled environments. This stays strictly opt-in and only marks whether the current release state is eligible for a helper-driven update command.

Supported fields in `auto_update`:

- `enabled`
- `allow_major`
- `require_healthy_providers`
- `max_unhealthy_providers`
- `apply_command`

Example:

```yaml
auto_update:
  enabled: true
  allow_major: false
  require_healthy_providers: true
  max_unhealthy_providers: 0
  apply_command: "foundrygate-update"
```

What the current runtime does with it:

- exposes eligibility in `GET /api/update` under `auto_update`
- shows the same state in the dashboard
- lets `foundrygate-auto-update --apply` run only when the current release state is eligible
- can block helper-driven rollout when provider health is already degraded

What it still does not do:

- it does not self-update over HTTP
- it does not schedule itself
- it does not apply major upgrades unless you opt in with `allow_major: true`

### Provider Capability Schema

Each provider can expose normalized capability metadata under `capabilities:` in `config.yaml`. This is the first building block for policy-aware routing and future local-worker support.

Supported keys today:

- Boolean flags: `chat`, `reasoning`, `vision`, `image_generation`, `image_editing`, `tools`, `long_context`, `streaming`, `local`, `cloud`
- String labels: `cost_tier`, `latency_tier`, `network_zone`, `compliance_scope`

What the current runtime does with them:

- validates the capability block at startup
- derives safe defaults for `chat`, `reasoning`, `streaming`, `local`, `cloud`, and `network_zone`
- rejects combinations the current runtime cannot honor, such as `google-genai` plus `streaming: true`
- exposes the normalized capabilities in `/health` and `/v1/models`

Example:

```yaml
providers:
  local-worker:
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
    capabilities:
      tools: true
      cost_tier: budget
      latency_tier: low
```

### Local Worker Contract

FoundryGate also supports an explicit `contract: local-worker` on provider definitions. Use this for network-local OpenAI-compatible workers such as Ollama, vLLM, LM Studio, LiteLLM, or a dedicated LAN worker.

What the current runtime guarantees for `local-worker`:

- backend must be `openai-compat`
- `base_url` must point to localhost or private network space
- `tier` defaults to `local`
- capability metadata is normalized to `local: true`, `cloud: false`, `network_zone: local`
- FoundryGate probes `GET /models` for `local-worker` providers at startup and on `/health` refresh intervals

Example:

```yaml
providers:
  local-worker:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "your-local-model"
    capabilities:
      tools: true
      cost_tier: budget
      latency_tier: low
```

### Image Provider Contract

FoundryGate also supports `contract: image-provider` for OpenAI-compatible backends that expose image generation or image editing paths.

What the current runtime guarantees for `image-provider`:

- backend must be `openai-compat`
- `capabilities.image_generation` is normalized to `true`
- explicit `image_editing: true` enables `POST /v1/images/edits`
- optional `image.max_outputs`, `image.max_side_px`, and `image.supported_sizes` help the router choose the best image-capable provider for `n` and `size`
- `model: "auto"` on `POST /v1/images/generations` selects only providers with image-generation capability
- `model: "auto"` on `POST /v1/images/edits` selects only providers with image-editing capability

Example:

```yaml
providers:
  openai-images:
    contract: image-provider
    backend: openai-compat
    base_url: "https://api.openai.com/v1"
    api_key: "${OPENAI_API_KEY}"
    model: "gpt-image-1"
    capabilities:
      image_editing: true
    image:
      max_outputs: 4
      max_side_px: 2048
      supported_sizes: ["1024x1024", "2048x2048"]
```

### Routing Policy Schema

The optional `routing_policies` block is validated at startup. FoundryGate rejects unknown provider references, unknown capability names, and unsupported select keys before the service comes up.

Supported `select` keys today:

- `allow_providers`
- `deny_providers`
- `prefer_providers`
- `prefer_tiers`
- `require_capabilities`
- `capability_values`

### Configuration Examples

Using the stock `config.yaml`, you can configure common setups entirely through `.env`.

Single provider:

```dotenv
DEEPSEEK_API_KEY=your-key-here
FOUNDRYGATE_DB_PATH=/home/you/.local/state/foundrygate/foundrygate.db
```

Multi-provider with fallback:

```dotenv
DEEPSEEK_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
OPENROUTER_API_KEY=your-key-here
FOUNDRYGATE_DB_PATH=/home/you/.local/state/foundrygate/foundrygate.db
```

Disable a provider:

- Remove or empty the relevant API key in `.env`, or comment out the provider stanza in `config.yaml`
- On startup, FoundryGate logs that the provider has no API key and skips loading it

## Deployment

FoundryGate runs fine as a plain Python process. `systemd` and helper scripts are optional conveniences. The repo now also ships a Dockerfile and a release-artifacts workflow for container and Python package distribution.

### Generic Linux Host

For a normal Linux host without `systemd`, use the Quickstart above and keep `FOUNDRYGATE_DB_PATH` on a writable path outside the repo checkout.

Recommended runtime paths:

- app checkout: wherever you keep the repo
- metrics DB: `/var/lib/foundrygate/foundrygate.db` for system services, or a user path such as `$HOME/.local/state/foundrygate/foundrygate.db` for local runs

### systemd

The repo includes [foundrygate.service](./foundrygate.service). Deploy it to:

```text
/etc/systemd/system/foundrygate.service
```

Key points:

- Working directory: `/opt/foundrygate`
- Environment file: `/opt/foundrygate/.env`
- Database path: `FOUNDRYGATE_DB_PATH=/var/lib/foundrygate/foundrygate.db`
- Writable state directory: `/var/lib/foundrygate/`

The unit also enables basic hardening with `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `ReadWritePaths=/var/lib/foundrygate`, and `PrivateTmp`.

Minimal `systemd` flow:

```bash
sudo useradd --system --home /opt/foundrygate --shell /usr/sbin/nologin foundrygate || true
sudo install -d -o foundrygate -g foundrygate -m 755 /var/lib/foundrygate
sudo install -m 644 foundrygate.service /etc/systemd/system/foundrygate.service
sudo systemctl daemon-reload
sudo systemctl enable --now foundrygate.service
sudo systemctl status foundrygate.service --no-pager -l
```

### Docker

The repo now ships [Dockerfile](./Dockerfile). A minimal local run looks like this:

```bash
docker build -t foundrygate:dev .
docker run --rm -p 8090:8090 \
  --env-file .env \
  -e FOUNDRYGATE_DB_PATH=/var/lib/foundrygate/foundrygate.db \
  foundrygate:dev
```

For persistent container state, mount `/var/lib/foundrygate`:

```bash
docker run --rm -p 8090:8090 \
  --env-file .env \
  -e FOUNDRYGATE_DB_PATH=/var/lib/foundrygate/foundrygate.db \
  -v foundrygate-data:/var/lib/foundrygate \
  foundrygate:dev
```

The release workflow also includes a GHCR publishing path for tagged releases.

### Python Package / PyPI Baseline

The repo now ships a release workflow that builds wheels and source distributions on version tags.

Local package build:

```bash
python -m pip install --upgrade build
python -m build
```

Tagged releases always build Python artifacts. PyPI publishing is wired behind the repository variable `PYPI_PUBLISH=true` plus GitHub trusted publishing for the `pypi` environment.

## Publishing

FoundryGate now has a real publish dry-run path for both Python artifacts and the container image.

GitHub workflow:

- [publish-dry-run](./.github/workflows/publish-dry-run.yml) builds the wheel and sdist, runs `twine check`, and builds the GHCR image without pushing it
- [release-artifacts](./.github/workflows/release-artifacts.yml) is still the tag-driven publish path for real releases

Local dry-run commands:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
docker build -t foundrygate:dry-run .
```

Use the dry run before cutting a release when Docker, packaging metadata, or release automation changed.

## Helper Scripts

The scripts in [scripts](./scripts) are optional wrappers around onboarding, `systemd`, `journalctl`, and `curl`.

Running `./scripts/foundrygate-install` also creates symlinks in `/usr/local/bin`.

| Script | What it does |
| --- | --- |
| `foundrygate-bootstrap` | Creates `.env` from `.env.example` if needed, creates a local state dir, and appends a safe local `FOUNDRYGATE_DB_PATH` if none is set |
| `foundrygate-doctor` | Checks for config/env presence, writable DB path, at least one configured provider key, and optional local health endpoints |
| `foundrygate-install` | Installs the unit file, creates `/var/lib/foundrygate`, creates helper symlinks, reloads `systemd`, and starts the service |
| `foundrygate-start` | Runs `systemctl start foundrygate.service` |
| `foundrygate-stop` | Runs `systemctl stop foundrygate.service` |
| `foundrygate-restart` | Runs `systemctl restart foundrygate.service` |
| `foundrygate-status` | Shows service status and checks whether `127.0.0.1:8090` is listening |
| `foundrygate-logs` | Tails `journalctl -u foundrygate.service` |
| `foundrygate-health` | Calls `GET /health` locally with `curl` |
| `foundrygate-update-check` | Calls `GET /api/update` locally and prints the cached release-check status |
| `foundrygate-auto-update` | Evaluates the cached update status and, with `--apply`, only runs the configured update command when the release is eligible |
| `foundrygate-update` | Fetches from Git, hard-resets to `origin/main`, cleans untracked files, reinstalls the unit, restarts, and retries health checks |
| `foundrygate-uninstall` | Stops and disables the service, removes the unit file, and removes helper symlinks |

`foundrygate-stats --json` now also includes client/profile breakdowns alongside provider and routing summaries.

## Update Checks

FoundryGate now includes a lightweight operator-facing release check.

What it does:

- queries the latest GitHub Release tag for the configured repository
- caches the result for `update_check.check_interval_seconds`
- exposes the cached status in `GET /api/update`
- surfaces the same status in the dashboard and `foundrygate-update-check`
- exposes opt-in auto-update eligibility and the configured apply command
- records operator-side update checks and apply attempts in `GET /api/operator-events`

What it does not do:

- it does not download releases
- it does not modify the checkout
- it does not auto-update the service unless an operator explicitly wires `foundrygate-auto-update --apply` into their own scheduler

Manual check:

```bash
curl -fsS http://127.0.0.1:8090/api/update
curl -fsS http://127.0.0.1:8090/api/operator-events
./scripts/foundrygate-update-check
./scripts/foundrygate-auto-update
./scripts/foundrygate-auto-update --apply
```

For controlled schedules, use the reviewed examples in:

- [docs/examples/foundrygate-auto-update.service](./docs/examples/foundrygate-auto-update.service)
- [docs/examples/foundrygate-auto-update.timer](./docs/examples/foundrygate-auto-update.timer)
- [docs/examples/foundrygate-auto-update.cron](./docs/examples/foundrygate-auto-update.cron)

## Community And Security

FoundryGate now includes the core public community-health files expected for a public open-source repo:

- [Code of Conduct](./CODE_OF_CONDUCT.md)
- [Contributing Guide](./CONTRIBUTING.md)
- [Security Policy](./SECURITY.md)
- [Issue Templates](./.github/ISSUE_TEMPLATE)
- [Pull Request Template](./.github/pull_request_template.md)

Security automation and review baseline:

- [repo-safety](./.github/workflows/repo-safety.yml) blocks tracked secrets-like artifacts and runtime files
- [CodeQL](./.github/workflows/codeql.yml) provides code scanning on `main`, pull requests, and a weekly schedule
- [Dependabot](./.github/dependabot.yml) tracks Python, GitHub Actions, and Docker dependencies
- GitHub secret scanning is already active at the repository level

## Repo Safety And CI

FoundryGate includes two GitHub Actions workflows:

- [CI](./.github/workflows/ci.yml): runs Ruff plus the test matrix on Python 3.10 through 3.13
- [publish-dry-run](./.github/workflows/publish-dry-run.yml): validates Python distributions and the container build without publishing them
- [release-artifacts](./.github/workflows/release-artifacts.yml): builds Python distributions on tags, pushes container images to GHCR, and can publish to PyPI when trusted publishing is configured
- [repo-safety](./.github/workflows/repo-safety.yml): rejects accidental artifacts and secrets-like files
- [CodeQL](./.github/workflows/codeql.yml): performs repository code scanning for Python

The `repo-safety` workflow fails pull requests if these patterns are tracked in the working tree or still exist anywhere in Git history:

- `.ssh/`
- `*.db*`
- `*.sqlite*`
- `*.log`

This keeps secrets and runtime artifacts out of a public repo and makes cleanup mistakes visible before merge.

## Workflow

FoundryGate uses a protected `main` branch and short-lived implementation branches.

- `main` stays stable and releaseable
- `feature/<topic>-<date>` is the default branch type for implementation
- `review/<topic>-<date>` is optional for review-only hardening or secondary agent passes
- `hotfix/<topic>-<date>` is reserved for urgent fixes on top of current `main`

The detailed workflow is documented in [docs/process/git-workflow.md](./docs/process/git-workflow.md).

## Troubleshooting

The full operator guide lives in [docs/TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md).

### `GET /health` fails

Check whether the service is running and listening:

```bash
curl -fsS http://127.0.0.1:8090/health
sudo ss -ltnp | grep -E '127\.0\.0\.1:8090\b' || true
```

### No providers are loaded

This usually means every configured provider resolved to an empty API key. Re-check `.env`, then restart the service or process.

### Port `8090` is already in use

Find the conflicting process:

```bash
sudo ss -ltnp | grep ':8090'
```

### The database path is not writable

Set `FOUNDRYGATE_DB_PATH` to a writable path, or create the service state directory:

```bash
mkdir -p "$HOME/.local/state/foundrygate"
sudo install -d -o foundrygate -g foundrygate -m 755 /var/lib/foundrygate
```

### A provider keeps failing over

Check `/health` for `last_error`, then inspect logs:

```bash
curl -fsS http://127.0.0.1:8090/health
foundrygate-logs
```

For `contract: local-worker`, `/health` also refreshes a lightweight `GET /models` probe on the configured health interval. If the worker is reachable but not OpenAI-compatible, the probe will keep marking it unhealthy.

### `foundrygate-update` removed local edits

That is intentional. The helper is designed for deployment checkouts and uses `git reset --hard origin/main` plus `git clean -fd`.

## Roadmap

The next product direction is tracked in [docs/FOUNDRYGATE-ROADMAP.md](./docs/FOUNDRYGATE-ROADMAP.md).

Short version:

- `FoundryGate` is the product name
- the completed foundation already covers capability-aware routing, local worker support, client profiles, request hooks, route introspection, route traces, local worker probing, and first multi-dimensional route-fit checks
- `v0.4.x` now focuses on deeper route scoring and dashboard refinement rather than the initial hook/dashboard baseline
- `v0.5.0` is the operator distribution baseline for Docker and PyPI publishing, onboarding helpers, and release update checks
- the path to `v1.0.0` includes modality expansion, update operations, a separate npm or TypeScript CLI package, and a full security review

## Releases

- [CHANGELOG.md](./CHANGELOG.md) tracks notable user-facing changes
- [RELEASES.md](./RELEASES.md) describes the lightweight release process for tags and GitHub Releases
- publishing path: GitHub Releases now, Docker and PyPI in `v0.5.0`, separate npm or TypeScript CLI package by `v1.0.0`
- GitHub Releases: [https://github.com/typelicious/FoundryGate/releases](https://github.com/typelicious/FoundryGate/releases)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## Security

- Do not commit `.env`, API keys, databases, sqlite files, or logs
- Use `repo-safety` and `.gitignore` as guardrails, not as a substitute for review
- Rotate credentials upstream first if you ever suspect a leak

## License

Apache-2.0. See [LICENSE](./LICENSE).

⭐ If FoundryGate saves you time or money, feel free to star the repo. ❤️
