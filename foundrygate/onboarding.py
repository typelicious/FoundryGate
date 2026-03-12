"""Onboarding reporting helpers for many-provider and many-client setups."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv

from .config import load_config


def _env_path(env_file: str | Path | None = None) -> Path:
    """Return the effective env file path."""
    if env_file is not None:
        return Path(env_file)
    return Path.cwd() / ".env"


def _is_unresolved_env(value: str) -> bool:
    """Return whether a config value still looks like an unresolved env placeholder."""
    stripped = value.strip()
    return stripped.startswith("${") and stripped.endswith("}")


def _provider_ready(provider: dict[str, Any]) -> tuple[bool, str]:
    """Return whether one provider looks ready for onboarding."""
    contract = provider.get("contract", "generic")
    backend = provider.get("backend", "openai-compat")
    api_key = str(provider.get("api_key", "") or "").strip()
    base_url = str(provider.get("base_url", "") or "").strip()
    if _is_unresolved_env(api_key):
        api_key = ""
    if _is_unresolved_env(base_url):
        base_url = ""

    if contract == "local-worker":
        if not base_url:
            return False, "missing base_url"
        return True, "local worker contract"

    if contract == "image-provider" and not base_url:
        return False, "missing base_url"

    if backend in {"openai-compat", "google-genai", "anthropic-compat"} and not api_key:
        return False, "missing api_key"

    return True, "configured"


def build_onboarding_report(
    *,
    config_path: str | Path | None = None,
    env_file: str | Path | None = None,
) -> dict[str, Any]:
    """Return a structured onboarding report for providers and clients."""
    resolved_env = _env_path(env_file)
    load_dotenv(resolved_env, override=True)
    config = load_config(config_path)
    env_values = dotenv_values(resolved_env) if resolved_env.exists() else {}

    providers = []
    ready = 0
    local_workers = 0
    image_capable = 0
    missing_api_keys = []

    for name, provider in sorted(config.providers.items()):
        is_ready, readiness_reason = _provider_ready(provider)
        if is_ready:
            ready += 1
        if provider.get("contract") == "local-worker":
            local_workers += 1
        capabilities = provider.get("capabilities") or {}
        if capabilities.get("image_generation") or capabilities.get("image_editing"):
            image_capable += 1
        if readiness_reason == "missing api_key":
            missing_api_keys.append(name)
        providers.append(
            {
                "name": name,
                "backend": provider.get("backend", "openai-compat"),
                "contract": provider.get("contract", "generic"),
                "model": provider.get("model", ""),
                "tier": provider.get("tier", ""),
                "ready": is_ready,
                "readiness_reason": readiness_reason,
                "capabilities": capabilities,
            }
        )

    client_profiles = config.client_profiles
    routing_policies = config.routing_policies
    request_hooks = config.request_hooks
    update_check = config.update_check
    auto_update = config.auto_update

    suggestions = []
    if not providers:
        suggestions.append("Add one provider before onboarding clients.")
    if providers and ready == 0:
        suggestions.append(
            "Configure at least one ready provider with a real key or local worker URL."
        )
    if not client_profiles.get("enabled"):
        suggestions.append("Enable client_profiles when multiple clients share one gateway.")
    if not client_profiles.get("presets"):
        suggestions.append("Start with client_profiles.presets for openclaw, n8n, or cli.")
    if len(config.fallback_chain) == 0:
        suggestions.append("Set a fallback_chain before onboarding multiple clients.")
    if update_check.get("enabled") and not auto_update.get("enabled"):
        suggestions.append("Keep auto_update disabled until the provider and client set is stable.")

    return {
        "config_path": str(Path(config_path) if config_path else Path.cwd() / "config.yaml"),
        "env_file": str(resolved_env),
        "env": {
            "exists": resolved_env.exists(),
            "provider_keys_present": sorted(key for key, value in env_values.items() if value),
        },
        "providers": {
            "total": len(providers),
            "ready": ready,
            "not_ready": len(providers) - ready,
            "local_workers": local_workers,
            "image_capable": image_capable,
            "missing_api_keys": missing_api_keys,
            "items": providers,
        },
        "clients": {
            "profiles_enabled": bool(client_profiles.get("enabled")),
            "default_profile": client_profiles.get("default", "generic"),
            "presets": list(client_profiles.get("presets", [])),
            "profile_count": len(client_profiles.get("profiles", {})),
            "rule_count": len(client_profiles.get("rules", [])),
        },
        "routing": {
            "fallback_chain": list(config.fallback_chain),
            "policy_layer_enabled": bool(routing_policies.get("enabled")),
            "policy_rule_count": len(routing_policies.get("rules", [])),
            "request_hooks_enabled": bool(request_hooks.get("enabled")),
            "request_hook_count": len(request_hooks.get("hooks", [])),
        },
        "operations": {
            "update_checks_enabled": bool(update_check.get("enabled")),
            "auto_update_enabled": bool(auto_update.get("enabled")),
            "rollout_ring": auto_update.get("rollout_ring", "early"),
        },
        "suggestions": suggestions,
    }


def build_onboarding_validation(report: dict[str, Any]) -> dict[str, Any]:
    """Return onboarding blockers and warnings for one report."""
    providers = report["providers"]
    clients = report["clients"]
    routing = report["routing"]
    env = report["env"]

    blockers: list[str] = []
    warnings: list[str] = []

    if not env.get("exists", False):
        blockers.append("Environment file is missing.")
    if providers["total"] == 0:
        blockers.append("No providers are configured.")
    elif providers["ready"] == 0:
        blockers.append("No configured provider is ready.")

    if providers["total"] > 1 and not routing["fallback_chain"]:
        blockers.append("Fallback chain is empty for a multi-provider setup.")

    if providers["not_ready"] > 0:
        warnings.append(
            f"{providers['not_ready']} provider(s) are not ready: "
            + ", ".join(item["name"] for item in providers["items"] if not item["ready"])
        )

    if not clients["profiles_enabled"]:
        warnings.append("Client profiles are disabled.")
    if clients["profiles_enabled"] and not clients["presets"]:
        warnings.append("No built-in client presets are enabled.")
    if routing["request_hooks_enabled"] and routing["request_hook_count"] == 0:
        warnings.append("Request hooks are enabled but no hooks are configured.")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }


def render_onboarding_report(report: dict[str, Any]) -> str:
    """Render the onboarding report as plain text."""
    provider_block = report["providers"]
    client_block = report["clients"]
    routing_block = report["routing"]
    ops_block = report["operations"]
    preset_text = ", ".join(client_block["presets"]) if client_block["presets"] else "none"
    fallback_text = (
        ", ".join(routing_block["fallback_chain"]) if routing_block["fallback_chain"] else "none"
    )

    lines = [
        "FoundryGate onboarding report",
        "",
        f"Config: {report['config_path']}",
        f"Env   : {report['env_file']}",
        "",
        "Providers",
        f"- total: {provider_block['total']}",
        f"- ready: {provider_block['ready']}",
        f"- not ready: {provider_block['not_ready']}",
        f"- local workers: {provider_block['local_workers']}",
        f"- image-capable: {provider_block['image_capable']}",
    ]
    if provider_block["missing_api_keys"]:
        lines.append(f"- missing api_key: {', '.join(provider_block['missing_api_keys'])}")

    if provider_block["items"]:
        lines.append("")
        lines.append("Provider inventory")
        for item in provider_block["items"]:
            readiness = "ready" if item["ready"] else f"not ready ({item['readiness_reason']})"
            lines.append(
                f"- {item['name']}: {item['contract']} / {item['backend']} / "
                f"{item['tier'] or 'default'} / {readiness}"
            )

    lines.extend(
        [
            "",
            "Clients",
            f"- profiles enabled: {client_block['profiles_enabled']}",
            f"- default profile: {client_block['default_profile']}",
            f"- presets: {preset_text}",
            f"- profiles: {client_block['profile_count']}",
            f"- rules: {client_block['rule_count']}",
            "",
            "Routing",
            f"- fallback chain: {fallback_text}",
            f"- policy layer: {routing_block['policy_layer_enabled']} "
            f"({routing_block['policy_rule_count']} rules)",
            f"- request hooks: {routing_block['request_hooks_enabled']} "
            f"({routing_block['request_hook_count']} hooks)",
            "",
            "Operations",
            f"- update checks: {ops_block['update_checks_enabled']}",
            f"- auto update: {ops_block['auto_update_enabled']}",
            f"- rollout ring: {ops_block['rollout_ring']}",
        ]
    )

    if report["suggestions"]:
        lines.extend(["", "Suggestions"])
        lines.extend(f"- {item}" for item in report["suggestions"])

    return "\n".join(lines) + "\n"


def render_onboarding_validation(validation: dict[str, Any]) -> str:
    """Render onboarding validation results as plain text."""
    lines = [
        "FoundryGate onboarding validation",
        "",
        f"Status: {'ok' if validation['ok'] else 'blocked'}",
    ]
    if validation["blockers"]:
        lines.extend(["", "Blockers"])
        lines.extend(f"- {item}" for item in validation["blockers"])
    if validation["warnings"]:
        lines.extend(["", "Warnings"])
        lines.extend(f"- {item}" for item in validation["warnings"])
    return "\n".join(lines) + "\n"
