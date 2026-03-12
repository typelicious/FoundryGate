from __future__ import annotations

from pathlib import Path

from foundrygate.onboarding import build_onboarding_report, render_onboarding_report


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
    assert "local-worker: local-worker / openai-compat / local / ready" in text
