# FoundryGate Changelog

All notable changes to FoundryGate should be documented here.

The format is intentionally lightweight and human-readable. Group entries by release and focus on user-visible behavior, operational changes, and compatibility notes.

## Unreleased

### Added

- Added optional `request_hooks` with a small built-in hook registry for per-request provider preferences, locality hints, and profile overrides
- Added a dedicated routing layer for hook-provided hints before client-profile defaults
- Added dry-run route output for applied hooks and effective request metadata

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
