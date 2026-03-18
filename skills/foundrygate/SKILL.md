---
name: foundrygate
description: FoundryGate routing stats and control. Use when the user asks about API costs, model routing, token usage, cache hit rates, provider health, or wants to test how a prompt would be routed. Commands — /foundrygate stats, /foundrygate route, /foundrygate health, /foundrygate daily.
metadata: {"openclaw":{"requires":{"bins":["curl"]},"emoji":"🚪","homepage":"https://github.com/typelicious/FoundryGate"}}
---

# FoundryGate Skill

FoundryGate is a local routing proxy that sits between OpenClaw and your model providers (chat and image-capable backends).

OpenClaw note: when OpenClaw talks to FoundryGate, the model ids in the OpenClaw config must match the provider ids returned by `GET /v1/models` from FoundryGate. Those ids are local FoundryGate ids such as `auto`, `deepseek-chat`, `local-worker`, or `image-provider`, not raw upstream model names.

## Available Commands

### /foundrygate stats
Show full routing statistics: total requests, cost, tokens, cache hit rate, per-provider breakdown.

```bash
curl -s http://127.0.0.1:8090/api/stats | python3 -m json.tool
```

Format the output as a clean summary table showing:
- Total requests, total cost (USD), avg latency
- Cache hit rate (higher = more savings from DeepSeek/Gemini prefix caching)
- Per-provider: requests, tokens, cost, cache%, failures
- Top routing rules by usage

### /foundrygate health
Check provider health status.

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool
```

Show each provider's health status, consecutive failures, and average latency. Flag any unhealthy providers.

### /foundrygate daily
Show daily cost breakdown with projected monthly cost.

```bash
curl -s http://127.0.0.1:8090/api/stats | python3 -c "
import sys,json
d=json.load(sys.stdin)
daily=d.get('daily',[])
for day in daily:
    print(f\"{day['day']}  reqs={day['requests']:4d}  cost=\${day['cost_usd']:.4f}  tokens={day['tokens']}\")
if daily:
    avg=sum(x['cost_usd'] for x in daily)/len(daily)
    print(f'---')
    print(f'Avg/day: \${avg:.4f}  Projected/month: \${avg*30:.2f}')
"
```

### /foundrygate route <message>
Dry-run: show which provider a message would be routed to without actually sending it upstream. Useful for testing routing rules, client profiles, and fallback order.

```bash
curl -s http://127.0.0.1:8090/api/route \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "USER_MESSAGE_HERE"}]
  }' | python3 -m json.tool
```

Show the selected provider, routing layer, rule, resolved profile, and attempt order. If relevant headers matter for routing, include them in the dry-run request.

### /foundrygate image-route <prompt>
Dry-run image routing without calling an upstream provider.

```bash
curl -s http://127.0.0.1:8090/api/route/image \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "generation",
    "model": "auto",
    "prompt": "PROMPT_HERE",
    "size": "1024x1024"
  }' | python3 -m json.tool
```

Show the selected provider, routing layer, rule, and candidate ranking for image traffic.

### /foundrygate image <prompt>
Send one real image-generation request through FoundryGate.

```bash
curl -s http://127.0.0.1:8090/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "prompt": "PROMPT_HERE",
    "size": "1024x1024"
  }' | python3 -m json.tool
```

### /foundrygate image-edit <prompt>
Send one image-edit request with a local input file and optional mask.

```bash
curl -s http://127.0.0.1:8090/v1/images/edits \
  -F "model=auto" \
  -F "prompt=PROMPT_HERE" \
  -F "image=@INPUT_IMAGE.png" \
  -F "mask=@OPTIONAL_MASK.png" | python3 -m json.tool
```

### /foundrygate recent
Show the last 10 requests with provider, layer, rule, tokens, cost, and status.

```bash
curl -s 'http://127.0.0.1:8090/api/recent?limit=10' | python3 -c "
import sys,json,time
d=json.load(sys.stdin)
for r in d.get('requests',[]):
    ago=time.time()-r['timestamp']
    t=f'{ago/60:.0f}m' if ago<3600 else f'{ago/3600:.1f}h'
    tok=r.get('prompt_tok',0)+r.get('compl_tok',0)
    print(f\"{t:>6s} ago  {r['provider']:20s} {r['layer']:10s} {r['rule_name']:20s} {tok:>6d}tok  \${r.get('cost_usd',0):.4f}  {'✓' if r.get('success') else '✗'}\")
"
```

### /foundrygate traces
Show the last 10 enriched route traces including requested model, resolved profile, client tag, decision reason, confidence, and attempt order.

```bash
curl -s 'http://127.0.0.1:8090/api/traces?limit=10' | python3 -m json.tool
```

## Dashboard

A web dashboard is available at http://127.0.0.1:8090/dashboard — open it in a browser for a live view with auto-refresh.

## How Routing Works

FoundryGate uses 6 routing stages for chat requests (evaluated in order, first decisive match wins):

1. **Policy rules**: Governance, local/cloud constraints, and capability-aware provider selection
2. **Static rules**: Pattern matching on model name and headers (heartbeats, explicit model requests, subagent detection)
3. **Heuristic scoring**: Keyword-weighted classification of user messages (NOT system prompt) into reasoning/code/simple/agent categories
4. **Request hooks**: optional per-request hints such as preferred provider, locality, or profile override
5. **Client profiles**: caller-specific defaults for OpenClaw, n8n, CLI wrappers, or local-only traffic
6. **LLM classifier** (optional): Cheapest model classifies the task when heuristics are uncertain

Key insight: Only user messages are scored, never the system prompt. OpenClaw's system prompt is large and keyword-rich — scoring it would route everything to the expensive reasoning tier.

## OpenClaw Integration Notes

- Prefer one OpenClaw provider named `foundrygate` that points to `http://127.0.0.1:8090/v1`.
- Use `foundrygate/auto` as the default `model.primary` unless you want to pin one explicit FoundryGate provider.
- Use `foundrygate/auto` for `imageModel.primary` when FoundryGate should pick among image-capable providers. Pin `foundrygate/<provider-id>` only when the image backend must be fixed.
- If many-agent traffic should be distinguishable, keep `x-openclaw-source` short and stable.
- If you want FoundryGate to classify OpenClaw traffic automatically, enable `client_profiles.presets: ["openclaw"]` in `config.yaml`.

## Prompt Caching

DeepSeek and Gemini automatically cache repeated prefixes server-side. FoundryGate tracks cache hit/miss tokens in metrics. To maximize cache hits:
- Keep system prompts stable (identical prefix between requests)
- Push variable content to the end of messages
- Use few-shot examples consistently

Cache pricing: DeepSeek charges ~10x less for cache hits ($0.014/M vs $0.14/M for cache miss).
