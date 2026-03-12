# FoundryGate Changelog

All notable changes to FoundryGate should be documented here.

The format is intentionally lightweight and human-readable. Group entries by release and focus on user-visible behavior, operational changes, and compatibility notes.

## Unreleased

### Added

- Added modality-aware metrics and filters so stats, traces, recent requests, and the dashboard can distinguish `chat`, `image_generation`, and `image_editing`
- Added `POST /api/route/image` for dry-run preview of image-generation and image-editing routing decisions
- Added optional `image` provider metadata (`max_outputs`, `max_side_px`, `supported_sizes`) so image-capable providers can be ranked against `n` and `size`
- Added top-level capability coverage to `GET /health` plus `GET /api/providers` for filtered provider inventory and dashboard coverage views

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
