# FoundryGate Onboarding

## Goal

FoundryGate should be understandable and usable for a deployment with many providers and many clients.

The safest onboarding order is:

1. one provider
2. one client
3. bootstrap + diagnostics
4. second provider
5. client-specific defaults
6. policy constraints

## Provider onboarding sequence

### 0. Bootstrap the local checkout

Run the generic helpers before changing config:

```bash
./scripts/foundrygate-bootstrap
$EDITOR .env
./scripts/foundrygate-doctor
./scripts/foundrygate-onboarding-report
```

`foundrygate-doctor` now also checks whether provider env placeholders referenced in `config.yaml` are actually present in `.env`.

`foundrygate-onboarding-report` now includes concrete OpenClaw, n8n, and CLI quickstart hints plus a staged provider-rollout view. Use it after every provider or client change to keep the deployment understandable for the next operator as well.

It also prints a client matrix:

- which client profiles exist
- whether they come from presets or custom config
- how they match traffic
- which routing hints they actually apply

### 1. Add one provider

- define the provider in `config.yaml`
- set the required API key or local auth value in `.env`
- keep the fallback chain simple

Starter snippets:

- [examples/provider-openai-compat.yaml](./examples/provider-openai-compat.yaml)
- [examples/provider-openai-compat.env.example](./examples/provider-openai-compat.env.example)
- [examples/provider-local-worker.yaml](./examples/provider-local-worker.yaml)
- [examples/provider-local-worker.env.example](./examples/provider-local-worker.env.example)
- [examples/provider-image-provider.yaml](./examples/provider-image-provider.yaml)
- [examples/provider-image-provider.env.example](./examples/provider-image-provider.env.example)

### 2. Verify provider health

- check `GET /health`
- check `GET /v1/models`
- for `contract: local-worker`, confirm that `GET /models` works on the worker
- for `contract: image-provider`, confirm that the upstream exposes `POST /images/generations`

### 3. Validate routing

- use `POST /api/route`
- confirm the selected provider and attempt order

### 4. Only then add another provider

Repeat the same path before introducing more routing complexity.

For many-provider rollouts, run the onboarding report after every provider change:

```bash
./scripts/foundrygate-onboarding-report
./scripts/foundrygate-onboarding-report --json
./scripts/foundrygate-onboarding-validate
```

The rollout section is intentionally staged:

1. stage 1 primary: ready local/default chat providers
2. stage 2 secondary: additional non-image providers
3. stage 3 modality: image-capable providers

This keeps provider growth incremental instead of introducing chat, fallback, and modality changes all at once.

## Client onboarding sequence

### 1. Keep the client on the common API

Prefer the standard OpenAI-compatible entry point.

### 2. Add a stable client tag

Examples:

- `x-openclaw-source`
- `X-FoundryGate-Client: n8n`
- `X-FoundryGate-Client: codex`

### 3. Apply a preset or custom profile

Start with:

- `openclaw`
- `n8n`
- `cli`

Then tighten it only if the default is not good enough.

When the client set grows, use the client matrix from `foundrygate-onboarding-report` to catch profiles that only work through explicit overrides and still have no real match rule.

### 3a. Start from one of the built-in quickstarts

OpenClaw:

```json
{
  "baseUrl": "http://127.0.0.1:8090/v1",
  "primary": "foundrygate/auto"
}
```

Starter file: [examples/openclaw-foundrygate.jsonc](./examples/openclaw-foundrygate.jsonc)

n8n:

```text
Base URL: http://127.0.0.1:8090/v1
Model: auto
Header: X-FoundryGate-Client: n8n
```

CLI:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8090/v1
export OPENAI_API_KEY=local
```

Starter files:

- [examples/n8n-foundrygate-http-request.json](./examples/n8n-foundrygate-http-request.json)
- [examples/cli-foundrygate-env.sh](./examples/cli-foundrygate-env.sh)

### 4. Add request hooks only if needed

Keep hooks opt-in and narrow. Good uses are:

- `X-FoundryGate-Prefer-Provider` for one explicit provider preference
- `X-FoundryGate-Locality: local-only` for private or worker-local traffic
- `X-FoundryGate-Profile` for a one-request profile override

### 5. Validate with route introspection

Use:

- `POST /api/route`
- `GET /api/traces`

## Many providers, many clients

When the stack grows, avoid changing everything at once.

Recommended rollout:

1. stabilize the provider set
2. group clients into a small number of profiles
3. introduce policies only for real constraints
4. keep route debugging enabled through traces and stats

## Update operations

Current state:

- manual updates via Git or `foundrygate-update`
- cached release update checks via `GET /api/update` and `foundrygate-update-check`
- optional eligibility reporting and helper-driven apply flow via `foundrygate-auto-update`
- tag-driven release artifacts for Python distributions and container images
- publish dry-run workflow for Python packaging and GHCR container builds

Planned state:

- scheduled use of `foundrygate-auto-update --apply` in controlled environments

This remains opt-in. FoundryGate does not self-schedule or mutate the checkout over HTTP.

### Controlled scheduling examples

Use scheduling only after you are comfortable with the manual path:

```bash
./scripts/foundrygate-update-check
./scripts/foundrygate-auto-update
```

Recommended `systemd` path:

1. review [examples/foundrygate-auto-update.service](./examples/foundrygate-auto-update.service)
2. review [examples/foundrygate-auto-update.timer](./examples/foundrygate-auto-update.timer)
3. install them under `/etc/systemd/system/`
4. enable the timer only after `auto_update.enabled: true` is set deliberately

Minimal flow:

```bash
sudo install -m 644 docs/examples/foundrygate-auto-update.service /etc/systemd/system/foundrygate-auto-update.service
sudo install -m 644 docs/examples/foundrygate-auto-update.timer /etc/systemd/system/foundrygate-auto-update.timer
sudo systemctl daemon-reload
sudo systemctl enable --now foundrygate-auto-update.timer
sudo systemctl list-timers foundrygate-auto-update.timer
```

Cron remains possible for simpler hosts. The example is in [examples/foundrygate-auto-update.cron](./examples/foundrygate-auto-update.cron), but `systemd` timers are usually the safer default because they provide visibility and persistence.
