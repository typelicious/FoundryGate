# FoundryGate Integrations

## Current integration model

FoundryGate works best when clients use the same OpenAI-compatible base URL and let the gateway handle routing and failover.

That keeps integrations shallow and makes routing policy reusable across tools.

## OpenClaw

OpenClaw is a first-class target for FoundryGate.

Current coverage:

- one-agent traffic through the normal OpenAI-compatible endpoint
- many-agent or delegated traffic when `x-openclaw-source` is present
- direct model aliases via the OpenClaw-side config
- caller-aware defaults through the `openclaw` client preset or explicit profile rules

Use:

- [openclaw-integration.jsonc](../openclaw-integration.jsonc)
- [examples/openclaw-foundrygate.jsonc](./examples/openclaw-foundrygate.jsonc)
- `client_profiles.presets: ["openclaw"]` for a standard starting point

Minimal direction:

```json
{
  "baseUrl": "http://127.0.0.1:8090/v1",
  "primary": "foundrygate/auto"
}
```

For a smaller starter snippet without the full alias block, use [examples/openclaw-foundrygate.jsonc](./examples/openclaw-foundrygate.jsonc).

## n8n

n8n can use FoundryGate as a stable local model gateway.

Recommended pattern:

- send requests to the OpenAI-compatible endpoint
- set `X-FoundryGate-Client: n8n`
- enable the `n8n` client preset or an explicit `n8n` profile
- optionally enable `request_hooks` if a workflow should prefer one provider or stay local-only

This gives you:

- cheaper default routing for workflow traffic
- shared fallback behavior
- route debugging through `POST /api/route`

Minimal direction:

```text
Base URL: http://127.0.0.1:8090/v1
Model: auto
Header: X-FoundryGate-Client: n8n
```

For an importable HTTP Request node example, use [examples/n8n-foundrygate-http-request.json](./examples/n8n-foundrygate-http-request.json).

## CLI clients

CLI tools should also use the same local gateway where possible.

Examples:

- Codex CLI
- Claude Code wrappers
- KiloCode CLI
- future DeepSeek-oriented wrappers

Recommended pattern:

- point the client to FoundryGate
- set `X-FoundryGate-Client: codex`, `claude`, `kilocode`, or another stable client tag
- use the built-in `cli` preset or a tighter custom profile
- optionally enable request hooks for per-request locality or provider hints:
  - `X-FoundryGate-Prefer-Provider`
  - `X-FoundryGate-Locality`
  - `X-FoundryGate-Profile`

Minimal direction:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8090/v1
export OPENAI_API_KEY=local
```

For a reusable shell starter, use [examples/cli-foundrygate-env.sh](./examples/cli-foundrygate-env.sh).

## Provider onboarding

When onboarding a new provider:

1. define the provider stanza in `config.yaml`
2. declare the right contract and capabilities
3. verify health and `/v1/models`
4. test routing with `POST /api/route`
5. then route real traffic

Starter snippets:

- [examples/provider-openai-compat.yaml](./examples/provider-openai-compat.yaml)
- [examples/provider-local-worker.yaml](./examples/provider-local-worker.yaml)
- [examples/provider-image-provider.yaml](./examples/provider-image-provider.yaml)

## Client onboarding

When onboarding a new client:

1. keep the client on the OpenAI-compatible API if possible
2. assign a stable client tag or header
3. start with a built-in preset or a minimal custom profile
4. add request hooks only if the client needs per-request overrides
5. use `/api/route` and `/api/traces` to validate behavior
6. only add a dedicated adapter if the client cannot cleanly use the common API surface

## Planned integration directions

These are roadmap items or early foundations:

- image generation and image editing routing through `POST /v1/images/generations` and `POST /v1/images/edits` for providers that declare `contract: image-provider`
- optional request hooks for context or optimization
- richer CLI-sidecar adapters
- provider and client onboarding helpers
