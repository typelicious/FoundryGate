# FoundryGate

[![repo-safety](https://github.com/typelicious/FoundryGate/actions/workflows/repo-safety.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/repo-safety.yml)
[![CI](https://github.com/typelicious/FoundryGate/actions/workflows/ci.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/ci.yml)
[![CodeQL](https://github.com/typelicious/FoundryGate/actions/workflows/codeql.yml/badge.svg)](https://github.com/typelicious/FoundryGate/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/typelicious/FoundryGate?display_name=tag)](https://github.com/typelicious/FoundryGate/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![OpenAI-compatible](https://img.shields.io/badge/OpenAI-compatible-0ea5e9.svg)](./docs/API.md)
[![OpenClaw-friendly](https://img.shields.io/badge/OpenClaw-friendly-111827.svg)](https://openclaw.ai/)
[![Workstations](https://img.shields.io/badge/workstations-linux%20%7C%20macOS%20%7C%20windows-0f766e.svg)](./docs/WORKSTATIONS.md)
[![Homebrew](https://img.shields.io/badge/homebrew-formula-fbbf24?logo=homebrew&logoColor=black)](./Formula/foundrygate.rb)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](./Dockerfile)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](./pyproject.toml)

Local OpenAI-compatible AI gateway for 🦞 [OpenClaw](https://openclaw.ai/) and other AI-native clients.

FoundryGate gives OpenClaw, n8n, CLI tools, and custom apps one local endpoint and routes each request to the best configured provider or local worker. It keeps routing, fallback, onboarding, and operator visibility under your control instead of scattering provider logic across every client.

Runs locally on Linux, macOS, and Windows, with first-class workstation guidance for `systemd`, `launchd`, Task Scheduler, and Homebrew-driven macOS installs.

## Quick Navigation

- [Quickstart](#quickstart)
- [Why FoundryGate](#why-foundrygate)
- [How It Works](#how-it-works)
- [API Surface](#api-surface)
- [How FoundryGate Compares](#how-foundrygate-compares)
- [Deployment](#deployment)
- [More Resources](#more-resources)
- [Community And Security](#community-and-security)

## Why FoundryGate

- Single local endpoint for many upstreams: cloud providers, proxy providers, and local workers can sit behind the same base URL.
- OpenAI-compatible runtime: chat completions, model discovery, image generation, and image editing use familiar OpenAI-style paths.
- Better routing than simple first-match proxying: policies, static rules, heuristics, client profiles, hooks, and route-fit scoring all participate.
- Strong operator visibility: `/health`, provider inventory, route previews, traces, stats, update checks, and dashboard views are built in, including per-client usage highlights.
- Practical rollout controls: fallback chains, maintenance windows, rollout rings, provider scopes, and post-update verification gates are already there.
- Copy/paste onboarding: OpenClaw, n8n, CLI, delegated-agent traffic, provider templates, and env starter files ship with the repo.

## Quickstart

The fastest local path is the helper-driven bootstrap.

Platform quick starts:

- Linux or generic source checkout: use the helper/bootstrap flow below, then `systemd` if you want a long-running service.
- macOS workstation: use the helper flow below or jump to [Homebrew](./docs/WORKSTATIONS.md#homebrew-on-macos) for `brew services`.
- Windows workstation: use the source checkout flow below, then the PowerShell and Task Scheduler examples in [docs/WORKSTATIONS.md](./docs/WORKSTATIONS.md).

```bash
git clone https://github.com/typelicious/FoundryGate.git foundrygate
cd foundrygate
cp .env.example .env
./scripts/foundrygate-bootstrap
$EDITOR .env
./scripts/foundrygate-doctor
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m foundrygate
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8090/v1/models
```

Then use the onboarding helpers to move from “the server starts” to “real clients are ready”:

```bash
./scripts/foundrygate-onboarding-report
./scripts/foundrygate-onboarding-validate
```

If you prefer a packaged or service-driven install, jump to [Deployment](#deployment) or the fuller [Operations guide](./docs/OPERATIONS.md).

Minimal Homebrew flow on macOS:

```bash
brew tap typelicious/foundrygate https://github.com/typelicious/FoundryGate
brew install typelicious/foundrygate/foundrygate
brew services start typelicious/foundrygate/foundrygate
```

## How It Works

```text
Client (OpenClaw, n8n, CLI, custom app)
  |
  v
http://127.0.0.1:8090/v1
  |
  +--> policy rules
  +--> static rules
  +--> heuristic rules
  +--> optional request hooks
  +--> optional client profile defaults
  +--> optional LLM classifier
  |
  +--> provider selection and fallback
         |- cloud APIs
         |- proxy providers
         `- local workers
```

Routing is layered on purpose:

1. Policies can enforce locality, capability, cost, or compliance preferences.
2. Static and heuristic rules catch known patterns without needing a classifier call.
3. Request hooks can inject bounded routing hints before the final decision.
4. Client profiles give OpenClaw, n8n, CLI tools, and custom apps different safe defaults.
5. Provider scoring considers health, latency, context headroom, token limits, cache hints, and recent failures.

For OpenClaw specifically, both one-agent and many-agent traffic can use the same endpoint. FoundryGate can distinguish delegated traffic through request headers such as `x-openclaw-source` when they are present.

## API Surface

FoundryGate keeps the primary surface compact and OpenAI-compatible. The full endpoint reference lives in [docs/API.md](./docs/API.md).

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Service health, provider status, and capability coverage |
| `GET /v1/models` | OpenAI-compatible model list |
| `POST /v1/chat/completions` | OpenAI-compatible chat routing |
| `POST /v1/images/generations` | OpenAI-compatible image generation |
| `POST /v1/images/edits` | OpenAI-compatible image editing |
| `POST /api/route` | Chat routing dry-run with decision details |
| `POST /api/route/image` | Image routing dry-run |
| `GET /api/providers` | Provider inventory and filterable coverage view |
| `GET /api/update` | Update status, guardrails, and rollout advice |

Quick checks:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8090/v1/models
curl -fsS http://127.0.0.1:8090/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Summarize why a local AI gateway is useful."}
    ]
  }'
```

## How FoundryGate Compares

The useful comparison is not “router vs router”, but how much routing and operator burden each approach leaves with you.

| Capability | Direct provider wiring | Hosted remote router | FoundryGate |
| --- | --- | --- | --- |
| One local endpoint for many clients | No | Varies | Yes |
| Local workers and cloud providers in one route set | Manual | Varies | Yes |
| Policy routing, client profiles, and hooks | Manual | Varies | Yes |
| Operator-owned health, traces, and update controls | Partial | Varies | Yes |
| Can stay fully under local operator control | Yes | Varies | Yes |
| Copy/paste onboarding for OpenClaw, n8n, and CLI tools | Manual | Varies | Yes |

FoundryGate is a local-first gateway. That means you can keep traffic, fallback policy, rollout controls, and provider selection logic close to the clients that actually depend on them.

## Deployment

FoundryGate can stay small in development and still scale into a more repeatable operator setup:

- Local Python run: quickest path for development and testing.
- `systemd` on Linux: recommended for long-running generic host installs.
- Workstation runtimes: macOS `launchd`, Linux `systemd`, and Windows task-scheduler style installs are documented separately.
- Homebrew path: a project-owned tap formula now lives under [`Formula/foundrygate.rb`](./Formula/foundrygate.rb) for macOS-oriented installs and `brew services`.
- Docker and GHCR path: tagged releases build container artifacts through the release workflow.
- Python package path: release workflows build `sdist` and `wheel`.
- Separate npm CLI package: `packages/foundrygate-cli` gives CLI-facing environments a small Node entry point without changing the Python service runtime.

Start here for the deeper deployment details:

- [Configuration reference](./docs/CONFIGURATION.md)
- [Operations guide](./docs/OPERATIONS.md)
- [Workstations guide](./docs/WORKSTATIONS.md)
- [Publishing and release flow](./docs/PUBLISHING.md)

## More Resources

- [Architecture](./docs/ARCHITECTURE.md)
- [AI-native client matrix](./docs/AI-NATIVE-MATRIX.md)
- [API reference](./docs/API.md)
- [Configuration reference](./docs/CONFIGURATION.md)
- [Operations guide](./docs/OPERATIONS.md)
- [Workstations guide](./docs/WORKSTATIONS.md)
- [Homebrew formula](./Formula/foundrygate.rb)
- [Integrations](./docs/INTEGRATIONS.md)
- [Onboarding](./docs/ONBOARDING.md)
- [Examples](./docs/examples)
- [macOS LaunchAgent example](./docs/examples/com.typelicious.foundrygate.plist)
- [OpenClaw integration starter](./openclaw-integration.jsonc)
- [Full OpenClaw example](./docs/examples/openclaw-foundrygate-full.jsonc)
- [Multi-provider stack example](./docs/examples/foundrygate-multi-provider-stack.yaml)
- [First-wave AI-native starters](./docs/AI-NATIVE-MATRIX.md#first-wave-template-set-for-v110)
- [Second-wave AI-native starters](./docs/AI-NATIVE-MATRIX.md#second-wave-template-set)
- [Third-wave AI-native starters](./docs/AI-NATIVE-MATRIX.md#third-wave-template-set)
- [Security review for `v1.0.0`](./docs/SECURITY-REVIEW-v1.0.0.md)
- [Publishing](./docs/PUBLISHING.md)
- [Troubleshooting](./docs/TROUBLESHOOTING.md)
- [Roadmap](./docs/FOUNDRYGATE-ROADMAP.md)
- [Releases](./RELEASES.md)

## Community And Security

- [Contributing](./CONTRIBUTING.md)
- [Security policy](./SECURITY.md)
- [Code of conduct](./CODE_OF_CONDUCT.md)
- [Repo safety and CI](./.github/workflows)

FoundryGate ships with repo-safety checks for `.ssh/`, `*.db*`, `*.sqlite*`, and `*.log`, plus CodeQL, Dependabot, secret scanning, and documented release review steps.

## License

Apache-2.0. See [LICENSE](./LICENSE).

⭐ If FoundryGate saves you time or money, feel free to star the repo. ❤️
