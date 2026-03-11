"""Provider registry – single source of truth for all supported providers.

This module defines every provider FoundryGate knows about, keyed by its
*canonical name* (the name used as config key and model alias).

Each entry describes:
  - backend      : which HTTP adapter to use (see providers.py)
  - base_url     : default base URL (may be overridden via env var)
  - api_key_env  : environment variable that supplies the API key
  - auth_optional: True if a key is not required (local servers)
  - tier         : default routing tier
  - example_model: a sensible default model id for this provider
  - pricing      : USD per 1M tokens (input/output/cache_read) – best-effort
                   defaults; override in config.yaml for accuracy
  - notes        : short human-readable description

Providers fall into four groups:
  A. Built-in (pi-ai catalog) – require only api_key + model selection
  B. Custom/proxy via models.providers – OpenAI-compat or Anthropic-compat
  C. Local runtimes – no auth, discovered automatically
  D. OAuth/special – require interactive login (documented but not auto-started)

Usage
-----
The registry is consumed by:
  - config.py  : validates and supplements provider configs from config.yaml
  - main.py    : lists all known providers in /v1/models
  - README     : generated provider table (via scripts/gen-docs)
"""

from __future__ import annotations

from typing import TypedDict


class ProviderDef(TypedDict, total=False):
    backend: str  # "openai-compat" | "anthropic-compat" | "google-genai"
    base_url: str  # Default base URL (may be overridden by env var)
    base_url_env: str  # Env var that overrides base_url (optional)
    api_key_env: str  # Primary env var for the API key
    api_key_env_alt: str  # Fallback env var (e.g. GOOGLE_API_KEY as fallback)
    auth_optional: bool  # True = no key required (local servers)
    tier: str  # "default" | "reasoning" | "cheap" | "mid" | "fallback" | "local"
    example_model: str  # Suggested default model id
    pricing: dict  # {"input": float, "output": float, "cache_read": float}
    notes: str  # One-liner description


# ---------------------------------------------------------------------------
# A. Built-in providers (pi-ai catalog)
# ---------------------------------------------------------------------------

BUILTIN: dict[str, ProviderDef] = {
    # ── OpenAI ─────────────────────────────────────────────────────────────
    "openai": ProviderDef(
        backend="openai-compat",
        base_url="https://api.openai.com/v1",
        base_url_env="OPENAI_BASE_URL",
        api_key_env="OPENAI_API_KEY",
        tier="default",
        example_model="gpt-4o",
        pricing={"input": 2.50, "output": 10.00, "cache_read": 1.25},
        notes="OpenAI – GPT-4o, GPT-4.1 series",
    ),
    # ── Anthropic ──────────────────────────────────────────────────────────
    "anthropic": ProviderDef(
        backend="anthropic-compat",
        base_url="https://api.anthropic.com/v1",
        base_url_env="ANTHROPIC_BASE_URL",
        api_key_env="ANTHROPIC_API_KEY",
        tier="default",
        example_model="claude-opus-4-6",
        pricing={"input": 15.00, "output": 75.00, "cache_read": 1.50},
        notes="Anthropic – Claude Opus/Sonnet/Haiku",
    ),
    # ── OpenAI Code / Codex (OAuth via ChatGPT) ────────────────────────────
    # Auth is OAuth-based; users must run: openclaw models auth login --provider openai-codex
    # No static API key env var. Documented only.
    "openai-codex": ProviderDef(
        backend="openai-compat",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_CODEX_TOKEN",  # token injected after OAuth login
        auth_optional=True,
        tier="default",
        example_model="openai-codex/gpt-5.3-codex",
        pricing={"input": 0.0, "output": 0.0},
        notes="OpenAI Codex (OAuth via ChatGPT) – requires interactive login",
    ),
    # ── OpenCode Zen ───────────────────────────────────────────────────────
    "opencode": ProviderDef(
        backend="anthropic-compat",
        base_url="https://api.opencode.ai/v1",
        base_url_env="OPENCODE_BASE_URL",
        api_key_env="OPENCODE_API_KEY",
        tier="default",
        example_model="opencode/claude-opus-4-6",
        pricing={"input": 0.0, "output": 0.0},
        notes="OpenCode Zen – Anthropic-compatible gateway",
    ),
    # ── Google Gemini (API key) ────────────────────────────────────────────
    "google": ProviderDef(
        backend="google-genai",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        base_url_env="GEMINI_BASE_URL",
        api_key_env="GEMINI_API_KEY",
        api_key_env_alt="GOOGLE_API_KEY",
        tier="mid",
        example_model="gemini-2.5-flash",
        pricing={"input": 0.15, "output": 0.60, "cache_read": 0.04},
        notes="Google Gemini via API key – Flash / Pro / Flash-Lite",
    ),
    # ── Z.AI / GLM ────────────────────────────────────────────────────────
    "zai": ProviderDef(
        backend="openai-compat",
        base_url="https://api.z.ai/api/paas/v4",
        base_url_env="ZAI_BASE_URL",
        api_key_env="ZAI_API_KEY",
        tier="default",
        example_model="glm-4.7",
        pricing={"input": 0.0, "output": 0.0},
        notes="Z.AI / GLM models (aliases: z.ai/*, z-ai/*)",
    ),
    # ── Vercel AI Gateway ─────────────────────────────────────────────────
    "vercel-ai-gateway": ProviderDef(
        backend="openai-compat",
        base_url="https://api.v0.ai/v1",
        base_url_env="VERCEL_AI_GATEWAY_BASE_URL",
        api_key_env="AI_GATEWAY_API_KEY",
        tier="fallback",
        example_model="vercel-ai-gateway/anthropic/claude-opus-4.6",
        pricing={"input": 0.0, "output": 0.0},
        notes="Vercel AI Gateway – multi-model proxy",
    ),
    # ── Kilo Gateway ──────────────────────────────────────────────────────
    "kilocode": ProviderDef(
        backend="openai-compat",
        base_url="https://api.kilo.ai/api/gateway/v1",
        base_url_env="KILOCODE_BASE_URL",
        api_key_env="KILOCODE_API_KEY",
        tier="fallback",
        example_model="kilocode/anthropic/claude-opus-4.6",
        pricing={"input": 0.0, "output": 0.0},
        notes="Kilo Gateway – expanded catalog incl. GLM-5, MiniMax, Kimi K2.5",
    ),
    # ── OpenRouter ────────────────────────────────────────────────────────
    "openrouter": ProviderDef(
        backend="openai-compat",
        base_url="https://openrouter.ai/api/v1",
        base_url_env="OPENROUTER_BASE_URL",
        api_key_env="OPENROUTER_API_KEY",
        tier="fallback",
        example_model="openrouter/anthropic/claude-opus-4.6",
        pricing={"input": 0.27, "output": 1.10},
        notes="OpenRouter – unified API to many providers",
    ),
    # ── xAI / Grok ────────────────────────────────────────────────────────
    "xai": ProviderDef(
        backend="openai-compat",
        base_url="https://api.x.ai/v1",
        base_url_env="XAI_BASE_URL",
        api_key_env="XAI_API_KEY",
        tier="default",
        example_model="grok-3",
        pricing={"input": 3.00, "output": 15.00},
        notes="xAI / Grok models",
    ),
    # ── Mistral ───────────────────────────────────────────────────────────
    "mistral": ProviderDef(
        backend="openai-compat",
        base_url="https://api.mistral.ai/v1",
        base_url_env="MISTRAL_BASE_URL",
        api_key_env="MISTRAL_API_KEY",
        tier="default",
        example_model="mistral/mistral-large-latest",
        pricing={"input": 2.00, "output": 6.00},
        notes="Mistral AI – Mistral Large, Codestral, etc.",
    ),
    # ── Groq ──────────────────────────────────────────────────────────────
    "groq": ProviderDef(
        backend="openai-compat",
        base_url="https://api.groq.com/openai/v1",
        base_url_env="GROQ_BASE_URL",
        api_key_env="GROQ_API_KEY",
        tier="cheap",
        example_model="llama-3.3-70b-versatile",
        pricing={"input": 0.05, "output": 0.10},
        notes="Groq – ultra-fast inference (LPU), Llama / DeepSeek",
    ),
    # ── Cerebras ──────────────────────────────────────────────────────────
    "cerebras": ProviderDef(
        backend="openai-compat",
        base_url="https://api.cerebras.ai/v1",
        base_url_env="CEREBRAS_BASE_URL",
        api_key_env="CEREBRAS_API_KEY",
        tier="cheap",
        example_model="llama3.3-70b",
        pricing={"input": 0.10, "output": 0.10},
        notes="Cerebras – fast inference, zai-glm-4.7 / zai-glm-4.6 compatible",
    ),
    # ── GitHub Copilot ────────────────────────────────────────────────────
    # Auth via GitHub token (COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN)
    "github-copilot": ProviderDef(
        backend="openai-compat",
        base_url="https://api.githubcopilot.com/v1",
        base_url_env="GITHUB_COPILOT_BASE_URL",
        api_key_env="COPILOT_GITHUB_TOKEN",
        api_key_env_alt="GH_TOKEN",
        auth_optional=True,
        tier="default",
        example_model="gpt-4o",
        pricing={"input": 0.0, "output": 0.0},
        notes="GitHub Copilot – requires GH_TOKEN / COPILOT_GITHUB_TOKEN",
    ),
    # ── Hugging Face Inference ────────────────────────────────────────────
    "huggingface": ProviderDef(
        backend="openai-compat",
        base_url="https://api-inference.huggingface.co/v1",
        base_url_env="HUGGINGFACE_BASE_URL",
        api_key_env="HUGGINGFACE_HUB_TOKEN",
        api_key_env_alt="HF_TOKEN",
        tier="default",
        example_model="huggingface/deepseek-ai/DeepSeek-R1",
        pricing={"input": 0.0, "output": 0.0},
        notes="HuggingFace Inference – OpenAI-compat router",
    ),
}


# ---------------------------------------------------------------------------
# B. Custom / proxy providers (configured via models.providers in OpenClaw)
# ---------------------------------------------------------------------------

CUSTOM: dict[str, ProviderDef] = {
    # ── Moonshot AI / Kimi ────────────────────────────────────────────────
    "moonshot": ProviderDef(
        backend="openai-compat",
        base_url="https://api.moonshot.ai/v1",
        base_url_env="MOONSHOT_BASE_URL",
        api_key_env="MOONSHOT_API_KEY",
        tier="default",
        example_model="moonshot/kimi-k2.5",
        pricing={"input": 0.0, "output": 0.0},
        notes=(
            "Moonshot AI / Kimi – OpenAI-compat; models: kimi-k2.5, kimi-k2-0905-preview,"
            " kimi-k2-turbo-preview, kimi-k2-thinking, kimi-k2-thinking-turbo"
        ),
    ),
    # ── Kimi Coding ───────────────────────────────────────────────────────
    # Uses Moonshot's Anthropic-compatible endpoint
    "kimi-coding": ProviderDef(
        backend="anthropic-compat",
        base_url="https://api.moonshot.ai/anthropic",
        base_url_env="KIMI_CODING_BASE_URL",
        api_key_env="KIMI_API_KEY",
        tier="default",
        example_model="kimi-coding/k2p5",
        pricing={"input": 0.0, "output": 0.0},
        notes="Kimi Coding – Anthropic-compat endpoint via Moonshot",
    ),
    # ── Volcano Engine / Doubao (China) ───────────────────────────────────
    "volcengine": ProviderDef(
        backend="openai-compat",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        base_url_env="VOLCANO_ENGINE_BASE_URL",
        api_key_env="VOLCANO_ENGINE_API_KEY",
        tier="default",
        example_model="volcengine/doubao-seed-1-8-251228",
        pricing={"input": 0.0, "output": 0.0},
        notes="Volcano Engine – Doubao, Kimi K2.5, GLM 4.7, DeepSeek V3.2 (CN)",
    ),
    # ── Volcano Engine plan (coding models) ───────────────────────────────
    "volcengine-plan": ProviderDef(
        backend="openai-compat",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        base_url_env="VOLCANO_ENGINE_BASE_URL",
        api_key_env="VOLCANO_ENGINE_API_KEY",
        tier="default",
        example_model="volcengine-plan/ark-code-latest",
        pricing={"input": 0.0, "output": 0.0},
        notes=(
            "Volcano Engine – coding models"
            " (ark-code-latest, doubao-seed-code, kimi-k2.5, kimi-k2-thinking, glm-4.7)"
        ),
    ),
    # ── BytePlus (international equivalent of Volcano Engine) ─────────────
    "byteplus": ProviderDef(
        backend="openai-compat",
        base_url="https://api.byteplus.com/api/v3",
        base_url_env="BYTEPLUS_BASE_URL",
        api_key_env="BYTEPLUS_API_KEY",
        tier="default",
        example_model="byteplus/seed-1-8-251228",
        pricing={"input": 0.0, "output": 0.0},
        notes="BytePlus ARK – international access to Volcano Engine models",
    ),
    # ── BytePlus plan (coding models) ─────────────────────────────────────
    "byteplus-plan": ProviderDef(
        backend="openai-compat",
        base_url="https://api.byteplus.com/api/v3",
        base_url_env="BYTEPLUS_BASE_URL",
        api_key_env="BYTEPLUS_API_KEY",
        tier="default",
        example_model="byteplus-plan/ark-code-latest",
        pricing={"input": 0.0, "output": 0.0},
        notes=(
            "BytePlus ARK – coding models"
            " (ark-code-latest, doubao-seed-code, kimi-k2.5, kimi-k2-thinking, glm-4.7)"
        ),
    ),
    # ── Synthetic ─────────────────────────────────────────────────────────
    "synthetic": ProviderDef(
        backend="anthropic-compat",
        base_url="https://api.synthetic.new/anthropic",
        base_url_env="SYNTHETIC_BASE_URL",
        api_key_env="SYNTHETIC_API_KEY",
        tier="default",
        example_model="synthetic/hf:MiniMaxAI/MiniMax-M2.1",
        pricing={"input": 0.0, "output": 0.0},
        notes="Synthetic – Anthropic-compat; exposes HuggingFace models (MiniMax, etc.)",
    ),
    # ── MiniMax ───────────────────────────────────────────────────────────
    "minimax": ProviderDef(
        backend="anthropic-compat",
        base_url="https://api.minimax.chat/v1",
        base_url_env="MINIMAX_BASE_URL",
        api_key_env="MINIMAX_API_KEY",
        tier="default",
        example_model="minimax/MiniMax-M2.1",
        pricing={"input": 0.0, "output": 0.0},
        notes="MiniMax – Anthropic-compat custom endpoint",
    ),
}


# ---------------------------------------------------------------------------
# C. Local / self-hosted runtimes (no API key required by default)
# ---------------------------------------------------------------------------

LOCAL: dict[str, ProviderDef] = {
    # ── Ollama ────────────────────────────────────────────────────────────
    "ollama": ProviderDef(
        backend="openai-compat",
        base_url="http://127.0.0.1:11434/v1",
        base_url_env="OLLAMA_BASE_URL",
        api_key_env="OLLAMA_API_KEY",
        auth_optional=True,
        tier="local",
        example_model="ollama/llama3.3",
        pricing={"input": 0.0, "output": 0.0},
        notes="Ollama – local LLM runtime, OpenAI-compat at :11434",
    ),
    # ── vLLM ──────────────────────────────────────────────────────────────
    "vllm": ProviderDef(
        backend="openai-compat",
        base_url="http://127.0.0.1:8000/v1",
        base_url_env="VLLM_BASE_URL",
        api_key_env="VLLM_API_KEY",
        auth_optional=True,
        tier="local",
        example_model="vllm/your-model-id",
        pricing={"input": 0.0, "output": 0.0},
        notes="vLLM – local/self-hosted OpenAI-compat server at :8000",
    ),
    # ── LM Studio ─────────────────────────────────────────────────────────
    "lmstudio": ProviderDef(
        backend="openai-compat",
        base_url="http://localhost:1234/v1",
        base_url_env="LMSTUDIO_BASE_URL",
        api_key_env="LMSTUDIO_API_KEY",
        auth_optional=True,
        tier="local",
        example_model="lmstudio/minimax-m2.1-gs32",
        pricing={"input": 0.0, "output": 0.0},
        notes="LM Studio – local OpenAI-compat server at :1234",
    ),
    # ── LiteLLM proxy ─────────────────────────────────────────────────────
    "litellm": ProviderDef(
        backend="openai-compat",
        base_url="http://localhost:4000/v1",
        base_url_env="LITELLM_BASE_URL",
        api_key_env="LITELLM_API_KEY",
        auth_optional=True,
        tier="local",
        example_model="litellm/your-model-id",
        pricing={"input": 0.0, "output": 0.0},
        notes="LiteLLM proxy – OpenAI-compat gateway to 100+ providers at :4000",
    ),
}


# ---------------------------------------------------------------------------
# D. OAuth / interactive providers
#    These require interactive login and cannot be auto-started by FoundryGate.
#    Listed for completeness; config.yaml can reference them once authenticated.
# ---------------------------------------------------------------------------

OAUTH: dict[str, ProviderDef] = {
    # ── Google Vertex AI ──────────────────────────────────────────────────
    "google-vertex": ProviderDef(
        backend="openai-compat",
        base_url="https://us-central1-aiplatform.googleapis.com/v1",
        base_url_env="GOOGLE_VERTEX_BASE_URL",
        api_key_env="GOOGLE_APPLICATION_CREDENTIALS",
        auth_optional=True,
        tier="mid",
        example_model="google-vertex/gemini-2.5-pro",
        pricing={"input": 0.0, "output": 0.0},
        notes="Google Vertex AI – uses gcloud ADC; interactive setup required",
    ),
    # ── Qwen OAuth (free tier) ────────────────────────────────────────────
    "qwen-portal": ProviderDef(
        backend="openai-compat",
        base_url="https://qwen-portal.example.com/v1",  # placeholder; set via oauth
        api_key_env="QWEN_PORTAL_TOKEN",
        auth_optional=True,
        tier="default",
        example_model="qwen-portal/coder-model",
        pricing={"input": 0.0, "output": 0.0},
        notes=(
            "Qwen OAuth (free tier) – device-code flow;"
            " requires: openclaw plugins enable qwen-portal-auth"
        ),
    ),
}


# ---------------------------------------------------------------------------
# Combined registry
# ---------------------------------------------------------------------------

ALL: dict[str, ProviderDef] = {**BUILTIN, **CUSTOM, **LOCAL, **OAUTH}


def get(name: str) -> ProviderDef | None:
    """Look up a provider definition by canonical name."""
    return ALL.get(name)


def known_names() -> list[str]:
    """Return all known provider names, sorted."""
    return sorted(ALL.keys())


def api_key_env(name: str) -> str | None:
    """Return the primary API key env var name for a provider, or None."""
    entry = ALL.get(name)
    if entry is None:
        return None
    return entry.get("api_key_env")


def is_auth_optional(name: str) -> bool:
    """Return True if the provider works without an explicit API key."""
    entry = ALL.get(name)
    if entry is None:
        return False
    return bool(entry.get("auth_optional", False))
