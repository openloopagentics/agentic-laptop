#!/usr/bin/env bash
# One-command install of agentic-laptop on an Arch-based machine running
# Hyprland (Arch, CachyOS, Asahi ALARM).
#
#   curl -fsSL https://raw.githubusercontent.com/openloopagentics/agentic-laptop/main/setup.sh | bash
#   curl -fsSL .../setup.sh | bash -s -- --from <host>
#
# It does everything install.sh only prints: packages, the repo checkout, the
# root-owned pieces, and -- on a machine with a Touch Bar -- the tiny-dfr fork
# built and switched in. A machine without one gets the on-screen bar instead.
#
# Options:
#   --from HOST      copy your personal config (local/, the fleet list, push
#                    settings, env files) from a machine that already has it
#   --dir DIR        where to check the repo out (default ~/src/agentic-laptop)
#   --repo URL       repo to clone (default the public one)
#   --no-packages    skip pacman
#   --no-touchbar    treat the machine as having no Touch Bar
#   --dry-run        print what would run, change nothing
#
# Safe to re-run: it pulls, re-links, and skips what is already in place.
set -euo pipefail

REPO_URL=https://github.com/openloopagentics/agentic-laptop.git
FORK_URL=https://github.com/openloopagentics/tiny-dfr.git
FORK_BRANCH=agentic-laptop
DIR="$HOME/src/agentic-laptop"
FROM=""
PACKAGES=1
TOUCHBAR=auto
DRY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --from)        FROM=${2:?--from needs a host}; shift ;;
        --dir)         DIR=${2:?--dir needs a path}; shift ;;
        --repo)        REPO_URL=${2:?--repo needs a url}; shift ;;
        --no-packages) PACKAGES=0 ;;
        --no-touchbar) TOUCHBAR=0 ;;
        --dry-run)     DRY=1 ;;
        -h|--help)     sed -n '2,24p' "$0" 2>/dev/null || true; exit 0 ;;
        *) echo "setup: unknown option $1" >&2; exit 2 ;;
    esac
    shift
done

say()  { printf '\n== %s ==\n' "$*"; }
note() { printf '  %s\n' "$*"; }
run()  {
    if [ "$DRY" = 1 ]; then printf '  + %s\n' "$*"; else "$@"; fi
}

[ "$(id -u)" != 0 ] || { echo "setup: run as your own user; it asks for sudo when needed" >&2; exit 1; }
command -v pacman >/dev/null || PACKAGES=0

# --- Touch Bar? ------------------------------------------------------------
# A Touch Bar is a DRM connector a few dozen pixels wide (60x2008 on the M1
# 13"). tiny-dfr already installed counts too.
if [ "$TOUCHBAR" = auto ]; then
    TOUCHBAR=0
    if grep -qsE '^[0-9]{2,3}x[0-9]{4}$' /sys/class/drm/*/modes || pacman -Q tiny-dfr >/dev/null 2>&1; then
        TOUCHBAR=1
    fi
fi
note "Touch Bar: $([ "$TOUCHBAR" = 1 ] && echo yes || echo 'no -- the on-screen bar will stand in')"

# --- packages --------------------------------------------------------------
if [ "$PACKAGES" = 1 ]; then
    say packages
    want=(git base-devel openssh curl tmux sqlite python python-gobject python-cairo
          gtk4 gtk4-layer-shell python-evdev nodejs npm tailscale
          hyprland hyprpaper hypridle hyprlock hyprlauncher waybar kitty mako
          libnotify swayosd brightnessctl playerctl wireplumber grim slurp
          wl-clipboard chromium dolphin)
    [ "$TOUCHBAR" = 1 ] && want+=(tiny-dfr rust cairo librsvg libinput freetype2 fontconfig)
    # Only ask pacman for what this repo set actually carries, and say what
    # was left out, rather than failing the whole transaction on one name.
    have=() missing=()
    for p in "${want[@]}"; do
        if pacman -Si "$p" >/dev/null 2>&1 || pacman -Q "$p" >/dev/null 2>&1; then have+=("$p"); else missing+=("$p"); fi
    done
    run sudo pacman -S --needed --noconfirm "${have[@]}"
    [ ${#missing[@]} -eq 0 ] || note "not in your repos, skipped: ${missing[*]}"
fi

# Hyprland's Lua config arrived in 0.56; the shipped config is Lua only.
if command -v Hyprland >/dev/null; then
    v=$(Hyprland --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    if [ -n "$v" ] && [ "$(printf '%s\n0.56.0\n' "$v" | sort -V | head -1)" != 0.56.0 ]; then
        note "warning: Hyprland $v is older than 0.56, which the Lua config needs"
    fi
fi

# The tailnet first: --from, and every node, are reached over it.
say tailscale
run sudo systemctl enable --now tailscaled
if [ "$DRY" = 0 ] && ! tailscale status >/dev/null 2>&1; then
    note "sign in with the link below"
    sudo tailscale up
fi

# --- the repo --------------------------------------------------------------
say repo
if [ -d "$DIR/.git" ]; then
    run git -C "$DIR" pull --ff-only
else
    run mkdir -p "$(dirname "$DIR")"
    run git clone "$REPO_URL" "$DIR"
fi

# --- personal config from another machine ----------------------------------
# None of this is in git: local/ holds real project names and accounts, the
# fleet file holds hostnames, push.conf holds the ntfy topic.
if [ -n "$FROM" ]; then
    say "config from $FROM"
    # Relative to the remote home, which scp resolves without needing ~.
    remote_dir=${DIR#"$HOME"/}
    run mkdir -p "$DIR/local" "$HOME/.config/claude-badged" "$HOME/.config/agentic-laptop"
    run scp -rq "$FROM:$remote_dir/local/." "$DIR/local/"
    for f in fleet push.conf; do
        run scp -q "$FROM:.config/claude-badged/$f" "$HOME/.config/claude-badged/$f" || note "no $f on $FROM"
    done
    run scp -q "$FROM:.config/agentic-laptop/*.env" "$HOME/.config/agentic-laptop/" 2>/dev/null || true
fi

# --- link everything -------------------------------------------------------
say install.sh
if [ "$DRY" = 1 ]; then note "+ $DIR/install.sh"; else "$DIR/install.sh" >/dev/null; note "linked and enabled"; fi

pick() { [ -f "$DIR/local/$1" ] && echo "$DIR/local/$1" || echo "$DIR/examples/$1"; }

# --- root-owned pieces -----------------------------------------------------
say "system (sudo)"
# Hand-off directory for the Touch Bar and overlays: the daemon runs as
# `nobody` and cannot read a home directory.
run sudo install -d -o "$USER" -m 755 /var/lib/claude-limits

# uinput, so bar buttons reach Hyprland's keybinds. Wanted either way: the
# on-screen bar also serves a Touch Bar machine on double-tap Ctrl.
run sudo groupadd -f uinput
run sudo install -m644 "$DIR/config/99-uinput.rules" /etc/udev/rules.d/99-uinput.rules
run sudo udevadm control --reload-rules
run sudo udevadm trigger /dev/uinput || true
relogin=0
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx uinput; then
    run sudo usermod -aG uinput "$USER"
    relogin=1
fi

# --- the bar ---------------------------------------------------------------
if [ "$TOUCHBAR" = 1 ]; then
    say "Touch Bar: tiny-dfr fork"
    src="$HOME/src/tiny-dfr-agentic"
    if [ -d "$src/.git" ]; then
        run git -C "$src" fetch -q origin "$FORK_BRANCH"
        run git -C "$src" checkout -q "origin/$FORK_BRANCH"
    else
        run git clone -q -b "$FORK_BRANCH" "$FORK_URL" "$src"
    fi
    run cargo build --release --manifest-path "$src/Cargo.toml"
    run sudo install -m755 "$src/target/release/tiny-dfr" /usr/local/bin/tiny-dfr-custom
    run sudo install -Dm644 "$src/share/tiny-dfr/config.toml" /usr/local/share/tiny-dfr/config.toml
    run sudo install -m755 "$DIR/tiny-dfr/dfr-switch" /usr/local/bin/dfr-switch
    run sudo install -Dm644 "$(pick tiny-dfr.config.toml)" /etc/tiny-dfr/config.toml
    run sudo dfr-switch custom
else
    say "on-screen bar"
    # dfrbar reads this after /etc; with no tiny-dfr package it is the layout.
    run mkdir -p "$HOME/.config/agentic-laptop"
    run install -m644 "$(pick tiny-dfr.config.toml)" "$HOME/.config/agentic-laptop/bar.toml"
    note "press Fn to show it"
fi

# --- what is left ----------------------------------------------------------
say done
[ -s "$HOME/.config/claude-badged/fleet" ] || note "add machines that run agents:  agentic-fleet install <host>"
[ -d "$DIR/local" ] || note "your own projects and accounts: copy examples/ to local/ and edit, or re-run with --from <host>"
[ "$relogin" = 0 ] || note "log out and back in, so the uinput group applies"
note "check the whole chain any time:  agentic-doctor"
