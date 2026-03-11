# FoundryGate Onboarding

## Goal

FoundryGate should be understandable and usable for a deployment with many providers and many clients.

The safest onboarding order is:

1. one provider
2. one client
3. observability
4. second provider
5. client-specific defaults
6. policy constraints

## Provider onboarding sequence

### 1. Add one provider

- define the provider in `config.yaml`
- set the required API key or local auth value in `.env`
- keep the fallback chain simple

### 2. Verify provider health

- check `GET /health`
- check `GET /v1/models`
- for `contract: local-worker`, confirm that `GET /models` works on the worker

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

### 4. Validate with route introspection

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

Planned state:

- update alerts
- optional auto-update enablers for controlled environments

These are roadmap items. They are not implemented as automatic runtime behavior today.
