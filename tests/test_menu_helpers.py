from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_faigate_menu_help_lists_primary_sections():
    result = subprocess.run(
        ["bash", "scripts/faigate-menu", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "fusionAIze Gate" in result.stdout
    assert "Interactive control center" in result.stdout


def test_faigate_client_integrations_help_lists_usage():
    result = subprocess.run(
        ["bash", "scripts/faigate-client-integrations", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-client-integrations" in result.stdout
    assert "--client NAME" in result.stdout
    assert "--matrix" in result.stdout


def test_faigate_client_integrations_json_filters_one_client(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
providers:
  deepseek-chat:
    backend: openai-compat
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
    tier: default
routing_modes:
  enabled: true
  default: auto
  modes:
    auto: {}
    eco: {}
client_profiles:
  enabled: true
  default: generic
  presets: [openclaw, n8n, cli]
  profiles:
    generic: {}
    openclaw:
      routing_mode: auto
    n8n:
      routing_mode: eco
  rules:
    - profile: openclaw
      match:
        header_present: [x-openclaw-source]
fallback_chain: [deepseek-chat]
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=test-key\n", encoding="utf-8")

    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        [
            "bash",
            "scripts/faigate-client-integrations",
            "--json",
            "--client",
            "openclaw",
            "--matrix",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = yaml.safe_load(result.stdout)

    assert set(payload["integrations"]) == {"openclaw"}
    assert payload["integrations"]["openclaw"]["profile"] == "openclaw"
    assert payload["client_matrix"]
    assert any(row["name"] == "openclaw" for row in payload["client_matrix"])


def test_faigate_server_settings_updates_config_and_creates_backup(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
providers: {}
fallback_chain: []
""".strip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", "scripts/faigate-server-settings"],
        cwd=REPO_ROOT,
        env=env,
        input="\n9091\nwarning\n",
        capture_output=True,
        text=True,
        check=True,
    )

    updated = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    backups = list(tmp_path.glob("config.yaml.*.bak"))

    assert updated["server"] == {
        "host": "127.0.0.1",
        "port": 9091,
        "log_level": "warning",
    }
    assert backups
    assert "Updated HTTP settings" in result.stdout


def test_faigate_api_keys_updates_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["FAIGATE_ENV_FILE"] = str(env_file)

    prompt_lines = [
        "sk-ant-demo",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]

    result = subprocess.run(
        ["bash", "scripts/faigate-api-keys"],
        cwd=REPO_ROOT,
        env=env,
        input="\n".join(prompt_lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )

    written = env_file.read_text(encoding="utf-8")

    assert "ANTHROPIC_API_KEY=sk-ant-demo" in written
    assert "API key env updated" in result.stdout


def test_faigate_routing_settings_updates_default_and_profile_modes(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
routing_modes:
  enabled: true
  default: auto
  modes:
    auto: {}
    eco: {}
    premium: {}
client_profiles:
  enabled: true
  profiles:
    generic:
      routing_mode: auto
    n8n:
      routing_mode: eco
model_shortcuts:
  enabled: true
  shortcuts:
    ds:
      target: deepseek-chat
      aliases: [chat]
providers: {}
fallback_chain: []
""".strip(),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", "scripts/faigate-routing-settings"],
        cwd=REPO_ROOT,
        env=env,
        input="premium\n\npremium\n",
        capture_output=True,
        text=True,
        check=True,
    )

    updated = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    backups = list(tmp_path.glob("config.yaml.*.bak"))

    assert updated["routing_modes"]["default"] == "premium"
    assert updated["client_profiles"]["profiles"]["generic"]["routing_mode"] == "auto"
    assert updated["client_profiles"]["profiles"]["n8n"]["routing_mode"] == "premium"
    assert backups
    assert "Updated routing settings" in result.stdout
