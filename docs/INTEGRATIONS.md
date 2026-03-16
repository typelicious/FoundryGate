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

For delegated or many-agent traffic, start from [examples/openclaw-delegated-request.json](./examples/openclaw-delegated-request.json) and keep `x-openclaw-source` stable across sub-agents so traces stay attributable.

Keep delegated/client headers short and stable. The runtime now bounds routing-header values before they reach traces, metrics, and rollout logic.

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

As with other clients, prefer token-like client tags over long free-form values so the bounded header surface remains readable in traces and operator views.

If you want a small Node-facing helper instead of shell aliases, the separate npm package lives in [packages/foundrygate-cli](../packages/foundrygate-cli).

## AI-native app clients

For future app-specific clients, keep the same OpenAI-compatible base URL and add one stable app header before creating multiple custom profiles.

Recommended pattern:

- set `X-FoundryGate-Client: your-app`
- create one explicit app profile
- only split into `ops`, `private`, or `local-only` profiles when real routing differences emerge

Starter snippet:

- [examples/client-ai-native-app-profile.yaml](./examples/client-ai-native-app-profile.yaml)

## First-wave agent and framework starters

The first post-`1.0` expansion wave focuses on clients that can already use FoundryGate cleanly through the common OpenAI-compatible path.

### SWE-AF

- starter: [examples/swe-af-foundrygate.env.example](./examples/swe-af-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: swe-af`
- recommended profile name: `swe-af`

### paperclip

- starter: [examples/paperclip-foundrygate.env.example](./examples/paperclip-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: paperclip`
- recommended profile name: `paperclip`

### ship-faster

- starter: [examples/ship-faster-foundrygate.env.example](./examples/ship-faster-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: ship-faster`
- recommended profile name: `ship-faster`

### LangChain

- starter: [examples/langchain-foundrygate.env.example](./examples/langchain-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: langchain`
- recommended profile name: `langchain`

### LangGraph

- starter: [examples/langgraph-foundrygate.env.example](./examples/langgraph-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: langgraph`
- recommended profile name: `langgraph`

These starters are intentionally small:

- keep one local OpenAI-compatible base URL
- keep one stable client tag
- use client profiles only when the framework traffic really needs distinct routing behavior
- validate with `POST /api/route` and `GET /api/traces` before adding policies or hooks

## Second-wave framework starters

The second wave keeps the same integration discipline while extending FoundryGate coverage into more active agent ecosystems.

### Agno

- starter: [examples/agno-foundrygate.env.example](./examples/agno-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: agno`
- recommended profile name: `agno`

### Semantic Kernel

- starter: [examples/semantic-kernel-foundrygate.env.example](./examples/semantic-kernel-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: semantic-kernel`
- recommended profile name: `semantic-kernel`

### Haystack

- starter: [examples/haystack-foundrygate.env.example](./examples/haystack-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: haystack`
- recommended profile name: `haystack`

### Mastra

- starter: [examples/mastra-foundrygate.env.example](./examples/mastra-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: mastra`
- recommended profile name: `mastra`

### Google ADK

- starter: [examples/google-adk-foundrygate.env.example](./examples/google-adk-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: google-adk`
- recommended profile name: `google-adk`

## Third-wave framework starters

The third wave rounds out the most visible remaining framework set from the AI-native matrix.

### AutoGen

- starter: [examples/autogen-foundrygate.env.example](./examples/autogen-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: autogen`
- recommended profile name: `autogen`

### LlamaIndex

- starter: [examples/llamaindex-foundrygate.env.example](./examples/llamaindex-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: llamaindex`
- recommended profile name: `llamaindex`

### CrewAI

- starter: [examples/crewai-foundrygate.env.example](./examples/crewai-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: crewai`
- recommended profile name: `crewai`

### PydanticAI

- starter: [examples/pydanticai-foundrygate.env.example](./examples/pydanticai-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: pydanticai`
- recommended profile name: `pydanticai`

### CAMEL

- starter: [examples/camel-foundrygate.env.example](./examples/camel-foundrygate.env.example)
- recommended header: `X-FoundryGate-Client: camel`
- recommended profile name: `camel`

## Provider onboarding

When onboarding a new provider:

1. define the provider stanza in `config.yaml`
2. declare the right contract and capabilities
3. verify health and `/v1/models`
4. test routing with `POST /api/route`
5. then route real traffic

Starter snippets:

- [examples/provider-openai-compat.yaml](./examples/provider-openai-compat.yaml)
- [examples/provider-openai-compat.env.example](./examples/provider-openai-compat.env.example)
- [examples/provider-local-worker.yaml](./examples/provider-local-worker.yaml)
- [examples/provider-local-worker.env.example](./examples/provider-local-worker.env.example)
- [examples/provider-image-provider.yaml](./examples/provider-image-provider.yaml)
- [examples/provider-image-provider.env.example](./examples/provider-image-provider.env.example)

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
