# FoundryGate Configuration

FoundryGate is configured through `config.yaml` plus environment variables loaded from `.env`.

## Start Here

- Main runtime config: [`config.yaml`](../config.yaml)
- Environment template: [`../.env.example`](../.env.example)
- Provider starter snippets: [`./examples`](./examples)

## Core Environment Variables

### `FOUNDRYGATE_DB_PATH`

Use this for the SQLite metrics database. The default service path is:

```text
/var/lib/foundrygate/foundrygate.db
```

For local non-root runs, point it somewhere writable outside the repo checkout:

```bash
export FOUNDRYGATE_DB_PATH="$HOME/.local/state/foundrygate/foundrygate.db"
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

- `foundrygate-doctor`
- `foundrygate-onboarding-report`
- `GET /api/provider-catalog`

The catalog now carries a little more structure than just one recommended model:

- `provider_type` such as `direct`, `aggregator`, or `wallet-router`
- `auth_modes` such as `api_key`, `byok`, or `wallet_x402`
- `offer_track` such as `direct`, `free`, `byok`, or `marketplace`
- `evidence_level` to distinguish fully official guidance from mixed/community-supported entries
- `official_source_url` plus optional watchlist sources for faster re-review

The intent is still simple: if a configured provider drifts away from the curated model recommendation, sits on a volatile free-tier track, or relies on less-than-fully-official guidance, operators get a visible warning before the setup silently rots.

For fast-moving offers, the current preferred review inputs are:

- official provider docs first
- OpenRouter BYOK and provider-routing docs
- Kilo gateway docs
- BlockRun / ClawRouter docs for wallet-routed traffic
- community watchlists such as `free-llm-api-resources` only as secondary signals

The config wizard can use this catalog metadata during first setup and later updates:

```bash
./scripts/foundrygate-config-wizard --purpose general --client generic --list-candidates
./scripts/foundrygate-config-wizard --current-config config.yaml --purpose general --client generic
./scripts/foundrygate-config-wizard --purpose free --client n8n \
  --select kilocode,blackbox-free,gemini-flash-lite > config.yaml
./scripts/foundrygate-config-wizard --current-config config.yaml --merge-existing \
  --select openrouter-fallback --write config.yaml
```

That gives operators one purpose-aware candidate list, config-aware update suggestions (`recommended_add`, `recommended_replace`, `recommended_keep`, `recommended_mode_changes`), the ability to pick multiple providers at once, and a safer merge path for incremental catalog-driven updates.

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

The comments in [`config.yaml`](../config.yaml) are the source of truth for the current schema.

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

If OpenClaw should route image traffic through FoundryGate, pair this with:

- `imageModel.primary: "foundrygate/auto"` for automatic image-provider selection
- or `imageModel.primary: "foundrygate/<provider-id>"` for one fixed image backend

## Client Profiles And Request Hooks

FoundryGate supports two lightweight extension seams:

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

For a first local config, let FoundryGate suggest one from the API keys already present in your env file:

```bash
./scripts/foundrygate-config-wizard --purpose general > config.yaml
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
./scripts/foundrygate-doctor
./scripts/foundrygate-onboarding-report
./scripts/foundrygate-onboarding-validate
```

These helpers catch missing env placeholders, rollout blockers, provider capability gaps, and profile issues before live traffic hits the gateway.
