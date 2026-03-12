"""Tests for provider capability normalization and validation."""

from pathlib import Path

import pytest

from foundrygate.config import ConfigError, load_config


def _write_config(tmp_path: Path, provider_block: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        "server:\n"
        '  host: "127.0.0.1"\n'
        "  port: 8090\n"
        "providers:\n"
        f"{provider_block}"
        "fallback_chain: []\n"
        "metrics:\n"
        "  enabled: false\n"
    )
    return path


def test_capabilities_infer_local_streaming_and_network_zone(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  local-worker:\n"
            "    backend: openai-compat\n"
            '    base_url: "http://127.0.0.1:11434/v1"\n'
            '    api_key: "local"\n'
            '    model: "llama3"\n'
            "    tier: local\n"
        ),
    )

    cfg = load_config(path)
    caps = cfg.provider("local-worker")["capabilities"]

    assert caps["chat"] is True
    assert caps["streaming"] is True
    assert caps["local"] is True
    assert caps["cloud"] is False
    assert caps["network_zone"] == "local"


def test_capabilities_infer_reasoning_from_tier_and_model(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  reasoner:\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "deepseek-reasoner"\n'
            "    tier: reasoning\n"
        ),
    )

    cfg = load_config(path)
    caps = cfg.provider("reasoner")["capabilities"]

    assert caps["reasoning"] is True
    assert caps["local"] is False
    assert caps["cloud"] is True
    assert caps["network_zone"] == "public"


def test_capabilities_preserve_explicit_overrides(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  tuned:\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "chat-model"\n'
            "    capabilities:\n"
            "      tools: true\n"
            "      cost_tier: budget\n"
            "      latency_tier: low\n"
            "      compliance_scope: internal-only\n"
        ),
    )

    cfg = load_config(path)
    caps = cfg.provider("tuned")["capabilities"]

    assert caps["tools"] is True
    assert caps["cost_tier"] == "budget"
    assert caps["latency_tier"] == "low"
    assert caps["compliance_scope"] == "internal-only"


def test_capabilities_reject_unknown_keys(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  invalid:\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "chat-model"\n'
            "    capabilities:\n"
            "      unsupported_flag: true\n"
        ),
    )

    with pytest.raises(ConfigError, match="unknown capability keys"):
        load_config(path)


def test_capabilities_reject_chat_false(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  invalid:\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "chat-model"\n'
            "    capabilities:\n"
            "      chat: false\n"
        ),
    )

    with pytest.raises(ConfigError, match="chat=true"):
        load_config(path)


def test_capabilities_reject_google_streaming_enablement(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  invalid:\n"
            "    backend: google-genai\n"
            '    base_url: "https://generativelanguage.googleapis.com/v1beta"\n'
            '    api_key: "secret"\n'
            '    model: "gemini-2.5-flash"\n'
            "    capabilities:\n"
            "      streaming: true\n"
        ),
    )

    with pytest.raises(ConfigError, match="google-genai"):
        load_config(path)


def test_local_worker_contract_defaults_tier_and_local_capabilities(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  local-worker:\n"
            "    contract: local-worker\n"
            "    backend: openai-compat\n"
            '    base_url: "http://127.0.0.1:11434/v1"\n'
            '    api_key: "local"\n'
            '    model: "llama3"\n'
        ),
    )

    cfg = load_config(path)
    provider = cfg.provider("local-worker")
    caps = provider["capabilities"]

    assert provider["contract"] == "local-worker"
    assert provider["tier"] == "local"
    assert caps["local"] is True
    assert caps["cloud"] is False
    assert caps["network_zone"] == "local"


def test_local_worker_contract_rejects_non_local_base_url(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  local-worker:\n"
            "    contract: local-worker\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "llama3"\n'
        ),
    )

    with pytest.raises(ConfigError, match="local/private base_url"):
        load_config(path)


def test_local_worker_contract_rejects_non_openai_backend(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  local-worker:\n"
            "    contract: local-worker\n"
            "    backend: google-genai\n"
            '    base_url: "http://127.0.0.1:11434/v1"\n'
            '    api_key: "secret"\n'
            '    model: "llama3"\n'
        ),
    )

    with pytest.raises(ConfigError, match="requires backend 'openai-compat'"):
        load_config(path)


def test_image_provider_contract_enables_image_generation(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  image-cloud:\n"
            "    contract: image-provider\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "gpt-image-1"\n'
        ),
    )

    cfg = load_config(path)
    provider = cfg.provider("image-cloud")

    assert provider["contract"] == "image-provider"
    assert provider["capabilities"]["image_generation"] is True
    assert provider["capabilities"]["image_editing"] is False


def test_image_provider_contract_rejects_non_openai_backend(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  image-cloud:\n"
            "    contract: image-provider\n"
            "    backend: google-genai\n"
            '    base_url: "https://generativelanguage.googleapis.com/v1beta"\n'
            '    api_key: "secret"\n'
            '    model: "imagen"\n'
        ),
    )

    with pytest.raises(ConfigError, match="image-provider"):
        load_config(path)


def test_image_provider_policy_tags_are_normalized(tmp_path):
    path = _write_config(
        tmp_path,
        (
            "  image-cloud:\n"
            "    contract: image-provider\n"
            "    backend: openai-compat\n"
            '    base_url: "https://api.example.com/v1"\n'
            '    api_key: "secret"\n'
            '    model: "gpt-image-1"\n'
            "    image:\n"
            '      policy_tags: ["Quality", " editing "]\n'
        ),
    )

    cfg = load_config(path)
    provider = cfg.provider("image-cloud")

    assert provider["image"]["policy_tags"] == ["quality", "editing"]
