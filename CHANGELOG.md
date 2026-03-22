# fusionAIze Gate Changelog

All notable changes to fusionAIze Gate should be documented here.

The format is intentionally lightweight and human-readable. Group entries by release and focus on user-visible behavior, operational changes, and compatibility notes.

## v1.8.0 - 2026-03-22

### Changed

- Started the adaptive-orchestration runtime line with canonical model-lane and provider-route metadata in config, wizard, runtime inventory, and provider-catalog surfaces
- Added the first lane-aware router scoring slice so `quality`, `balanced`, `eco`, and `free` postures now influence candidate ranking through lane cluster, benchmark cluster, route type, and runtime pressure instead of only provider tier
- Added Same-Lane-Route fallback preference before weaker cluster downgrades when a compatible alternate route exists for the same canonical model
- Added an in-memory adaptation state for rate-limit, quota, timeout, and latency pressure so hot routes can be demoted conservatively at runtime
- Persisted routing explainability fields such as `canonical_model`, `route_type`, `lane_cluster`, `selection_path`, and `decision_details` into metrics and route traces
- Expanded candidate cards, client scenarios, and provider dashboard drilldowns so operators can now see route mirrors, degrade chains, canonical lanes, and runtime penalties directly in Gate

## v1.7.1 - 2026-03-22

### Changed

- Tightened the terminal header rendering again so interactive screens no longer insert apparent blank spacer lines between the three wordmark rows
- Fixed the client-scenario apply flow so choosing `Write config` now returns cleanly to the calling menu after the confirmation step instead of dropping operators straight back into the same scenario list

## v1.7.0 - 2026-03-22

### Changed

- Added internal Gate drilldowns for client quickstarts, provider discovery, and dashboard details so operators no longer need to leave the menu just to open one parameterized view
- Expanded client scenarios into lane-based explanations with explicit quality, reasoning, workhorse, budget, and fallback roles so templates like `opencode / balanced` now explain why `kilocode`, `blackbox-free`, or `openrouter-fallback` are in or out
- Added family-coverage hints for scenario output so operators can see when a provider family currently has only one quality or balanced slot and would need separate provider entries for richer `Opus / Sonnet / Haiku`-style splits
- Refined the shell header color segmentation again to match the tighter blue / yellow / blue / green brand grouping across all three wordmark rows

## v1.6.3 - 2026-03-22

### Changed

- Hardened config-wizard merge writes so existing configs with `null` sections such as `client_profiles.rules`, `routing_policies.rules`, or `request_hooks.hooks` now merge into real runtime config safely instead of failing mid-write
- Closed the remaining Homebrew helper-parity gap so user-facing commands such as `faigate-config-wizard`, `faigate-status`, `faigate-restart`, `faigate-logs`, `faigate-start`, `faigate-stop`, `faigate-update`, and `faigate-auto-update` ship through the Brew formula too
- Refined the terminal wordmark again with the new three-color brand palette and kept the inline version sourced dynamically from the current package version

## v1.6.2 - 2026-03-22

### Changed

- Fixed the config-wizard write path so guided `Write config` flows persist the actual runtime config instead of accidentally writing the `purpose/client/suggestions` summary payload back into `config.yaml`
- Added an explicit doctor warning when `config.yaml` appears to contain wizard summary keys, which makes accidental miswrites easier to catch before restart and rollout work
- Restored executable bits for packaged helper scripts such as `faigate-config-wizard`, `faigate-config-overview`, `faigate-provider-discovery`, and the onboarding/client helper scripts so Brew-installed helper entrypoints no longer fail with `Permission denied`

## v1.6.1 - 2026-03-20

### Changed

- Fixed the packaged `faigate-dashboard` helper so the shipped script keeps its executable bit and the Brew-installed dashboard no longer fails with `Permission denied`
- Polished the interactive terminal wordmark again so the large `I` aligns with the intended shape and the current version now appears inline at the right edge of the logo in the same subdued tone as the subtitle

## v1.6.0 - 2026-03-20
### Added

- Added `faigate-provider-setup` plus matching `Quick Setup` / `Configure` menu entries so operators can add known providers, custom OpenAI-compatible upstreams, and local workers before dropping into the purpose-aware config wizard
- Added `faigate-provider-probe` so configured sources can be checked against config, env, and the live `/health` payload before client rollout begins
- Added `faigate-client-scenarios` plus matching menu entries so operators can apply named templates such as `opencode / eco`, `opencode / quality`, `n8n / reliable`, or `cli / free` instead of thinking only in raw profile-mode edits
- Added `faigate-dashboard` plus a new top-level `Dashboard` menu section so operators now get one shell-native performance view for traffic, latency, spend, token volume, provider/client hotspots, and action-oriented alerts

### Changed

- Tightened the onboarding docs and main README around the new provider-source-first UX so first setup now reads more like `Provider Setup -> Provider Probe -> API Keys -> Full Config Wizard -> Client Scenarios -> Validate -> Client Quickstarts`
- Renamed the old `FOUNDRYGATE STATS` CLI banner to `fusionAIze Gate Stats` so the terminal metrics surfaces stay on-brand
- Expanded client scenarios with clearer `budget`, `best when`, and `tradeoff` guidance so operators can pick templates by intent instead of only by routing-mode names
- Expanded the new dashboard with budget, quota, and routing-pressure hints so it now helps answer whether traffic should shift, a cheaper scenario is worth trying, or a provider likely needs more budget

- Added a dedicated adaptive-orchestration roadmap that sketches the path from lane metadata to scoring, live adaptation, benchmark freshness, and budget-/quota-aware routing through the `v1.10.x` and `v1.11.x` lines

## v1.5.1 - 2026-03-20

### Changed

- Reworked the interactive config wizard candidate screen so purpose/client selection now shows compact `Ready now`, `More options if you add keys`, and `Optional specialty add-ons` cards instead of a raw provider metadata dump
- Improved the client quickstart surfaces so the menu and client helper now show a clearer `Best next step` hint and friendlier `Preset matches` wording instead of implying that `Presets 0` means something is broken
- Clarified the API-key helper so provider base URL overrides are explicitly labeled as optional upstream overrides, reducing confusion between local Gate client URLs and upstream provider endpoints
- Nudged the terminal logo spacing closer to the intended fusionAIze Gate wordmark in interactive screens

## v1.5.0 - 2026-03-20

### Changed

- Fixed the standalone shell helpers on macOS/Homebrew so service status, logs, and service-manager labels now recognize the Brew-managed `homebrew.mxcl.faigate` path instead of assuming only the manual LaunchAgent path
- Fixed `faigate-menu` model listing so it parses the `/v1/models` payload correctly instead of trying to read JSON through a broken stdin pipeline
- Fixed `faigate-auto-update` on macOS's default Bash 3.2 by removing the `mapfile` dependency from its payload parsing path
- Fixed user-facing helper scripts so `--help` exits safely instead of accidentally triggering live install/update logic in shell environments that only wanted usage text
- Improved `faigate-health`, `faigate-update-check`, and `faigate-menu` so operators now see compact human-readable summaries before diving into raw payloads
- Added a service-manager mismatch warning when `/health` responds but the configured manager reports a stopped or missing service, which helps catch stale old runtimes still bound to the same port
- Polished the terminal header to align more closely with the intended fusionAIze Gate visual identity in interactive terminals
- Added a dedicated `Quick Setup` happy path and summary cards for gateway, config, providers, and clients in the main menu flows
- Updated the client helper and the `Clients` menu so operators see compact recommendation cards first and can drill into one client without dumping the full cross-client quickstart wall every time
- Added first `Next step` receipts after the key guided actions in the shell flow so wizard, validation, restart, and client-setup paths now end with a short operator-oriented “what to do next” block

## v1.4.5 - 2026-03-19

### Added

- Added a first `faigate-menu` control center with a shared terminal UI, the new fusionAIze Gate header, and consistent `q`/`c` navigation across status, configure, explore, validate, control, and update menus
- Added `faigate-api-keys` and `faigate-server-settings` so API keys, host, port, and log-level changes have a Gate-native interactive path instead of living only in external orchestration layers
- Added `faigate-routing-settings` so the global default routing mode and client-profile routing defaults can be reviewed and adjusted from the same Gate-native control flow
- Added `faigate-client-integrations` plus a `Clients` section in `faigate-menu` so OpenClaw, n8n, opencode, and generic CLI quickstarts can be reviewed and driven through client-scoped wizard flows
- Added `faigate-config-overview` plus a clearer `Current Config` / `Guided Setup` / `Direct Settings` split inside `faigate-menu` so configuration flows now map more cleanly to the later Grid-style orchestration model

### Changed

- Aligned helper scripts such as `faigate-health`, `faigate-status`, `faigate-update-check`, `faigate-auto-update`, and `faigate-doctor` around shared config/env/port resolution so repo, packaged, and later Grid-driven flows can behave consistently
- Extended install and Homebrew helper exposure so the new menu/config helpers can ship through the same operator-facing paths as the existing scripts
- Expanded `faigate-status`, `faigate-logs`, and `faigate-restart` so service control now carries clearer service-manager context, recent-vs-live log flows, and restart verification instead of only raw process-manager commands
- Polished `faigate-menu` with compact runtime/config snapshots in the main and control/config submenus plus short inline tips so the shell UX stays self-orienting between steps

## v1.4.0 - 2026-03-19

### Changed

- Renamed the product branding from `FoundryGate` to `fusionAIze Gate` across the repository, documentation, examples, and operator-facing surfaces
- Renamed the technical runtime slug from `foundrygate` to `faigate`, including the Python package, npm CLI package, helper scripts, example file names, service templates, and Homebrew formula path
- Moved the repository references from `typelicious/FoundryGate` to `fusionAIze/faigate` and aligned env prefixes, headers, and operational examples with the new `FAIGATE_` / `x-faigate-*` naming
- Completed the first release-prep baseline for the rebrand so future releases, installs, and documentation no longer depend on the old names

## v1.3.0 - 2026-03-19

### Added

- Added a first `faigate-config-wizard` helper that suggests an initial `config.yaml` from the API keys already present in `.env`
- Added first-class `routing_modes` and `model_shortcuts` config blocks so virtual model ids such as `auto`, `eco`, `premium`, `free`, or custom names can participate in routing
- Added wizard candidate listing and conservative config merging so operators can select multiple provider candidates during first setup or later catalog-driven updates
- Added config-aware wizard update suggestions so existing installs can see `recommended_add`, `recommended_replace`, and `recommended_keep` groups before applying provider changes
- Added wizard `recommended_mode_changes` suggestions so existing client profiles can be nudged toward the current purpose-aware routing defaults without silently rewriting them
- Added an `apply suggestions` wizard flow so selected provider and client-mode recommendations can be merged into an existing config without manual copy/paste
- Added a wizard dry-run change summary so operators can preview added providers, model replacements, fallback changes, and client-mode changes before writing config updates
- Added optional wizard write-backup snapshots so config updates can keep a local pre-change copy before overwriting `config.yaml`
- Added a built-in `faigate-config-wizard --help` flow so first setup, catalog review, update suggestions, dry-run previews, and backup-aware writes are all discoverable directly from the CLI
- Added optional provider-catalog discovery metadata and env-backed signup-link overrides so future CLI or control-center surfaces can show disclosed provider links without mixing link configuration into normal config files
- Added first CLI surfacing of disclosed provider discovery links in onboarding and doctor outputs, always alongside a link-neutral recommendation policy signal
- Added `faigate-provider-discovery` for one compact text/JSON discovery view that later browser or control-center work can consume
- Added discovery-link filters for CLI and API views so operators can narrow provider links by `offer_track`, `link_source`, or `disclosed_only`

### Changed

- `client_profiles` can now choose a default `routing_mode`, letting one client keep the global mode while another uses a different or custom mode by default
- `GET /v1/models`, route previews, and runtime response headers now expose configured routing modes and resolved shortcut/mode metadata
- `faigate-doctor`, onboarding reports, and the provider-catalog API now surface curated model-drift, source-confidence, volatility, and catalog-freshness alerts for configured providers
- Provider catalog entries now distinguish direct providers from aggregators and wallet routers, track auth modes such as `api_key`, `byok`, and `wallet_x402`, and keep community watchlists explicitly secondary to official sources
- `faigate-config-wizard` can now filter candidates by purpose and client, accept multi-select provider input, and merge selected providers back into an existing config instead of forcing a full rewrite
- Tightened the roadmap and user-facing docs around `v1.3.0` so guided setup, catalog-assisted updates, and future recommendation-link work stay transparent and clearly separated from ranking logic
- Provider discovery metadata now carries an explicit link-neutral recommendation policy so provider-link configuration can never be mistaken for a ranking signal

## v1.2.3 - 2026-03-19

### Changed

- Hardened the Homebrew formula so native Python extensions such as `pydantic-core` and `watchfiles` are built from source with extra Mach-O header padding on macOS instead of relying on the vendored wheel layout
- Strengthened the formula test so it validates the wrapped `faigate --version` entrypoint instead of only importing the package inside `libexec`
- Fixed the Python service entrypoint so `python -m faigate.main` and the Brew-managed wrapper both execute the runtime correctly
- Clarified in the README, workstation guide, and troubleshooting docs that active Python virtualenvs can shadow the Brew-installed `faigate` binary

## v1.2.1 - 2026-03-19

### Changed

- Switched the Homebrew formula baseline from `python@3.13` to `python@3.12` to reduce macOS packaging friction around vendored native Python wheels
- Clarified in the README and workstation docs that `brew install faigate` resolves cleanly after tapping `fusionAIze/faigate`, while the fully qualified install path remains the safest first-run example

## v1.2.0 - 2026-03-19

### Added

- Added a workstation operations guide for Linux, macOS, and Windows runtime layouts
- Added a macOS `launchd` LaunchAgent example for local workstation installs
- Added Windows PowerShell and Task Scheduler starter examples for local workstation installs
- Added platform-aware runtime helper scripts so macOS can use the same `faigate-install` / `start` / `stop` / `status` flow style as Linux
- Added a project-owned Homebrew formula plus `brew services` guidance for packaged macOS workstation installs
- Added explicit `FAIGATE_CONFIG_FILE` config discovery and `faigate --config` / `--version` support so service wrappers and packaged installs can point to config outside the repo
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
- Added a separate npm CLI package under `packages/faigate-cli` for basic health, model, update, and route-preview checks
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

- Added `faigate-onboarding-report` plus a testable onboarding report module for many-provider and many-client readiness checks
- Added `faigate-onboarding-validate` so onboarding blockers can fail fast in local setup and CI-style validation flows
- Added built-in OpenClaw, n8n, and CLI quickstart examples to the onboarding report and integration docs so client onboarding can stay copy/paste friendly
- Added staged provider-rollout reporting and fallback/image readiness warnings so many-provider onboarding is easier to phase safely
- Added a client matrix to the onboarding report so profile match rules and routing intent are visible before traffic goes live
- Added starter example files for OpenClaw, n8n, and CLI clients under `docs/examples/` so onboarding can begin from copy/pasteable templates
- Added starter provider snippets for cloud, local-worker, and image-provider setups under `docs/examples/`
- Added matching provider `.env` starter files for cloud, local-worker, and image-provider onboarding flows
- Added provider env placeholder checks to `faigate-doctor` so missing `.env` values are surfaced before rollout
- Added `--markdown` output to `faigate-onboarding-report` so onboarding state can be pasted into issues, PRs, or hand-off notes
- Added delegated OpenClaw request and generic AI-native app profile starters to round out the `v0.8.x` onboarding path

## v0.7.0 - 2026-03-12

### Added

- Added stronger update-alert metadata to `GET /api/update`, including update type, alert level, and recommended action for operators and dashboard consumers
- Added an opt-in `auto_update` policy block plus `faigate-auto-update` so controlled deployments can gate helper-driven updates without enabling silent self-updates
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
- Added generic onboarding helpers (`faigate-bootstrap`, `faigate-doctor`) and a publish-dry-run workflow for GHCR and Python package validation
- Added cached release update checks via `GET /api/update`, the dashboard, and `faigate-update-check`

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

- Rebranded the public documentation around the fusionAIze Gate product name
- Completed the technical rename from earlier runtime identifiers to `faigate`
- Added validated provider capability metadata with normalized local/cloud and streaming defaults
- Added an optional policy layer for capability-aware provider selection on `auto` requests
- Added an explicit `local-worker` provider contract for network-local OpenAI-compatible runtimes
- Added optional client profiles for caller-aware routing defaults based on request headers
- Added a dry-run route introspection endpoint at `POST /api/route`
- Added enriched route traces and client/profile breakdowns in metrics, stats, and CLI output
- Added startup and `/health` probing for `contract: local-worker` providers via `GET /models`
- Added built-in `client_profiles` presets for `openclaw`, `n8n`, and `cli`
- Added a repository `AGENTS.md` and a documented Git workflow for `main`, `feature/*`, `review/*`, and `hotfix/*`
- Aligned release guidance around semantic-style `x.y.z` versioning with `v0.3.0` as the first fusionAIze Gate-branded release

### Docs

- Reworked the README into a more generic, portable open-source landing page
- Added clearer API, configuration, deployment, and helper script documentation
- Added release process documentation, roadmap updates, and a lightweight release checklist template
- Added architecture, integrations, onboarding, and troubleshooting docs for external users
