from __future__ import annotations

from pathlib import Path

from foundrygate.wizard import (
    build_initial_config,
    build_update_suggestions,
    detect_wizard_providers,
    list_provider_candidates,
    merge_initial_config,
    render_initial_config_yaml,
)


def test_detect_wizard_providers_uses_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "OPENAI_API_KEY=sk-openai",
                "ANTHROPIC_API_KEY=sk-anthropic",
            ]
        ),
        encoding="utf-8",
    )

    assert detect_wizard_providers(env_file=env_file) == [
        "deepseek-chat",
        "deepseek-reasoner",
        "openai-gpt4o",
        "openai-images",
        "anthropic-claude",
    ]


def test_build_initial_config_adds_modes_shortcuts_and_profile_defaults(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "GEMINI_API_KEY=gm-demo",
                "OPENROUTER_API_KEY=or-demo",
                "KILOCODE_API_KEY=kilo-demo",
                "BLACKBOX_API_KEY=bb-demo",
            ]
        ),
        encoding="utf-8",
    )

    config = build_initial_config(env_file=env_file, purpose="free")

    assert config["routing_modes"]["enabled"] is True
    assert config["routing_modes"]["default"] == "free"
    assert "free" in config["routing_modes"]["modes"]
    assert config["model_shortcuts"]["enabled"] is True
    assert config["model_shortcuts"]["shortcuts"]["deepseek-chat"]["target"] == "deepseek-chat"
    assert config["client_profiles"]["profiles"]["n8n"]["routing_mode"] == "eco"
    assert config["client_profiles"]["profiles"]["opencode"]["routing_mode"] == "auto"
    assert config["fallback_chain"][0] == "kilocode"


def test_list_provider_candidates_marks_defaults_and_catalog_metadata(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "GEMINI_API_KEY=gm-demo",
                "KILOCODE_API_KEY=kilo-demo",
                "BLACKBOX_API_KEY=bb-demo",
            ]
        ),
        encoding="utf-8",
    )

    rows = list_provider_candidates(env_file=env_file, purpose="free", client="n8n")

    by_name = {row["provider"]: row for row in rows}
    assert by_name["kilocode"]["selected_by_default"] is True
    assert by_name["kilocode"]["offer_track"] == "free"
    assert by_name["blackbox-free"]["evidence_level"] == "mixed"
    assert by_name["gemini-flash-lite"]["provider_type"] == "direct"


def test_build_initial_config_honors_multiselect(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "OPENROUTER_API_KEY=or-demo",
                "KILOCODE_API_KEY=kilo-demo",
            ]
        ),
        encoding="utf-8",
    )

    config = build_initial_config(
        env_file=env_file,
        purpose="general",
        client="opencode",
        selected_providers=["deepseek-chat", "kilocode"],
    )

    assert sorted(config["providers"].keys()) == ["deepseek-chat", "kilocode"]
    assert config["fallback_chain"] == ["deepseek-chat", "kilocode"]
    assert "openrouter-fallback" not in config["providers"]


def test_merge_initial_config_adds_selected_providers_without_overwriting_defaults(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "OPENAI_API_KEY=sk-openai",
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
fallback_chain:
  - deepseek-chat
routing_modes:
  enabled: true
  default: auto
  modes:
    auto:
      description: "Balanced"
      select:
        prefer_tiers: ["default"]
""",
        encoding="utf-8",
    )

    suggestion = build_initial_config(
        env_file=env_file,
        purpose="quality",
        selected_providers=["openai-gpt4o", "openai-images"],
    )
    merged = merge_initial_config(config_path=config_path, suggestion=suggestion)

    assert "deepseek-chat" in merged["providers"]
    assert "openai-gpt4o" in merged["providers"]
    assert "openai-images" in merged["providers"]
    assert merged["routing_modes"]["default"] == "auto"
    assert "premium" in merged["routing_modes"]["modes"]
    assert merged["fallback_chain"] == ["deepseek-chat", "openai-gpt4o"]


def test_render_initial_config_yaml_includes_custom_sections(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-openai\n", encoding="utf-8")

    rendered = render_initial_config_yaml(env_file=env_file, purpose="quality")

    assert "routing_modes:" in rendered
    assert "model_shortcuts:" in rendered
    assert "openai-images:" in rendered
    assert "default: premium" in rendered


def test_render_initial_config_yaml_can_merge_existing_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("KILOCODE_API_KEY=kilo-demo\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers: {}
fallback_chain: []
""",
        encoding="utf-8",
    )

    rendered = render_initial_config_yaml(
        env_file=env_file,
        purpose="free",
        selected_providers=["kilocode"],
        config_path=config_path,
        merge_existing=True,
    )

    assert "kilocode:" in rendered
    assert "warn_on_volatile_offers: true" in rendered


def test_build_update_suggestions_returns_add_replace_keep_groups(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "OPENROUTER_API_KEY=or-demo",
                "KILOCODE_API_KEY=kilo-demo",
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
  openrouter-fallback:
    backend: openai-compat
    base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_API_KEY}"
    model: "openrouter/wrong"
fallback_chain:
  - deepseek-chat
  - openrouter-fallback
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
    n8n:
      routing_mode: premium
""",
        encoding="utf-8",
    )

    suggestions = build_update_suggestions(
        env_file=env_file,
        purpose="free",
        client="generic",
        config_path=config_path,
    )

    add_names = {item["provider"] for item in suggestions["recommended_add"]}
    replace_names = {item["provider"] for item in suggestions["recommended_replace"]}
    keep_names = {item["provider"] for item in suggestions["recommended_keep"]}
    mode_profiles = {item["profile"] for item in suggestions["recommended_mode_changes"]}

    assert "kilocode" in add_names
    assert "openrouter-fallback" in replace_names
    assert "deepseek-chat" in keep_names
    assert "generic" in mode_profiles
    assert "n8n" in mode_profiles
