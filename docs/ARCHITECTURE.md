# FoundryGate Architecture

## Purpose

FoundryGate is a local-first AI gateway plane.

Its job is to sit between many clients and many model backends while keeping one stable operational surface:

- one OpenAI-compatible endpoint
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

Before a candidate is accepted, FoundryGate also scores and validates route fit against provider metadata such as context window, input/output token limits, cache hints, locality, health, latency, and recent failure state.

## Provider layer

The provider layer already supports:

- OpenAI-compatible backends
- Google GenAI backends
- `contract: local-worker` for LAN/local OpenAI-compatible workers

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
- `x-foundrygate-client`
- `x-foundrygate-profile`
- `x-foundrygate-prefer-provider`
- `x-foundrygate-locality`

This is enough to support:

- OpenClaw one-agent traffic
- OpenClaw many-agent/sub-agent traffic
- n8n workflows
- CLI wrappers

Request hooks sit beside these caller-aware signals as a narrow extension seam. They can add sanitized request-level hints or profile overrides without giving arbitrary code the ability to mutate the full routing surface.

## Operational surface

The main operational endpoints are:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /api/route`
- `GET /api/stats`
- `GET /api/recent`
- `GET /api/traces`
- `GET /dashboard`

`/api/stats`, `/api/recent`, and `/api/traces` can now be filtered by provider, client profile, client tag, layer, and success state. The dashboard is a thin UI over those same filtered endpoints and persists its active filters in the URL so operators can share one filtered view.

## Design target

The longer-term design target is to outperform simpler router designs by making routing multi-dimensional instead of mostly keyword- or model-name-driven.

The dimensions FoundryGate should eventually combine include:

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
