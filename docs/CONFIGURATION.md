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

## Security Settings

`config.yaml` exposes explicit security controls for the request surface:

- `security.response_headers`
- `security.cache_control`
- `security.max_json_body_bytes`
- `security.max_upload_bytes`
- `security.max_header_value_chars`

These settings drive the bounded JSON, upload, and routing-header behavior that ships in `v0.9.0+`.

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

## Client Profiles And Request Hooks

FoundryGate supports two lightweight extension seams:

- `client_profiles`
  - caller-aware defaults for OpenClaw, n8n, CLI tools, and custom apps
  - only apply when policy/static/heuristic routing did not already make a stronger decision
- `request_hooks`
  - bounded pre-routing hint injection
  - can fail closed depending on `request_hooks.on_error`

Use the onboarding docs and starter examples when introducing a new client instead of hand-authoring these sections from scratch.

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
- matching provider `.env` examples

## Validation Helpers

Use these before rolling out a new provider or client:

```bash
./scripts/foundrygate-doctor
./scripts/foundrygate-onboarding-report
./scripts/foundrygate-onboarding-validate
```

These helpers catch missing env placeholders, rollout blockers, provider capability gaps, and profile issues before live traffic hits the gateway.
