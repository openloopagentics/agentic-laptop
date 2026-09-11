#!/usr/bin/env bash
# Session / power menu, in place of Omarchy's `omarchy-menu system`.
# Safe entries first; nothing fires without an explicit pick.
set -euo pipefail

choice="$(printf '%s\n' \
    "Lock" \
    "Suspend" \
    "Reload config" \
    "Log out (closes all windows)" \
    "Reboot" \
    "Shutdown" | hyprlauncher --dmenu)" || exit 0

case "$choice" in
    "Lock")            loginctl lock-session ;;
    "Suspend")         systemctl suspend ;;
    "Reload config")   hyprctl reload && notify-send -u low "Hyprland" "Config reloaded" ;;
    "Log out"*)        hyprctl dispatch 'hl.dsp.exit()' ;;
    "Reboot")          systemctl reboot ;;
    "Shutdown")        systemctl poweroff ;;
    *)                 exit 0 ;;
esac
