# Security Policy

## Supported Versions

FoundryGate is currently maintained on the latest `main` branch and the most recent tagged release line.

| Version | Supported |
| --- | --- |
| `main` | Yes |
| Latest tagged release | Yes |
| Older releases | Best effort only |

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability.

Preferred path:

1. Use GitHub private vulnerability reporting for this repository when available.
2. If private reporting is not available in your GitHub session, open a private GitHub security advisory draft for this repository.
3. Include affected version or commit, reproduction steps, impact, and any suggested mitigation.

Expected handling:

- initial acknowledgement target: within 5 business days
- status update target: within 10 business days after acknowledgement
- coordinated disclosure after a fix or documented mitigation is ready

## Scope

Please report issues such as:

- request, header, or parameter injection
- dashboard XSS or HTML/CSS injection
- unsafe file-path handling or writable-path assumptions
- auth or secret-handling mistakes
- dependency vulnerabilities with practical impact
- trust-boundary issues between FoundryGate and upstream or local providers

## Operational Guidance

To reduce risk in deployments:

- keep `FOUNDRYGATE_DB_PATH` outside the repo checkout
- avoid committing `.env`, database files, SQLite files, logs, or SSH material
- run with the provided `systemd` hardening or an equivalent container/runtime policy
- keep provider API keys scoped to the minimum set of enabled providers
