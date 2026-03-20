#!/usr/bin/env bash
set -euo pipefail

FAIGATE_UI_RESET=$'\033[0m'
FAIGATE_UI_BOLD=$'\033[1m'
FAIGATE_UI_DIM=$'\033[2m'
FAIGATE_UI_CYAN=$'\033[36m'
FAIGATE_UI_GREEN=$'\033[32m'
FAIGATE_UI_YELLOW=$'\033[33m'
FAIGATE_UI_RED=$'\033[31m'
FAIGATE_UI_ORANGE=$'\033[38;5;214m'
FAIGATE_UI_LIME=$'\033[38;5;190m'
FAIGATE_UI_GREEN2=$'\033[38;5;82m'
FAIGATE_UI_CYAN2=$'\033[38;5;45m'
FAIGATE_UI_BLUE2=$'\033[38;5;39m'
FAIGATE_UI_MAGENTA2=$'\033[38;5;207m'
FAIGATE_UI_CORAL=$'\033[38;5;203m'

faigate_ui_clear() {
  if [ -t 1 ] && command -v clear >/dev/null 2>&1; then
    clear
  fi
}

faigate_ui_has_color() {
  [ -t 1 ] && [ -z "${NO_COLOR:-}" ]
}

faigate_ui_logo() {
  if faigate_ui_has_color; then
    printf "  %b%s%b%b%s%b%b%s%b\n" \
      "$FAIGATE_UI_ORANGE" "▐▘    ▘    " "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_GREEN2" "▄▖▄▖      " "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_MAGENTA2" "▄▖  ▗   " "$FAIGATE_UI_RESET"
    printf "  %b%s%b%b%s%b%b%s%b%b%s%b%b%s%b\n" \
      "$FAIGATE_UI_ORANGE" "▜▘▌▌▛▘▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_LIME" " ▛▌▛▌▌▌▐ ▀▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_CYAN2" "█▌  ▌ ▀▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_MAGENTA2" "▜▘" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_CORAL" "█▌" "$FAIGATE_UI_RESET"
    printf "  %b%s%b%b%s%b%b%s%b%b%s%b\n" \
      "$FAIGATE_UI_ORANGE" "▐ ▙▌▄▌▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_GREEN2" "▙▌▌▌▛▌▟▖▙▖" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_CYAN2" "▙▖  ▙▌█▌" "$FAIGATE_UI_RESET" \
      "$FAIGATE_UI_CORAL" "▐▖▙▖" "$FAIGATE_UI_RESET"
  else
    printf "  %s\n" "▐▘    ▘    ▄▖▄▖      ▄▖  ▗   "
    printf "  %s\n" "▜▘▌▌▛▘▌ ▛▌▛▌▌▌▐ ▀▌█▌  ▌ ▀▌▜▘█▌"
    printf "  %s\n" "▐ ▙▌▄▌▌▙▌▌▌▛▌▟▖▙▖▙▖  ▙▌█▌▐▖▙▖"
  fi
}

faigate_ui_header() {
  local title="${1:-fusionAIze Gate}"
  local subtitle="${2:-}"
  faigate_ui_clear
  printf "\n"
  faigate_ui_logo
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
