#!/usr/bin/env bash
# Link this repo into place on an Asahi laptop.
#
# User-owned files are symlinked, so editing the repo takes effect directly.
# Anything under /etc or /usr/local needs root and is only printed, never run.
set -euo pipefail
REPO=$(cd "$(dirname "$0")" && pwd)

link() {
    local src=$REPO/$1 dst=$2
    mkdir -p "$(dirname "$dst")"
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        mv "$dst" "$dst.pre-agentic"
        echo "  backed up $dst -> $dst.pre-agentic"
    fi
    ln -sfn "$src" "$dst"
    echo "  $dst -> $src"
}

echo "== user scripts =="
for f in "$REPO"/bin/*; do
    chmod +x "$f"
    link "bin/$(basename "$f")" "$HOME/.local/bin/$(basename "$f")"
done

# Your own configuration lives in local/ (git-ignored). examples/ is the
# shareable version; the installer prefers yours when it exists.
pick() { [ -f "$REPO/local/$1" ] && echo "local/$1" || echo "examples/$1"; }

echo "== hyprland =="
link "$(pick hyprland.lua)" "$HOME/.config/hypr/hyprland.lua"
for f in "$REPO"/hypr/*.conf;    do link "hypr/$(basename "$f")" "$HOME/.config/hypr/$(basename "$f")"; done
for f in "$REPO"/hypr/scripts/*; do chmod +x "$f"; link "hypr/scripts/$(basename "$f")" "$HOME/.config/hypr/scripts/$(basename "$f")"; done

echo "== waybar =="
link waybar/config.jsonc "$HOME/.config/waybar/config.jsonc"
link waybar/style.css    "$HOME/.config/waybar/style.css"

echo "== systemd user units =="
for f in "$REPO"/systemd/user/*; do link "systemd/user/$(basename "$f")" "$HOME/.config/systemd/user/$(basename "$f")"; done
systemctl --user daemon-reload
units="claude-limits.timer claude-badges.service claude-actions.service
       agentic-doctor.timer agentic-index.timer git-commits.timer"
systemctl --user enable --now $units
echo "  enabled:$(echo " $units" | tr -s ' \n' ' ')"

cat <<NOTE

== still needs root (run these yourself) ==
  sudo install -d -o "$USER" -m 755 /var/lib/claude-limits
  sudo install -m644 $REPO/$(pick tiny-dfr.config.toml) /etc/tiny-dfr/config.toml
  sudo install -m755 $REPO/tiny-dfr/dfr-switch  /usr/local/bin/dfr-switch
  # then build the fork (see README) and:
  sudo install -m755 ~/src/tiny-dfr/target/release/tiny-dfr /usr/local/bin/tiny-dfr-custom
  sudo dfr-switch custom

== still needs the remote host ==
  agentic-fleet install <host>     # see remote/README.md

== optional: the commit counter ==
  # ~/.config/agentic-laptop/gitcommits.env
  GITCOMMITS_HOST=<host with your repos>
  GITCOMMITS_ROOT='~/src'
  GITCOMMITS_AUTHORS=you@example.com
NOTE
