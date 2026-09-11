#!/usr/bin/env bash
# Wallpaper manager for hyprpaper.
#
#   wallpaper.sh            apply the remembered wallpaper (random if none) - used at login
#   wallpaper.sh <path>     apply a specific image
#   wallpaper.sh random     apply a random one from the library
#   wallpaper.sh menu       pick one with hyprlauncher
#   wallpaper.sh list       print the library
set -euo pipefail

LIB="$HOME/Pictures/wallpapers"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/hypr"
CURRENT="$STATE/wallpaper"
mkdir -p "$STATE"

list() {
    find -L "$LIB" -type f \
        \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) | sort
}

start_daemon() {
    pgrep -x hyprpaper >/dev/null || { hyprpaper >/dev/null 2>&1 & disown; }
    for _ in {1..30}; do
        hyprctl hyprpaper listactive >/dev/null 2>&1 && return 0
        sleep 0.2
    done
    return 1
}

apply() {
    local wp="$1"
    [[ -f "$wp" ]] || { echo "wallpaper not found: $wp" >&2; exit 1; }
    start_daemon || { echo "hyprpaper did not come up" >&2; exit 1; }

    # hyprpaper 0.8.4 does not reliably apply the config's `wallpaper =` line at
    # startup (logs "Monitor <name> has no target"), but the IPC path works.
    hyprctl hyprpaper unload all >/dev/null 2>&1 || true
    hyprctl hyprpaper preload "$wp" >/dev/null 2>&1 || true
    while read -r m; do
        hyprctl hyprpaper wallpaper "$m,$wp" >/dev/null 2>&1 || true
    done < <(hyprctl monitors | awk '/^Monitor /{print $2}')

    printf '%s\n' "$wp" >"$CURRENT"
}

case "${1:-}" in
    list)
        list
        ;;
    random)
        wp="$(list | shuf -n1)"
        apply "$wp"
        notify-send -u low "Wallpaper" "${wp#"$LIB"/}"
        ;;
    menu)
        # Show library-relative names; map the choice back to a full path.
        choice="$(list | sed "s|^$LIB/||" | hyprlauncher --dmenu)" || exit 0
        [[ -n "$choice" ]] || exit 0
        apply "$LIB/$choice"
        notify-send -u low "Wallpaper" "$choice"
        ;;
    "")
        # Login path: restore the last wallpaper, or pick one at random.
        if [[ -s "$CURRENT" ]] && [[ -f "$(cat "$CURRENT")" ]]; then
            apply "$(cat "$CURRENT")"
        else
            apply "$(list | shuf -n1)"
        fi
        ;;
    *)
        apply "$1"
        ;;
esac
