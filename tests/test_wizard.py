from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from faigate.wizard import (
    apply_client_scenario,
    apply_provider_setup,
    apply_update_suggestions,
    build_config_change_summary,
    build_initial_config,
    build_interactive_candidate_sections,
    build_provider_probe_report,
    build_update_suggestions,
    detect_wizard_providers,
    list_client_scenarios,
    list_provider_candidates,
    merge_initial_config,
    render_candidate_cards_text,
    render_client_scenario_summary,
    render_client_scenarios_text,
    render_current_provider_sources_text,
    render_initial_config_yaml,
    render_known_provider_sources_text,
    render_provider_probe_text,
    render_provider_setup_summary,
    write_env_updates,
    write_output_file,
)


def test_detect_wizard_providers_uses_env_file(tmp_path: Path, monkeypatch):
    for name in (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "KILOCODE_API_KEY",
        "BLACKBOX_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

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
    assert config["providers"]["deepseek-chat"]["lane"]["canonical_model"] == "deepseek/chat"
    assert config["providers"]["kilocode"]["lane"]["route_type"] == "aggregator"
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
    assert by_name["kilocode"]["ready_now"] is True
    assert by_name["kilocode"]["recommended_now"] is True
    assert by_name["kilocode"]["discovery_url"].startswith("https://")
    assert by_name["kilocode"]["discovery_link_source"] == "official"
    assert "performance-led" in by_name["kilocode"]["discovery_disclosure"]


def test_build_interactive_candidate_sections_splits_ready_and_needs_key(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "GEMINI_API_KEY=gm-demo",
                "OPENROUTER_API_KEY=or-demo",
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
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
fallback_chain:
  - deepseek-chat
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    opencode: {}
""",
        encoding="utf-8",
    )

    sections = build_interactive_candidate_sections(
        env_file=env_file,
        purpose="coding",
        client="opencode",
        config_path=config_path,
    )

    ready_names = [row["provider"] for row in sections["ready_now"]]
    missing_names = [row["provider"] for row in sections["available_with_key"]]

    assert "deepseek-chat" in ready_names
    assert "deepseek-reasoner" in ready_names
    assert "openai-gpt4o" in missing_names
    assert "anthropic-claude" in missing_names


def test_render_candidate_cards_text_prefers_compact_operator_view(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-demo",
                "GEMINI_API_KEY=gm-demo",
                "OPENROUTER_API_KEY=or-demo",
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
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
fallback_chain:
  - deepseek-chat
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    opencode: {}
""",
        encoding="utf-8",
    )

    rendered = render_candidate_cards_text(
        env_file=env_file,
        purpose="coding",
        client="opencode",
        config_path=config_path,
    )

    assert "Ready now" in rendered
    assert "More options if you add keys" in rendered
    assert "deepseek-chat  (recommended · already in config)" in rendered
    assert "openai-gpt4o  (needs OPENAI_API_KEY)" in rendered
    assert "lane: deepseek/chat | route: direct | cluster: balanced-workhorse" in rendered
    assert "discovery_env_var" not in rendered


def test_render_known_provider_sources_text_marks_key_and_config_status(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-demo\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  deepseek-chat:
    backend: openai-compat
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
""".strip(),
        encoding="utf-8",
    )

    rendered = render_known_provider_sources_text(env_file=env_file, config_path=config_path)

    assert "Known providers" in rendered
    assert "deepseek-chat  (key ready · already in config)" in rendered
    assert "anthropic-claude  (needs ANTHROPIC_API_KEY)" in rendered


def test_apply_provider_setup_can_add_known_custom_and_local_sources(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("providers: {}\n", encoding="utf-8")

    payload = apply_provider_setup(
        config_path=config_path,
        env_file=tmp_path / ".env",
        known_providers=[
            {
                "provider": "anthropic-claude",
                "env_value": "sk-ant",
            }
        ],
        custom_provider={
            "name": "agency-router",
            "base_url": "https://api.example.com/v1",
            "base_url_env": "CUSTOM_AGENCY_ROUTER_BASE_URL",
            "model": "example-model",
            "api_env": "CUSTOM_AGENCY_ROUTER_API_KEY",
            "api_key_value": "sk-custom",
            "tier": "mid",
        },
        local_worker={
            "name": "lmstudio-local",
            "base_url": "http://127.0.0.1:1234/v1",
            "model": "local-model",
        },
    )

    providers = payload["config"]["providers"]
    assert "anthropic-claude" in providers
    assert providers["agency-router"]["base_url"] == "${CUSTOM_AGENCY_ROUTER_BASE_URL}"
    assert providers["lmstudio-local"]["contract"] == "local-worker"
    assert payload["env_updates"]["ANTHROPIC_API_KEY"] == "sk-ant"
    assert payload["env_updates"]["CUSTOM_AGENCY_ROUTER_API_KEY"] == "sk-custom"
    assert payload["env_updates"]["CUSTOM_AGENCY_ROUTER_BASE_URL"] == "https://api.example.com/v1"


def test_write_env_updates_preserves_existing_lines(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\nDEEPSEEK_API_KEY=old\nUNCHANGED=value\n",
        encoding="utf-8",
    )

    result = write_env_updates(
        env_path=env_path,
        env_updates={
            "DEEPSEEK_API_KEY": "new",
            "ANTHROPIC_API_KEY": "sk-ant",
        },
    )

    payload = env_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=new" in payload
    assert "UNCHANGED=value" in payload
    assert "ANTHROPIC_API_KEY=sk-ant" in payload
    assert result["updated_keys"] == ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"]


def test_render_current_provider_sources_text_summarizes_existing_config(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("LOCAL_WORKER_KEY=abc\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  local-worker:
    contract: local-worker
    backend: openai-compat
    api_key: "${LOCAL_WORKER_KEY}"
    base_url: "http://127.0.0.1:1234/v1"
    model: "local-model"
    tier: local
""".strip(),
        encoding="utf-8",
    )

    rendered = render_current_provider_sources_text(env_file=env_file, config_path=config_path)

    assert "Current provider sources" in rendered
    assert "local-worker  (ready · local-worker)" in rendered
    assert "base_url: http://127.0.0.1:1234/v1" in rendered


def test_render_provider_setup_summary_lists_added_providers_and_env_updates(tmp_path: Path):
    summary = render_provider_setup_summary(
        {
            "config": {"providers": {"deepseek-chat": {}, "anthropic-claude": {}}},
            "added_providers": ["anthropic-claude"],
            "env_updates": {"ANTHROPIC_API_KEY": "sk-ant", "OPENAI_BASE_URL": ""},
        }
    )

    assert "Providers to add/update" in summary
    assert "- anthropic-claude" in summary
    assert "- ANTHROPIC_API_KEY  (set)" in summary
    assert "- OPENAI_BASE_URL  (left blank)" in summary
    assert "Resulting configured providers: 2" in summary


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


def test_config_wizard_help_lists_primary_flows():
    result = subprocess.run(
        ["bash", "scripts/faigate-config-wizard", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--list-candidates" in result.stdout
    assert "--text-candidates" in result.stdout
    assert "--dry-run-summary" in result.stdout
    assert "--write-backup" in result.stdout
    assert "recommended_mode_changes" in result.stdout


def test_apply_update_suggestions_can_apply_provider_and_mode_changes(tmp_path: Path):
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
    n8n:
      routing_mode: premium
fallback_chain:
  - deepseek-chat
  - openrouter-fallback
""",
        encoding="utf-8",
    )

    merged = apply_update_suggestions(
        env_file=env_file,
        purpose="free",
        client="generic",
        config_path=config_path,
        apply_groups=["recommended_add", "recommended_replace", "recommended_mode_changes"],
        selected_providers=["kilocode", "openrouter-fallback"],
        selected_profiles=["n8n"],
    )

    assert "kilocode" in merged["providers"]
    assert merged["providers"]["openrouter-fallback"]["model"] == "openrouter/auto"
    assert merged["client_profiles"]["profiles"]["n8n"]["routing_mode"] == "eco"
    assert merged["client_profiles"]["profiles"]["generic"]["routing_mode"] == "premium"


def test_config_wizard_write_uses_runtime_config_when_apply_groups_are_set(tmp_path: Path):
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
fallback_chain:
  - deepseek-chat
  - openrouter-fallback
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FAIGATE_PYTHON"] = sys.executable

    subprocess.run(
        [
            "bash",
            "scripts/faigate-config-wizard",
            "--env-file",
            str(env_file),
            "--purpose",
            "free",
            "--client",
            "generic",
            "--current-config",
            str(config_path),
            "--merge-existing",
            "--apply",
            "recommended_add,recommended_replace,recommended_mode_changes",
            "--write",
            str(config_path),
            "--write-backup",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    written = config_path.read_text(encoding="utf-8")
    backups = list(tmp_path.glob("config.yaml.bak"))

    assert "suggestions:" not in written
    assert "providers:" in written
    assert "kilocode:" in written
    assert "openrouter-fallback:" in written
    assert "openrouter/auto" in written
    assert len(backups) == 1


def test_config_wizard_write_handles_nullish_existing_sections(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=test-deepseek",
                "OPENROUTER_API_KEY=test-openrouter",
            ]
        )
        + "\n",
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
fallback_chain: null
routing_modes:
  enabled: true
  default: auto
  modes: null
model_shortcuts:
  enabled: true
  shortcuts: null
client_profiles:
  enabled: true
  default: generic
  presets: null
  profiles:
    generic: {}
  rules: null
routing_policies:
  enabled: true
  rules: null
request_hooks:
  enabled: true
  on_error: continue
  hooks: null
""",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FAIGATE_PYTHON"] = sys.executable

    subprocess.run(
        [
            "bash",
            "scripts/faigate-config-wizard",
            "--env-file",
            str(env_file),
            "--purpose",
            "free",
            "--client",
            "cli",
            "--current-config",
            str(config_path),
            "--apply",
            "recommended_add,recommended_replace,recommended_mode_changes",
            "--write",
            str(config_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert isinstance(written["fallback_chain"], list)
    assert isinstance(written["routing_modes"]["modes"], dict)
    assert isinstance(written["model_shortcuts"]["shortcuts"], dict)
    assert isinstance(written["client_profiles"]["presets"], list)
    assert isinstance(written["client_profiles"]["rules"], list)
    assert isinstance(written["routing_policies"]["rules"], list)
    assert isinstance(written["request_hooks"]["hooks"], list)


def test_build_config_change_summary_reports_added_replaced_and_mode_changes(tmp_path: Path):
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    n8n:
      routing_mode: premium
fallback_chain:
  - deepseek-chat
""",
        encoding="utf-8",
    )

    updated = {
        "providers": {
            "deepseek-chat": {
                "model": "deepseek-chat-v2",
            },
            "kilocode": {
                "model": "z-ai/glm-5:free",
            },
        },
        "client_profiles": {
            "profiles": {
                "n8n": {"routing_mode": "eco"},
            }
        },
        "fallback_chain": ["deepseek-chat", "kilocode"],
    }

    summary = build_config_change_summary(config_path=config_path, updated_config=updated)

    assert summary["added_providers"] == ["kilocode"]
    assert summary["replaced_models"] == [
        {
            "provider": "deepseek-chat",
            "from_model": "deepseek-chat",
            "to_model": "deepseek-chat-v2",
        }
    ]
    assert summary["changed_profile_modes"] == [
        {
            "profile": "n8n",
            "from_mode": "premium",
            "to_mode": "eco",
        }
    ]
    assert summary["fallback_additions"] == ["kilocode"]


def test_write_output_file_can_create_backup_snapshot(tmp_path: Path):
    output_path = tmp_path / "config.yaml"
    output_path.write_text("old: config\n", encoding="utf-8")

    result = write_output_file(
        output_path=output_path,
        rendered="new: config\n",
        write_backup=True,
        backup_suffix=".before-wizard",
    )

    assert output_path.read_text(encoding="utf-8") == "new: config\n"
    assert result["backup_created"] is True
    assert result["backup_path"].endswith(".before-wizard")
    assert Path(result["backup_path"]).read_text(encoding="utf-8") == "old: config\n"


def test_build_provider_probe_report_classifies_missing_key_and_ready_states(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  deepseek-chat:
    backend: openai-compat
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
    tier: default
  anthropic-claude:
    backend: anthropic-compat
    api_key: "${ANTHROPIC_API_KEY}"
    base_url: "https://api.anthropic.com/v1"
    model: "claude-opus-4-6"
    tier: mid
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-demo\n", encoding="utf-8")

    report = build_provider_probe_report(
        config_path=config_path,
        env_file=env_file,
        health_payload={
            "providers": {
                "deepseek-chat": {"healthy": True, "avg_latency_ms": 112.0},
                "anthropic-claude": {"healthy": False, "last_error": "insufficient_quota"},
            }
        },
    )

    by_name = {row["provider"]: row for row in report["providers"]}
    assert by_name["deepseek-chat"]["status"] == "ready"
    assert by_name["anthropic-claude"]["status"] == "missing-key"
    assert by_name["deepseek-chat"]["transport_profile"] == "openai-compatible"
    rendered = render_provider_probe_text(report)
    assert "Configured: 2 | Ready now: 1" in rendered
    assert "- deepseek-chat  (ready)" in rendered
    assert "transport: openai-compatible | native | confidence: high" in rendered


def test_list_client_scenarios_exposes_opencode_quality_path(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-demo\nOPENAI_API_KEY=sk-openai\nANTHROPIC_API_KEY=sk-ant\n",
        encoding="utf-8",
    )

    scenarios = list_client_scenarios(env_file=env_file, config_path=tmp_path / "missing.yaml")
    by_id = {item["id"]: item for item in scenarios}

    assert by_id["opencode-quality"]["routing_mode"] == "premium"
    assert "anthropic-claude" in by_id["opencode-quality"]["ready_providers"]
    assert any("anthropic/opus-4.6:" in line for line in by_id["opencode-quality"]["route_mirrors"])
    assert any(
        line.startswith("anthropic/opus-4.6 ->")
        for line in by_id["opencode-quality"]["degrade_chains"]
    )


def test_apply_client_scenario_sets_client_profile_mode_and_adds_providers(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
fallback_chain:
  - deepseek-chat
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    opencode:
      routing_mode: auto
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-demo\nOPENAI_API_KEY=sk-openai\nANTHROPIC_API_KEY=sk-ant\n",
        encoding="utf-8",
    )

    payload = apply_client_scenario(
        scenario_id="opencode-quality",
        config_path=config_path,
        env_file=env_file,
    )

    assert payload["config"]["client_profiles"]["profiles"]["opencode"]["routing_mode"] == "premium"
    assert "anthropic-claude" in payload["config"]["providers"]
    summary = render_client_scenario_summary(payload)
    assert "Scenario: opencode / quality" in summary
    assert "Operator guidance" in summary
    assert "best when:" in summary
    assert "Change preview" in summary


def test_render_client_scenarios_text_mentions_opencode_free(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("KILOCODE_API_KEY=kilo-demo\nBLACKBOX_API_KEY=bb-demo\n", encoding="utf-8")

    rendered = render_client_scenarios_text(env_file=env_file, config_path=tmp_path / "none.yaml")

    assert "opencode / free" in rendered
    assert "budget: free" in rendered
    assert "best when:" in rendered
    assert "tradeoff:" in rendered
    assert "known route mirrors:" in rendered or "degrade chain:" in rendered
    assert "ready now" in rendered or "needs keys for" in rendered
