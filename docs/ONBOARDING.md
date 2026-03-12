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
```

### 1. Add one provider

- define the provider in `config.yaml`
- set the required API key or local auth value in `.env`
- keep the fallback chain simple

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
