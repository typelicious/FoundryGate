"""FoundryGate – FastAPI application.

OpenAI-compatible /v1/chat/completions proxy that routes requests
through a 3-layer classification engine to the optimal provider.
"""

# ruff: noqa: E501

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from .config import Config, load_config
from .metrics import MetricsStore, calc_cost
from .providers import ProviderBackend, ProviderError
from .router import Router, RoutingDecision

logger = logging.getLogger("foundrygate")

# ── Globals (initialized in lifespan) ──────────────────────────
_config: Config
_providers: dict[str, ProviderBackend] = {}
_router: Router
_metrics: MetricsStore


def _collect_routing_headers(request: Request) -> dict[str, str]:
    """Return the request headers that are relevant for routing decisions."""
    prefixes = ("x-openclaw", "x-foundrygate")
    return {k.lower(): v for k, v in request.headers.items() if k.lower().startswith(prefixes)}


def _match_client_profile_rule(match: dict, headers: dict[str, str]) -> bool:
    """Evaluate one client profile match block."""
    if not match:
        return True
    if "all" in match:
        return all(_match_client_profile_rule(item, headers) for item in match["all"])
    if "any" in match:
        return any(_match_client_profile_rule(item, headers) for item in match["any"])
    if "header_present" in match:
        return all(header_name in headers for header_name in match["header_present"])
    if "header_contains" in match:
        for header_name, patterns in match["header_contains"].items():
            header_value = headers.get(header_name, "").lower()
            if any(pattern.lower() in header_value for pattern in patterns):
                return True
        return False
    return False


def _resolve_client_profile(
    config: Config, headers: dict[str, str]
) -> tuple[str, dict[str, object]]:
    """Resolve the active client profile and its routing hints from request headers."""
    profiles_cfg = config.client_profiles
    default_profile = profiles_cfg.get("default", "generic")
    active_profile = default_profile

    if profiles_cfg.get("enabled"):
        for rule in profiles_cfg.get("rules", []):
            if _match_client_profile_rule(rule.get("match", {}), headers):
                active_profile = rule["profile"]
                break

    hints = profiles_cfg.get("profiles", {}).get(active_profile, {})
    return active_profile, hints


def _resolve_client_tag(headers: dict[str, str], client_profile: str) -> str:
    """Return a stable client tag for metrics and trace grouping."""
    if headers.get("x-foundrygate-client"):
        return headers["x-foundrygate-client"].strip().lower()
    if headers.get("x-openclaw-source"):
        return "openclaw"
    return client_profile


def _build_attempt_order(primary_provider: str) -> list[str]:
    """Return the provider attempt order for one routed request."""
    attempt_order = []
    for provider_name in [primary_provider, *_config.fallback_chain]:
        if provider_name in _providers and provider_name not in attempt_order:
            attempt_order.append(provider_name)
    return attempt_order


def _serialize_provider(name: str) -> dict[str, Any] | None:
    """Return one provider snapshot for API responses."""
    provider = _providers.get(name)
    if not provider:
        return None

    return {
        "name": name,
        "model": provider.model,
        "backend": provider.backend_type,
        "contract": provider.contract,
        "tier": provider.tier,
        "healthy": provider.health.healthy,
        "capabilities": provider.capabilities,
    }


async def _resolve_route_preview(
    body: dict[str, Any], headers: dict[str, str]
) -> tuple[RoutingDecision, str, str, list[str], str]:
    """Resolve one request into a routing decision without calling a provider."""
    messages = body.get("messages", [])
    model_requested = body.get("model", "auto")
    tools = body.get("tools")

    client_profile, profile_hints = _resolve_client_profile(_config, headers)
    client_tag = _resolve_client_tag(headers, client_profile)

    if model_requested != "auto" and model_requested in _providers:
        decision = RoutingDecision(
            provider_name=model_requested,
            layer="direct",
            rule_name="explicit-model",
            confidence=1.0,
            reason=f"Directly requested provider: {model_requested}",
        )
    else:
        health_map = {name: p.health.to_dict() for name, p in _providers.items()}
        decision = await _router.route(
            messages,
            model_requested=model_requested,
            has_tools=bool(tools),
            client_profile=client_profile,
            profile_hints=profile_hints,
            headers=headers,
            provider_health=health_map,
        )

    return (
        decision,
        client_profile,
        client_tag,
        _build_attempt_order(decision.provider_name),
        model_requested,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _config, _providers, _router, _metrics

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    _config = load_config()
    logger.info("Loaded config with %d providers", len(_config.providers))

    # Initialize provider backends
    for name, pcfg in _config.providers.items():
        if not pcfg.get("api_key"):
            logger.warning("Provider %s has no API key, skipping", name)
            continue
        _providers[name] = ProviderBackend(name, pcfg)
        logger.info("  ✓ %s → %s (%s)", name, pcfg["model"], pcfg.get("tier", "default"))

    _router = Router(_config)

    # Metrics
    _metrics = MetricsStore(db_path=_config.metrics["db_path"])
    if _config.metrics.get("enabled"):
        _metrics.init()

    logger.info(
        "FoundryGate ready on %s:%s",
        _config.server.get("host", "127.0.0.1"),
        _config.server.get("port", 8090),
    )

    yield

    # Shutdown
    for p in _providers.values():
        await p.close()
    _metrics.close()
    logger.info("FoundryGate shut down")


app = FastAPI(
    title="FoundryGate",
    version="0.3.0",
    description="Local OpenAI-compatible routing gateway for OpenClaw and other clients.",
    lifespan=lifespan,
)


# ── Health / Info endpoints ────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "providers": {
            name: {
                **p.health.to_dict(),
                "contract": p.contract,
                "backend": p.backend_type,
                "tier": p.tier,
                "capabilities": p.capabilities,
            }
            for name, p in _providers.items()
        },
    }


@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible model listing."""
    models = []
    # Expose a virtual "auto" model + each real provider
    models.append(
        {
            "id": "auto",
            "object": "model",
            "owned_by": "foundrygate",
            "description": "Auto-routed to optimal provider",
        }
    )
    for name, p in _providers.items():
        models.append(
            {
                "id": name,
                "object": "model",
                "owned_by": p.backend_type,
                "description": f"{p.model} ({p.tier})",
                "contract": p.contract,
                "capabilities": p.capabilities,
            }
        )
    return {"object": "list", "data": models}


@app.get("/api/stats")
async def stats():
    """Full statistics: totals, per-provider, routing breakdown, time series."""
    return {
        "totals": _metrics.get_totals(),
        "providers": _metrics.get_provider_summary(),
        "routing": _metrics.get_routing_breakdown(),
        "clients": _metrics.get_client_breakdown(),
        "hourly": _metrics.get_hourly_series(24),
        "daily": _metrics.get_daily_totals(30),
    }


@app.get("/api/recent")
async def recent(limit: int = 50):
    """Recent request log."""
    return {"requests": _metrics.get_recent(limit)}


@app.get("/api/traces")
async def traces(limit: int = 50):
    """Recent enriched route traces for debugging and policy tuning."""
    return {"traces": _metrics.get_recent(limit)}


@app.post("/api/route")
async def preview_route(request: Request):
    """Dry-run one routing decision without sending a provider request."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    headers = _collect_routing_headers(request)
    (
        decision,
        client_profile,
        client_tag,
        attempt_order,
        model_requested,
    ) = await _resolve_route_preview(body, headers)

    return {
        "requested_model": model_requested,
        "resolved_profile": client_profile,
        "client_tag": client_tag,
        "routing_headers": headers,
        "decision": decision.to_dict(),
        "selected_provider": _serialize_provider(decision.provider_name),
        "attempt_order": [_serialize_provider(name) for name in attempt_order],
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Minimal self-contained dashboard – no build step, no deps."""
    return _DASHBOARD_HTML


# ── Main completion endpoint ───────────────────────────────────


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completion endpoint.

    If model is "auto" or omitted: routes through the 3-layer engine.
    If model matches a provider name: routes directly to that provider.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    stream = body.get("stream", False)
    temperature = body.get("temperature")
    max_tokens = body.get("max_tokens")
    tools = body.get("tools")

    headers = _collect_routing_headers(request)
    (
        decision,
        client_profile,
        client_tag,
        attempt_order,
        model_requested,
    ) = await _resolve_route_preview(body, headers)
    messages = body.get("messages", [])

    logger.info(
        "Route: %s [%s/%s] %.1fms",
        decision.provider_name,
        decision.layer,
        decision.rule_name,
        decision.elapsed_ms,
    )

    # ── Execute with fallback ──────────────────────────────

    errors: list[str] = []

    for provider_name in attempt_order:
        provider = _providers.get(provider_name)
        if not provider:
            continue
        if not provider.health.healthy and provider_name != attempt_order[0]:
            continue  # Skip known-unhealthy fallbacks (but always try the chosen one)

        try:
            result = await provider.complete(
                messages,
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )

            # Log metrics with cost (cache-aware)
            if _config.metrics.get("enabled") and isinstance(result, dict):
                usage = result.get("usage", {})
                cg = result.get("_foundrygate", {})
                pt = usage.get("prompt_tokens", 0)
                ct = usage.get("completion_tokens", 0)
                ch = cg.get("cache_hit_tokens", 0)
                cm = cg.get("cache_miss_tokens", 0)
                provider_cfg = _config.provider(provider_name)
                pricing = provider_cfg.get("pricing", {}) if provider_cfg else {}
                cost = calc_cost(pt, ct, pricing, cache_hit=ch, cache_miss=cm)
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    cache_hit=ch,
                    cache_miss=cm,
                    cost_usd=cost,
                    latency_ms=cg.get("latency_ms", 0),
                    requested_model=model_requested,
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )

            if stream:
                return StreamingResponse(
                    result,
                    media_type="text/event-stream",
                    headers={
                        "X-FoundryGate-Provider": provider_name,
                        "X-FoundryGate-Profile": client_profile,
                    },
                )

            # Add routing info to response headers (non-streaming)
            resp = JSONResponse(result)
            resp.headers["X-FoundryGate-Provider"] = provider_name
            resp.headers["X-FoundryGate-Profile"] = client_profile
            resp.headers["X-FoundryGate-Layer"] = decision.layer
            resp.headers["X-FoundryGate-Rule"] = decision.rule_name
            return resp

        except ProviderError as e:
            errors.append(f"{provider_name}: {e.detail}")
            logger.warning("Provider %s failed: %s, trying next...", provider_name, e.detail[:200])
            if _config.metrics.get("enabled"):
                _metrics.log_request(
                    provider=provider_name,
                    model=provider.model,
                    layer=decision.layer,
                    rule_name=decision.rule_name,
                    success=False,
                    error=e.detail[:500],
                    requested_model=model_requested,
                    client_profile=client_profile,
                    client_tag=client_tag,
                    decision_reason=decision.reason,
                    confidence=decision.confidence,
                    attempt_order=attempt_order,
                )
            continue

    # All providers failed
    return JSONResponse(
        {
            "error": {
                "message": f"All providers failed: {'; '.join(errors)}",
                "type": "provider_error",
                "attempts": errors,
            }
        },
        status_code=502,
    )


# ── CLI entry point ────────────────────────────────────────────


def main():
    """Run with: python -m foundrygate"""
    import uvicorn

    config = load_config()
    uvicorn.run(
        "foundrygate.main:app",
        host=config.server.get("host", "127.0.0.1"),
        port=config.server.get("port", 8090),
        log_level=config.server.get("log_level", "info"),
        reload=False,
    )


# ── Dashboard HTML ─────────────────────────────────────────────

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FoundryGate</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0a0a0f;color:#e0e0e0;padding:20px}
h1{font-size:1.4em;color:#7af;margin-bottom:4px}
.sub{color:#888;font-size:.85em;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px}
.card{background:#14141f;border:1px solid #222;border-radius:8px;padding:16px}
.card .label{font-size:.75em;color:#888;text-transform:uppercase;letter-spacing:.5px}
.card .value{font-size:1.8em;font-weight:700;color:#7af;margin-top:2px}
.card .value.cost{color:#5e5}
.card .value.err{color:#f66}
.card .detail{font-size:.75em;color:#666;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:.85em;margin-bottom:24px}
th{text-align:left;padding:8px 10px;border-bottom:2px solid #333;color:#888;font-weight:600;text-transform:uppercase;font-size:.7em;letter-spacing:.5px}
td{padding:6px 10px;border-bottom:1px solid #1a1a2a}
tr:hover td{background:#1a1a2a}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75em;font-weight:600}
.tag-static{background:#2a2a4a;color:#99f}
.tag-heuristic{background:#2a3a2a;color:#9f9}
.tag-direct{background:#3a3a2a;color:#ff9}
.tag-fallback{background:#3a2a2a;color:#f99}
.tag-llm{background:#2a3a3a;color:#9ff}
.bar-wrap{height:6px;background:#1a1a2a;border-radius:3px;overflow:hidden;margin-top:6px}
.bar{height:100%;border-radius:3px;transition:width .5s}
.bar-ds{background:#7af}.bar-r1{background:#f7a}.bar-gl{background:#5e5}.bar-gf{background:#5dd}.bar-or{background:#fa5}
.sect{margin-bottom:24px}
.sect h2{font-size:1em;color:#aaa;margin-bottom:10px;border-bottom:1px solid #222;padding-bottom:6px}
#status{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.refresh-btn{background:#222;color:#888;border:1px solid #333;border-radius:4px;padding:4px 12px;cursor:pointer;font-size:.8em}
.refresh-btn:hover{background:#2a2a3a;color:#aaa}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.mono{font-family:'SF Mono',Consolas,monospace;font-size:.8em}
</style>
</head>
<body>
<div class="topbar">
  <div><h1><span id="status"></span>FoundryGate</h1><div class="sub">Local AI Gateway Dashboard</div></div>
  <div><button class="refresh-btn" onclick="load()">&#x21bb; Refresh</button> <span id="ago" class="mono" style="color:#666"></span></div>
</div>

<div class="grid" id="cards"></div>

<div class="sect"><h2>Provider Breakdown</h2><table id="providers"><thead><tr>
  <th>Provider</th><th>Requests</th><th>Tokens</th><th>Cost</th><th>Cache%</th><th>Failures</th><th>Avg Latency</th><th>Share</th>
</tr></thead><tbody></tbody></table></div>

<div class="sect"><h2>Routing Rules</h2><table id="routing"><thead><tr>
  <th>Layer</th><th>Rule</th><th>Provider</th><th>Requests</th><th>Cost</th><th>Avg Latency</th>
</tr></thead><tbody></tbody></table></div>

<div class="sect"><h2>Recent Requests</h2><table id="recent"><thead><tr>
  <th>Time</th><th>Provider</th><th>Layer</th><th>Rule</th><th>Tokens</th><th>Cost</th><th>Latency</th><th>Status</th>
</tr></thead><tbody></tbody></table></div>

<script>
const $ = s => document.querySelector(s);
const fmt = (n,d=2) => n!=null ? n.toLocaleString('en',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
const fmtUsd = n => n!=null ? '$'+fmt(n,4) : '—';
const fmtTok = n => n!=null ? (n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':''+n) : '0';
const fmtMs = n => n!=null ? fmt(n,0)+'ms' : '—';
const ago = ts => {if(!ts)return '—';const s=Date.now()/1000-ts;return s<60?Math.round(s)+'s ago':s<3600?Math.round(s/60)+'m ago':Math.round(s/3600)+'h ago';};
const layerTag = l => '<span class="tag tag-'+l+'">'+l+'</span>';
const barClass = p => p.includes('reasoner')?'bar-r1':p.includes('flash-lite')?'bar-gl':p.includes('flash')?'bar-gf':p.includes('openrouter')?'bar-or':'bar-ds';

async function load(){
  try{
    const [stats,rec] = await Promise.all([
      fetch('/api/stats').then(r=>r.json()),
      fetch('/api/recent?limit=30').then(r=>r.json())
    ]);
    const t = stats.totals || {};
    $('#status').style.background='#5e5';
    $('#ago').textContent = ago(t.last_request);

    // Cards
    $('#cards').innerHTML = `
      <div class="card"><div class="label">Total Requests</div><div class="value">${fmtTok(t.total_requests)}</div></div>
      <div class="card"><div class="label">Total Cost</div><div class="value cost">${fmtUsd(t.total_cost_usd)}</div></div>
      <div class="card"><div class="label">Total Tokens</div><div class="value">${fmtTok((t.total_prompt_tokens||0)+(t.total_compl_tokens||0))}</div>
        <div class="detail">${fmtTok(t.total_prompt_tokens)} in / ${fmtTok(t.total_compl_tokens)} out</div></div>
      <div class="card"><div class="label">Avg Latency</div><div class="value">${fmtMs(t.avg_latency_ms)}</div></div>
      <div class="card"><div class="label">Cache Hit Rate</div><div class="value cost">${t.cache_hit_pct||0}%</div>
        <div class="detail">${fmtTok(t.total_cache_hit)} hit / ${fmtTok(t.total_cache_miss)} miss</div></div>
      <div class="card"><div class="label">Failures</div><div class="value ${t.total_failures>0?'err':''}">${t.total_failures||0}</div></div>
    `;

    // Provider table
    const maxReq = Math.max(...(stats.providers||[]).map(p=>p.requests),1);
    $('#providers tbody').innerHTML = (stats.providers||[]).map(p=>`<tr>
      <td><strong>${p.provider}</strong></td>
      <td>${p.requests}</td>
      <td class="mono">${fmtTok(p.total_tokens)}</td>
      <td class="mono">${fmtUsd(p.cost_usd)}</td>
      <td class="mono">${p.cache_hit_pct||0}%</td>
      <td>${p.failures||0}</td>
      <td class="mono">${fmtMs(p.avg_latency_ms)}</td>
      <td style="min-width:100px"><div class="bar-wrap"><div class="bar ${barClass(p.provider)}" style="width:${(p.requests/maxReq*100).toFixed(0)}%"></div></div></td>
    </tr>`).join('');

    // Routing table
    $('#routing tbody').innerHTML = (stats.routing||[]).map(r=>`<tr>
      <td>${layerTag(r.layer)}</td>
      <td class="mono">${r.rule_name}</td>
      <td>${r.provider}</td>
      <td>${r.requests}</td>
      <td class="mono">${fmtUsd(r.cost_usd)}</td>
      <td class="mono">${fmtMs(r.avg_latency_ms)}</td>
    </tr>`).join('');

    // Recent
    $('#recent tbody').innerHTML = (rec.requests||[]).map(r=>`<tr>
      <td class="mono">${ago(r.timestamp)}</td>
      <td>${r.provider}</td>
      <td>${layerTag(r.layer)}</td>
      <td class="mono">${r.rule_name}</td>
      <td class="mono">${fmtTok(r.prompt_tok+r.compl_tok)}</td>
      <td class="mono">${fmtUsd(r.cost_usd)}</td>
      <td class="mono">${fmtMs(r.latency_ms)}</td>
      <td>${r.success?'\\u2705':'\\u274c'}</td>
    </tr>`).join('');

  }catch(e){
    $('#status').style.background='#f66';
    console.error(e);
  }
}
load();
setInterval(load, 30000);
</script>
</body></html>"""
