#!/usr/bin/env bash
# Open one kitty per tmux session name, each attached via r.
# usage: workspace-terminals.sh alpha alpha1 alpha2
R="$HOME/.local/bin/r"
for s in "$@"; do
    kitty -e "$R" "$s" &
    sleep 0.4   # stagger so the tiling order is deterministic
done
