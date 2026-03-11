# ClawGate

[![repo-safety](https://github.com/typelicious/ClawGate/actions/workflows/repo-safety.yml/badge.svg)](https://github.com/typelicious/ClawGate/actions/workflows/repo-safety.yml)
[![CI](https://github.com/typelicious/ClawGate/actions/workflows/ci.yml/badge.svg)](https://github.com/typelicious/ClawGate/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![OpenAI-compatible](https://img.shields.io/badge/OpenAI-compatible-0ea5e9.svg)](./README.md#api)
[![OpenClaw-friendly](https://img.shields.io/badge/OpenClaw-friendly-111827.svg)](https://openclaw.ai/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](./pyproject.toml)

## Quick Navigation

- [Quickstart](#quickstart)
- [How It Works](#how-it-works)
- [API](#api)
- [Model Aliases And Routing](#model-aliases-and-routing)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Helper Scripts](#helper-scripts)
- [Repo Safety And CI](#repo-safety-and-ci)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Releases](#releases)

🦞 Local OpenAI-compatible router for [OpenClaw](https://openclaw.ai/).

ClawGate is a local OpenAI-compatible router/proxy for OpenClaw and other clients. Point your client at a single local endpoint, and ClawGate routes each request to the configured upstream provider and model, applies fallbacks on failures, and exposes health and usage data for operations.

OpenClaw site: [https://openclaw.ai/](https://openclaw.ai/)
OpenClaw docs: [https://docs.openclaw.ai/](https://docs.openclaw.ai/)

## Why ClawGate

- OpenAI-compatible API: expose `/v1/models` and `/v1/chat/completions` to OpenClaw or any OpenAI-style client.
- Single endpoint, multiple providers: clients call one local base URL while ClawGate chooses the upstream provider.
- Multi-provider routing: use `auto` for routing or target a provider directly by model id.
- Robust fallback behavior: provider errors, timeouts, and connection failures fall through the configured fallback chain.
- Useful observability: `/health` reports provider status, consecutive failures, last error, and average latency.
- Safe database path handling: metrics use `CLAWGATE_DB_PATH`, so the SQLite database does not need to live in the repo checkout.

## Who Is This For?

- OpenClaw users who want one local endpoint instead of wiring every upstream model into the client
- Agent stacks that already speak the OpenAI chat completions API
- Operators who want local routing, failover, and lightweight request/cost visibility
- Developers who want a small FastAPI service instead of a larger gateway stack

## Quickstart

The fastest path is a local Python run using the stock `config.yaml`.

1. Clone the repo and create your environment file.
2. Set at least one provider API key in `.env`.
3. Override `CLAWGATE_DB_PATH` to a writable path outside the repo if you are not using the systemd unit.
4. Install dependencies and run the app.

```bash
git clone https://github.com/typelicious/ClawGate.git
cd ClawGate
cp .env.example .env
mkdir -p "$HOME/.local/state/clawgate"
printf '\nCLAWGATE_DB_PATH=%s\n' "$HOME/.local/state/clawgate/clawgate.db" >> .env
$EDITOR .env
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m clawgate
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8090/v1/models
```

If every configured provider API key is empty, ClawGate still starts, but it skips those providers at startup and `v1/models` will only expose the virtual `auto` model.

## How It Works

```text
Client (OpenClaw or any OpenAI-style client)
  |
  v
http://127.0.0.1:8090/v1
  |
  +--> Layer 1: static rules
  +--> Layer 2: heuristic rules
  +--> Layer 3: optional LLM classifier
  |
  +--> chosen provider
         |- deepseek-chat
         |- deepseek-reasoner
         |- gemini-flash-lite
         |- gemini-flash
         `- openrouter-fallback
```

Routing decisions happen in order:

1. Static rules for known patterns such as heartbeat, explicit model hints, and sub-agent traffic
2. Heuristic rules for user-message content, tools, and rough token size
3. An optional LLM classifier if you enable it in `config.yaml`

Important implementation detail: heuristic keyword scoring only evaluates user messages, not the system prompt. This avoids over-routing to expensive tiers because of long system prompts.

## API

These endpoints are implemented today in [clawgate/main.py](./clawgate/main.py).

### `GET /health`

Returns overall service status plus one object per loaded provider. Each provider entry includes:

- `healthy`
- `consecutive_failures`
- `avg_latency_ms`
- `last_error`

```bash
curl -fsS http://127.0.0.1:8090/health
```

### `GET /v1/models`

Returns an OpenAI-compatible model list. It always includes the virtual `auto` model, plus one entry for every provider that actually loaded at startup.

```bash
curl -fsS http://127.0.0.1:8090/v1/models
```

### `POST /v1/chat/completions`

OpenAI-compatible chat completions endpoint.

- `model: "auto"` routes through ClawGate
- `model: "<provider-id>"` routes directly to that loaded provider

For non-streaming responses, ClawGate also adds these response headers:

- `X-ClawGate-Provider`
- `X-ClawGate-Layer`
- `X-ClawGate-Rule`

```bash
curl -fsS http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Summarize the benefits of a local LLM gateway."}
    ],
    "max_tokens": 128
  }'
```

### Additional Stable Operational Endpoints

- `GET /api/stats`
- `GET /api/recent?limit=50`
- `GET /dashboard`

```bash
curl -fsS http://127.0.0.1:8090/api/stats
curl -fsS 'http://127.0.0.1:8090/api/recent?limit=10'
```

## Model Aliases And Routing

ClawGate itself exposes:

- `auto` as the virtual routing model
- direct provider ids such as `deepseek-chat`, `deepseek-reasoner`, `gemini-flash-lite`, `gemini-flash`, and `openrouter-fallback` when those providers are loaded

The stock routing rules also understand short explicit model hints:

- `r1`, `reasoner`, `think` -> `deepseek-reasoner`
- `flash`, `gemini`, `vision` -> `gemini-flash`
- `ds`, `chat`, `default` -> `deepseek-chat`

If you use OpenClaw, the recommended client-side aliases live in [openclaw-integration.jsonc](./openclaw-integration.jsonc):

- `auto`
- `ds`
- `r1`
- `lite`
- `flash`
- `or`

Those aliases are defined on the OpenClaw side. ClawGate only sees the resulting `model` value and routes accordingly.

## Configuration

ClawGate loads configuration from:

- `config.yaml`
- `.env` via `python-dotenv`

String values in `config.yaml` support `${ENV_VAR}` and `${ENV_VAR:-default}` expansion.

### Core Environment Variables

| Variable | What it does | Notes |
| --- | --- | --- |
| `CLAWGATE_DB_PATH` | Path to the metrics SQLite database | Stock `config.yaml` defaults to `/var/lib/clawgate/clawgate.db` (not `./clawgate.db`) |
| `DEEPSEEK_API_KEY` | Enables the default DeepSeek providers | Used by `deepseek-chat` and `deepseek-reasoner` |
| `GEMINI_API_KEY` | Enables the default Gemini providers | Used by `gemini-flash-lite` and `gemini-flash` |
| `OPENROUTER_API_KEY` | Enables the default OpenRouter fallback provider | Optional |
| `DEEPSEEK_BASE_URL` | Overrides the DeepSeek base URL | Optional |
| `GEMINI_BASE_URL` | Overrides the Gemini base URL | Optional |
| `OPENROUTER_BASE_URL` | Overrides the OpenRouter base URL | Optional |

### Additional Provider Key Variables Referenced In The Stock Config

The stock `config.yaml` ships many commented provider stanzas. If you uncomment one, its `api_key` field expects one of these variables:

- Cloud APIs: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENCODE_API_KEY`, `ZAI_API_KEY`, `AI_GATEWAY_API_KEY`, `KILOCODE_API_KEY`, `XAI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `COPILOT_GITHUB_TOKEN`, `HUGGINGFACE_HUB_TOKEN`, `MOONSHOT_API_KEY`, `KIMI_API_KEY`, `VOLCANO_ENGINE_API_KEY`, `BYTEPLUS_API_KEY`, `SYNTHETIC_API_KEY`, `MINIMAX_API_KEY`
- Local/OpenAI-compatible proxies: `OLLAMA_API_KEY`, `VLLM_API_KEY`, `LMSTUDIO_API_KEY`, `LITELLM_API_KEY`

Only providers whose `api_key` resolves to a non-empty value are initialized at startup.

Today, the runtime code implements:

- `openai-compat`
- `google-genai`

The stock config also includes commented templates for a wider provider catalog. Enable only the providers that match the backends implemented by your current ClawGate version.

### Timeout Notes

The stock `config.yaml` includes per-provider `timeout` stanzas for documentation and future tuning, but the current runtime uses one shared `httpx` client timeout:

- connect timeout: `10s`
- read/response timeout: `120s`

Timeouts and connection errors still participate in fallback behavior and health tracking.

### Configuration Examples

Using the stock `config.yaml`, you can configure common setups entirely through `.env`.

Single provider:

```dotenv
DEEPSEEK_API_KEY=your-key-here
CLAWGATE_DB_PATH=/home/you/.local/state/clawgate/clawgate.db
```

Multi-provider with fallback:

```dotenv
DEEPSEEK_API_KEY=your-key-here
GEMINI_API_KEY=your-key-here
OPENROUTER_API_KEY=your-key-here
CLAWGATE_DB_PATH=/home/you/.local/state/clawgate/clawgate.db
```

Disable a provider:

- Remove or empty the relevant API key in `.env`, or comment out the provider stanza in `config.yaml`
- On startup, ClawGate logs that the provider has no API key and skips loading it

## Deployment

ClawGate runs fine as a plain Python process. `systemd` and helper scripts are optional conveniences. Docker can be used for quick evaluation even though the repo does not currently ship a Dockerfile.

### Generic Linux Host

For a normal Linux host without `systemd`, use the Quickstart above and keep `CLAWGATE_DB_PATH` on a writable path outside the repo checkout.

Recommended runtime paths:

- app checkout: wherever you keep the repo
- metrics DB: `/var/lib/clawgate/clawgate.db` for system services, or a user path such as `$HOME/.local/state/clawgate/clawgate.db` for local runs

### systemd

The repo includes [clawgate.service](./clawgate.service). Deploy it to:

```text
/etc/systemd/system/clawgate.service
```

Key points:

- Working directory: `/opt/clawgate`
- Environment file: `/opt/clawgate/.env`
- Database path: `CLAWGATE_DB_PATH=/var/lib/clawgate/clawgate.db`
- Writable state directory: `/var/lib/clawgate/`

The unit also enables basic hardening with `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `ReadWritePaths=/var/lib/clawgate`, and `PrivateTmp`.

Minimal `systemd` flow:

```bash
sudo useradd --system --home /opt/clawgate --shell /usr/sbin/nologin clawgate || true
sudo install -d -o clawgate -g clawgate -m 755 /var/lib/clawgate
sudo install -m 644 clawgate.service /etc/systemd/system/clawgate.service
sudo systemctl daemon-reload
sudo systemctl enable --now clawgate.service
sudo systemctl status clawgate.service --no-pager -l
```

### Docker (quick example, no Dockerfile required)

This repo does not currently ship a Dockerfile. For a quick evaluation run, you can use the official Python image and mount the repo read-only:

```bash
docker volume create clawgate-data
docker run --rm -p 8090:8090 \
  --env-file .env \
  -e CLAWGATE_DB_PATH=/data/clawgate.db \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD":/app:ro \
  -v clawgate-data:/data \
  -w /app \
  python:3.13-slim \
  sh -lc 'pip install --no-cache-dir -r requirements.txt && python -m uvicorn clawgate.main:app --host 0.0.0.0 --port 8090'
```

This is meant for quick evaluation. For longer-lived deployments, build your own image around the same commands.

## Helper Scripts

The scripts in [scripts](./scripts) are optional wrappers around `systemd`, `journalctl`, and `curl`. They are most useful on Linux hosts that already use the included `systemd` unit.

Running `./scripts/clawgate-install` also creates symlinks in `/usr/local/bin`.

| Script | What it does |
| --- | --- |
| `clawgate-install` | Installs the unit file, creates `/var/lib/clawgate`, creates helper symlinks, reloads `systemd`, and starts the service |
| `clawgate-start` | Runs `systemctl start clawgate.service` |
| `clawgate-stop` | Runs `systemctl stop clawgate.service` |
| `clawgate-restart` | Runs `systemctl restart clawgate.service` |
| `clawgate-status` | Shows service status and checks whether `127.0.0.1:8090` is listening |
| `clawgate-logs` | Tails `journalctl -u clawgate.service` |
| `clawgate-health` | Calls `GET /health` locally with `curl` |
| `clawgate-update` | Fetches from Git, hard-resets to `origin/main`, cleans untracked files, reinstalls the unit, restarts, and retries health checks |
| `clawgate-uninstall` | Stops and disables the service, removes the unit file, and removes helper symlinks |

## Repo Safety And CI

ClawGate includes two GitHub Actions workflows:

- [CI](./.github/workflows/ci.yml): runs Ruff plus the test matrix on Python 3.10 through 3.13
- [repo-safety](./.github/workflows/repo-safety.yml): rejects accidental artifacts and secrets-like files

The `repo-safety` workflow fails pull requests if these patterns are tracked in the working tree or still exist anywhere in Git history:

- `.ssh/`
- `*.db*`
- `*.sqlite*`
- `*.log`

This keeps secrets and runtime artifacts out of a public repo and makes cleanup mistakes visible before merge.

## Troubleshooting

### `GET /health` fails

Check whether the service is running and listening:

```bash
curl -fsS http://127.0.0.1:8090/health
sudo ss -ltnp | grep -E '127\.0\.0\.1:8090\b' || true
```

### No providers are loaded

This usually means every configured provider resolved to an empty API key. Re-check `.env`, then restart the service or process.

### Port `8090` is already in use

Find the conflicting process:

```bash
sudo ss -ltnp | grep ':8090'
```

### The database path is not writable

Set `CLAWGATE_DB_PATH` to a writable path, or create the service state directory:

```bash
mkdir -p "$HOME/.local/state/clawgate"
sudo install -d -o clawgate -g clawgate -m 755 /var/lib/clawgate
```

### A provider keeps failing over

Check `/health` for `last_error`, then inspect logs:

```bash
curl -fsS http://127.0.0.1:8090/health
clawgate-logs
```

### `clawgate-update` removed local edits

That is intentional. The helper is designed for deployment checkouts and uses `git reset --hard origin/main` plus `git clean -fd`.

## Roadmap

The next product direction is tracked in [docs/FOUNDRYGATE-ROADMAP.md](./docs/FOUNDRYGATE-ROADMAP.md).

Short version:

- `ClawGate` is the current codebase
- `FoundryGate` is the working name for the broader gateway direction
- the next steps focus on capability-aware routing, local worker support, client profiles, and optional context/optimization hooks

## Releases

- [CHANGELOG.md](./CHANGELOG.md) tracks notable user-facing changes
- [RELEASES.md](./RELEASES.md) describes the lightweight release process for tags and GitHub Releases
- GitHub Releases: [https://github.com/typelicious/ClawGate/releases](https://github.com/typelicious/ClawGate/releases)

## Suggested GitHub About

Suggested description:

> Local OpenAI-compatible router/proxy for OpenClaw and other LLM clients.

Suggested topics:

- `openclaw`
- `openai-compatible`
- `llm-router`
- `llm-gateway`
- `proxy`
- `multi-provider`
- `fastapi`

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## Security

- Do not commit `.env`, API keys, databases, sqlite files, or logs
- Use `repo-safety` and `.gitignore` as guardrails, not as a substitute for review
- Rotate credentials upstream first if you ever suspect a leak

## License

MIT. See [LICENSE](./LICENSE).

⭐ If ClawGate saves you time or money, feel free to star the repo. ❤️
