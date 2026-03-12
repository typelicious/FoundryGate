# FoundryGate Roadmap

## Status

FoundryGate is now the public product, runtime, and repository name.

The foundation that used to be the near-term buildout is largely in place:

- provider capability schema
- policy-based provider selection
- local worker provider contract
- client profiles and presets
- optional request hook interfaces
- multi-dimensional candidate scoring for context windows, token limits, locality, cache alignment, health, latency, and recent failures
- route introspection
- routing traces and client/profile metrics
- local worker probing
- a hardened simple dashboard with filtered traces, client/provider views, URL-persisted filters, and operator summary cards

This roadmap now shifts from "rename and foundation" to "deepen the gateway plane without bloating it".

`v0.4.0` is the current routing-baseline release line: hooks, richer scoring, route introspection, and the refined dashboard are now in place.

## Big Picture

The opportunity is not to build another thin router.

The opportunity is to build a reusable AI gateway plane that works across:

- local model workers
- direct provider APIs
- proxy providers
- OpenClaw
- workflow systems such as n8n
- CLI-native development environments
- agent tools
- future AI-native SaaS products

If the core stays disciplined, FoundryGate can become the common routing and policy layer shared by several products without collapsing into a bloated platform.

That is the target shape:

- one gateway core
- many providers
- many clients
- optional context and optimization layers
- clear operational boundaries

## Design principles

### 1. Gateway first

FoundryGate should stay a gateway and control plane, not a monolithic platform.

### 2. Standard protocols first

If a client can use the OpenAI-compatible API cleanly, keep it on that path before building a custom adapter.

### 3. Multi-dimensional routing

The design target is to exceed simpler router behavior by making routing explicitly multi-dimensional.

That means FoundryGate should increasingly consider:

- capability support
- health and latency
- cost tier
- local vs cloud locality
- context window size
- cache behavior and cache pricing
- tool usage
- client identity
- modality requirements
- compliance or tenancy constraints

The intent is not to claim that this is fully implemented today. The intent is to make this the guiding routing architecture.

### 4. Optional extension layers

Context, memory, optimization, and sidecar adapters should plug into the gateway cleanly, not become mandatory core behavior.

## Current runtime baseline

Today the runtime already supports:

- one OpenAI-compatible endpoint
- multiple providers behind a single local base URL
- policy, static, heuristic, client-profile, and optional LLM-assisted routing stages
- direct model pinning and fallback chains
- local worker contracts and health probes
- route introspection and traces
- client-aware routing defaults for OpenClaw, n8n, and CLI callers

## OpenClaw direction

OpenClaw remains a first-class integration surface.

Current coverage:

- one-agent traffic through the normal OpenAI-compatible path
- many-agent or delegated traffic through the same path with `x-openclaw-source`
- OpenClaw-side model aliases and profile defaults

Near-term direction:

- document one-agent and many-agent behavior explicitly
- keep the integration header-based and OpenAI-compatible
- avoid forking the core gateway logic just for OpenClaw

## Modality expansion

Inspired by the value of image-router patterns in other gateways, FoundryGate should eventually support modality-aware routing beyond chat.

Planned direction:

- add a provider contract for image-generation-capable backends
- add modality-aware request classification
- route image tasks to the right backend without polluting the chat path

This is a roadmap item, not a current runtime claim.

## Architecture direction

### Gateway core

Responsibilities:

- request normalization
- route selection
- fallback handling
- timeout boundaries
- usage and trace recording
- operational endpoints

### Provider layer

Responsibilities:

- cloud providers
- OpenAI-compatible proxies
- local workers
- future modality-specific providers

### Client layer

Responsibilities:

- OpenClaw
- n8n and workflow clients
- CLI wrappers and proxy clients
- future AI-native app integrations

### Optional extension layer

Responsibilities:

- request hooks
- context or memory enrichment
- optimization hooks
- policy overlays

## Release path to v1.0.0

`v0.3.0` is the first public FoundryGate release. The path to `v1.0.0` should stay incremental and reviewable.

### `v0.4.x`: deeper routing and extension hardening

Primary goals:

- deepen multi-dimensional scoring beyond simple fit checks for cache behavior, context windows, provider limits, locality, latency, and recent failures
- keep refining the simple dashboard around traces, provider/client breakdowns, route visibility, and safe operator ergonomics
- keep OpenClaw one-agent and many-agent flows on the same OpenAI-compatible path with clearer defaults
- harden the request hook seam for context, memory, and optimization layers, including fail-closed behavior and input sanitization

This release line should deepen the gateway core without turning it into a monolith.

### `v0.5.0`: operator distribution baseline

Primary goals:

- publish an official Docker release path
- publish FoundryGate to PyPI
- add provider and client onboarding helpers for many-provider and many-client deployments
- add validation workflows so operators can catch config mistakes before rollout

This is the first release line where installation and upgrade paths should feel productized for external users.

### `v0.6.x`: modality expansion

Primary goals:

- add modality-aware provider contracts, starting with image generation
- extend that contract toward image editing where the provider surface supports it
- keep chat and image paths explicit instead of mixing modality-specific behavior into one opaque route
- expose modality-aware health and routing visibility in the dashboard and operational endpoints

This should borrow the useful parts of image-router patterns without copying another gateway's product shape.

### `v0.7.x`: operations polish

Primary goals:

- add update alerts so operators can see when a newer release is available
- add an optional automatic update enabler for controlled deployments
- improve route traces, metrics, and dashboard filters for providers, clients, and profiles
- keep the dashboard simple, read-heavy, and operationally safe

This release line is about day-2 operations rather than new routing concepts.

### `v0.8.x`: many-provider and many-client onboarding

Primary goals:

- make onboarding repeatable for many providers and many clients on one gateway
- ship clearer presets and validation for OpenClaw, n8n, CLI wrappers, and future AI-native applications
- reduce manual config editing for common deployment shapes
- tighten integration coverage for delegated or many-agent traffic where headers identify sub-clients

The target is faster adoption without custom glue for every client.

### `v0.9.x`: pre-1.0 hardening

Primary goals:

- stabilize request hook boundaries and extension contracts
- expand integration and functional test coverage across real client flows
- complete documentation review across README, onboarding, integrations, troubleshooting, and release docs
- close obvious operational gaps discovered during earlier releases

This release line should leave `v1.0.0` focused on stability and security gates, not backlog cleanup.

### `v1.0.0`: stable gateway baseline

Primary goals:

- declare a stable FoundryGate gateway baseline for local-first, multi-provider routing
- publish the first separate npm or TypeScript CLI package for FoundryGate-adjacent CLI usage
- complete a comprehensive security review before release

The `v1.0.0` security review should explicitly cover:

- cross-site scripting and HTML or CSS injection risks in the dashboard
- request, header, and parameter injection risks in proxy and routing paths
- dependency vulnerabilities and unsafe defaults
- local-worker and upstream proxy trust boundaries
- auth, secret-handling, and writable-path assumptions

`v1.0.0` should only ship after those review results are addressed or documented with a clear mitigation plan.

## Updated near-term PR sequence

The next sequence should ladder directly into the release path above:

1. `feat(provider): add modality-aware provider contracts, starting with image generation`
2. `feat(provider): extend modality contracts toward image editing where supported`
3. `feat(onboarding): add provider/client onboarding helpers and validation workflows`
4. `feat(dist): add Docker release path and PyPI publishing baseline`
5. `feat(ops): add update alerts and an optional auto-update enabler for controlled deployments`
6. `feat(cli): define the separate npm or TypeScript CLI package path for the v1.0.0 line`

## Check on the earlier sequence

The earlier near-term sequence is now effectively complete up through the routing and observability foundation:

1. `docs: add FoundryGate roadmap and rename note` -> done
2. `feat(config): add provider capability schema` -> done
3. `feat(router): add policy-based provider selection` -> done
4. `feat(provider): add local worker provider contract` -> done
5. `feat(api): add client profile support` -> done
6. `feat(obs): add route introspection and policy metrics` -> done, and now extended with traces and local worker probing
7. `feat(ext): add optional request hook interfaces` -> done
8. `feat(router): add first multi-dimensional route-fit inputs for cache, context windows, provider limits, and locality` -> done
9. `feat(obs): harden the simple dashboard around traces, provider/client filters, and route visibility` -> done

## Detailed near-term backlog

### 1. Optional request hook interfaces

Why:

- this creates the seam for context, memory, and optimization layers without hard-coupling them

Examples:

- optional memory or context enrichment before routing
- request-shaping hooks for RTK-like CLI optimization
- operator-controlled extension points that can stay disabled by default

### 2. Multi-dimensional routing inputs

Why:

- routing should understand more than keywords and simple tier preferences

Examples:

- cache-read vs cache-miss economics
- context window fit
- locality and policy constraints
- latency/health tradeoffs
- provider-specific max context and cache behavior

### 3. Simple dashboard hardening

Why:

- FoundryGate already exposes a dashboard endpoint, but operators need a clearer read-only control surface

Examples:

- route trace table with provider and client filters
- provider health panel with capabilities and contract type
- quick links to dry-run routing and recent failure context

### 4. Image generation and editing routing

Why:

- multi-modal routing is a natural next expansion for a gateway plane

Examples:

- image-generation-capable provider contracts
- image-editing-capable provider contracts
- explicit modality routing so chat, image generation, and image editing stay understandable

### 5. Provider and client onboarding helpers

Why:

- many-provider, many-client deployments need a clearer adoption path than manual config editing alone

Examples:

- bootstrap helpers for provider credentials and base URLs
- starter profiles for OpenClaw, n8n, CLI, and future AI-native applications
- preflight config validation before a rollout or restart

### 6. Update alerts and optional automatic update enablers

Why:

- operators need a safer path than only ad hoc manual updates

This should remain opt-in and operationally conservative.

### 7. Distribution channels

Why:

- the project should become easier to adopt without coupling packaging strategy to one runtime

Examples:

- GitHub Releases as the default channel now
- Docker images and PyPI packages by `v0.5.0`
- a separate npm or TypeScript CLI package by `v1.0.0`, not a Node rewrite of the core gateway

### 8. Security review as a release gate

Why:

- `v1.0.0` needs a credible stability and security bar, not just a larger feature list

Examples:

- dashboard rendering review for XSS and HTML or CSS injection paths
- request routing review for injection, header abuse, and unsafe forwarding behavior
- dependency and configuration review for known vulnerabilities and insecure defaults
- documentation review so security expectations and deployment assumptions are explicit

## Documentation direction

FoundryGate should be understandable from the outside in under a few minutes.

That means keeping these docs current:

- README for the landing page
- architecture for technical orientation
- integrations for OpenClaw, n8n, CLI, and future clients
- onboarding for many-provider and many-client adoption
- troubleshooting for operators
- process docs for contributors

## Review cadence

Every 4 or 5 merged PRs, run a broader review pass:

- review unit tests
- review integration tests
- review functional coverage against real workflows
- update every relevant doc
- refresh the roadmap and process docs if the direction changed

This is necessary because FoundryGate is evolving quickly and the docs can drift even when individual PRs are clean.

## Assumptions

- OpenAI-compatible HTTP remains the default interoperability surface in the near term
- OpenClaw, n8n, and CLI tools should keep sharing one gateway unless a client truly requires a dedicated adapter
- modality expansion should stay contract-driven instead of adding ad hoc special cases
- context, memory, and optimization remain optional layers around the gateway core
