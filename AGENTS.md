# AGENTS.md — FoundryGate

## Project identity

This repository hosts `FoundryGate`, a public MIT-licensed local-first AI gateway.

FoundryGate provides:

1. one OpenAI-compatible local endpoint,
2. routing across multiple upstream providers,
3. fallback and health-aware request handling,
4. a path toward local workers, client profiles, and optional context or optimization hooks.

## Current naming status

The product name is `FoundryGate`.

During the transition, some technical compatibility identifiers still use `clawgate`, including:

- the Python package name,
- the `clawgate.service` unit file,
- `CLAWGATE_DB_PATH`,
- helper script names,
- the current OpenClaw integration example.

Do not rename compatibility identifiers casually. Keep runtime changes explicit and reviewable.

## Product priority

The gateway is the product.

Do not turn this repository into a monolithic agent framework, workflow engine, or memory platform.

Prioritize:

- reliable request routing,
- clear provider contracts,
- policy-driven behavior,
- local and cloud portability,
- operational visibility,
- clean integration points for higher-level tools.

## Architecture principles

Use a pragmatic gateway-first architecture:

- small gateway core,
- clear provider boundaries,
- client adapters instead of one-off integrations,
- optional extensions for context, memory, or optimization,
- operational simplicity over platform sprawl.

Prefer standard API surfaces first.
If a tool can speak an OpenAI-compatible endpoint cleanly, use that before adding a custom adapter.

## Supported interaction surfaces

FoundryGate should support these surfaces over time:

### Current

- OpenAI-compatible HTTP clients
- OpenClaw
- local operators using helper scripts and systemd

### Near term

- n8n and automation clients
- local or network-local model workers
- CLI-oriented adapters or proxy wrappers

### Later

- optional dashboards or admin surfaces
- optional context, memory, and optimization hooks

## Implementation rules

Implement now:

- routing reliability,
- provider capability metadata,
- policy-based routing,
- local worker support,
- client profile support,
- observability improvements,
- release and process documentation.

Defer or keep optional:

- heavy UI surfaces,
- hard-coupled memory systems,
- mandatory token optimization in the core request path,
- tool-specific integrations when a standard API already works.

## Code quality rules

- keep modules small and testable
- prefer explicit contracts over implicit behavior
- avoid hidden routing magic
- keep operational failure modes visible in logs and health output
- preserve backwards compatibility when a rename or integration change is user-facing

## Workflow rules

Work in small coherent steps.
Prefer commit-sized implementation blocks.
Stop after each major block and summarize what changed, what remains, and what is intentionally deferred.

Follow the branch workflow defined in:

- `docs/process/git-workflow.md`

Default branch model:

- `main`
- `feature/<topic>-<date>`
- `review/<topic>-<date>`
- `hotfix/<topic>-<date>` when production-oriented urgency justifies it

Do not introduce a long-lived `develop` branch unless the repository truly needs one.

## RTK shell command preference

For Codex and other shell-driven agents without stronger native command hooks, prefer RTK-wrapped shell commands whenever applicable.

Use raw commands only when RTK is not available or not a good fit, and state that briefly.

## Documentation rules

Maintain:

- the README as the primary public landing page,
- roadmap documentation,
- release and changelog documentation,
- process documentation for workflow-critical conventions,
- compatibility notes when product naming and technical identifiers differ.

Do not document features that do not exist.

## Security rules

- never hardcode secrets
- never commit `.env`, keys, databases, sqlite files, or logs
- keep runtime state outside the repo checkout
- treat repo-safety rules as mandatory guardrails, not optional hygiene

## Release rules

- `main` should remain stable and releaseable
- document user-visible changes in `CHANGELOG.md`
- use lightweight semantic versioning in `x.y.z` form
- prefer minor bumps for meaningful features or operational behavior changes
- prefer patch bumps for fixes, polish, and small compatibility updates
- reserve major bumps for explicit breaking changes and documented migrations
