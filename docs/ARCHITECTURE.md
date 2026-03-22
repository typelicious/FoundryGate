# fusionAIze Gate Architecture

## Purpose

fusionAIze Gate is a local-first AI gateway plane.

Its job is to sit between many clients and many model backends while keeping one stable operational surface:

- one OpenAI-compatible endpoint
- one gateway surface for chat and image-generation requests
- many providers
- explicit routing and fallback behavior
- observable health and usage data

## Current runtime shape

Today the gateway has four main parts:

1. Gateway core
2. Provider layer
3. Client profile and policy layer
4. Operational surface

## Gateway core

The core handles:

- request normalization
- route selection
- fallback order
- timeout and failure handling
- request-size and upload-size guardrails
- response metadata
- metrics and traces

The current chat path is:

1. policy rules
2. static rules
3. heuristic rules
4. optional request hooks
5. client profile defaults
6. optional LLM classifier
7. fallback chain if the chosen provider fails

Within one `static` or `heuristic` match block, configured fields now behave as cumulative constraints. Use explicit `any:` only when you want OR behavior across subconditions. This keeps combined rules explainable and avoids accidental matches when only one of several intended constraints is present.

Policy matches follow the same discipline. `client_profile` is additive inside one policy match block, not a shortcut that bypasses the other configured fields. If one policy rule should match on either caller identity or a static/heuristic signal, express that explicitly with `any:`.

In practice, the layers split into two categories:

- hard decision layers: `policy`, `static`, and `heuristic`
- soft preference layers: `request hooks`, `client profiles`, and the optional `llm-classify`

The hard layers should carry governance, routing intent, and deterministic behavior. The soft layers should only add provider preference or narrow the candidate set when no harder layer has already made the decision.

Before a candidate is accepted, fusionAIze Gate also scores and validates route fit against provider metadata such as context window, input/output token limits, cache hints, locality, health, latency, and recent failure state.

The next architecture step is to separate:

- canonical model lane
- execution route
- scenario policy

That line is described in more detail in [Adaptive model orchestration](./ADAPTIVE-ORCHESTRATION.md). The short version is that Gate should increasingly choose the right *lane* first and then the best current *route* to that lane, especially when direct provider quotas and aggregator routes overlap.

## Provider layer

The provider layer already supports:

- OpenAI-compatible backends
- Google GenAI backends
- `contract: local-worker` for LAN/local OpenAI-compatible workers
- `contract: image-provider` for OpenAI-compatible image generation backends

Each provider can expose:

- capability metadata
- tier
- contract
- backend type
- context window
- token limits
- cache metadata
- health state
- ranking metadata surfaced through route introspection

## Client layer

The public entry point stays OpenAI-compatible, but callers can still be distinguished.

Current caller-aware signals:

- `x-openclaw-source`
- `x-faigate-client`
- `x-faigate-profile`
- `x-faigate-prefer-provider`
- `x-faigate-locality`

This is enough to support:

- OpenClaw one-agent traffic
- OpenClaw many-agent/sub-agent traffic
- n8n workflows
- CLI wrappers

Request hooks sit beside these caller-aware signals as a narrow extension seam. They can add sanitized request-level hints or profile overrides without giving arbitrary code the ability to mutate the full routing surface.

The pre-`v1.0` hardening baseline also treats caller-controlled headers as bounded inputs. Relevant routing and operator headers are normalized before they influence traces, client tags, or rollout decisions.

## Operational surface

The main operational endpoints are:

- `GET /health`
- `GET /api/providers`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/images/generations`
- `POST /v1/images/edits`
- `POST /api/route`
- `GET /api/stats`
- `GET /api/recent`
- `GET /api/traces`
- `GET /api/operator-events`
- `GET /dashboard`

`/health` now exposes both provider-level health and top-level capability coverage, so operators can quickly see whether the gateway currently has healthy support for `chat`, `image_generation`, `image_editing`, or other boolean capabilities exposed by loaded providers.

`/api/providers` exposes the normalized provider inventory with optional `capability` and `healthy` filters. This is the inventory surface the dashboard should use when it needs provider metadata beyond raw request metrics.

`/api/stats`, `/api/recent`, and `/api/traces` can now be filtered by provider, client profile, client tag, layer, and success state. `/api/operator-events` captures operator-side update checks and helper-driven apply attempts. The dashboard is a thin UI over those same filtered endpoints and persists its active filters in the URL so operators can share one filtered view.

The operational surface now also applies conservative response headers by default. The no-build dashboard ships with a restrictive CSP and frame denial, while JSON and multipart request paths use bounded payload limits so obvious oversize failures are rejected before provider calls.

## Design target

The longer-term design target is to outperform simpler router designs by making routing multi-dimensional instead of mostly keyword- or model-name-driven.

The dimensions fusionAIze Gate should eventually combine include:

- provider capabilities
- latency and health
- cost tier
- local vs cloud locality
- client type
- tool usage
- context window limits
- cache behavior and cache pricing
- modality requirements such as chat vs image generation
- policy and compliance constraints

That is the intended shape:

- one gateway core
- many providers
- many clients
- optional context and optimization layers
- clear operational boundaries
