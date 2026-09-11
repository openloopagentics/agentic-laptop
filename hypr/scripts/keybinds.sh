#!/usr/bin/env bash
# Show the keybind cheatsheet in a floating terminal.
# Toggles: if the window is already open, close it instead of stacking copies.
if pgrep -f "kitty --class hypr-keybinds" >/dev/null; then
    pkill -f "kitty --class hypr-keybinds"
    exit 0
fi
exec kitty --class hypr-keybinds \
    -o confirm_os_window_close=0 \
    -e bash -c '"$HOME/.config/hypr/scripts/keybinds.py"; echo; read -n1 -rsp "  Press any key to close…"'
