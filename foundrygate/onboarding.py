"""Onboarding reporting helpers for many-provider and many-client setups."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values, load_dotenv

from .config import load_config
from .provider_catalog import build_provider_catalog_report


def _env_path(env_file: str | Path | None = None) -> Path:
    """Return the effective env file path."""
    if env_file is not None:
        return Path(env_file)
    return Path.cwd() / ".env"


def _is_unresolved_env(value: str) -> bool:
    """Return whether a config value still looks like an unresolved env placeholder."""
    stripped = value.strip()
    return stripped.startswith("${") and stripped.endswith("}")


def collect_provider_env_requirements(
    *,
    config_path: str | Path | None = None,
    env_file: str | Path | None = None,
) -> dict[str, list[str]]:
    """Return which provider env variables are configured and which are missing."""
    resolved_config = Path(config_path) if config_path else Path.cwd() / "config.yaml"
    resolved_env = _env_path(env_file)
    env_values = dotenv_values(resolved_env) if resolved_env.exists() else {}

    with resolved_config.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    required: set[str] = set()
    for provider in (raw.get("providers") or {}).values():
        if not isinstance(provider, dict):
            continue
        for field in ("api_key", "base_url"):
            value = provider.get(field, "")
            if isinstance(value, str) and _is_unresolved_env(value):
                required.add(value.strip()[2:-1].split(":-", 1)[0])

    present = sorted(name for name in required if env_values.get(name))
    missing = sorted(name for name in required if not env_values.get(name))
    return {"required": sorted(required), "present": present, "missing": missing}


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


def _build_provider_rollout(
    providers: list[dict[str, Any]],
    fallback_chain: list[str],
) -> dict[str, Any]:
    """Return a staged rollout view for many-provider setups."""
    primary_stage: list[str] = []
    secondary_stage: list[str] = []
    modality_stage: list[str] = []

    provider_index = {provider["name"]: provider for provider in providers}
    fallback_status: list[dict[str, Any]] = []

    for provider in providers:
        if not provider["ready"]:
            continue

        capabilities = provider.get("capabilities") or {}
        is_image_capable = capabilities.get("image_generation") or capabilities.get("image_editing")
        if provider.get("contract") == "image-provider" or is_image_capable:
            modality_stage.append(provider["name"])
            continue

        if provider.get("tier") in {"local", "default"}:
            primary_stage.append(provider["name"])
        else:
            secondary_stage.append(provider["name"])

    ready_fallback_targets = 0
    for name in fallback_chain:
        provider = provider_index.get(name)
        is_ready = bool(provider and provider["ready"])
        if is_ready:
            ready_fallback_targets += 1
        fallback_status.append(
            {
                "name": name,
                "configured": provider is not None,
                "ready": is_ready,
            }
        )

    gaps: list[str] = []
    if providers and not primary_stage:
        gaps.append("No ready primary provider is available for the first rollout stage.")
    if len(providers) > 1 and fallback_chain and ready_fallback_targets == 0:
        gaps.append("Fallback chain is configured, but none of its targets are currently ready.")
    if (
        any(
            (provider.get("capabilities") or {}).get("image_generation")
            or (provider.get("capabilities") or {}).get("image_editing")
            for provider in providers
        )
        and not modality_stage
    ):
        gaps.append("Image-capable providers are configured, but none are ready yet.")

    return {
        "stage_1_primary": primary_stage,
        "stage_2_secondary": secondary_stage,
        "stage_3_modality": modality_stage,
        "fallback_targets": fallback_status,
        "gaps": gaps,
    }


def _describe_client_match(match: dict[str, Any]) -> str:
    """Return a compact text summary for one client-profile match rule."""
    parts: list[str] = []
    if match.get("header_present"):
        parts.append("headers present: " + ", ".join(match["header_present"]))
    if match.get("header_contains"):
        header_parts = [
            f"{header}~{', '.join(values)}"
            for header, values in sorted(match["header_contains"].items())
        ]
        parts.append("header contains: " + "; ".join(header_parts))
    if match.get("any"):
        any_parts = []
        for item in match["any"]:
            summary = _describe_client_match(item)
            if summary:
                any_parts.append(summary)
        if any_parts:
            parts.append("any(" + " | ".join(any_parts) + ")")
    if match.get("all"):
        all_parts = []
        for item in match["all"]:
            summary = _describe_client_match(item)
            if summary:
                all_parts.append(summary)
        if all_parts:
            parts.append("all(" + " & ".join(all_parts) + ")")
    return "; ".join(parts)


def _summarize_profile_hints(profile: dict[str, Any]) -> list[str]:
    """Return compact routing-intent text for one client profile."""
    hints: list[str] = []
    if profile.get("routing_mode"):
        hints.append("routing mode: " + str(profile["routing_mode"]))
    if profile.get("prefer_tiers"):
        hints.append("prefer tiers: " + ", ".join(profile["prefer_tiers"]))
    if profile.get("prefer_providers"):
        hints.append("prefer providers: " + ", ".join(profile["prefer_providers"]))
    if profile.get("allow_providers"):
        hints.append("allow providers: " + ", ".join(profile["allow_providers"]))
    if profile.get("deny_providers"):
        hints.append("deny providers: " + ", ".join(profile["deny_providers"]))
    if profile.get("require_capabilities"):
        hints.append("require caps: " + ", ".join(profile["require_capabilities"]))
    if profile.get("capability_values"):
        value_parts = []
        for name, value in sorted(profile["capability_values"].items()):
            rendered = value
            if isinstance(value, list) and len(value) == 1:
                rendered = value[0]
            value_parts.append(f"{name}={rendered}")
        hints.append("capability values: " + ", ".join(value_parts))
    return hints or ["no extra routing hints"]


def _build_client_matrix(client_profiles: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a report-friendly matrix of client profiles and match rules."""
    presets = set(client_profiles.get("presets", []))
    rules_by_profile = {rule["profile"]: rule["match"] for rule in client_profiles.get("rules", [])}

    matrix = []
    for name, profile in sorted(client_profiles.get("profiles", {}).items()):
        match = rules_by_profile.get(name)
        matrix.append(
            {
                "name": name,
                "source": "preset" if name in presets else "custom",
                "default": name == client_profiles.get("default", "generic"),
                "matched_by": (
                    _describe_client_match(match) if match else "default or explicit override"
                ),
                "routing_intent": _summarize_profile_hints(profile),
                "has_rule": match is not None,
            }
        )
    return matrix


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
    provider_rollout = _build_provider_rollout(providers, list(config.fallback_chain))
    client_matrix = _build_client_matrix(client_profiles)
    provider_catalog = build_provider_catalog_report(config)
    env_requirements = collect_provider_env_requirements(
        config_path=config_path,
        env_file=resolved_env,
    )

    enabled_presets = set(client_profiles.get("presets", []))
    profile_names = set(client_profiles.get("profiles", {}).keys())
    integration_examples = {
        "openclaw": {
            "recommended": "openclaw" in enabled_presets or "openclaw" in profile_names,
            "header": "x-openclaw-source: planner",
            "profile": "openclaw",
            "snippet": [
                '"baseUrl": "http://127.0.0.1:8090/v1"',
                '"primary": "foundrygate/auto"',
            ],
            "notes": [
                "Keep one-agent and many-agent traffic on the same OpenAI-compatible base URL.",
                "Use x-openclaw-source when you want sub-agent traffic to resolve differently.",
            ],
        },
        "ai-native-app": {
            "recommended": any(
                name not in {"generic", "openclaw", "n8n", "cli", "local-only"}
                for name in profile_names
            ),
            "header": "X-FoundryGate-Client: your-app",
            "profile": "custom app profile",
            "snippet": [
                "client_profiles.rules -> match on X-FoundryGate-Client",
                "client_profiles.profiles -> define app-specific prefer_tiers or locality",
            ],
            "notes": [
                "Start with one stable client header before adding more than one app profile.",
                "Keep app-private traffic on a dedicated profile instead of ad hoc hooks.",
            ],
        },
        "n8n": {
            "recommended": "n8n" in enabled_presets or "n8n" in profile_names,
            "header": "X-FoundryGate-Client: n8n",
            "profile": "n8n",
            "snippet": [
                "Base URL: http://127.0.0.1:8090/v1",
                "Model: auto",
            ],
            "notes": [
                "Start workflow traffic with the n8n preset before adding custom policy rules.",
                "Use route dry-runs to confirm cheaper or local-first defaults before"
                " production runs.",
            ],
        },
        "cli": {
            "recommended": "cli" in enabled_presets or "cli" in profile_names,
            "header": "X-FoundryGate-Client: codex",
            "profile": "cli",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Use a stable client tag such as codex, claude, or kilocode to keep"
                " traces readable.",
                "Only add hook-based locality or provider overrides when one CLI flow"
                " truly needs them.",
            ],
        },
        "swe-af": {
            "recommended": "swe-af" in profile_names,
            "header": "X-FoundryGate-Client: swe-af",
            "profile": "swe-af",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Treat SWE-AF like another OpenAI-compatible agent client first, not a"
                " special runtime.",
                "Keep a stable client header so coding and delegated subflows remain"
                " attributable in traces.",
            ],
        },
        "paperclip": {
            "recommended": "paperclip" in profile_names,
            "header": "X-FoundryGate-Client: paperclip",
            "profile": "paperclip",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Start with the common OpenAI-compatible path before inventing a deeper adapter.",
                "Use client profiles only when paperclip traffic should differ from"
                " other app traffic.",
            ],
        },
        "ship-faster": {
            "recommended": "ship-faster" in profile_names,
            "header": "X-FoundryGate-Client: ship-faster",
            "profile": "ship-faster",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Use one short client tag first; add more profile splits only when the"
                " workflow actually needs them.",
                "Prefer hook-based overrides only for narrow rollout or locality constraints.",
            ],
        },
        "langchain": {
            "recommended": "langchain" in profile_names,
            "header": "X-FoundryGate-Client: langchain",
            "profile": "langchain",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "LangChain should stay on the OpenAI-compatible path unless a"
                " framework-specific blocker appears.",
                "Use route previews before splitting chain traffic into multiple custom profiles.",
            ],
        },
        "langgraph": {
            "recommended": "langgraph" in profile_names,
            "header": "X-FoundryGate-Client: langgraph",
            "profile": "langgraph",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Keep LangGraph on the shared gateway path and use client tags to"
                " distinguish graph traffic from generic LangChain traffic.",
                "Only add dedicated policies when graph workloads need stricter"
                " locality or cost boundaries.",
            ],
        },
        "agno": {
            "recommended": "agno" in profile_names,
            "header": "X-FoundryGate-Client: agno",
            "profile": "agno",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Keep Agno on the shared OpenAI-compatible path first.",
                (
                    "Split profiles only when one agent family needs different cost "
                    "or locality defaults."
                ),
            ],
        },
        "semantic-kernel": {
            "recommended": "semantic-kernel" in profile_names,
            "header": "X-FoundryGate-Client: semantic-kernel",
            "profile": "semantic-kernel",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                (
                    "Use one stable client tag for kernel traffic before adding "
                    "skill-specific routing."
                ),
                "Validate tool-heavy paths with route previews before adding custom hook hints.",
            ],
        },
        "haystack": {
            "recommended": "haystack" in profile_names,
            "header": "X-FoundryGate-Client: haystack",
            "profile": "haystack",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                (
                    "Treat Haystack as another OpenAI-compatible client unless a "
                    "pipeline-specific gap appears."
                ),
                (
                    "Keep retrieval and generation traffic together until a real "
                    "routing split is needed."
                ),
            ],
        },
        "mastra": {
            "recommended": "mastra" in profile_names,
            "header": "X-FoundryGate-Client: mastra",
            "profile": "mastra",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Keep Mastra on one shared gateway path first.",
                (
                    "Only add dedicated policies when workflow classes need stronger "
                    "provider separation."
                ),
            ],
        },
        "google-adk": {
            "recommended": "google-adk" in profile_names,
            "header": "X-FoundryGate-Client: google-adk",
            "profile": "google-adk",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Keep Google ADK traffic on the common gateway path for provider consistency.",
                (
                    "Use a dedicated profile only when ADK workloads need different "
                    "fallback or locality rules."
                ),
            ],
        },
        "autogen": {
            "recommended": "autogen" in profile_names,
            "header": "X-FoundryGate-Client: autogen",
            "profile": "autogen",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Keep AutoGen on the shared OpenAI-compatible path first.",
                (
                    "Split assistant families into separate profiles only when traces "
                    "show a real locality or cost split."
                ),
            ],
        },
        "llamaindex": {
            "recommended": "llamaindex" in profile_names,
            "header": "X-FoundryGate-Client: llamaindex",
            "profile": "llamaindex",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Keep retrieval and generation on one gateway surface to start with.",
                (
                    "Add dedicated routing only when one index or workflow class needs "
                    "different provider behavior."
                ),
            ],
        },
        "crewai": {
            "recommended": "crewai" in profile_names,
            "header": "X-FoundryGate-Client: crewai",
            "profile": "crewai",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Use one stable client tag for CrewAI orchestration before splitting roles.",
                (
                    "Only add profile-specific routing when crew classes need distinct "
                    "fallback, locality, or cost constraints."
                ),
            ],
        },
        "pydanticai": {
            "recommended": "pydanticai" in profile_names,
            "header": "X-FoundryGate-Client: pydanticai",
            "profile": "pydanticai",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                (
                    "Keep PydanticAI on the common OpenAI-compatible path unless a "
                    "model API gap appears."
                ),
                (
                    "Use client profiles only when tool or validation-heavy traffic "
                    "deserves a different provider set."
                ),
            ],
        },
        "camel": {
            "recommended": "camel" in profile_names,
            "header": "X-FoundryGate-Client: camel",
            "profile": "camel",
            "snippet": [
                "export OPENAI_BASE_URL=http://127.0.0.1:8090/v1",
                "export OPENAI_API_KEY=local",
            ],
            "notes": [
                "Start CAMEL traffic on the shared gateway path and keep one stable client tag.",
                (
                    "Only add narrower policies when multi-agent workloads need stronger "
                    "provider isolation."
                ),
            ],
        },
    }

    return {
        "config_path": str(Path(config_path) if config_path else Path.cwd() / "config.yaml"),
        "env_file": str(resolved_env),
        "env": {
            "exists": resolved_env.exists(),
            "provider_keys_present": sorted(key for key, value in env_values.items() if value),
            "provider_requirements": env_requirements,
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
            "matrix": client_matrix,
        },
        "routing": {
            "fallback_chain": list(config.fallback_chain),
            "policy_layer_enabled": bool(routing_policies.get("enabled")),
            "policy_rule_count": len(routing_policies.get("rules", [])),
            "request_hooks_enabled": bool(request_hooks.get("enabled")),
            "request_hook_count": len(request_hooks.get("hooks", [])),
        },
        "provider_rollout": provider_rollout,
        "provider_catalog": provider_catalog,
        "operations": {
            "update_checks_enabled": bool(update_check.get("enabled")),
            "auto_update_enabled": bool(auto_update.get("enabled")),
            "rollout_ring": auto_update.get("rollout_ring", "early"),
        },
        "integrations": integration_examples,
        "suggestions": suggestions,
    }


def build_onboarding_validation(report: dict[str, Any]) -> dict[str, Any]:
    """Return onboarding blockers and warnings for one report."""
    providers = report["providers"]
    clients = report["clients"]
    routing = report["routing"]
    provider_rollout = report["provider_rollout"]
    provider_catalog = report["provider_catalog"]
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
    if providers["total"] > 1 and not provider_rollout["stage_1_primary"]:
        blockers.append(
            "No ready primary provider is available for a staged multi-provider rollout."
        )

    if providers["not_ready"] > 0:
        warnings.append(
            f"{providers['not_ready']} provider(s) are not ready: "
            + ", ".join(item["name"] for item in providers["items"] if not item["ready"])
        )
    warnings.extend(provider_rollout["gaps"])
    for alert in provider_catalog.get("alerts", []):
        warnings.append(alert["message"])

    if not clients["profiles_enabled"]:
        warnings.append("Client profiles are disabled.")
    if clients["profiles_enabled"] and not clients["presets"]:
        warnings.append("No built-in client presets are enabled.")
    if clients["profiles_enabled"] and clients["profile_count"] > 1 and clients["rule_count"] == 0:
        warnings.append("Multiple client profiles are configured, but no client match rules exist.")
    for row in clients.get("matrix", []):
        if row["name"] != clients["default_profile"] and not row["has_rule"]:
            warnings.append(
                f"Client profile '{row['name']}' has no match rule and only applies"
                " via explicit override."
            )
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
    rollout_block = report["provider_rollout"]
    catalog_block = report["provider_catalog"]
    ops_block = report["operations"]
    integration_block = report["integrations"]
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
        ]
    )

    if client_block["matrix"]:
        lines.extend(["", "Client matrix"])
        for row in client_block["matrix"]:
            default_text = " [default]" if row["default"] else ""
            lines.append(f"- {row['name']}{default_text}: {row['source']}")
            lines.append(f"  match: {row['matched_by']}")
            lines.append(f"  intent: {'; '.join(row['routing_intent'])}")

    lines.extend(
        [
            "",
            "Routing",
            f"- fallback chain: {fallback_text}",
            f"- policy layer: {routing_block['policy_layer_enabled']} "
            f"({routing_block['policy_rule_count']} rules)",
            f"- request hooks: {routing_block['request_hooks_enabled']} "
            f"({routing_block['request_hook_count']} hooks)",
            "",
            "Provider rollout",
            "- stage 1 primary: " + (", ".join(rollout_block["stage_1_primary"]) or "none"),
            "- stage 2 secondary: " + (", ".join(rollout_block["stage_2_secondary"]) or "none"),
            "- stage 3 modality: " + (", ".join(rollout_block["stage_3_modality"]) or "none"),
            "",
            "Provider catalog",
            f"- tracked providers: {catalog_block['tracked_providers']} / "
            f"{catalog_block['total_providers']}",
            f"- alerts: {catalog_block['alert_count']}",
            "",
            "Operations",
            f"- update checks: {ops_block['update_checks_enabled']}",
            f"- auto update: {ops_block['auto_update_enabled']}",
            f"- rollout ring: {ops_block['rollout_ring']}",
        ]
    )

    if rollout_block["fallback_targets"]:
        lines.append("- fallback targets:")
        for item in rollout_block["fallback_targets"]:
            readiness = "ready" if item["ready"] else "not ready"
            lines.append(f"  - {item['name']}: {readiness}")
    tracked_items = [item for item in catalog_block.get("items", []) if item.get("tracked")]
    if tracked_items:
        lines.append("- catalog inventory:")
        for item in tracked_items:
            lines.append(
                "  - "
                + f"{item['provider']}: {item['provider_type']} / {item['offer_track']} / "
                + f"{item['evidence_level']} / {item['volatility']}"
            )
    discovery_items = [
        item for item in tracked_items if (item.get("discovery") or {}).get("resolved_url")
    ]
    if discovery_items:
        policy = catalog_block.get("recommendation_policy", {})
        lines.append("- provider discovery:")
        lines.append(
            "  - "
            + "policy: payout affects ranking = "
            + f"{policy.get('affiliate_payout_affects_ranking', False)}"
        )
        for item in discovery_items:
            discovery = item["discovery"]
            label = "disclosed link" if discovery.get("disclosure_required") else "official link"
            lines.append("  - " + f"{item['provider']}: {label} -> {discovery['resolved_url']}")
    if catalog_block["alerts"]:
        lines.append("- catalog alerts:")
        for alert in catalog_block["alerts"]:
            lines.append(f"  - {alert['provider']}: {alert['message']}")

    lines.extend(["", "Integration quickstarts"])
    for client_name, data in integration_block.items():
        readiness = "ready" if data["recommended"] else "needs preset or custom profile"
        lines.append(f"- {client_name}: {readiness}")
        lines.append(f"  header: {data['header']}")
        lines.append(f"  profile: {data['profile']}")
        for snippet_line in data["snippet"]:
            lines.append(f"  example: {snippet_line}")

    if report["suggestions"]:
        lines.extend(["", "Suggestions"])
        lines.extend(f"- {item}" for item in report["suggestions"])

    return "\n".join(lines) + "\n"


def render_onboarding_report_markdown(report: dict[str, Any]) -> str:
    """Render the onboarding report as Markdown."""
    provider_block = report["providers"]
    client_block = report["clients"]
    routing_block = report["routing"]
    rollout_block = report["provider_rollout"]
    catalog_block = report["provider_catalog"]
    ops_block = report["operations"]
    integration_block = report["integrations"]
    env_block = report["env"]

    lines = [
        "# FoundryGate Onboarding Report",
        "",
        f"- Config: `{report['config_path']}`",
        f"- Env: `{report['env_file']}`",
        "",
        "## Providers",
        f"- Total: {provider_block['total']}",
        f"- Ready: {provider_block['ready']}",
        f"- Not ready: {provider_block['not_ready']}",
        f"- Local workers: {provider_block['local_workers']}",
        f"- Image-capable: {provider_block['image_capable']}",
    ]

    env_requirements = env_block.get("provider_requirements", {})
    if env_requirements.get("missing"):
        lines.append(
            "- Missing provider env: "
            + ", ".join(f"`{item}`" for item in env_requirements["missing"])
        )

    if provider_block["items"]:
        lines.extend(["", "### Provider Inventory"])
        for item in provider_block["items"]:
            readiness = "ready" if item["ready"] else f"not ready ({item['readiness_reason']})"
            lines.append(
                f"- `{item['name']}`: {item['contract']} / {item['backend']} / "
                f"{item['tier'] or 'default'} / {readiness}"
            )

    lines.extend(
        [
            "",
            "## Clients",
            f"- Profiles enabled: {client_block['profiles_enabled']}",
            f"- Default profile: `{client_block['default_profile']}`",
            "- Presets: " + (", ".join(f"`{item}`" for item in client_block["presets"]) or "none"),
            f"- Profiles: {client_block['profile_count']}",
            f"- Rules: {client_block['rule_count']}",
        ]
    )

    if client_block["matrix"]:
        lines.extend(["", "### Client Matrix"])
        for row in client_block["matrix"]:
            default_text = " (default)" if row["default"] else ""
            lines.append(f"- `{row['name']}`{default_text}: {row['source']}")
            lines.append(f"  - Match: {row['matched_by']}")
            lines.append(f"  - Intent: {'; '.join(row['routing_intent'])}")

    lines.extend(
        [
            "",
            "## Routing",
            "- Fallback chain: "
            + (", ".join(f"`{item}`" for item in routing_block["fallback_chain"]) or "none"),
            f"- Policy layer: {routing_block['policy_layer_enabled']} "
            f"({routing_block['policy_rule_count']} rules)",
            f"- Request hooks: {routing_block['request_hooks_enabled']} "
            f"({routing_block['request_hook_count']} hooks)",
            "",
            "## Provider Rollout",
            "- Stage 1 primary: "
            + (", ".join(f"`{item}`" for item in rollout_block["stage_1_primary"]) or "none"),
            "- Stage 2 secondary: "
            + (", ".join(f"`{item}`" for item in rollout_block["stage_2_secondary"]) or "none"),
            "- Stage 3 modality: "
            + (", ".join(f"`{item}`" for item in rollout_block["stage_3_modality"]) or "none"),
            "",
            "## Provider Catalog",
            f"- Tracked providers: {catalog_block['tracked_providers']} / "
            f"{catalog_block['total_providers']}",
            f"- Alerts: {catalog_block['alert_count']}",
        ]
    )

    if rollout_block["fallback_targets"]:
        lines.append("- Fallback targets:")
        for item in rollout_block["fallback_targets"]:
            readiness = "ready" if item["ready"] else "not ready"
            lines.append(f"  - `{item['name']}`: {readiness}")
    tracked_items = [item for item in catalog_block.get("items", []) if item.get("tracked")]
    if tracked_items:
        lines.append("- Catalog inventory:")
        for item in tracked_items:
            lines.append(
                "  - "
                + f"`{item['provider']}`: {item['provider_type']} / {item['offer_track']} / "
                + f"{item['evidence_level']} / {item['volatility']}"
            )
    discovery_items = [
        item for item in tracked_items if (item.get("discovery") or {}).get("resolved_url")
    ]
    if discovery_items:
        policy = catalog_block.get("recommendation_policy", {})
        lines.append("- Provider discovery:")
        lines.append(
            "  - Policy: payout affects ranking = "
            + f"`{policy.get('affiliate_payout_affects_ranking', False)}`"
        )
        for item in discovery_items:
            discovery = item["discovery"]
            label = "disclosed link" if discovery.get("disclosure_required") else "official link"
            lines.append("  - " + f"`{item['provider']}`: {label} -> `{discovery['resolved_url']}`")
    if catalog_block["alerts"]:
        lines.append("- Catalog alerts:")
        for alert in catalog_block["alerts"]:
            lines.append(f"  - `{alert['provider']}`: {alert['message']}")

    lines.extend(
        [
            "",
            "## Operations",
            f"- Update checks: {ops_block['update_checks_enabled']}",
            f"- Auto update: {ops_block['auto_update_enabled']}",
            f"- Rollout ring: `{ops_block['rollout_ring']}`",
            "",
            "## Integration Quickstarts",
        ]
    )

    for client_name, data in integration_block.items():
        readiness = "ready" if data["recommended"] else "needs preset or custom profile"
        lines.append(f"- `{client_name}`: {readiness}")
        lines.append(f"  - Header: `{data['header']}`")
        lines.append(f"  - Profile: `{data['profile']}`")
        for snippet_line in data["snippet"]:
            lines.append(f"  - Example: `{snippet_line}`")

    if report["suggestions"]:
        lines.extend(["", "## Suggestions"])
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
