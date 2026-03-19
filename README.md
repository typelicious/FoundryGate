# fusionAIze Gate

[![repo-safety](https://github.com/fusionAIze/faigate/actions/workflows/repo-safety.yml/badge.svg)](https://github.com/fusionAIze/faigate/actions/workflows/repo-safety.yml)
[![CI](https://github.com/fusionAIze/faigate/actions/workflows/ci.yml/badge.svg)](https://github.com/fusionAIze/faigate/actions/workflows/ci.yml)
[![CodeQL](https://github.com/fusionAIze/faigate/actions/workflows/codeql.yml/badge.svg)](https://github.com/fusionAIze/faigate/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/fusionAIze/faigate?display_name=tag)](https://github.com/fusionAIze/faigate/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![OpenAI-compatible](https://img.shields.io/badge/OpenAI-compatible-0ea5e9.svg)](./docs/API.md)
[![OpenClaw-friendly](https://img.shields.io/badge/OpenClaw-friendly-111827.svg)](https://openclaw.ai/)
[![Workstations](https://img.shields.io/badge/workstations-linux%20%7C%20macOS%20%7C%20windows-0f766e.svg)](./docs/WORKSTATIONS.md)
[![Homebrew](https://img.shields.io/badge/homebrew-formula-fbbf24?logo=homebrew&logoColor=black)](./Formula/faigate.rb)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](./Dockerfile)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](./pyproject.toml)

Local OpenAI-compatible AI gateway for 🦞 [OpenClaw](https://openclaw.ai/) and other AI-native clients.

fusionAIze Gate gives OpenClaw, n8n, CLI tools, and custom apps one local endpoint and routes each request to the best configured provider or local worker. It keeps routing, fallback, onboarding, and operator visibility under your control instead of scattering provider logic across every client.

Runs locally on Linux, macOS, and Windows, with first-class workstation guidance for `systemd`, `launchd`, Task Scheduler, and Homebrew-driven macOS installs.

## Quick Navigation

- [Quickstart](#quickstart)
- [Why fusionAIze Gate](#why-fusionaize-gate)
- [How It Works](#how-it-works)
- [API Surface](#api-surface)
- [How fusionAIze Gate Compares](#how-fusionaize-gate-compares)
- [Deployment](#deployment)
- [More Resources](#more-resources)
- [Community And Security](#community-and-security)

## Why fusionAIze Gate

- Single local endpoint for many upstreams: cloud providers, proxy providers, and local workers can sit behind the same base URL.
- OpenAI-compatible runtime: chat completions, model discovery, image generation, and image editing use familiar OpenAI-style paths.
- Better routing than simple first-match proxying: policies, static rules, heuristics, client profiles, hooks, and route-fit scoring all participate.
- Strong operator visibility: `/health`, provider inventory, route previews, traces, stats, update checks, and dashboard views are built in, including per-client usage highlights.
- Practical rollout controls: fallback chains, maintenance windows, rollout rings, provider scopes, and post-update verification gates are already there.
- Copy/paste onboarding: OpenClaw, n8n, CLI, delegated-agent traffic, provider templates, and env starter files ship with the repo.
- Curated provider-catalog checks catch stale model choices, volatile free-tier picks, and source-confidence gaps before local configs quietly age out.
- Provider discovery can stay transparent: catalog entries can expose official or operator-configured signup links, while recommendation ranking stays performance-led and link-neutral.
- The onboarding report and doctor CLI can surface those links with disclosure, so operators can share a signup path without turning discovery into biased ranking.

## Quickstart

The fastest local path is the helper-driven bootstrap.

Platform quick starts:

- Linux or generic source checkout: use the helper/bootstrap flow below, then `systemd` if you want a long-running service.
- macOS workstation: use the helper flow below or jump to [Homebrew](./docs/WORKSTATIONS.md#homebrew-on-macos) for `brew services`.
- Windows workstation: use the source checkout flow below, then the PowerShell and Task Scheduler examples in [docs/WORKSTATIONS.md](./docs/WORKSTATIONS.md).

```bash
git clone https://github.com/fusionAIze/faigate.git faigate
cd faigate
cp .env.example .env
./scripts/faigate-bootstrap
$EDITOR .env
./scripts/faigate-doctor
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m faigate
```

In another terminal:

```bash
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1:8090/v1/models
```

Then use the onboarding helpers to move from “the server starts” to “real clients are ready”:

```bash
./scripts/faigate-menu
./scripts/faigate-config-wizard --help
./scripts/faigate-config-wizard --purpose general --client generic > config.yaml
./scripts/faigate-onboarding-report
./scripts/faigate-provider-discovery
./scripts/faigate-provider-discovery --json --offer-track free
./scripts/faigate-onboarding-validate
```

`./scripts/faigate-menu` now also gives you one Gate-native shell entrypoint for API keys, HTTP settings, routing modes, validation helpers, service control, and update checks.

To review and selectively adopt multiple candidates during first setup or a later update:

```bash
./scripts/faigate-config-wizard --purpose free --client n8n --list-candidates
./scripts/faigate-config-wizard --current-config config.yaml --purpose free --client n8n
./scripts/faigate-config-wizard --purpose free --client n8n \
  --select kilocode,blackbox-free,gemini-flash-lite > config.yaml
./scripts/faigate-config-wizard --current-config config.yaml --merge-existing \
  --select openrouter-fallback,anthropic-claude --write config.yaml
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

If you prefer a packaged or service-driven install, jump to [Deployment](#deployment) or the fuller [Operations guide](./docs/OPERATIONS.md).

Minimal Homebrew flow on macOS:

```bash
brew tap fusionAIze/faigate https://github.com/fusionAIze/faigate
brew install fusionAIze/faigate/faigate
# or, after the tap is present:
brew install faigate
brew services start fusionAIze/faigate/faigate
```

If you already have an active Python virtualenv, check which binary you are calling before testing the Brew install:

```bash
which -a faigate
/opt/homebrew/bin/faigate --version
/opt/homebrew/bin/faigate-menu --help
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
  +--> optional routing modes (auto / eco / premium / free / custom)
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
4. Routing modes expose stable virtual model ids like `auto`, `eco`, `premium`, or custom names.
5. Client profiles can choose their own default routing mode before the final scoring step.
6. Provider scoring considers health, latency, context headroom, token limits, cache hints, and recent failures.

For OpenClaw specifically, both one-agent and many-agent traffic can use the same endpoint. fusionAIze Gate can distinguish delegated traffic through request headers such as `x-openclaw-source` when they are present.

## API Surface

fusionAIze Gate keeps the primary surface compact and OpenAI-compatible. The full endpoint reference lives in [docs/API.md](./docs/API.md).

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

## How fusionAIze Gate Compares

The useful comparison is not “router vs router”, but how much routing and operator burden each approach leaves with you.

| Capability | Direct provider wiring | Hosted remote router | fusionAIze Gate |
| --- | --- | --- | --- |
| One local endpoint for many clients | No | Varies | Yes |
| Local workers and cloud providers in one route set | Manual | Varies | Yes |
| Policy routing, client profiles, and hooks | Manual | Varies | Yes |
| Operator-owned health, traces, and update controls | Partial | Varies | Yes |
| Can stay fully under local operator control | Yes | Varies | Yes |
| Copy/paste onboarding for OpenClaw, n8n, and CLI tools | Manual | Varies | Yes |

fusionAIze Gate is a local-first gateway. That means you can keep traffic, fallback policy, rollout controls, and provider selection logic close to the clients that actually depend on them.

## Deployment

fusionAIze Gate can stay small in development and still scale into a more repeatable operator setup:

- Local Python run: quickest path for development and testing.
- `systemd` on Linux: recommended for long-running generic host installs.
- Workstation runtimes: macOS `launchd`, Linux `systemd`, and Windows task-scheduler style installs are documented separately.
- Homebrew path: a project-owned tap formula now lives under [`Formula/faigate.rb`](./Formula/faigate.rb) for macOS-oriented installs and `brew services`.
- Docker and GHCR path: tagged releases build container artifacts through the release workflow.
- Python package path: release workflows build `sdist` and `wheel`.
- Separate npm CLI package: `packages/faigate-cli` gives CLI-facing environments a small Node entry point without changing the Python service runtime.

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
- [Homebrew formula](./Formula/faigate.rb)
- [Integrations](./docs/INTEGRATIONS.md)
- [Onboarding](./docs/ONBOARDING.md)
- [Examples](./docs/examples)
- [macOS LaunchAgent example](./docs/examples/com.fusionaize.faigate.plist)
- [OpenClaw integration starter](./openclaw-integration.jsonc)
- [Full OpenClaw example](./docs/examples/openclaw-faigate-full.jsonc)
- [Multi-provider stack example](./docs/examples/faigate-multi-provider-stack.yaml)
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

fusionAIze Gate ships with repo-safety checks for `.ssh/`, `*.db*`, `*.sqlite*`, and `*.log`, plus CodeQL, Dependabot, secret scanning, and documented release review steps.

## License

Apache-2.0. See [LICENSE](./LICENSE).

⭐ If fusionAIze Gate saves you time or money, feel free to star the repo. ❤️
