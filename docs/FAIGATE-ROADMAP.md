# fusionAIze Gate Roadmap

## Status

fusionAIze Gate is now the public product, runtime, and repository name.

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
- a hardened simple dashboard with filtered traces, client/provider views, URL-persisted filters, operator summary cards, and modality/capability coverage

This roadmap now shifts from "rename and foundation" to "deepen the gateway plane without bloating it".

The next major product track is now explicit: adaptive model orchestration.

That means the next meaningful line is not just "more providers" or "more UI". It is:

- canonical model lanes
- route-aware aggregator handling
- benchmark and cost clusters
- live adaptation under quota, latency, and failure pressure
- operator explainability for every major routing decision

The detailed design lives in [Adaptive model orchestration](./ADAPTIVE-ORCHESTRATION.md).

`v1.2.0` is now shipped. The workstation baseline is in place: Linux, macOS, and Windows runtime guidance is documented, macOS helpers now auto-detect `launchd`, and a project-owned Homebrew path exists for packaged macOS installs.

`v1.2.x` also closed the immediate Homebrew/macOS packaging loop. The next active release line should therefore shift to `v1.3.0`: guided setup, catalog-assisted updates, and safer operator ergonomics for many fast-moving providers.

The next block should stay disciplined: build on the workstation baseline, keep packaging practical, and avoid turning fusionAIze Gate into a sprawling platform.

## `v1.8.0` to `v1.11.x`: adaptive model orchestration

Primary goals:

- treat providers, aggregators, and direct routes as execution paths to canonical model lanes rather than as one flat list of alternatives
- let scenarios such as `quality`, `balanced`, `eco`, and `free` choose the right lane threshold and degradation path instead of only choosing a provider tier
- preserve same-lane quality when direct quota is exhausted by trying equivalent aggregator routes before dropping to a weaker model cluster
- keep benchmark and cost assumptions visible, curated, and refreshable so "magical" routing still stays explainable

Release sequence:

1. `v1.8.0`: lane registry, provider lane metadata, and route-aware catalog surfaces
2. `v1.9.0`: lane-aware router scoring and "why this lane?" traces
3. `v1.10.0`: live lane adaptation using quota, latency, failure, and fallback pressure
4. `v1.10.x`: benchmark freshness, cluster-level degradation rules, and stronger budget hints
5. `v1.11.x`: operator controls, budget rails, and controlled adaptive-routing automation

Non-negotiable guardrails:

- never hide a downgrade from operators
- prefer same-lane route substitution before weaker-model degradation
- keep old configs compatible while lane metadata is introduced
- treat benchmarks and cost heuristics as curated operational inputs, not as magic constants

## `v1.5.0`: guided control-center UX

Primary goals:

- make the standalone Gate shell feel like the first serious product surface instead of a loose set of helper scripts
- introduce one obvious happy path for first setup, validation, restart, and client connection
- replace raw JSON-first operator views with compact human summaries plus drill-downs where needed
- keep the Gate UX aligned with the later Grid orchestration direction so the products feel like one family

Recommended minimal slices:

1. `Quick Setup` happy path inside `faigate-menu`
2. compact summary cards for gateway, config, providers, and clients in the main operational menus
3. shorter, recommendation-first client quickstarts with per-client drilldown instead of long first-contact dumps
4. explicit next-step receipts after wizard, validation, restart, and client-setup actions

Guardrails:

- keep the shell UX scriptable and helper-driven; do not turn `faigate-menu` into a full-screen TUI yet
- prefer compact default output plus optional detail/raw views over large payload dumps
- keep wording calm and operational, especially when health, service-manager state, and bound port state disagree

Post-`1.5.0` UX items already worth bookmarking:

- readiness score and richer setup progress scoring
- port/runtime conflict auto-detection with one-step recovery suggestions
- client route previews that show where a given client would land right now
- richer action receipts and broader `what to do next` guidance
- more compact client cards before the long quickstart text

## Licensing direction to bookmark after `v1.5.0`

The likely direction for the wider fusionAIze stack is hybrid:

- open what accelerates adoption, integration, and ecosystem fit
- protect what becomes the real differentiation and operating moat

Proposed tiering:

### Tier A — Open (`Apache-2.0`)

Best fit for:

- SDKs
- schemas
- reference adapters
- integration libraries
- local helper tooling
- generic client/provider compatibility layers

For fusionAIze Gate specifically, the likely open surface is:

- baseline local gateway core
- config schemas
- local/dev install flow
- generic provider adapters
- generic client adapters
- API specifications
- sample configs and reference templates

### Tier B — Open-core / source-available

Best fit for:

- advanced routing logic
- premium policy packs
- advanced observability packs
- orchestration helpers
- managed-operations modules
- enterprise connectors

### Tier C — Proprietary / commercial

Best fit for:

- managed control-plane features
- billing / metering / org policy layers
- enterprise governance integrations
- higher-value orchestration IP that belongs with the broader fusionAIze stack

Working conclusion for Gate:

- Gate still looks like a strong open-core product
- keep the baseline gateway broadly adoptable
- reserve the differentiated premium logic for later, once the `1.5.x` UX and product boundaries are settled cleanly

## `v1.3.0`: guided setup and catalog-assisted updates

Primary goals:

- make first setup and later provider updates realistic without turning `config.yaml` into hand-edited drift bait
- keep routing modes, client defaults, and provider selection understandable across many clients
- improve provider-catalog freshness and update suggestions without silently rewriting operator intent
- start the provider-discovery and recommendation-link line only in a transparency-first, metadata-first shape

Recommended minimal slices:

1. wizard candidate selection, update suggestions, dry-run summaries, and backup-aware writes
2. provider-catalog source metadata, offer-track volatility flags, and freshness alerts
3. wizard and CLI usage polish so the guided flow is self-explanatory from `--help`
4. optional provider recommendation-link metadata with explicit disclosure, but still no ranking changes based on provider-link metadata

Guardrails for any recommendation-link work in this line:

- recommendation ranking must never use provider-link metadata as an input and must stay performance-led, preferring fit, quality, health, capability, and cost behavior
- provider-link metadata should stay operator-owned and secret-backed, not embedded in user-editable client configs
- docs and CLI output should disclose clearly when a shown signup link is informational only
- the first slice should be metadata and display only; managed short links, browser control-center surfaces, and richer landing-page flows can come later

## `v1.2.0`: workstation operations baseline

Primary goals:

- add a dedicated workstation operations guide
- document macOS `launchd` as a first-class local-runtime path
- document Windows Task Scheduler / PowerShell as the baseline Windows path
- keep development checkouts and runtime installs clearly separated
- add a project-owned Homebrew packaging path for macOS workstations

Recommended minimal slices:

1. workstation baseline docs and path layout
2. macOS `launchd` example and instructions
3. Windows startup examples and documentation
4. optional lightweight install helpers only if the docs prove insufficient
5. Homebrew formula and `brew services` guidance for the packaged macOS path

## Post-1.0 direction

The first post-`1.0` block should stay narrow enough to ship as `v1.1.0`.

Primary goals:

- double-check and extend AI-native client support beyond the current OpenClaw, n8n, and CLI baseline
- ship the next wave of integration starters for requested and high-signal agent frameworks
- expose more useful per-client token and usage metrics in the operator surface
- audit the routing-stage stack so the responsibility of each layer stays clear
- keep a structured watch on ClawRouter-style product evolution without copying features blindly

The current framework prioritization lives in [AI-NATIVE-MATRIX.md](./AI-NATIVE-MATRIX.md).

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

If the core stays disciplined, fusionAIze Gate can become the common routing and policy layer shared by several products without collapsing into a bloated platform.

That is the target shape:

- one gateway core
- many providers
- many clients
- optional context and optimization layers
- clear operational boundaries

## Design principles

### 1. Gateway first

fusionAIze Gate should stay a gateway and control plane, not a monolithic platform.

### 2. Standard protocols first

If a client can use the OpenAI-compatible API cleanly, keep it on that path before building a custom adapter.

### 3. Multi-dimensional routing

The design target is to exceed simpler router behavior by making routing explicitly multi-dimensional.

That means fusionAIze Gate should increasingly consider:

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

The next runtime gap to close is not “more core abstraction”. It is “more real clients with less glue”.

## `v1.1.0`: AI-native client expansion and operator visibility

Primary goals:

- add the first post-`1.0` starter wave for requested and high-signal AI-native clients
- add a curated framework matrix so external users can quickly see where fusionAIze Gate fits
- deepen client and token reporting in API and dashboard surfaces
- review policy, static, heuristic, hook, client-profile, and classifier boundaries with clearer ownership and tests

Recommended minimal slices:

1. AI-native client matrix plus roadmap update
2. first-wave starter templates for `SWE-AF`, `paperclip`, `ship-faster`, and the highest-fit external frameworks
3. per-client token and usage reporting in stats and dashboard views
4. routing-layer review plus targeted rule/test cleanup

The plugin question should stay explicitly out of scope for `v1.1.0` and be revisited only after this release line lands.

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

Inspired by the value of image-router patterns in other gateways, fusionAIze Gate should eventually support modality-aware routing beyond chat.

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

`v0.3.0` is the first public fusionAIze Gate release. The path to `v1.0.0` should stay incremental and reviewable.

### `v0.4.x`: deeper routing and extension hardening

Primary goals:

- deepen multi-dimensional scoring beyond simple fit checks for cache behavior, context windows, provider limits, locality, latency, and recent failures
- keep refining the simple dashboard around traces, provider/client breakdowns, route visibility, and safe operator ergonomics
- keep OpenClaw one-agent and many-agent flows on the same OpenAI-compatible path with clearer defaults
- harden the request hook seam for context, memory, and optimization layers, including fail-closed behavior and input sanitization

This release line should deepen the gateway core without turning it into a monolith.

### `v0.5.0`: operator distribution baseline

Primary goals:

- add the first modality-aware provider contract, starting with image generation
- publish an official Docker release path
- publish fusionAIze Gate to PyPI
- add provider and client onboarding helpers for many-provider and many-client deployments
- add a publish dry-run path for Python package and GHCR validation before real release tags
- add validation workflows so operators can catch config mistakes before rollout
- complete the public community-health baseline and security-overview baseline for the repo

This is the first release line where installation and upgrade paths should feel productized for external users.

### `v0.6.x`: modality expansion

Primary goals:

- add modality-aware provider contracts, starting with image generation
- extend that contract toward image editing where the provider surface supports it
- keep chat and image paths explicit instead of mixing modality-specific behavior into one opaque route
- expose modality-aware health, provider inventory, and routing visibility in the dashboard and operational endpoints

This should borrow the useful parts of image-router patterns without copying another gateway's product shape.

### `v0.7.x`: operations polish

Primary goals:

- expand the release-check baseline into stronger update alerts so operators can see when a newer release is available
- add an optional automatic update enabler for controlled deployments
- improve route traces, metrics, and dashboard filters for providers, clients, and profiles
- keep the dashboard simple, read-heavy, and operationally safe

This release line is about day-2 operations rather than new routing concepts.

The first small slice in this line is to turn `GET /api/update` from a plain boolean check into an operator-facing alert surface with update type, alert level, and recommended action.

The next small slice is to keep auto-update conservative:

- disabled by default
- no checkout mutation over HTTP
- helper-driven and operator-triggered only
- major upgrades still manual unless explicitly allowed

### `v0.8.x`: many-provider and many-client onboarding

Primary goals:

- make onboarding repeatable for many providers and many clients on one gateway
- ship clearer presets and validation for OpenClaw, n8n, CLI wrappers, and future AI-native applications
- reduce manual config editing for common deployment shapes
- tighten integration coverage for delegated or many-agent traffic where headers identify sub-clients

The target is faster adoption without custom glue for every client.

Current `v0.8.x` baseline already includes:

- onboarding report plus validation helpers
- staged provider rollout reporting
- client matrix reporting
- starter templates for OpenClaw, n8n, CLI, cloud providers, local workers, and image providers
- matching provider `.env` starter files
- delegated OpenClaw request examples
- starter custom-profile examples for future AI-native applications
- doctor checks for missing provider env placeholders
- JSON and Markdown onboarding exports

### `v0.9.x`: pre-1.0 hardening

Primary goals:

- stabilize request hook boundaries and extension contracts
- expand integration and functional test coverage across real client flows
- complete documentation review across README, onboarding, integrations, troubleshooting, and release docs
- close obvious operational gaps discovered during earlier releases

This release line should leave `v1.0.0` focused on stability and security gates, not backlog cleanup.

Current `v0.9.x` baseline is aimed at:

- conservative response headers and dashboard CSP defaults
- explicit JSON and multipart size guardrails
- bounded routing and operator header handling
- broader functional API tests around dashboard, routing, and upload surfaces
- documentation updates that make the hardened defaults visible to operators

### `v1.0.0`: stable gateway baseline

Primary goals:

- declare a stable fusionAIze Gate gateway baseline for local-first, multi-provider routing
- publish the first separate npm CLI package for fusionAIze Gate-adjacent CLI usage
- complete a comprehensive security review before release

The `v1.0.0` security review should explicitly cover:

- cross-site scripting and HTML or CSS injection risks in the dashboard
- request, header, and parameter injection risks in proxy and routing paths
- dependency vulnerabilities and unsafe defaults
- local-worker and upstream proxy trust boundaries
- auth, secret-handling, and writable-path assumptions

`v1.0.0` should only ship after those review results are addressed or documented with a clear mitigation plan.

Current `v1.0.0` baseline is aimed at:

- dashboard CSP hardening without turning the no-build UI into a separate frontend app
- reduced leakage of upstream provider failure details in client responses
- clearer trust-boundary validation for provider base URLs
- a documented release-gate security review with explicit residual risks
- a separate npm CLI package that complements the Python gateway instead of replacing it

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

1. `docs: add fusionAIze Gate roadmap and rename note` -> done
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

- fusionAIze Gate already exposes a dashboard endpoint, but operators need a clearer read-only control surface

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

Current baseline:

- cached release checks via `GET /api/update`
- dashboard visibility for current vs latest known release
- local helper access via `faigate-update-check`
- opt-in eligibility reporting and helper-driven apply flow via `faigate-auto-update`

This should remain opt-in and operationally conservative as it expands toward scheduled helper use, stronger rollout controls, clearer operator approval boundaries, and small rollout-ring/channel distinctions.

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

fusionAIze Gate should be understandable from the outside in under a few minutes.

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

This is necessary because fusionAIze Gate is evolving quickly and the docs can drift even when individual PRs are clean.

## Provider discovery and recommendation links

fusionAIze Gate should be able to help operators and end users discover suitable providers, but it should not turn recommendation output into a monetized marketplace.

That means the future recommendation-link line should stay deliberately staged:

### First slices that make sense soon

- add optional provider-catalog fields for signup URLs, disclosure labels, and source ownership
- surface those links in CLI or later browser-based control-center output only when they are available and disclosed
- allow operator-managed secret or env-backed provider-link overrides rather than baking them into normal client-visible config

### Later slices that make sense after that

- optional managed short-link or landing-page wrappers
- richer provider discovery views in a small browser control center
- trust/performance signals derived from historical provider behavior, so recommendations can explain quality and reliability more concretely

The non-negotiable rule is simple: recommendation quality must stay fully independent from provider-link metadata, and signup links may only follow from a recommendation rather than shaping it.

## Assumptions

- OpenAI-compatible HTTP remains the default interoperability surface in the near term
- OpenClaw, n8n, and CLI tools should keep sharing one gateway unless a client truly requires a dedicated adapter
- modality expansion should stay contract-driven instead of adding ad hoc special cases
- context, memory, and optimization remain optional layers around the gateway core
