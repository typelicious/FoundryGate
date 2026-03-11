# FoundryGate Roadmap

## Status

FoundryGate is now the public product, runtime, and repository name.

The foundation that used to be the near-term buildout is largely in place:

- provider capability schema
- policy-based provider selection
- local worker provider contract
- client profiles and presets
- route introspection
- routing traces and client/profile metrics
- local worker probing

This roadmap now shifts from "rename and foundation" to "deepen the gateway plane without bloating it".

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

## Updated near-term PR sequence

The original near-term sequence has mostly landed. The next sequence should now be:

1. `docs: refresh roadmap, architecture, onboarding, integrations, and troubleshooting`
2. `feat(ext): add optional request hook interfaces`
3. `feat(router): add multi-dimensional routing inputs for cache, context windows, and provider limits`
4. `feat(provider): add modality-aware provider contracts, starting with image generation`
5. `feat(onboarding): add provider/client onboarding helpers and validation workflows`
6. `feat(ops): add update alerts and an optional auto-update enabler for controlled deployments`

## Check on the earlier sequence

The earlier near-term sequence is now effectively complete up through the routing and observability foundation:

1. `docs: add FoundryGate roadmap and rename note` -> done
2. `feat(config): add provider capability schema` -> done
3. `feat(router): add policy-based provider selection` -> done
4. `feat(provider): add local worker provider contract` -> done
5. `feat(api): add client profile support` -> done
6. `feat(obs): add route introspection and policy metrics` -> done, and now extended with traces and local worker probing
7. `feat(ext): add optional request hook interfaces` -> still open and should stay near the top of the next sequence

## Detailed near-term backlog

### 1. Optional request hook interfaces

Why:

- this creates the seam for context, memory, and optimization layers without hard-coupling them

### 2. Multi-dimensional routing inputs

Why:

- routing should understand more than keywords and simple tier preferences

Examples:

- cache-read vs cache-miss economics
- context window fit
- locality and policy constraints
- latency/health tradeoffs

### 3. Image generation routing

Why:

- multi-modal routing is a natural next expansion for a gateway plane

### 4. Provider and client onboarding helpers

Why:

- many-provider, many-client deployments need a clearer adoption path than manual config editing alone

### 5. Update alerts and optional automatic update enablers

Why:

- operators need a safer path than only ad hoc manual updates

This should remain opt-in and operationally conservative.

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
