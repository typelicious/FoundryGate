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
