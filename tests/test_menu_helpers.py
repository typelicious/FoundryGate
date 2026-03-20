from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fake_curl(tmp_path: Path, routes: dict[str, str]) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    route_json = json.dumps(routes)
    fake_curl.write_text(
        f"""#!/usr/bin/env python3
import json
import sys

routes = {route_json}
url = sys.argv[-1]
for suffix, payload in routes.items():
    if url.endswith(suffix):
        sys.stdout.write(payload)
        raise SystemExit(0)
sys.stderr.write(f"no fake payload for {{url}}\\n")
raise SystemExit(22)
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    return fake_bin


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


def test_faigate_menu_quit_renders_snapshot_and_tip(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8092
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    openclaw: {}
    opencode: {}
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
        ["bash", "scripts/faigate-menu"],
        cwd=REPO_ROOT,
        env=env,
        input="q\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Gateway" in result.stdout
    assert "Default mode" in result.stdout
    assert "Providers" in result.stdout
    assert "Preset matches" in result.stdout
    assert "Best next step" in result.stdout
    assert "opencode" in result.stdout
    assert "Tip:" in result.stdout


def test_faigate_status_help_lists_summary_and_raw_modes():
    result = subprocess.run(
        ["bash", "scripts/faigate-status", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-status" in result.stdout
    assert "--summary|--raw" in result.stdout


def test_faigate_logs_help_lists_follow_and_lines_options():
    result = subprocess.run(
        ["bash", "scripts/faigate-logs", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-logs" in result.stdout
    assert "--follow" in result.stdout
    assert "--lines N" in result.stdout


def test_faigate_restart_help_lists_verify_options():
    result = subprocess.run(
        ["bash", "scripts/faigate-restart", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-restart" in result.stdout
    assert "--no-verify" in result.stdout
    assert "--timeout N" in result.stdout


def test_faigate_update_help_is_safe_and_lists_purpose():
    result = subprocess.run(
        ["bash", "scripts/faigate-update", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-update" in result.stdout
    assert "/opt/faigate" in result.stdout


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
    assert "--recommended" in result.stdout


def test_faigate_config_overview_help_lists_output_modes():
    result = subprocess.run(
        ["bash", "scripts/faigate-config-overview", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-config-overview" in result.stdout
    assert "--json|--text" in result.stdout


def test_faigate_config_overview_json_summarizes_current_config(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8091
  log_level: "warning"
providers:
  deepseek-chat:
    backend: openai-compat
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
    tier: default
routing_modes:
  enabled: true
  default: premium
  modes:
    auto: {}
    premium: {}
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic:
      routing_mode: premium
model_shortcuts:
  enabled: true
  shortcuts:
    ds:
      target: deepseek-chat
      aliases: [chat]
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
        ["bash", "scripts/faigate-config-overview", "--json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = yaml.safe_load(result.stdout)

    assert payload["server"]["port"] == 8091
    assert payload["routing_modes"]["default"] == "premium"
    assert payload["providers"][0]["name"] == "deepseek-chat"
    assert payload["client_profiles"][0]["name"] == "generic"
    assert payload["shortcuts"][0]["name"] == "ds"


def test_faigate_service_lib_detects_homebrew_runtime_paths(tmp_path: Path):
    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = "/opt/homebrew/etc/faigate/config.yaml"

    result = subprocess.run(
        [
            "bash",
            "-lc",
            "source scripts/faigate-service-lib.sh && "
            "if faigate_is_homebrew_runtime; then echo yes; else echo no; fi && "
            "faigate_service_target && "
            "faigate_logs_stdout_path && "
            "faigate_service_manager",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    lines = result.stdout.strip().splitlines()
    assert lines[0] == "yes"
    assert lines[1] == "homebrew.mxcl.faigate"
    assert lines[2] == "/opt/homebrew/var/log/faigate/output.log"
    assert lines[3] == "brew services (launchd)"


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


def test_faigate_client_integrations_text_shows_recommended_cards_and_more_available(
    tmp_path: Path,
):
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
client_profiles:
  enabled: true
  default: generic
  presets: [openclaw, n8n, cli]
  profiles:
    generic: {}
    openclaw: {}
    n8n: {}
    cli: {}
    opencode: {}
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
        ["bash", "scripts/faigate-client-integrations"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Recommended clients now" in result.stdout
    assert "Best next step: opencode" in result.stdout
    assert "- openclaw" in result.stdout
    assert "- n8n" in result.stdout
    assert "- cli" in result.stdout
    assert "More available" in result.stdout
    assert "Use --client NAME for a detailed drilldown." in result.stdout


def test_faigate_client_integrations_text_drilldown_for_opencode(tmp_path: Path):
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    opencode: {}
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
        ["bash", "scripts/faigate-client-integrations", "--client", "opencode"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Client drilldown" in result.stdout
    assert "- opencode: ready" in result.stdout
    assert "best for: Coding-heavy editor and agent flows" in result.stdout
    assert "header: X-faigate-Client: opencode" in result.stdout


def test_faigate_config_wizard_text_candidates_are_compact(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
    opencode: {}
fallback_chain: [deepseek-chat]
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=test-key",
                "GEMINI_API_KEY=gm-key",
                "OPENROUTER_API_KEY=or-key",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            "scripts/faigate-config-wizard",
            "--env-file",
            str(env_file),
            "--purpose",
            "coding",
            "--client",
            "opencode",
            "--current-config",
            str(config_file),
            "--list-candidates",
            "--text-candidates",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "FAIGATE_PYTHON": sys.executable},
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Ready now" in result.stdout
    assert "More options if you add keys" in result.stdout
    assert "deepseek-chat  (recommended · already in config)" in result.stdout
    assert "openai-gpt4o  (needs OPENAI_API_KEY)" in result.stdout
    assert "discovery_env_var" not in result.stdout


def test_faigate_auto_update_parses_payload_without_mapfile(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    payload = json.dumps(
        {
            "current_version": "1.4.5",
            "latest_version": "1.4.5",
            "status": "ok",
            "update_type": "current",
            "recommended_action": "No action needed",
            "auto_update": {
                "enabled": False,
                "eligible": False,
                "blocked_reason": "Auto-update is disabled",
                "apply_command": "faigate-update",
                "verification": {
                    "enabled": False,
                    "command": "faigate-health",
                    "timeout_seconds": 30,
                    "rollback_command": "",
                },
            },
        }
    )
    fake_curl.write_text(
        f"""#!/usr/bin/env bash
cat <<'EOF'
{payload}
EOF
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", "scripts/faigate-auto-update"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Current: 1.4.5" in result.stdout
    assert "Auto-update: disabled" in result.stdout


def test_faigate_health_summarizes_payload(tmp_path: Path):
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "status": "ok",
                    "summary": {
                        "providers_total": 3,
                        "providers_healthy": 2,
                        "providers_unhealthy": 1,
                    },
                    "coverage": {
                        "chat": {"healthy": 2, "total": 3},
                        "reasoning": {"healthy": 1, "total": 1},
                    },
                    "providers": {
                        "deepseek-chat": {"healthy": True},
                        "gemini-flash": {"healthy": True},
                        "openrouter-fallback": {"healthy": False},
                    },
                }
            )
        },
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", "scripts/faigate-health"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Status: ok" in result.stdout
    assert "Providers: 2/3 healthy" in result.stdout
    assert "Coverage: chat 2/3, reasoning 1/1" in result.stdout


def test_faigate_update_check_warns_on_runtime_mismatch(tmp_path: Path):
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/api/update": json.dumps(
                {
                    "enabled": True,
                    "current_version": "1.2.3",
                    "latest_version": "1.4.5",
                    "update_available": True,
                    "repository": "typelicious/FoundryGate",
                    "release_url": "",
                    "published_at": "",
                    "checked_at": 0,
                    "status": "ok",
                    "release_channel": "stable",
                    "update_type": "minor",
                    "alert_level": "warning",
                    "recommended_action": "Upgrade recommended",
                    "auto_update": {
                        "enabled": False,
                        "eligible": False,
                        "blocked_reason": "Auto-update is disabled",
                        "apply_command": "faigate-update",
                    },
                }
            )
        },
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-update-check"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Current runtime: 1.2.3" in result.stdout
    assert "Repository: typelicious/FoundryGate" in result.stdout
    assert "Warning: /api/update is reporting a different repository" in result.stdout
    assert "Warning: local helper version is" in result.stdout


def test_faigate_menu_status_models_flow_formats_model_list(tmp_path: Path):
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
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
fallback_chain: [deepseek-chat]
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=test-key\n", encoding="utf-8")
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "status": "ok",
                    "summary": {"providers_total": 1, "providers_healthy": 1},
                }
            ),
            "/v1/models": json.dumps(
                {"data": [{"id": "auto"}, {"id": "deepseek-chat"}, {"id": "gemini-flash"}]}
            ),
        },
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-menu"],
        cwd=REPO_ROOT,
        env=env,
        input="2\n3\n\nc\nq\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Exposed models: 3" in result.stdout
    assert "1. auto (recommended default)" in result.stdout
    assert "2. deepseek-chat" in result.stdout


def test_faigate_menu_update_flow_surfaces_runtime_mismatch_warning(tmp_path: Path):
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
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "status": "ok",
                    "summary": {"providers_total": 0, "providers_healthy": 0},
                }
            ),
            "/api/update": json.dumps(
                {
                    "enabled": True,
                    "current_version": "1.2.3",
                    "latest_version": "1.4.5",
                    "update_available": True,
                    "repository": "typelicious/FoundryGate",
                    "status": "ok",
                    "release_channel": "stable",
                    "update_type": "minor",
                    "recommended_action": "Upgrade recommended",
                    "auto_update": {
                        "enabled": False,
                        "eligible": False,
                        "blocked_reason": "Auto-update is disabled",
                    },
                }
            ),
        },
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-menu"],
        cwd=REPO_ROOT,
        env=env,
        input="8\n1\n\nc\nq\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Current runtime: 1.2.3" in result.stdout
    assert "Warning: /api/update is reporting a different repository" in result.stdout


def test_faigate_menu_quick_setup_renders_guidance(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
providers: {}
fallback_chain: []
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "status": "ok",
                    "summary": {"providers_total": 0, "providers_healthy": 0},
                }
            )
        },
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", "scripts/faigate-menu"],
        cwd=REPO_ROOT,
        env=env,
        input="1\nc\nq\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "fusionAIze Gate Quick Setup" in result.stdout
    assert "Start with API Keys" in result.stdout


def test_faigate_menu_quick_setup_validate_shows_next_steps(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
  log_level: "info"
providers: {}
fallback_chain: []
client_profiles:
  enabled: true
  default: generic
  profiles:
    generic: {}
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "status": "ok",
                    "summary": {"providers_total": 0, "providers_healthy": 0},
                }
            ),
            "/v1/models": json.dumps({"data": [{"id": "auto"}]}),
        },
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-menu"],
        cwd=REPO_ROOT,
        env=env,
        input="1\n3\n\nc\nq\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Validation completed." in result.stdout
    assert "Fix any missing env or endpoint warnings before restart work." in result.stdout


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
    assert "optional upstream provider overrides" in result.stdout
    assert "OPENAI_BASE_URL (upstream)" in result.stdout


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
