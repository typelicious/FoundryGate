# FoundryGate Changelog

All notable changes to FoundryGate should be documented here.

The format is intentionally lightweight and human-readable. Group entries by release and focus on user-visible behavior, operational changes, and compatibility notes.

## Unreleased

### Added

- Added a first `foundrygate-config-wizard` helper that suggests an initial `config.yaml` from the API keys already present in `.env`
- Added first-class `routing_modes` and `model_shortcuts` config blocks so virtual model ids such as `auto`, `eco`, `premium`, `free`, or custom names can participate in routing

### Changed

- `client_profiles` can now choose a default `routing_mode`, letting one client keep the global mode while another uses a different or custom mode by default
- `GET /v1/models`, route previews, and runtime response headers now expose configured routing modes and resolved shortcut/mode metadata
- `foundrygate-doctor`, onboarding reports, and a new provider-catalog API now surface curated model-drift and catalog-freshness alerts for configured providers

## v1.2.3 - 2026-03-19

### Changed

- Hardened the Homebrew formula so native Python extensions such as `pydantic-core` and `watchfiles` are built from source with extra Mach-O header padding on macOS instead of relying on the vendored wheel layout
- Strengthened the formula test so it validates the wrapped `foundrygate --version` entrypoint instead of only importing the package inside `libexec`
- Fixed the Python service entrypoint so `python -m foundrygate.main` and the Brew-managed wrapper both execute the runtime correctly
- Clarified in the README, workstation guide, and troubleshooting docs that active Python virtualenvs can shadow the Brew-installed `foundrygate` binary

## v1.2.1 - 2026-03-19

### Changed

- Switched the Homebrew formula baseline from `python@3.13` to `python@3.12` to reduce macOS packaging friction around vendored native Python wheels
- Clarified in the README and workstation docs that `brew install foundrygate` resolves cleanly after tapping `typelicious/foundrygate`, while the fully qualified install path remains the safest first-run example

## v1.2.0 - 2026-03-19

### Added

- Added a workstation operations guide for Linux, macOS, and Windows runtime layouts
- Added a macOS `launchd` LaunchAgent example for local workstation installs
- Added Windows PowerShell and Task Scheduler starter examples for local workstation installs
- Added platform-aware runtime helper scripts so macOS can use the same `foundrygate-install` / `start` / `stop` / `status` flow style as Linux
- Added a project-owned Homebrew formula plus `brew services` guidance for packaged macOS workstation installs
- Added explicit `FOUNDRYGATE_CONFIG_FILE` config discovery and `foundrygate --config` / `--version` support so service wrappers and packaged installs can point to config outside the repo
- Added a helper-level onboarding smoke test for explicit config/env/python wiring

### Changed

- Updated the README quickstart so Linux, macOS, Windows, and Homebrew paths are visible earlier
- Replaced the weak PyPI workflow badge with clearer workstation and Homebrew badges

## v1.1.0 - 2026-03-16

### Added

- Added richer client usage reporting in `GET /api/stats` and the dashboard, including per-client tokens, failures, success rate, and aggregate client totals
- Added a second wave of AI-native starter templates for Agno, Semantic Kernel, Haystack, Mastra, and Google ADK
- Added client highlight summaries to `GET /api/stats` and the built-in dashboard for top request, token, cost, failure, and latency signals
- Added a third wave of AI-native starter templates for AutoGen, LlamaIndex, CrewAI, PydanticAI, and CAMEL

### Changed

- Tightened `static` and `heuristic` match semantics so combined fields now behave as cumulative constraints unless `any:` is used explicitly
- Tightened `policy` match semantics so `client_profile` acts as an additive constraint inside one rule instead of bypassing sibling static or heuristic fields

## v1.0.0 - 2026-03-15

### Added

- Added dashboard CSP hashes plus stricter response-security defaults for the no-build operator UI
- Added stronger provider base URL validation so non-local upstreams must use `https`
- Added reduced leakage of upstream provider failure details in client-facing error payloads
- Added a separate npm CLI package under `packages/foundrygate-cli` for basic health, model, update, and route-preview checks
- Added a documented `v1.0.0` security review with mitigations and residual-risk notes
- Added functional API coverage for upstream error sanitization on top of the earlier dashboard and request-boundary hardening tests
- Streamlined the root README into a shorter landing page and moved deeper API, configuration, and operations detail into dedicated docs pages

## v0.9.0 - 2026-03-15

### Added

- Added conservative response-security headers plus a dashboard CSP for the no-build operator UI
- Added explicit `security` config controls for JSON body size, upload size, and bounded routing-header values
- Added functional API coverage for dashboard headers, JSON request limits, upload limits, and sanitized routing-header behavior

## v0.8.0 - 2026-03-15

### Added

- Added `foundrygate-onboarding-report` plus a testable onboarding report module for many-provider and many-client readiness checks
- Added `foundrygate-onboarding-validate` so onboarding blockers can fail fast in local setup and CI-style validation flows
- Added built-in OpenClaw, n8n, and CLI quickstart examples to the onboarding report and integration docs so client onboarding can stay copy/paste friendly
- Added staged provider-rollout reporting and fallback/image readiness warnings so many-provider onboarding is easier to phase safely
- Added a client matrix to the onboarding report so profile match rules and routing intent are visible before traffic goes live
- Added starter example files for OpenClaw, n8n, and CLI clients under `docs/examples/` so onboarding can begin from copy/pasteable templates
- Added starter provider snippets for cloud, local-worker, and image-provider setups under `docs/examples/`
- Added matching provider `.env` starter files for cloud, local-worker, and image-provider onboarding flows
- Added provider env placeholder checks to `foundrygate-doctor` so missing `.env` values are surfaced before rollout
- Added `--markdown` output to `foundrygate-onboarding-report` so onboarding state can be pasted into issues, PRs, or hand-off notes
- Added delegated OpenClaw request and generic AI-native app profile starters to round out the `v0.8.x` onboarding path

## v0.7.0 - 2026-03-12

### Added

- Added stronger update-alert metadata to `GET /api/update`, including update type, alert level, and recommended action for operators and dashboard consumers
- Added an opt-in `auto_update` policy block plus `foundrygate-auto-update` so controlled deployments can gate helper-driven updates without enabling silent self-updates
- Added `GET /api/operator-events` plus operator-event metrics for update checks and helper-driven auto-update attempts
- Added dashboard cards and tables for operator-side update checks and apply attempts
- Added provider-health rollout guardrails so helper-driven auto-updates can block when gateway health is already degraded
- Added `update_check.release_channel` and `auto_update.rollout_ring` so operators can distinguish stable vs preview checks and tighter rollout rings
- Added `auto_update.min_release_age_hours` so helper-driven auto-updates can wait for a release to age before becoming eligible
- Added `auto_update.maintenance_window` so helper-driven auto-updates can stay inside explicit local maintenance hours
- Added `auto_update.provider_scope` so rollout-health guardrails can evaluate only a selected provider subset
- Added `auto_update.verification` so helper-driven auto-updates can run a post-update check and emit a rollback hint on failure

## v0.6.0 - 2026-03-12

### Added

- Added modality-aware metrics and filters so stats, traces, recent requests, and the dashboard can distinguish `chat`, `image_generation`, and `image_editing`
- Added `POST /api/route/image` for dry-run preview of image-generation and image-editing routing decisions
- Added optional `image` provider metadata (`max_outputs`, `max_side_px`, `supported_sizes`) so image-capable providers can be ranked against `n` and `size`
- Added top-level capability coverage to `GET /health` plus `GET /api/providers` for filtered provider inventory and dashboard coverage views
- Added shared request validation for image-generation, image-editing, and image-route preview payloads so invalid `size`, `n`, and scalar fields fail fast before provider calls
- Added optional `image.policy_tags` plus request-side image-policy hints so image routing can prefer providers tagged for `quality`, `cost`, `balanced`, `batch`, or `editing`

## v0.5.0 - 2026-03-12

### Added

- Added `contract: image-provider` plus OpenAI-compatible `POST /v1/images/generations` and `POST /v1/images/edits` paths for image-capable providers
- Added a shipped Dockerfile and tag-driven release-artifacts workflow for Python distributions, GHCR images, and optional PyPI publishing
- Added public community-health and security baseline files: Code of Conduct, Security Policy, issue templates, PR template, Dependabot, and CodeQL
- Added generic onboarding helpers (`foundrygate-bootstrap`, `foundrygate-doctor`) and a publish-dry-run workflow for GHCR and Python package validation
- Added cached release update checks via `GET /api/update`, the dashboard, and `foundrygate-update-check`

## v0.4.0 - 2026-03-12

### Changed

- Added optional `request_hooks` with a small built-in hook registry for per-request provider preferences, locality hints, and profile overrides
- Added a dedicated routing layer for hook-provided hints before client-profile defaults
- Added dry-run route output for applied hooks, effective request metadata, and candidate ranking details
- Added provider route-fit metadata for `context_window`, token limits, and cache behavior
- Added filtered stats, recent-request, and trace queries for provider, client, layer, and success views
- Hardened the built-in dashboard with provider health, client breakdowns, route traces, URL-persisted filters, summary cards, and escaped rendering
- Deepened provider scoring so routing now considers health, latency, recent failures, cache alignment, and request headroom instead of only first-fit dimension checks
- Hardened request hooks with sanitized body updates and routing hints plus optional fail-closed behavior via `request_hooks.on_error`

## v0.3.0 - 2026-03-12

### Changed

- Rebranded the public documentation around the FoundryGate product name
- Completed the technical rename from earlier runtime identifiers to `foundrygate`
- Added validated provider capability metadata with normalized local/cloud and streaming defaults
- Added an optional policy layer for capability-aware provider selection on `auto` requests
- Added an explicit `local-worker` provider contract for network-local OpenAI-compatible runtimes
- Added optional client profiles for caller-aware routing defaults based on request headers
- Added a dry-run route introspection endpoint at `POST /api/route`
- Added enriched route traces and client/profile breakdowns in metrics, stats, and CLI output
- Added startup and `/health` probing for `contract: local-worker` providers via `GET /models`
- Added built-in `client_profiles` presets for `openclaw`, `n8n`, and `cli`
- Added a repository `AGENTS.md` and a documented Git workflow for `main`, `feature/*`, `review/*`, and `hotfix/*`
- Aligned release guidance around semantic-style `x.y.z` versioning with `v0.3.0` as the first FoundryGate-branded release

### Docs

- Reworked the README into a more generic, portable open-source landing page
- Added clearer API, configuration, deployment, and helper script documentation
- Added release process documentation, roadmap updates, and a lightweight release checklist template
- Added architecture, integrations, onboarding, and troubleshooting docs for external users
