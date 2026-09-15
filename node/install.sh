#!/usr/bin/env bash
# Configure this machine as an agent node.
#
# Idempotent, and deliberately non-destructive: Claude hooks are appended to
# whatever is already registered, and an existing Codex `notify` program is
# chained rather than replaced. Other tools register on these same events.
#
# Reads NTFY_TOPIC / ACTION_TOKEN from the environment (the fleet installer
# passes them) or from an existing ~/.agentic/config.
set -euo pipefail

AG="$HOME/.agentic"
mkdir -p "$AG/bin"

# --- config -----------------------------------------------------------------
# Values passed in by the installer win over what is already on the node --
# otherwise sourcing the existing config would silently undo a key rotation.
IN_TOPIC=${NTFY_TOPIC:-}
IN_TOKEN=${ACTION_TOKEN:-}
IN_PORT=${ACTION_PORT:-}
[ -f "$AG/config" ] && . "$AG/config" || true
NTFY_TOPIC=${IN_TOPIC:-${NTFY_TOPIC:-}}
ACTION_TOKEN=${IN_TOKEN:-${ACTION_TOKEN:-}}
ACTION_PORT=${IN_PORT:-${ACTION_PORT:-}}
ACTION_PORT=${ACTION_PORT:-8787}
NODE_NAME=${NODE_NAME:-$(hostname -s)}
ACTION_BIND=$(tailscale ip -4 2>/dev/null | head -1)
[ -n "$ACTION_BIND" ] || ACTION_BIND=127.0.0.1

cat > "$AG/config" <<CONF
# Written by agentic node install. The topic and token are the only secrets.
NTFY_TOPIC="$NTFY_TOPIC"
ACTION_TOKEN="$ACTION_TOKEN"
ACTION_BIND="$ACTION_BIND"
ACTION_PORT="$ACTION_PORT"
NODE_NAME="$NODE_NAME"
CONF
chmod 600 "$AG/config"

# --- migrate away from any earlier hand-rolled hooks -------------------------
python3 - <<'MIGRATE'
import json, pathlib
p = pathlib.Path.home() / ".claude/settings.json"
if p.exists():
    d = json.loads(p.read_text())
    removed = 0
    for event, groups in list((d.get("hooks") or {}).items()):
        for g in groups:
            keep = [h for h in g.get("hooks", [])
                    if ".claude/hooks/badge.sh" not in (h.get("command") or "")]
            removed += len(g.get("hooks", [])) - len(keep)
            g["hooks"] = keep
        d["hooks"][event] = [g for g in groups if g.get("hooks")]
    if removed:
        p.write_text(json.dumps(d, indent=2) + "\n")
        print(f"  migrated: dropped {removed} legacy badge.sh hook(s)")
MIGRATE

# --- claude hooks: append, never replace ------------------------------------
mkdir -p "$HOME/.claude/hooks"
python3 - "$AG/bin/agentic-badge" <<'PY'
import json, pathlib, shutil, sys, time
badge = sys.argv[1]
home = pathlib.Path.home()
# A second account under CLAUDE_CONFIG_DIR reads its own settings.json, so
# hooks written only to ~/.claude/ never fire for it.
targets = [home / ".claude/settings.json"] + sorted(
    q / "settings.json" for q in home.glob(".claude-*")
    if q.is_dir() and (q / ".claude.json").exists())
for p in targets:
  d = json.loads(p.read_text()) if p.exists() else {}
  if p.exists():
    shutil.copy2(p, f"{p}.bak-agentic-{int(time.time())}")
  hooks = d.setdefault("hooks", {})
  # SubagentStop is deliberately absent: it fires per subagent, and writing
  # `done` there would clear the parent's badge while the parent is still going.
  # Stop passes through `stop` so the hook can read its own payload.
  # Tool events mark work resumed after you answer a prompt: answering fires no
  # UserPromptSubmit, so without them the badge stays on `ask` while the agent
  # works. PreToolUse covers a long command, which fires no PostToolUse until
  # it ends. agentic-badge throttles both, so a tool storm is one log line.
  for event, state in (("Notification", "ask"), ("Stop", "stop"),
                       ("UserPromptSubmit", "busy"), ("SubagentStart", "busy"),
                       ("PreToolUse", "busy"), ("PostToolUse", "busy")):
      cmd = f"{badge} {state}"
      groups = hooks.setdefault(event, [])
      # Drop any earlier agentic-badge command for this event before appending.
      # Matching on the exact string alone leaves a stale entry behind whenever
      # the argument changes, and the old one still fires.
      for g in groups:
          g["hooks"] = [h for h in g.get("hooks", [])
                        if badge not in (h.get("command") or "") or h.get("command") == cmd]
      already = any(h.get("command") == cmd for g in groups for h in g.get("hooks", []))
      if already:
          continue
      if groups:
          groups[-1].setdefault("hooks", []).append({"type": "command", "command": cmd})
      else:
          groups.append({"hooks": [{"type": "command", "command": cmd}]})
  # Claude Code deletes transcripts older than 30 days by default, and with
  # them the only record ccusage can price. Keep them unless the user has
  # already chosen a period.
  d.setdefault("cleanupPeriodDays", 3650)
  p.write_text(json.dumps(d, indent=2) + "\n")
print("  claude hooks: ok")
PY

# --- opencode plugin: drop in beside whatever is already there ---------------
# Global plugins load from ~/.config/opencode/plugins/*.js with no config edit,
# so the `plugin` array in opencode.json -- which may already carry npm
# plugins -- is left alone.
OC_PLUGINS="$HOME/.config/opencode/plugins"
if [ -d "$HOME/.config/opencode" ]; then
    mkdir -p "$OC_PLUGINS"
    # The directory needs to be an ES module for `import` to work; only write
    # a package.json if nobody else has.
    [ -f "$OC_PLUGINS/package.json" ] || printf '{ "type": "module" }\n' > "$OC_PLUGINS/package.json"
    cp "$AG/bin/agentic-badge.js" "$OC_PLUGINS/agentic-badge.js"
    echo "  opencode plugin: ok"
else
    echo "  opencode plugin: skipped (opencode not configured here)"
fi

# --- codex notify: chain, never replace -------------------------------------
if [ -d "$HOME/.codex" ]; then
python3 - "$AG/bin/agentic-badge" <<'PY'
import pathlib, re, shlex, sys, tomllib
badge = sys.argv[1]
home = pathlib.Path.home()
cfg = home / ".codex/config.toml"
raw = cfg.read_text() if cfg.exists() else ""
existing = tomllib.loads(raw).get("notify") if raw else None
chain = home / ".codex/agentic-notify.sh"

if existing and str(chain) in existing:
    print("  codex notify: already chained"); raise SystemExit
orig = " ".join(shlex.quote(a) for a in (existing or []))
body = "#!/usr/bin/env bash\n# Codex allows one notify program; fan out to each in turn.\npayload=${1:-}\n"
if orig:
    body += f'{orig} "$payload" || true\n'
body += f'''type=$(printf '%s' "$payload" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("type",""))
except Exception: print("")' 2>/dev/null)
# Turn completion is reported by the Stop hook now; notify is left to cover
# approvals, which have no hook event.
case "$type" in
    agent-turn-complete|turn-complete) ;;
    *) "{badge}" ask ;;
esac
'''
chain.write_text(body); chain.chmod(0o755)
if raw:
    cfg.write_text(re.sub(r'^notify = .*$', f'notify = ["{chain}"]', raw, count=1, flags=re.M)
                   if existing else f'notify = ["{chain}"]\n\n' + raw)
else:
    cfg.write_text(f'notify = ["{chain}"]\n')
print("  codex notify: chained")
PY
fi

# --- codex hooks: turn start and end ----------------------------------------
# Codex gained a hooks engine with UserPromptSubmit and Stop, which is what a
# spinner needs; its older `notify` program only fires at turn end. Hooks are
# untrusted until approved once in the Codex TUI -- deliberately, since a hook
# runs arbitrary commands.
if [ -d "$HOME/.codex" ]; then
python3 - "$AG/bin/agentic-badge" <<'CODEXHOOKS'
import json, pathlib, sys
badge = sys.argv[1]
p = pathlib.Path.home() / ".codex/hooks.json"
doc = {}
if p.exists():
    try:
        doc = json.loads(p.read_text())
    except ValueError:
        doc = {}
doc.setdefault("description", "agentic-laptop attention badges")
hooks = doc.setdefault("hooks", {})
for event, state in (("UserPromptSubmit", "busy"), ("Stop", "done")):
    cmd = f"{badge} {state}"
    groups = hooks.setdefault(event, [])
    if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
        continue
    if groups:
        groups[-1].setdefault("hooks", []).append({"type": "command", "command": cmd})
    else:
        groups.append({"hooks": [{"type": "command", "command": cmd}]})
p.write_text(json.dumps(doc, indent=2) + "\n")
print("  codex hooks: written (trust them once in the codex TUI)")
CODEXHOOKS
fi

# --- tmux persistence -------------------------------------------------------
if command -v tmux >/dev/null; then
    mkdir -p "$HOME/.tmux/plugins"
    for p in tpm tmux-resurrect tmux-continuum; do
        url=https://github.com/tmux-plugins/$p
        [ -d "$HOME/.tmux/plugins/$p" ] || git clone -q --depth 1 "$url" "$HOME/.tmux/plugins/$p"
    done
    if ! grep -q continuum-restore "$HOME/.tmux.conf" 2>/dev/null; then
        cat >> "$HOME/.tmux.conf" <<'CONF'

# agentic: session persistence only, no defaults changed
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @continuum-restore 'on'
set -g @continuum-save-interval '15'
set -g @resurrect-capture-pane-contents 'on'
run '~/.tmux/plugins/tpm/tpm'
CONF
    fi
    tmux source-file "$HOME/.tmux.conf" 2>/dev/null || true
    echo "  tmux persistence: ok"
fi

# --- action endpoint under launchd (macOS) or systemd (linux) ---------------
PLIST="$HOME/Library/LaunchAgents/com.agentic.actiond.plist"
if [ "$(uname)" = "Darwin" ]; then
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.agentic.actiond</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/python3</string><string>$AG/bin/agentic-actiond</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$AG/actiond.log</string>
</dict></plist>
PL
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "  action endpoint: launchd loaded on $ACTION_BIND:$ACTION_PORT"
fi

echo "  node ready: $NODE_NAME ($ACTION_BIND)"
