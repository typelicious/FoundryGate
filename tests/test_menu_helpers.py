from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

EXECUTABLE_HELPERS = [
    "scripts/faigate-auto-update",
    "scripts/faigate-client-integrations",
    "scripts/faigate-config-overview",
    "scripts/faigate-config-wizard",
    "scripts/faigate-dashboard",
    "scripts/faigate-logs",
    "scripts/faigate-onboarding-report",
    "scripts/faigate-onboarding-validate",
    "scripts/faigate-provider-discovery",
    "scripts/faigate-restart",
    "scripts/faigate-start",
    "scripts/faigate-status",
    "scripts/faigate-stop",
    "scripts/faigate-update",
]

EXPECTED_BREW_HELPERS = [
    "faigate-config-wizard",
    "faigate-status",
    "faigate-restart",
    "faigate-logs",
    "faigate-start",
    "faigate-stop",
    "faigate-update",
    "faigate-auto-update",
]


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


def test_packaged_helper_scripts_keep_execute_bit():
    for helper in EXECUTABLE_HELPERS:
        mode = (REPO_ROOT / helper).stat().st_mode
        assert mode & stat.S_IXUSR, helper


def test_homebrew_formula_wraps_expected_user_facing_helpers():
    formula = (REPO_ROOT / "Formula" / "faigate.rb").read_text(encoding="utf-8")
    match = re.search(r"%w\[(.*?)\]\.each", formula, re.S)
    assert match is not None
    helpers = match.group(1).split()

    for helper in EXPECTED_BREW_HELPERS:
        assert helper in helpers, helper


def test_faigate_ui_logo_plaintext_includes_version_and_expected_shape():
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["FAIGATE_UI_VERSION"] = "v1.6.3"
    result = subprocess.run(
        [
            "bash",
            "-lc",
            'source scripts/faigate-ui-lib.sh && faigate_ui_logo "$(faigate_ui_version)"',
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "▐▘    ▘    ▄▖▄▖      ▄▖  ▗" in result.stdout
    assert "▜▘▌▌▛▘▌▛▌▛▌▌▌▐ ▀▌█▌  ▌ ▀▌▜▘█▌" in result.stdout
    assert "▐ ▙▌▄▌▌▙▌▌▌▛▌▟▖▙▖▙▖  ▙▌█▌▐▖▙▖" in result.stdout
    assert "v1.6.3" in result.stdout


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
    assert "Dashboard" in result.stdout
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


def test_faigate_doctor_warns_when_config_contains_wizard_suggestions(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
purpose: coding
client: opencode
suggestions:
  recommended_add:
    - provider: anthropic-claude
server:
  host: "127.0.0.1"
  port: 8090
providers:
  deepseek-chat:
    backend: openai-compat
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
    model: "deepseek-chat"
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
        ["bash", "scripts/faigate-doctor"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "config appears to contain wizard suggestions" in result.stdout


def test_faigate_service_lib_detects_homebrew_runtime_paths(tmp_path: Path):
    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = "/opt/homebrew/etc/faigate/config.yaml"

    result = subprocess.run(
        [
            "bash",
            "-lc",
            "source scripts/faigate-service-lib.sh && "
            "faigate_platform(){ echo Darwin; } && "
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


def test_faigate_client_integrations_interactive_drilldown(tmp_path: Path):
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
        ["bash", "scripts/faigate-client-integrations", "--interactive"],
        cwd=REPO_ROOT,
        env=env,
        input="1\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Open client drilldown" in result.stdout
    assert "1)  opencode" in result.stdout
    assert "Client drilldown" in result.stdout


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
        input="3\n3\n\nc\nq\n",
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
        input="9\n1\n\nc\nq\n",
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
    assert "Start with Provider Setup" in result.stdout


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
        input="1\n5\n\nc\nq\n",
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


def test_faigate_provider_setup_help_lists_supported_modes():
    result = subprocess.run(
        ["bash", "scripts/faigate-provider-setup", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-provider-setup" in result.stdout
    assert "--known --text" in result.stdout
    assert "--current --text" in result.stdout


def test_faigate_provider_probe_help_lists_usage():
    result = subprocess.run(
        ["bash", "scripts/faigate-provider-probe", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-provider-probe" in result.stdout
    assert "--json|--text" in result.stdout


def test_faigate_dashboard_help_lists_views():
    result = subprocess.run(
        ["bash", "scripts/faigate-dashboard", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-dashboard" in result.stdout
    assert "--providers" in result.stdout
    assert "--alerts" in result.stdout


def test_faigate_dashboard_overview_summarizes_live_stats(tmp_path: Path):
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
                    "providers": {
                        "deepseek-chat": {"healthy": True, "tier": "default"},
                        "gemini-flash": {"healthy": True, "tier": "cheap"},
                        "openrouter-fallback": {
                            "healthy": False,
                            "tier": "fallback",
                            "last_error": "rate limit",
                        },
                    },
                }
            ),
            "/api/stats": json.dumps(
                {
                    "totals": {
                        "total_requests": 120,
                        "total_failures": 3,
                        "total_prompt_tokens": 42000,
                        "total_compl_tokens": 21000,
                        "total_cost_usd": 3.4,
                        "avg_latency_ms": 812.5,
                        "first_request": 1700000000,
                        "last_request": 4102444800,
                    },
                    "providers": [
                        {
                            "provider": "deepseek-chat",
                            "requests": 72,
                            "failures": 1,
                            "total_tokens": 36000,
                            "cost_usd": 1.4,
                            "avg_latency_ms": 610.0,
                        },
                        {
                            "provider": "openrouter-fallback",
                            "requests": 28,
                            "failures": 2,
                            "total_tokens": 19000,
                            "cost_usd": 1.6,
                            "avg_latency_ms": 1240.0,
                        },
                    ],
                    "routing": [
                        {
                            "layer": "fallback",
                            "rule_name": "fallback",
                            "provider": "openrouter-fallback",
                            "requests": 28,
                            "cost_usd": 1.6,
                        },
                        {
                            "layer": "heuristic",
                            "rule_name": "default",
                            "provider": "deepseek-chat",
                            "requests": 92,
                            "cost_usd": 1.4,
                        },
                    ],
                    "client_totals": [
                        {
                            "client_profile": "opencode",
                            "client_tag": "opencode",
                            "requests": 74,
                            "failures": 2,
                            "success_pct": 97.3,
                            "total_tokens": 44000,
                            "cost_usd": 2.5,
                            "cost_per_request_usd": 0.041,
                            "avg_latency_ms": 860.0,
                            "providers": "deepseek-chat,openrouter-fallback",
                        }
                    ],
                    "client_highlights": {
                        "top_requests": {
                            "client_profile": "opencode",
                            "client_tag": "opencode",
                            "requests": 74,
                            "cost_usd": 2.5,
                            "avg_latency_ms": 860.0,
                            "total_tokens": 44000,
                        }
                    },
                    "operator_actions": [
                        {
                            "event_type": "update",
                            "action": "check",
                            "status": "unavailable",
                            "update_type": "unknown",
                            "events": 2,
                        }
                    ],
                    "hourly": [
                        {"hour_offset": 0, "requests": 18, "cost_usd": 0.3, "tokens": 9000},
                        {"hour_offset": 1, "requests": 12, "cost_usd": 0.2, "tokens": 7000},
                    ],
                    "daily": [
                        {
                            "day": "2026-03-18",
                            "requests": 40,
                            "cost_usd": 1.2,
                            "tokens": 18000,
                            "failures": 1,
                        },
                        {
                            "day": "2026-03-19",
                            "requests": 80,
                            "cost_usd": 2.2,
                            "tokens": 45000,
                            "failures": 2,
                        },
                    ],
                }
            ),
        },
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["FAIGATE_DB_PATH"] = str(tmp_path / "faigate.db")

    result = subprocess.run(
        ["bash", "scripts/faigate-dashboard", "--overview"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "fusionAIze Gate Dashboard" in result.stdout
    assert "Source: live-api" in result.stdout
    assert "Top provider        deepseek-chat" in result.stdout
    assert "Top client          opencode" in result.stdout
    assert "Fallback traffic    28 requests" in result.stdout
    assert "Top alert" in result.stdout
    assert "Decision support" in result.stdout


def test_faigate_provider_probe_summarizes_config_env_and_health(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
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
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "providers": {
                        "deepseek-chat": {"healthy": True, "avg_latency_ms": 42.0},
                        "anthropic-claude": {"healthy": False, "last_error": "rate limit"},
                    }
                }
            )
        },
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-provider-probe"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Provider probe" in result.stdout
    assert "Configured: 2 | Ready now: 1" in result.stdout
    assert "- deepseek-chat  (ready)" in result.stdout
    assert "- anthropic-claude  (missing-key)" in result.stdout


def test_faigate_client_scenarios_help_lists_usage():
    result = subprocess.run(
        ["bash", "scripts/faigate-client-scenarios", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "faigate-client-scenarios" in result.stdout
    assert "--scenario ID --apply" in result.stdout


def test_faigate_client_scenarios_text_lists_opencode_templates(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-demo\nOPENAI_API_KEY=sk-openai\nANTHROPIC_API_KEY=sk-ant\n",
        encoding="utf-8",
    )
    config_file = tmp_path / "config.yaml"
    config_file.write_text("providers: {}\n", encoding="utf-8")

    env = os.environ.copy()
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-client-scenarios", "--text"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Client scenarios" in result.stdout
    assert "opencode / quality" in result.stdout
    assert "ready now:" in result.stdout
    assert "budget / free: kilocode (free coding coverage)" in result.stdout
    assert "family note: Anthropic is currently represented by one quality lane." in result.stdout
    assert "family coverage: Anthropic: quality lane active" in result.stdout


def test_faigate_client_scenarios_write_shows_client_specific_next_steps(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=sk-demo\nOPENAI_API_KEY=sk-openai\nANTHROPIC_API_KEY=sk-ant\n",
        encoding="utf-8",
    )
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

    env = os.environ.copy()
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-client-scenarios"],
        cwd=REPO_ROOT,
        env=env,
        input="2\n2\n\n",
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Client scenario applied." in result.stdout
    assert "new opencode profile default" in result.stdout
    assert "drill into opencode Details" in result.stdout


def test_faigate_provider_discovery_interactive_opens_provider_detail(tmp_path: Path):
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
    tier: default
  openrouter-fallback:
    backend: openai-compat
    api_key: "${OPENROUTER_API_KEY}"
    base_url: "https://openrouter.ai/api/v1"
    model: "openrouter/auto"
    tier: fallback
""".strip(),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-provider-discovery", "--interactive"],
        cwd=REPO_ROOT,
        env=env,
        input="1\n1\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Discovery filters" in result.stdout
    assert "Open provider detail" in result.stdout
    assert "official source:" in result.stdout
    assert "deepseek-chat" in result.stdout


def test_faigate_dashboard_interactive_opens_provider_detail(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
providers: {}
""".strip(),
        encoding="utf-8",
    )
    fake_bin = _write_fake_curl(
        tmp_path,
        {
            "/health": json.dumps(
                {
                    "summary": {"providers_total": 1, "providers_unhealthy": 0},
                    "providers": {"deepseek-chat": {"healthy": True, "tier": "default"}},
                }
            ),
            "/api/stats": json.dumps(
                {
                    "totals": {
                        "total_requests": 42,
                        "total_failures": 1,
                        "avg_latency_ms": 850,
                        "total_prompt_tokens": 12000,
                        "total_compl_tokens": 4000,
                        "total_cost_usd": 0.42,
                    },
                    "providers": [
                        {
                            "provider": "deepseek-chat",
                            "requests": 42,
                            "failures": 1,
                            "avg_latency_ms": 850,
                            "cost_usd": 0.42,
                            "total_tokens": 16000,
                            "prompt_tokens": 12000,
                            "completion_tokens": 4000,
                        }
                    ],
                    "clients": [
                        {
                            "client_tag": "opencode",
                            "client_profile": "opencode",
                            "requests": 42,
                            "success_pct": 97.6,
                            "avg_latency_ms": 850,
                            "cost_usd": 0.42,
                            "total_tokens": 16000,
                            "providers": "deepseek-chat",
                        }
                    ],
                    "routing": [],
                    "client_totals": [],
                    "hourly": [],
                    "daily": [],
                    "operator_actions": [],
                }
            ),
        },
    )
    env = os.environ.copy()
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        ["bash", "scripts/faigate-dashboard", "--interactive"],
        cwd=REPO_ROOT,
        env=env,
        input="4\n1\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert "Provider Detail" in result.stdout
    assert "Provider detail: deepseek-chat" in result.stdout
    assert "Status            live-healthy" in result.stdout


def test_faigate_provider_setup_known_text_lists_curated_sources(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-demo\n", encoding="utf-8")
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
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

    env = os.environ.copy()
    env["FAIGATE_ENV_FILE"] = str(env_file)
    env["FAIGATE_CONFIG_FILE"] = str(config_file)
    env["FAIGATE_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", "scripts/faigate-provider-setup", "--known", "--text"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Known providers" in result.stdout
    assert "deepseek-chat  (key ready · already in config)" in result.stdout
    assert "anthropic-claude  (needs ANTHROPIC_API_KEY)" in result.stdout


def test_faigate_menu_quick_setup_lists_provider_setup(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8090
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
    env = os.environ.copy()
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

    assert "Provider Setup" in result.stdout
    assert "Add known providers, custom endpoints, or local workers" in result.stdout


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
