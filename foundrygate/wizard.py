"""Initial configuration wizard helpers for local FoundryGate installs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

ProviderFactory = dict[str, Any]


_PURPOSES = {"general", "coding", "quality", "free"}


_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "deepseek-chat": {
        "env": "DEEPSEEK_API_KEY",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-chat",
            "max_tokens": 8000,
            "tier": "default",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "streaming": True,
                "cost_tier": "standard",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "DeepSeek Chat",
            "aliases": ["chat", "ds"],
        },
    },
    "deepseek-reasoner": {
        "env": "DEEPSEEK_API_KEY",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}",
            "api_key": "${DEEPSEEK_API_KEY}",
            "model": "deepseek-reasoner",
            "max_tokens": 8000,
            "tier": "reasoning",
            "timeout": {"connect_s": 10, "read_s": 120},
            "capabilities": {
                "reasoning": True,
                "streaming": True,
                "cost_tier": "standard",
                "latency_tier": "balanced",
            },
        },
        "shortcut": {
            "description": "DeepSeek reasoning path",
            "aliases": ["reasoner", "r1", "think"],
        },
    },
    "gemini-flash-lite": {
        "env": "GEMINI_API_KEY",
        "provider": {
            "backend": "google-genai",
            "base_url": "${GEMINI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta}",
            "api_key": "${GEMINI_API_KEY}",
            "model": "gemini-2.5-flash-lite",
            "max_tokens": 8000,
            "tier": "cheap",
            "timeout": {"connect_s": 10, "read_s": 45},
            "capabilities": {
                "cost_tier": "cheap",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "Gemini Flash-Lite",
            "aliases": ["lite", "flash-lite"],
        },
    },
    "gemini-flash": {
        "env": "GEMINI_API_KEY",
        "provider": {
            "backend": "google-genai",
            "base_url": "${GEMINI_BASE_URL:-https://generativelanguage.googleapis.com/v1beta}",
            "api_key": "${GEMINI_API_KEY}",
            "model": "gemini-2.5-flash",
            "max_tokens": 8000,
            "tier": "mid",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "cheap",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "Gemini Flash",
            "aliases": ["flash", "gemini"],
        },
    },
    "openrouter-fallback": {
        "env": "OPENROUTER_API_KEY",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}",
            "api_key": "${OPENROUTER_API_KEY}",
            "model": "openrouter/auto",
            "max_tokens": 8000,
            "tier": "fallback",
            "timeout": {"connect_s": 10, "read_s": 90},
            "capabilities": {
                "streaming": True,
                "cost_tier": "marketplace",
                "latency_tier": "balanced",
            },
        },
    },
    "kilocode": {
        "env": "KILOCODE_API_KEY",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${KILOCODE_BASE_URL:-https://api.kilo.ai/api/gateway/v1}",
            "api_key": "${KILOCODE_API_KEY}",
            "model": "z-ai/glm-5:free",
            "max_tokens": 8000,
            "tier": "fallback",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "free",
                "latency_tier": "balanced",
            },
        },
        "shortcut": {
            "description": "Kilo free-tier gateway path",
            "aliases": ["kilo", "glm5"],
        },
    },
    "blackbox-free": {
        "env": "BLACKBOX_API_KEY",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${BLACKBOX_BASE_URL:-https://api.blackbox.ai}",
            "api_key": "${BLACKBOX_API_KEY}",
            "model": "blackboxai/x-ai/grok-code-fast-1:free",
            "max_tokens": 8000,
            "tier": "fallback",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "free",
                "latency_tier": "fast",
            },
        },
        "shortcut": {
            "description": "BLACKBOX free-tier route",
            "aliases": ["blackbox", "bb"],
        },
    },
    "openai-gpt4o": {
        "env": "OPENAI_API_KEY",
        "provider": {
            "backend": "openai-compat",
            "base_url": "${OPENAI_BASE_URL:-https://api.openai.com/v1}",
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4o",
            "max_tokens": 8192,
            "tier": "mid",
            "timeout": {"connect_s": 10, "read_s": 60},
            "capabilities": {
                "cost_tier": "premium",
                "latency_tier": "balanced",
            },
        },
        "shortcut": {
            "description": "OpenAI GPT-4o",
            "aliases": ["gpt4o", "gpt-4o"],
        },
    },
    "openai-images": {
        "env": "OPENAI_API_KEY",
        "provider": {
            "contract": "image-provider",
            "backend": "openai-compat",
            "base_url": "${OPENAI_BASE_URL:-https://api.openai.com/v1}",
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-image-1",
            "tier": "specialty",
            "capabilities": {
                "image_editing": True,
                "cost_tier": "premium",
            },
            "image": {
                "max_outputs": 4,
                "max_side_px": 2048,
                "supported_sizes": ["1024x1024", "1536x1024", "1024x1536"],
                "policy_tags": ["quality", "editing", "batch"],
            },
        },
        "shortcut": {
            "description": "OpenAI image generation and editing",
            "aliases": ["img", "image", "gpt-image"],
        },
    },
    "anthropic-claude": {
        "env": "ANTHROPIC_API_KEY",
        "provider": {
            "backend": "anthropic-compat",
            "base_url": "${ANTHROPIC_BASE_URL:-https://api.anthropic.com/v1}",
            "api_key": "${ANTHROPIC_API_KEY}",
            "model": "claude-opus-4-6",
            "max_tokens": 64000,
            "tier": "mid",
            "timeout": {"connect_s": 10, "read_s": 120},
            "capabilities": {
                "reasoning": True,
                "cost_tier": "premium",
                "latency_tier": "quality",
            },
        },
        "shortcut": {
            "description": "Anthropic Claude Opus",
            "aliases": ["opus", "claude", "br-sonnet"],
        },
    },
}


def _load_env_values(env_file: str | Path | None = None) -> dict[str, str]:
    """Return environment values from one env file, ignoring empty entries."""
    values = {
        key: value for key, value in os.environ.items() if isinstance(value, str) and value.strip()
    }
    if env_file is None:
        path = Path.cwd() / ".env"
    else:
        path = Path(env_file)
    if not path.exists():
        return values
    values.update(
        {k: v for k, v in dotenv_values(path).items() if isinstance(v, str) and v.strip()}
    )
    return values


def detect_wizard_providers(*, env_file: str | Path | None = None) -> list[str]:
    """Return provider names that can be configured from the current env file."""
    env_values = _load_env_values(env_file)
    detected = []
    for name, spec in _PROVIDER_FACTORIES.items():
        if env_values.get(spec["env"]):
            detected.append(name)
    return detected


def _preferred_fallback_chain(available: list[str], *, purpose: str) -> list[str]:
    """Return a purpose-aware fallback chain over available providers."""
    by_purpose = {
        "general": [
            "deepseek-chat",
            "deepseek-reasoner",
            "gemini-flash",
            "openai-gpt4o",
            "anthropic-claude",
            "openrouter-fallback",
            "kilocode",
            "blackbox-free",
        ],
        "coding": [
            "deepseek-reasoner",
            "deepseek-chat",
            "anthropic-claude",
            "openai-gpt4o",
            "gemini-flash",
            "openrouter-fallback",
            "kilocode",
            "blackbox-free",
        ],
        "quality": [
            "anthropic-claude",
            "openai-gpt4o",
            "deepseek-reasoner",
            "deepseek-chat",
            "gemini-flash",
            "openrouter-fallback",
            "kilocode",
            "blackbox-free",
        ],
        "free": [
            "kilocode",
            "blackbox-free",
            "gemini-flash-lite",
            "deepseek-chat",
            "openrouter-fallback",
        ],
    }
    return [name for name in by_purpose[purpose] if name in available]


def _available_shortcuts(available: list[str]) -> dict[str, dict[str, Any]]:
    """Return shortcut mappings for available providers only."""
    shortcuts: dict[str, dict[str, Any]] = {}
    for name in available:
        shortcut = _PROVIDER_FACTORIES[name].get("shortcut")
        if not shortcut:
            continue
        shortcuts[name] = {
            "target": name,
            "aliases": list(shortcut.get("aliases", [])),
            "description": str(shortcut.get("description", "") or "").strip(),
        }
    return shortcuts


def _premium_targets(available: list[str]) -> list[str]:
    return [
        name
        for name in ("anthropic-claude", "openai-gpt4o", "deepseek-reasoner", "gemini-flash")
        if name in available
    ]


def _free_targets(available: list[str]) -> list[str]:
    return [name for name in ("kilocode", "blackbox-free") if name in available]


def _build_modes(available: list[str], *, purpose: str) -> dict[str, Any]:
    premium_targets = _premium_targets(available)
    free_targets = _free_targets(available)
    default_mode = {
        "general": "auto",
        "coding": "auto",
        "quality": "premium",
        "free": "free",
    }[purpose]

    modes = {
        "auto": {
            "description": "Balanced (default)",
            "best_for": "General use",
            "savings": "Balanced",
            "aliases": [],
            "select": {
                "prefer_tiers": ["default", "reasoning", "mid"],
            },
        },
        "eco": {
            "description": "Cheapest possible",
            "best_for": "Maximum savings",
            "savings": "Aggressive savings",
            "aliases": [],
            "select": {
                "prefer_tiers": ["cheap", "fallback", "default", "mid"],
                "capability_values": {
                    "cost_tier": ["free", "cheap", "standard"],
                },
            },
        },
        "premium": {
            "description": "Best quality",
            "best_for": "Mission-critical work",
            "savings": "Lowest savings",
            "aliases": [],
            "select": {
                "prefer_providers": premium_targets,
                "prefer_tiers": ["mid", "reasoning", "default"],
            },
        },
    }
    if free_targets:
        modes["free"] = {
            "description": "Free tier only",
            "best_for": "Zero-cost routing",
            "savings": "100%",
            "aliases": [],
            "select": {
                "allow_providers": free_targets,
                "prefer_providers": free_targets,
                "capability_values": {
                    "cost_tier": ["free"],
                },
            },
        }

    return {
        "enabled": True,
        "default": default_mode if default_mode in modes else "auto",
        "modes": modes,
    }


def build_initial_config(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
) -> dict[str, Any]:
    """Build a suggested initial config from detected API keys and one purpose."""
    if purpose not in _PURPOSES:
        supported = ", ".join(sorted(_PURPOSES))
        raise ValueError(f"Unsupported purpose '{purpose}'. Choose one of: {supported}")

    available = detect_wizard_providers(env_file=env_file)
    providers = {
        name: yaml.safe_load(yaml.safe_dump(_PROVIDER_FACTORIES[name]["provider"]))
        for name in available
    }
    shortcuts = _available_shortcuts(available)
    fallback_chain = _preferred_fallback_chain(available, purpose=purpose)

    config: dict[str, Any] = {
        "server": {
            "host": "127.0.0.1",
            "port": 8090,
            "log_level": "info",
        },
        "security": {
            "response_headers": True,
            "cache_control": "no-store",
            "max_json_body_bytes": 1048576,
            "max_upload_bytes": 10485760,
            "max_header_value_chars": 160,
        },
        "providers": providers,
        "fallback_chain": fallback_chain,
        "routing_modes": _build_modes(available, purpose=purpose),
        "model_shortcuts": {
            "enabled": bool(shortcuts),
            "shortcuts": shortcuts,
        },
        "routing_policies": {
            "enabled": True,
            "rules": [
                {
                    "name": "n8n-cheap-default",
                    "match": {
                        "any": [
                            {"header_contains": {"x-foundrygate-client": ["n8n"]}},
                            {"client_profile": ["n8n"]},
                        ]
                    },
                    "select": {
                        "prefer_tiers": ["cheap", "default", "mid"],
                    },
                },
                {
                    "name": "opencode-general",
                    "match": {
                        "any": [
                            {"header_contains": {"x-foundrygate-client": ["opencode"]}},
                            {"client_profile": ["opencode"]},
                        ]
                    },
                    "select": {
                        "prefer_tiers": ["default", "mid", "reasoning"],
                    },
                },
            ],
        },
        "client_profiles": {
            "enabled": True,
            "default": "generic",
            "presets": ["openclaw", "n8n", "cli"],
            "profiles": {
                "generic": {},
                "n8n": {
                    "routing_mode": "eco",
                },
                "openclaw": {
                    "routing_mode": "auto",
                },
                "cli": {
                    "routing_mode": "auto",
                },
                "opencode": {
                    "routing_mode": "auto",
                    "prefer_tiers": ["default", "mid", "reasoning"],
                },
            },
            "rules": [
                {
                    "profile": "opencode",
                    "match": {
                        "any": [
                            {"header_contains": {"x-foundrygate-client": ["opencode"]}},
                        ]
                    },
                }
            ],
        },
        "request_hooks": {
            "enabled": True,
            "on_error": "continue",
            "hooks": [
                "prefer-provider-header",
                "locality-header",
                "profile-override-header",
            ],
        },
        "update_check": {
            "enabled": True,
            "repository": "typelicious/FoundryGate",
            "api_base": "https://api.github.com",
            "timeout_seconds": 5.0,
            "check_interval_seconds": 21600,
            "release_channel": "stable",
        },
        "auto_update": {
            "enabled": False,
            "allow_major": False,
            "rollout_ring": "stable",
            "require_healthy_providers": True,
            "max_unhealthy_providers": 0,
            "min_release_age_hours": 24,
            "provider_scope": {
                "allow_providers": [],
                "deny_providers": ["openrouter-fallback"],
            },
            "verification": {
                "enabled": False,
                "command": "foundrygate-health",
                "timeout_seconds": 30,
                "rollback_command": "",
            },
            "maintenance_window": {
                "enabled": False,
                "timezone": "UTC",
                "days": ["sat", "sun"],
                "start_hour": 2,
                "end_hour": 5,
            },
            "apply_command": "foundrygate-update",
        },
    }
    return config


def render_initial_config_yaml(
    *,
    env_file: str | Path | None = None,
    purpose: str = "general",
) -> str:
    """Render the suggested initial config as YAML."""
    return yaml.safe_dump(
        build_initial_config(env_file=env_file, purpose=purpose),
        sort_keys=False,
        allow_unicode=False,
    )
