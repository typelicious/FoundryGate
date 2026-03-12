# FoundryGate Troubleshooting

## Health endpoint fails

Check:

```bash
curl -fsS http://127.0.0.1:8090/health
sudo ss -ltnp | grep -E '127\.0\.0\.1:8090\b' || true
```

## No providers are loaded

Typical cause:

- missing or empty API keys

Check:

- `.env`
- startup logs
- `GET /v1/models`

## Route choice looks wrong

Use the dry-run and trace surfaces first.

```bash
curl -fsS http://127.0.0.1:8090/api/route \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"debug this route"}]}'

curl -fsS 'http://127.0.0.1:8090/api/traces?limit=10'
```

Check:

- selected provider
- layer
- rule
- resolved profile
- hook errors
- attempt order
- candidate ranking details in the `decision.details` block

If you enabled request hooks, also decide whether the runtime should continue or fail closed:

```yaml
request_hooks:
  enabled: true
  on_error: fail
```

## Local worker stays unhealthy

For `contract: local-worker`, FoundryGate probes `GET /models`.

Common causes:

- the worker is not listening
- the worker is not actually OpenAI-compatible
- the configured `base_url` is wrong
- the worker is reachable but returns HTTP errors

Validate directly:

```bash
curl -fsS http://127.0.0.1:11434/v1/models
```

Then re-check:

```bash
curl -fsS http://127.0.0.1:8090/health
```

If the worker is healthy but still loses route selection, inspect `POST /api/route` and compare:

- `decision.details.candidate_ranking`
- `context_score`
- `input_score`
- `output_score`
- `locality_score`
- `latency_score`

## Image generation or image editing fails

Check whether any loaded provider actually exposes the required image capability:

```bash
curl -fsS http://127.0.0.1:8090/v1/models
curl -fsS http://127.0.0.1:8090/health
```

For `contract: image-provider`, validate the upstream directly:

```bash
curl -fsS https://api.example.com/v1/images/generations \
  -H 'Authorization: Bearer YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-image-1","prompt":"test"}'
```

For image editing, validate the upstream edit surface too:

```bash
curl -fsS https://api.example.com/v1/images/edits \
  -H 'Authorization: Bearer YOUR_KEY' \
  -F 'model=gpt-image-1' \
  -F 'prompt=test' \
  -F 'image=@input.png'
```

If `model: "auto"` still fails, verify that at least one loaded provider reports `capabilities.image_generation: true` for generation or `capabilities.image_editing: true` for editing.

## Many-agent OpenClaw traffic is not separated

Check whether `x-openclaw-source` is present.

That header is the current signal used for OpenClaw sub-agent differentiation in the stock config and built-in presets.

## Database path is wrong or unwritable

Use an absolute path outside the repo checkout:

```bash
mkdir -p "$HOME/.local/state/foundrygate"
printf 'FOUNDRYGATE_DB_PATH=%s\n' "$HOME/.local/state/foundrygate/foundrygate.db"
```

## Update went wrong

Current update path is manual or helper-script driven.

Use:

```bash
foundrygate-status
foundrygate-logs
foundrygate-health
```

If you use `foundrygate-update`, remember that it is meant for deployment checkouts and removes local untracked changes.

## Update checks fail or show unavailable

Check the cached runtime view first:

```bash
curl -fsS http://127.0.0.1:8090/api/update
curl -fsS http://127.0.0.1:8090/api/operator-events
./scripts/foundrygate-update-check
./scripts/foundrygate-auto-update
```

Common causes:

- outbound GitHub API access is blocked
- `update_check.repository` is wrong
- `update_check.api_base` points to the wrong host
- the runtime hit a temporary network or TLS error

If needed, reduce the problem to config:

```yaml
update_check:
  enabled: true
  repository: "typelicious/FoundryGate"
  api_base: "https://api.github.com"
  timeout_seconds: 5
  check_interval_seconds: 21600
```

Use `force=true` when you need an immediate refresh instead of the cached result:

```bash
curl -fsS 'http://127.0.0.1:8090/api/update?force=true'
```

If `foundrygate-auto-update --apply` refuses to run, inspect the `auto_update` block in the JSON response. Common blockers are:

- `auto_update.enabled: false`
- the latest release is a major upgrade while `allow_major: false`
- `provider_scope.allow_providers` / `deny_providers` resolves to no matching providers
- one or more providers are unhealthy while `require_healthy_providers: true`
- the number of unhealthy providers exceeds `max_unhealthy_providers`
- the configured `verification.command` failed after the update command ran
- the current time is outside the configured `maintenance_window.days` or `maintenance_window.start_hour` / `end_hour`
- `maintenance_window.timezone` is invalid for the host runtime
- the release lookup itself is unavailable
