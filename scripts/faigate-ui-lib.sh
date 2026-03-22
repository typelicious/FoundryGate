#!/usr/bin/env bash
set -euo pipefail

FAIGATE_UI_RESET=$'\033[0m'
FAIGATE_UI_BOLD=$'\033[1m'
FAIGATE_UI_DIM=$'\033[2m'
FAIGATE_UI_CYAN=$'\033[36m'
FAIGATE_UI_GREEN=$'\033[32m'
FAIGATE_UI_YELLOW=$'\033[33m'
FAIGATE_UI_RED=$'\033[31m'
FAIGATE_UI_BRAND_BLUE=$'\033[38;2;0;82;204m'
FAIGATE_UI_BRAND_YELLOW=$'\033[38;2;196;217;0m'
FAIGATE_UI_BRAND_GREEN=$'\033[38;2;46;167;93m'

faigate_ui_clear() {
  if [ -t 1 ] && command -v clear >/dev/null 2>&1; then
    clear
  fi
}

faigate_ui_has_color() {
  [ -t 1 ] && [ -z "${NO_COLOR:-}" ]
}

faigate_ui_version() {
  if [ -n "${FAIGATE_UI_VERSION:-}" ]; then
    printf "%s" "$FAIGATE_UI_VERSION"
    return 0
  fi

  if [ -n "${FAIGATE_PYTHON:-}" ] && [ -x "${FAIGATE_PYTHON}" ]; then
    local version
    version="$("${FAIGATE_PYTHON}" - <<'PY' 2>/dev/null || true
from faigate import __version__
print(__version__)
PY
)"
    if [ -n "$version" ]; then
      printf "v%s" "$version"
      return 0
    fi
  fi

  local script_dir repo_version
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_version="$(
    python3 - <<'PY' "$script_dir/../faigate/__init__.py" 2>/dev/null || true
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
if path.exists():
    match = re.search(r'__version__ = "([^"]+)"', path.read_text())
    if match:
        print(f"v{match.group(1)}")
PY
  )"
  printf "%s" "$repo_version"
}

faigate_ui_logo() {
  local version_text="${1:-}"
  if faigate_ui_has_color; then
    printf '  %b%s%b%b%s%b%b%s%b  %b%s%b\n' \
      "$FAIGATE_UI_BRAND_BLUE" "▐▘    ▘    " "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_YELLOW" "▄▖▄▖" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_BLUE" "    " "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_GREEN" "▄▖  ▗" "$FAIGATE_UI_RESET"
    printf '  %b%s%b%b%s%b%b%s%b  %b%s%b\n' \
      "$FAIGATE_UI_BRAND_BLUE" "▜▘▌▌▛▘▌▛▌▛▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_YELLOW" "▌▌▐ " "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_BLUE" "▀▌█▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_GREEN" "▌ ▀▌▜▘█▌" "$FAIGATE_UI_RESET"
    printf '  %b%s%b%b%s%b%b%s%b  %b%s%b' \
      "$FAIGATE_UI_BRAND_BLUE" "▐ ▙▌▄▌▌▙▌▌▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_YELLOW" "▛▌▟▖" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_BLUE" "▙▖▙▖" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_BRAND_GREEN" "▙▌█▌▐▖▙▖" "$FAIGATE_UI_RESET"
    if [ -n "$version_text" ]; then
      printf "   %b%s%b" "$FAIGATE_UI_DIM" "$version_text" "$FAIGATE_UI_RESET"
    fi
    printf "\n"
  else
    printf "  %s\n" "▐▘    ▘    ▄▖▄▖      ▄▖  ▗"
    printf "  %s\n" "▜▘▌▌▛▘▌▛▌▛▌▌▌▐ ▀▌█▌  ▌ ▀▌▜▘█▌"
    printf "  %s" "▐ ▙▌▄▌▌▙▌▌▌▛▌▟▖▙▖▙▖  ▙▌█▌▐▖▙▖"
    if [ -n "$version_text" ]; then
      printf "   %s" "$version_text"
    fi
    printf "\n"
  fi
}

faigate_ui_header() {
  local title="${1:-fusionAIze Gate}"
  local subtitle="${2:-}"
  local version_text
  version_text="$(faigate_ui_version)"
  faigate_ui_clear
  printf "\n"
  faigate_ui_logo "$version_text"
  printf "\n"
  printf "  %b%s%b\n" "$FAIGATE_UI_BOLD" "$title" "$FAIGATE_UI_RESET"
  if [ -n "$subtitle" ]; then
    printf "  %b%s%b\n" "$FAIGATE_UI_DIM" "$subtitle" "$FAIGATE_UI_RESET"
  fi
  printf "  %s\n\n" "──────────────────────────────────────────────────────────────"
}

faigate_ui_info() {
  printf "  %bℹ%b  %s\n" "$FAIGATE_UI_CYAN" "$FAIGATE_UI_RESET" "$1"
}

faigate_ui_success() {
  printf "  %b✔%b  %s\n" "$FAIGATE_UI_GREEN" "$FAIGATE_UI_RESET" "$1"
}

faigate_ui_warn() {
  printf "  %b!%b  %s\n" "$FAIGATE_UI_YELLOW" "$FAIGATE_UI_RESET" "$1"
}

faigate_ui_error() {
  printf "  %b✖%b  %s\n" "$FAIGATE_UI_RED" "$FAIGATE_UI_RESET" "$1" >&2
}

faigate_ui_pause() {
  printf "\n  Press Enter to continue..."
  read -r _
}

faigate_ui_tip() {
  printf "  %bTip:%b %s\n" "$FAIGATE_UI_CYAN" "$FAIGATE_UI_RESET" "$1"
}
