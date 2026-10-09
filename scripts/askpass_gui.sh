#!/usr/bin/env bash
# GUI credential prompt for the unattended systemd timer runs: when git
# pushes and the credential cache is cold (usually right after boot),
# core.askPass points here and a zenity password dialog pops up instead
# of a terminal prompt. Without a graphical session the script exits 1,
# the push fails cleanly, and a later run pushes instead.
set -euo pipefail

prompt="${1:-Password:}"

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "askpass_gui: no graphical session, cannot prompt" >&2
    exit 1
fi
if ! command -v zenity >/dev/null 2>&1; then
    echo "askpass_gui: zenity not installed" >&2
    exit 1
fi

# --timeout so a boot while away cannot wedge the build run forever
answer="$(zenity --password --title="rss-feeds: git push" \
    --text="$prompt" --timeout=180 2>/dev/null)" || {
    echo "askpass_gui: dialog dismissed, timed out or no display" >&2
    exit 1
}
printf '%s' "$answer"
