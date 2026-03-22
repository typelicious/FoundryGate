# fusionAIze Gate Configuration

fusionAIze Gate is configured through `config.yaml` plus environment variables loaded from `.env`.

## Start Here

- Main runtime config: [`config.yaml`](../config.yaml)
- Environment template: [`../.env.example`](../.env.example)
- Provider starter snippets: [`./examples`](./examples)

## Core Environment Variables

### `FAIGATE_DB_PATH`

Use this for the SQLite metrics database. The default service path is:

```text
/var/lib/faigate/faigate.db
```

For local non-root runs, point it somewhere writable outside the repo checkout:

```bash
export FAIGATE_DB_PATH="$HOME/.local/state/faigate/faigate.db"
```

### Stock Provider API Keys

The stock config references these variables directly:

- `DEEPSEEK_API_KEY`
- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`

Optional base URL overrides in `.env.example`:

- `DEEPSEEK_BASE_URL`
- `GEMINI_BASE_URL`
- `OPENROUTER_BASE_URL`
- `OPENAI_BASE_URL`

Additional optional provider entries in `config.yaml` reference further env vars when you uncomment them.

Examples in `docs/examples` also cover optional provider API keys such as:

- `KILOCODE_API_KEY`
- `BLACKBOX_API_KEY`

ClawRouter / BlockRun is different: its current public path is wallet-/x402-oriented rather than a normal API-key field, so it is better treated as a separate integration model instead of another `*_API_KEY` example.

## Security Settings

`config.yaml` exposes explicit security controls for the request surface:

- `security.response_headers`
- `security.cache_control`
- `security.max_json_body_bytes`
- `security.max_upload_bytes`
- `security.max_header_value_chars`

These settings drive the bounded JSON, upload, and routing-header behavior that ships in `v0.9.0+`.

## Provider Catalog Checks

`provider_catalog_check` controls a curated drift/freshness check for known providers.

- `enabled`
- `warn_on_untracked`
- `warn_on_model_drift`
- `warn_on_unofficial_sources`
- `warn_on_volatile_offers`
- `max_catalog_age_days`

This does not rewrite `config.yaml` automatically. It powers:

- `faigate-doctor`
- `faigate-onboarding-report`
- `GET /api/provider-catalog`

The catalog now carries a little more structure than just one recommended model:

- `provider_type` such as `direct`, `aggregator`, or `wallet-router`
- `auth_modes` such as `api_key`, `byok`, or `wallet_x402`
- `offer_track` such as `direct`, `free`, `byok`, or `marketplace`
- `evidence_level` to distinguish fully official guidance from mixed/community-supported entries
- `official_source_url` plus optional watchlist sources for faster re-review

The intent is still simple: if a configured provider drifts away from the curated model recommendation, sits on a volatile free-tier track, or relies on less-than-fully-official guidance, operators get a visible warning before the setup silently rots.

Provider-discovery links can also be layered onto the catalog without touching `config.yaml`.

Pattern:

```bash
export FAIGATE_PROVIDER_LINK_OPENROUTER_FALLBACK_URL="https://go.example.com/openrouter"
export FAIGATE_PROVIDER_LINK_KILOCODE_URL="https://go.example.com/kilo"
```

These env vars are operator-controlled full URLs. They are intended for disclosed signup or discovery links and keep link configuration out of normal client config. If unset, the catalog falls back to the provider's official signup or landing URL.

The guardrail is strict:

- recommendation ranking does not use provider-link metadata as an input
- operator-configured discovery links are only shown after a recommendation or candidate row already exists
- CLI and API output should disclose that a shown link is informational only

The first CLI surfaces for this are the existing operator helpers:

- `faigate-onboarding-report`
- `faigate-doctor`
- `faigate-provider-discovery`

They show the resolved link together with the link-neutral policy state, so later browser or control-center work can build on the same rule set.

The compact discovery helper can also filter those links without changing the catalog itself:

```bash
./scripts/faigate-provider-discovery --offer-track free
./scripts/faigate-provider-discovery --json --link-source operator_override --disclosed-only
curl -fsS 'http://127.0.0.1:8090/api/provider-discovery?offer_track=byok'
```

For fast-moving offers, the current preferred review inputs are:

- official provider docs first
- OpenRouter BYOK and provider-routing docs
- Kilo gateway docs
- BlockRun / ClawRouter docs for wallet-routed traffic
- community watchlists such as `free-llm-api-resources` only as secondary signals

The config wizard can use this catalog metadata during first setup and later updates:

```bash
./scripts/faigate-config-wizard --help
./scripts/faigate-config-wizard --purpose general --client generic --list-candidates
./scripts/faigate-config-wizard --current-config config.yaml --purpose general --client generic
./scripts/faigate-config-wizard --purpose free --client n8n \
  --select kilocode,blackbox-free,gemini-flash-lite > config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --merge-existing \
  --select openrouter-fallback --write config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --purpose free --client n8n \
  --apply recommended_add,recommended_replace,recommended_mode_changes \
  --select kilocode,openrouter-fallback --select-profiles n8n --write config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --purpose free --client n8n \
  --apply recommended_add,recommended_replace,recommended_mode_changes \
  --select kilocode,openrouter-fallback --select-profiles n8n --dry-run-summary
./scripts/faigate-config-wizard --current-config config.yaml --purpose free --client n8n \
  --apply recommended_add,recommended_replace,recommended_mode_changes \
  --select kilocode,openrouter-fallback --select-profiles n8n \
  --write config.yaml --write-backup --backup-suffix .before-wizard
```

That gives operators one purpose-aware candidate list, config-aware update suggestions (`recommended_add`, `recommended_replace`, `recommended_keep`, `recommended_mode_changes`), the ability to pick multiple providers at once, and a safer merge path for incremental catalog-driven updates.

If you want the shortest reminder of the whole flow, run:

```bash
./scripts/faigate-config-wizard --help
```

## Provider Fields

Each provider entry can include:

- `contract`
- `backend`
- `base_url`
- `api_key`
- `model`
- `max_tokens`
- `context_window`
- `tier`
- `limits`
- `cache`
- `capabilities`
- `timeout`
- `pricing`
- `image`
- `lane`

The comments in [`config.yaml`](../config.yaml) are the source of truth for the current schema.

### `provider.lane`

`v1.8.0` starts the lane foundation for adaptive orchestration.

The intent is to separate:

- the canonical model lane Gate wants for a task
- the execution route used to reach it

Current `lane` fields are:

- `family`
- `name`
- `canonical_model`
- `route_type`
- `cluster`
- `benchmark_cluster`
- `quality_tier`
- `reasoning_strength`
- `context_strength`
- `tool_strength`
- `same_model_group`
- `degrade_to`

Example:

```yaml
providers:
  anthropic-claude:
    backend: anthropic-compat
    base_url: ${ANTHROPIC_BASE_URL:-https://api.anthropic.com/v1}
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-opus-4-6
    lane:
      family: anthropic
      name: quality
      canonical_model: anthropic/opus-4.6
      route_type: direct
      cluster: elite-reasoning
      benchmark_cluster: quality-coding
      quality_tier: premium
      reasoning_strength: high
      context_strength: high
      tool_strength: medium
      same_model_group: anthropic/opus-4.6
      degrade_to:
        - anthropic/sonnet-4.6
        - openai/gpt-4o
```

This does not mean the full adaptive routing line already ships. It means the runtime, wizard, and provider catalog can now carry the vocabulary needed for:

- same-lane aggregator fallback
- cluster-aware degradation
- benchmark-aware scoring
- richer dashboard explanations later

## OpenClaw-Oriented Baseline

If OpenClaw is one of the main clients, these settings give the cleanest fit:

- keep provider ids readable and stable because `GET /v1/models` exposes them directly to OpenClaw
- enable `client_profiles.presets: ["openclaw"]`
- keep `auto` in the fallback path so OpenClaw can stay on one stable primary model id
- use `contract: local-worker` for local chat workers
- use `contract: image-provider` plus `image` metadata for image-capable backends

That gives OpenClaw one provider entry, one primary model id, and optional explicit aliases without mirroring every upstream directly in the OpenClaw config.

## Provider Contracts

### `generic`

Default contract for normal chat-capable providers.

### `local-worker`

Use this for network-local OpenAI-compatible workers.

Runtime rules:

- backend must be `openai-compat`
- `base_url` must point to localhost or private network space
- `tier` defaults to `local`
- capabilities are normalized to `local=true`, `cloud=false`, `network_zone=local`

### `image-provider`

Use this for providers that can serve `POST /v1/images/generations` and optionally `POST /v1/images/edits`.

Useful `image` metadata:

- `max_outputs`
- `max_side_px`
- `supported_sizes`
- `policy_tags`

If OpenClaw should route image traffic through fusionAIze Gate, pair this with:

- `imageModel.primary: "faigate/auto"` for automatic image-provider selection
- or `imageModel.primary: "faigate/<provider-id>"` for one fixed image backend

## Client Profiles And Request Hooks

fusionAIze Gate supports two lightweight extension seams:

- `routing_modes`
  - virtual model ids such as `auto`, `eco`, `premium`, `free`, or custom names
  - can be global defaults or reused by multiple clients
- `client_profiles`
  - caller-aware defaults for OpenClaw, n8n, CLI tools, and custom apps
  - can set `routing_mode` per client before any profile-specific provider hints are applied
  - only apply when policy/static/heuristic routing did not already make a stronger decision
- `request_hooks`
  - bounded pre-routing hint injection
  - can fail closed depending on `request_hooks.on_error`

Use the onboarding docs and starter examples when introducing a new client instead of hand-authoring these sections from scratch.

## Config Wizard

For a first local config, let fusionAIze Gate suggest one from the API keys already present in your env file:

```bash
./scripts/faigate-config-wizard --help
./scripts/faigate-config-wizard --purpose general > config.yaml
```

Supported starting purposes:

- `general`
- `coding`
- `quality`
- `free`

The generated config includes:

- detected provider blocks
- a fallback chain
- stock routing modes
- model shortcuts
- client profile defaults for OpenClaw, n8n, CLI, and `opencode`

## Update And Rollout Settings

Operational update behavior is also configured in `config.yaml`.

Important blocks:

- `update_check`
  - release channel
  - refresh interval
- `auto_update`
  - enable/disable
  - rollout ring
  - release age guard
  - maintenance window
  - provider scope
  - post-update verification

See [Operations](./OPERATIONS.md) for the helper and schedule side of the same feature set.

## Examples

The repo ships ready-to-copy examples under [`docs/examples`](./examples):

- OpenClaw client config
- n8n HTTP Request node example
- CLI environment starter
- cloud provider starter YAML
- local-worker starter YAML
- image-provider starter YAML
- Kilo Gateway starter YAML
- BLACKBOX AI starter YAML
- matching provider `.env` examples

## Validation Helpers

Use these before rolling out a new provider or client:

```bash
./scripts/faigate-doctor
./scripts/faigate-onboarding-report
./scripts/faigate-onboarding-validate
```

These helpers catch missing env placeholders, rollout blockers, provider capability gaps, and profile issues before live traffic hits the gateway.
