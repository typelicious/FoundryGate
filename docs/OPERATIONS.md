# FoundryGate Operations

This page keeps the deployment, helper-script, and update-control details out of the root README while staying copy/paste friendly for operators.

## Deployment Modes

### Local Python Run

Good for development and early validation:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m foundrygate
```

### `systemd` On Generic Linux

The repo ships a service file:

```text
/etc/systemd/system/foundrygate.service
```

Recommended persistent state path:

```text
/var/lib/foundrygate/foundrygate.db
```

That path is wired through `FOUNDRYGATE_DB_PATH`.

### Docker / GHCR

Tagged releases build container artifacts through the release workflow. For local validation you can build from the repo root:

```bash
docker build -t foundrygate:local .
docker run --rm -p 8090:8090 --env-file .env foundrygate:local
```

### Python Package And npm CLI

Release workflows build Python `sdist` and `wheel` artifacts.

For CLI-facing environments, the repo also includes a separate package:

```text
packages/foundrygate-cli
```

That package is intentionally separate from the Python gateway runtime.

## Helper Scripts

FoundryGate ships optional wrappers around `systemd`, `journalctl`, `curl`, onboarding checks, and release-update flows.

| Script | What it does |
| --- | --- |
| `foundrygate-install` | install service + helper links |
| `foundrygate-start` / `foundrygate-stop` / `foundrygate-restart` | basic service control |
| `foundrygate-status` / `foundrygate-logs` / `foundrygate-health` | operator visibility |
| `foundrygate-bootstrap` | local bootstrap convenience flow |
| `foundrygate-doctor` | validate env and config readiness |
| `foundrygate-onboarding-report` | summarize rollout readiness |
| `foundrygate-onboarding-validate` | fail fast on onboarding blockers |
| `foundrygate-update-check` | release-status and guardrail check |
| `foundrygate-auto-update` | helper-driven, opt-in update apply flow |
| `foundrygate-update` / `foundrygate-uninstall` | lifecycle helpers |

Examples:

```bash
./scripts/foundrygate-install
./scripts/foundrygate-status
./scripts/foundrygate-health
./scripts/foundrygate-update-check
```

## Update Checks And Auto-Update

FoundryGate supports explicit operator-side update control without turning the service into a self-mutating daemon.

API surfaces:

- `GET /api/update`
- `GET /api/operator-events`

Relevant config blocks:

- `update_check`
- `auto_update`

Guardrails available today:

- release channels
- rollout rings
- minimum release age
- maintenance windows
- provider scopes
- post-update verification

Major upgrades stay blockable through config, and helper-driven apply flows remain opt-in.

## Scheduled Examples

The repo ships example schedules under [`docs/examples`](./examples):

- `foundrygate-auto-update.service`
- `foundrygate-auto-update.timer`
- `foundrygate-auto-update.cron`

Use them only after the manual update path is already validated.

## Troubleshooting

Start with:

- [`docs/TROUBLESHOOTING.md`](./TROUBLESHOOTING.md)
- `./scripts/foundrygate-health`
- `./scripts/foundrygate-status`
- `./scripts/foundrygate-logs`

The most common rollout issues are:

- provider API keys missing or still templated
- DB path not writable
- port `8090` already in use
- a provider repeatedly failing into fallback
