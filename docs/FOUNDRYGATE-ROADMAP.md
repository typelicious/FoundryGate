# FoundryGate Roadmap

## Status

`FoundryGate` is now the product and runtime name for this project direction.

This document is intentionally pragmatic. It describes the target shape of the project, the boundaries that keep it maintainable, and the next concrete implementation steps.

## Why FoundryGate

The current codebase already solves a real problem well:

- one local OpenAI-compatible endpoint
- multiple upstream providers
- routing and fallback behavior
- health and lightweight operational visibility

The next step is not to turn the project into a monolithic "AI platform". The next step is to turn it into a stronger gateway plane that can sit between many clients and many model backends across local and cloud environments.

That means:

- local and cloud providers should look uniform to the caller
- routing should be policy-driven, not hard-coded per client
- new clients should integrate through stable adapters, not one-off hacks
- memory, context, and token optimization should plug into the gateway cleanly without becoming mandatory core dependencies

## Goal State

FoundryGate should become:

- a local-first AI gateway for self-hosted and hybrid environments
- an OpenAI-compatible entry point for tools that already speak common LLM APIs
- a routing layer that can choose between local workers, direct provider APIs, and proxy providers
- an operational control point for fallback, health, latency, usage, and policy enforcement
- an extensible integration layer for higher-level clients such as OpenClaw, n8n, SaaS platforms, and CLI wrappers

## Non-Goals

FoundryGate should not become all of these at once:

- a full agent framework
- a workflow engine
- a hard-coupled long-term memory system
- a mandatory token optimizer in the request path
- a UI-heavy platform before the routing plane is stable

Those capabilities may exist around FoundryGate, but the gateway should remain composable and operationally simple.

## Who It Should Serve

### Primary users

- OpenClaw users who want one stable local endpoint across multiple providers
- operators running mixed local/cloud AI stacks
- n8n and automation builders who want routing and fallback without wiring each provider manually
- developers using CLI-based AI tools that can benefit from a local proxy layer

### Secondary users

- teams building AI-native products that need a reusable gateway in development and production
- operators who want to insert local workers, context services, or optimization layers without changing every client

## Architecture Direction

FoundryGate should evolve into four clear layers.

### 1. Gateway Core

Responsibilities:

- request normalization
- provider selection
- fallback handling
- timeouts and retry boundaries
- usage and latency recording
- stable operational endpoints

This remains the center of the system.

### 2. Provider Layer

Responsibilities:

- direct cloud providers
- OpenAI-compatible proxies
- local runtimes and workers
- future network-local model workers

A local worker should be modeled as a normal provider with declared capabilities, not as a special case.

### 3. Client Adapter Layer

Responsibilities:

- OpenAI-compatible HTTP entry point
- OpenClaw-focused configuration and alias guidance
- automation and workflow clients such as n8n
- optional CLI proxy or command-wrapper entry points

The core rule is simple: prefer standard protocols first. Add dedicated adapters only when a client cannot cleanly use the common API surface.

### 4. Optional Extension Layer

Responsibilities:

- context and memory hooks
- token optimization or prompt compaction
- policy packs
- tenant- or client-specific routing overlays

These extensions should remain optional and explicitly enabled.

## Capability Model

The next major technical step is a capability-aware provider model.

Each provider should advertise fields such as:

- `chat`
- `reasoning`
- `vision`
- `tools`
- `long_context`
- `streaming`
- `local`
- `cloud`
- `cost_tier`
- `latency_tier`
- `network_zone`
- `compliance_scope`

Routing can then move away from brittle model-name assumptions and toward explicit policy decisions.

Examples:

- interactive low-latency requests prefer cheap or local providers
- sensitive local-only traffic is pinned to a network-local worker
- tool-using agent tasks prefer providers with better tool reliability
- long-context workloads prefer providers or preprocessors optimized for context handling

## Policy Model

FoundryGate should support policy-based routing on top of capabilities.

Policies should be declarative and easy to audit. A policy can consider:

- client identity
- request class
- explicit model request
- capabilities required
- budget or cost tier
- latency preference
- local-only or cloud-allowed constraints

This is the bridge between "generic gateway" and "AI-native control plane".

## Local Worker Direction

A future network-local worker should be integrated as a first-class provider.

Requirements:

- reachable over a stable HTTP API
- capability metadata declared in config
- health and timeout behavior equivalent to cloud providers
- policy addressable as `local`, `reasoning`, `private`, or similar

The gateway should not care whether the backend is a cloud API, a local model server, or a worker running somewhere else in the local network, as long as the provider contract is stable.

## Context And Memory Direction

Context and memory are important, but they should not be forced into the core request path too early.

The cleaner design is:

- FoundryGate remains the gateway and routing plane
- context services enrich or retrieve relevant context
- memory systems remain external but pluggable
- the gateway can call out to them through hooks or preprocessors

This leaves room for integrating ideas such as structured context stores, knowledge graphs, or ICM-style memory layers without hard-coding one memory architecture into the gateway itself.

## CLI Proxy And Token Optimization

A CLI proxy or command-wrapper router is a good fit, but as an adapter or optional preprocessor rather than a mandatory gateway feature.

Good uses:

- normalize requests from CLI tools that do not share one API shape
- compress or optimize context before forwarding
- apply policy and observability to terminal-native AI workflows

Bad uses:

- hiding unstable prompt rewrites deep inside the core router
- making every request dependent on a fragile optimizer

The correct shape is likely:

- client adapter or sidecar process
- optional optimization stage
- explicit enablement per client profile

## Admin And Monitoring Direction

An admin surface is useful, but it should start as an operational console, not a full control UI.

### Phase 1 dashboard goals

- provider health
- last errors
- average latency
- recent routed requests
- fallback counts
- basic usage and cost summaries
- active routing rules and policy hits

### Later dashboard goals

- config validation
- dry-run route simulation
- client profile inspection
- policy editing

Write access should come after read-heavy observability is stable.

## Rename Strategy

The technical rename to `FoundryGate` is complete in the runtime, operational surface, and GitHub repository name.

The remaining rename work is release-facing:

1. publish the first FoundryGate-branded release
2. communicate migration notes for existing `clawgate` users if they are still present downstream

## Phased Plan

### Phase 0: Stabilize The Current Core

Objective:

- keep the current OpenAI-compatible routing path reliable
- preserve current integrations while preparing for broader use

Deliverables:

- cleanly document the rename plan
- tighten provider contracts
- make health, timeout, and fallback behavior explicit in tests
- keep the DB path and runtime state outside the repo checkout

### Phase 1: Capability-Aware Routing

Objective:

- make routing depend on declared provider capabilities and policies

Deliverables:

- provider capability schema
- policy schema
- router changes that resolve providers by capability plus policy
- config validation for invalid or contradictory provider definitions

### Phase 2: Local Worker Integration

Objective:

- add network-local model workers as first-class providers

Deliverables:

- local worker provider contract
- example config for a local worker backend
- health and timeout handling for local workers
- policy examples for local-only, hybrid, and fallback routing

### Phase 3: Client Profiles And Adapters

Objective:

- support different caller types without forking the gateway logic

Deliverables:

- client profile system
- OpenClaw profile
- n8n profile
- generic automation profile
- initial CLI proxy design or sidecar adapter

### Phase 4: Operational Console

Objective:

- make the system observable enough to operate confidently

Deliverables:

- dashboard for health, routes, fallbacks, and usage
- route debugging or dry-run tools
- clearer operational endpoints

### Phase 5: Optional Context And Optimization Hooks

Objective:

- allow context and optimization layers without coupling them to the gateway core

Deliverables:

- request preprocessor hook interface
- context retrieval hook interface
- optional token optimization integration
- policy guardrails around these extensions

## Concrete Next Backlog

These are the next implementation-sized work items, ordered by leverage.

### 1. Define a provider capability schema

Why:

- this unlocks generic routing and future local worker support

Work:

- extend provider config with capability metadata
- validate config at startup
- expose capabilities in internal provider state

### 2. Add a policy engine layer

Why:

- routing rules should be declarative and auditable

Work:

- introduce policy objects
- resolve route candidates from request + provider capabilities
- preserve direct model pinning for explicit requests

### 3. Add a first-class local worker provider example

Why:

- this is the key differentiator versus cloud-only routers

Work:

- define an OpenAI-compatible local worker provider contract
- add example config
- verify fallback and timeout behavior

### 4. Add client profiles

Why:

- OpenClaw, n8n, and CLI tools have different routing needs even when they share an API

Work:

- identify callers through config or headers
- apply profile-specific policy defaults
- document profile examples

### 5. Add route introspection

Why:

- operators need to know why a route was chosen

Work:

- enrich response headers where safe
- add debug metadata in logs and operational endpoints
- expose rule and policy hit counters

### 6. Define an extension contract for context and optimization hooks

Why:

- this creates a clean seam for memory and RTK-like integrations later

Work:

- define pre-route and pre-dispatch hook points
- keep hooks optional and bounded
- document failure handling and timeouts for extensions

## Suggested Near-Term PR Sequence

To keep the work reviewable, the next PRs should stay small.

1. `docs: add FoundryGate roadmap and rename note`
2. `feat(config): add provider capability schema`
3. `feat(router): add policy-based provider selection`
4. `feat(provider): add local worker provider contract`
5. `feat(api): add client profile support`
6. `feat(obs): add route introspection and policy metrics`
7. `feat(ext): add optional request hook interfaces`

## Big Picture

The larger opportunity is not "another router". The larger opportunity is a reusable AI gateway plane that works across:

- local model workers
- direct provider APIs
- proxy providers
- agent tools
- workflow systems
- CLI-native development environments
- future AI-native SaaS products

If the core stays disciplined, FoundryGate can become the common routing and policy layer shared by several products without collapsing into a bloated platform.

That is the right long-term shape:

- one gateway core
- many providers
- many clients
- optional context and optimization layers
- clear operational boundaries

## Assumptions

- OpenAI-compatible HTTP remains the primary interoperability surface for the near term
- local worker support will be easiest to operationalize if the worker speaks an OpenAI-compatible or similarly simple HTTP contract
- memory, context, and optimization will remain optional extensions rather than mandatory core behavior
- the GitHub repository rename, if done, will be handled as a separate external step
