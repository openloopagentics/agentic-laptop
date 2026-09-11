#!/usr/bin/env bash
# Move between sub-workspaces of the current project workspace.
# Project workspaces are named "<project>.<n>"; anything else is left alone.
# Lua dispatch syntax is required: this config is hyprland.lua, so the legacy
# "dispatch workspace name:x" form is parsed as Lua and fails.
set -euo pipefail
dir=${1:?usage: ws-sub.sh next|prev}

cur=$(hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')
case "$cur" in
    *.[0-9]) ;;
    *) exit 0 ;;   # not a project workspace
esac

prefix=${cur%.*}
n=${cur##*.}
case "$dir" in
    next) n=$(( n + 1 )); (( n > 9 )) && n=9 ;;
    prev) n=$(( n - 1 )); (( n < 1 )) && n=1 ;;
    *) echo "usage: ws-sub.sh next|prev" >&2; exit 2 ;;
esac

hyprctl dispatch "hl.dsp.focus({workspace = \"name:$prefix.$n\"})"
