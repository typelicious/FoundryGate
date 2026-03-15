from __future__ import annotations

from pathlib import Path

from foundrygate.onboarding import (
    build_onboarding_report,
    build_onboarding_validation,
    render_onboarding_report,
    render_onboarding_validation,
)


def test_onboarding_report_marks_missing_api_keys_and_presets(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain:
  - deepseek-chat
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
    tier: default
client_profiles:
  enabled: true
  default: generic
  presets: ["openclaw"]
  profiles:
    generic: {}
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: false
  hooks: []
update_check:
  enabled: true
  repository: "typelicious/FoundryGate"
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=env_file)

    assert report["providers"]["total"] == 1
    assert report["providers"]["ready"] == 0
    assert report["providers"]["missing_api_keys"] == ["deepseek-chat"]
    assert report["clients"]["presets"] == ["openclaw"]
    assert report["integrations"]["openclaw"]["recommended"] is True
    assert report["integrations"]["n8n"]["recommended"] is False
    assert (
        "Keep auto_update disabled until the provider and client set is stable."
        in report["suggestions"]
    )


def test_onboarding_report_marks_local_worker_ready(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain:
  - local-worker
providers:
  local-worker:
    contract: local-worker
    backend: openai-compat
    base_url: "http://127.0.0.1:11434/v1"
    api_key: "local"
    model: "llama3"
    tier: local
    capabilities:
      local: true
      cloud: false
client_profiles:
  enabled: false
  profiles:
    generic: {}
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: false
  hooks: []
update_check:
  enabled: false
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=env_file)
    text = render_onboarding_report(report)

    assert report["providers"]["ready"] == 1
    assert report["providers"]["local_workers"] == 1
    assert report["provider_rollout"]["stage_1_primary"] == ["local-worker"]
    assert "local-worker: local-worker / openai-compat / local / ready" in text
    assert "- stage 1 primary: local-worker" in text
    assert "Integration quickstarts" in text
    assert "header: X-FoundryGate-Client: codex" in text


def test_onboarding_validation_blocks_missing_env_and_unready_providers(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain: []
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
    tier: default
  gemini-flash:
    backend: google-genai
    base_url: "https://generativelanguage.googleapis.com/v1beta"
    api_key: "${GEMINI_API_KEY}"
    model: "gemini-2.5-flash"
    tier: mid
client_profiles:
  enabled: false
  profiles:
    generic: {}
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: true
  hooks: []
update_check:
  enabled: false
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=tmp_path / ".env")
    validation = build_onboarding_validation(report)
    text = render_onboarding_validation(validation)

    assert validation["ok"] is False
    assert "Environment file is missing." in validation["blockers"]
    assert "No configured provider is ready." in validation["blockers"]
    assert "Fallback chain is empty for a multi-provider setup." in validation["blockers"]
    assert (
        "No ready primary provider is available for a staged multi-provider rollout."
        in validation["blockers"]
    )
    assert "Client profiles are disabled." in validation["warnings"]
    assert "Request hooks are enabled but no hooks are configured." in validation["warnings"]
    assert "Status: blocked" in text


def test_onboarding_validation_passes_for_ready_multi_provider_setup(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-demo\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain:
  - deepseek-chat
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
    tier: default
client_profiles:
  enabled: true
  default: generic
  presets: ["openclaw", "cli"]
  profiles:
    generic: {}
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: false
  hooks: []
update_check:
  enabled: true
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=env_file)
    validation = build_onboarding_validation(report)

    assert validation["ok"] is True
    assert validation["blockers"] == []


def test_onboarding_report_marks_all_builtin_integrations_ready(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-demo\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain:
  - deepseek-chat
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
    tier: default
client_profiles:
  enabled: true
  default: generic
  presets: ["openclaw", "n8n", "cli"]
  profiles:
    generic: {}
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: false
  hooks: []
update_check:
  enabled: true
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=env_file)

    assert report["integrations"]["openclaw"]["recommended"] is True
    assert report["integrations"]["n8n"]["recommended"] is True
    assert report["integrations"]["cli"]["recommended"] is True
    assert report["clients"]["matrix"][0]["name"] == "cli"
    assert report["clients"]["matrix"][0]["has_rule"] is True


def test_onboarding_report_includes_client_matrix_and_unmatched_profile_warning(
    tmp_path: Path,
):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-demo\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain:
  - deepseek-chat
providers:
  deepseek-chat:
    backend: openai-compat
    base_url: "https://api.deepseek.com/v1"
    api_key: "${DEEPSEEK_API_KEY}"
    model: "deepseek-chat"
    tier: default
client_profiles:
  enabled: true
  default: generic
  presets: ["n8n"]
  profiles:
    generic: {}
    local-only:
      capability_values:
        local: true
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: false
  hooks: []
update_check:
  enabled: false
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=env_file)
    validation = build_onboarding_validation(report)
    text = render_onboarding_report(report)

    local_only = next(row for row in report["clients"]["matrix"] if row["name"] == "local-only")

    assert local_only["matched_by"] == "default or explicit override"
    assert "capability values: local=True" in local_only["routing_intent"]
    assert (
        "Client profile 'local-only' has no match rule and only applies via explicit override."
        in validation["warnings"]
    )
    assert "Client matrix" in text
    assert "match: default or explicit override" in text


def test_onboarding_report_includes_provider_rollout_stages_and_gaps(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("PRIMARY_KEY=sk-primary\n", encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
fallback_chain:
  - image-worker
providers:
  primary-chat:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "${PRIMARY_KEY}"
    model: "primary-chat"
    tier: default
  image-worker:
    contract: image-provider
    backend: openai-compat
    base_url: "http://127.0.0.1:9000/v1"
    api_key: "${IMAGE_KEY}"
    model: "image-model"
    tier: specialty
    capabilities:
      image_generation: true
client_profiles:
  enabled: true
  default: generic
  presets: ["openclaw", "n8n"]
  profiles:
    generic: {}
  rules: []
routing_policies:
  enabled: false
  rules: []
request_hooks:
  enabled: false
  hooks: []
update_check:
  enabled: false
auto_update:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    report = build_onboarding_report(config_path=config_file, env_file=env_file)
    validation = build_onboarding_validation(report)
    text = render_onboarding_report(report)

    assert report["provider_rollout"]["stage_1_primary"] == ["primary-chat"]
    assert report["provider_rollout"]["stage_2_secondary"] == []
    assert report["provider_rollout"]["stage_3_modality"] == []
    assert report["provider_rollout"]["fallback_targets"] == [
        {"name": "image-worker", "configured": True, "ready": False}
    ]
    assert (
        "Image-capable providers are configured, but none are ready yet."
        in report["provider_rollout"]["gaps"]
    )
    assert (
        "Fallback chain is configured, but none of its targets are currently ready."
        in validation["warnings"]
    )
    assert "- stage 1 primary: primary-chat" in text
    assert "- fallback targets:" in text
