# agentic-laptop

Run coding agents on a fleet of machines, and drive them from one laptop.

Agents live in tmux on nodes; the laptop is where you watch and steer them. A
node is self-sufficient by design — it notifies your phone and answers its own
prompts — so closing the laptop costs you a display, not a notification.

Built for an Apple Silicon MacBook Pro on Asahi Linux with Hyprland, driving
Macs over Tailscale. The fleet, notification and search pieces are portable;
the Touch Bar pieces need Apple Silicon and Asahi.

## Requirements

- A controller running Linux with Hyprland, and `tailscale`
- One or more nodes (macOS or Linux) reachable over the tailnet, running
  Claude Code and/or Codex inside tmux
- A phone with [ntfy](https://ntfy.sh) installed, for notifications
- Optional, controller-only: an Apple Silicon Mac with a Touch Bar, for the
  Touch Bar features
- For the overlays: GTK 4, gtk4-layer-shell and PyGObject (on Arch:
  `gtk4 gtk4-layer-shell python-gobject`)

## Your config vs the shipped examples

`examples/` holds shareable configuration with placeholder names. Your real
configuration goes in `local/`, which is git-ignored; `install.sh` and the
health check prefer `local/` when it exists and fall back to `examples/`. That
way you can track this repo without publishing your project names, account
addresses or home paths. What this repo adds is the connective tissue: one keystroke per
project, live usage limits and attention badges on the Touch Bar, and a way to
tell at a glance which agent wants you.

## Features

**Remote sessions**

- `r <name>` attaches to a named tmux session on the remote host, creating it if
  absent. One command, from any workspace.
- kitty's terminfo is installed on the remote, without which tmux refuses to
  start over ssh at all.

**Workspaces**

- Seven named project workspaces, each opening three terminals already attached
  to matching tmux sessions.
- Sub-workspaces per project (`alpha.1`, `alpha.2`, …), cycled with
  `SUPER+]` / `SUPER+[`. Only `.1` launches terminals.
- Table-driven: adding a project is one line, which generates both the workspace
  rule and the keybind.
- Clickable workspaces in waybar, via the `ext-workspace-v1` protocol rather than
  a dispatch string, which a Lua Hyprland config rejects.
- A click-through F1-F12 overlay on the main screen that never takes keyboard
  focus, so its keys land in whatever window is actually focused.

**Touch Bar**

A patch series on upstream tiny-dfr, which ships greyscale text buttons and two
fixed layers:

- Per-button colour, foreground and background, from a named `[Palette]`.
- Widgets drawn into the button rectangle: sparkline, concentric rings, and
  stacked bars. At ten buttons each one is a 186x42 cairo surface.
- Built-in cpu and memory sources, plus a file source for state produced
  outside the daemon.
- Three layers: default, Fn, and a third switched from a button, carrying real
  function keys.
- Attention badges as counted pills.
- A spinner while an agent is working. When it finishes, the ring shatters
  and drifts apart in slow motion, and the label's letters are thrown out and
  land back in place -- so the end of work is something you catch from across
  the room.
- A `commits` widget: today, this week and this month as three figures.
- Configurable dim and off delays.
- The stock package is never modified. `dfr-switch custom|stock|status` flips a
  systemd drop-in, checks the config for keys the custom build requires, and
  rolls back automatically if it fails to stay up.

**Usage limits**

- `climits` collects both Claude accounts -- locally and over ssh -- plus Codex,
  whose figures come from its app-server over JSON-RPC rather than any file.
- A window whose reset time has passed reports 0 instead of its stale figure.
- Three bars per account on the Touch Bar: 5-hourly, weekly, weekly-scoped.
- `claude-rings` renders the same data as fitness-style rings in a standalone
  HTML page.
- Refreshed every five minutes by a systemd user timer.
- Tap an account's bars for an overlay with everything its API reports: plan
  tier, which host it was read from, live or cached and how old, and per
  window the percentage, headroom, the server's own severity, the model it is
  scoped to and a reset countdown. Claude accounts add this week's split by
  surface (Claude Code, chat, Cowork); Codex adds its banked rate-limit reset
  credits and when each one expires. `‹ ›` or the arrow keys page between
  accounts.

**Attention badges**

- Claude Code's `Notification` and `Stop` hooks, and Codex's `notify` program,
  report per tmux session.
- One long-lived ssh stream carries those events to the laptop.
- Pink means an agent wants your input, green means one finished, with a count
  of events since you last looked.
- Cleared when you enter the workspace, and never raised for the workspace you
  are already in.
- Collected from every machine you name, plus this one, each followed from a
  persisted byte offset -- so a dropped ssh connection (Tailscale forces
  re-auth periodically) resumes exactly where it stopped instead of skipping
  whatever arrived meanwhile. Pending badges also survive a restart of the
  bridge itself.
- `SUPER+N` jumps to whatever has waited longest: a pending question before a
  finished command, oldest of each, so pressing it repeatedly walks the backlog
  in the order it formed.
- Optional phone push over [ntfy](https://ntfy.sh), fired only on the
  transition into "waiting" and only while the screen is locked -- a badge you
  cannot see is exactly when a push earns its place. Copy
  `config/push.conf.example` to `~/.config/claude-badged/push.conf` and set
  your own topic.

**The fleet**

- `agentic-fleet list` reads the tailnet and says which machines are nodes,
  which are eligible, and which are something else (a phone is not a node).
- `agentic-fleet install <host>|--all` copies the node package and configures
  it: hooks, notifications, its own action endpoint under launchd, and tmux
  persistence. Idempotent, and non-destructive -- Claude hooks are appended to
  whatever is already registered and an existing Codex `notify` is chained, on
  the assumption other tools got there first.
- `agentic-fleet status` reports each node's endpoint and session count;
  `agentic-fleet exec` runs a command across all of them.
- Nodes push and answer for themselves. The controller pushes only for agents
  running on the controller, so nothing is notified twice.

**Answer from your phone**

- Notifications carry Approve / Deny buttons that answer the prompt without
  going to the laptop.
- Served by the node the agent runs on, so it works while the controller is
  closed. `agentic-actiond` on a node, `claude-actiond` on the controller.
- Both bind to the tailnet address only, requires a token from a
  0600 file, accepts two named actions mapping to fixed keystrokes -- never
  arbitrary input -- and refuses any session that has no pending badge.

**Search and attribution**

- `ask <query>` searches every conversation from both agents across every
  machine. Extraction runs at the source, because the corpus is over a
  gigabyte, and only compact records cross the network; the index is SQLite
  FTS5 and rebuilds in seconds.
- `agentic-costs` attributes spend per project, from the cost records Claude
  writes into each transcript. `climits` says you are at 24%; this says which
  project spent it.

**The Touch Bar on a machine that has none**

- `dfrbar.py` draws the same buttons in a layer-shell bar along the bottom of
  the screen, reading the same tiny-dfr config and the same state files, so
  badges, usage bars and the commit counter all appear as they do on the
  strip.
- How you summon it depends on the machine, and `dfrbar-launch` decides per
  machine so one config is right everywhere: where a real Touch Bar exists Fn
  belongs to the strip's own layers, so there the bar answers to a **double-tap
  of Ctrl**; on a machine without one, **Fn** shows it. The Ctrl binding is
  non-consuming, so Ctrl keeps working as an ordinary modifier.
- Navigation is by tap, since there is no Fn to hold: the `fn` chip toggles
  the media layer, and buttons carrying a `Layer` key switch to it (the stock
  config's `F1-12`, and `back` to return). The trigger key dismisses it, the
  same key that summoned it.
- It reserves its own strip: tiled windows are pushed up to make room rather
  than being covered, the way waybar reserves the top. `--overlay` floats it
  over the windows instead.
- Icons come from tiny-dfr's own set when installed, and from the icon theme
  otherwise, painted through a mask so symbolic icons -- black on transparent,
  and invisible on a dark bar -- take the button's colour.
- Clicks are injected through a uinput virtual keyboard, which needs the udev
  rule in `config/99-uinput.rules` and membership of the `uinput` group. That
  grants permission to inject events, not to read your keystrokes. The Wayland
  virtual-keyboard protocol is not enough: keys sent that way reach
  applications but never trigger compositor keybinds, so a workspace or media
  button would do nothing. Without uinput the bar still draws and still
  switches layers.

**Commit counter**

- `gitcommits` counts the commits you authored across every repo under one
  directory on a remote host -- all branches, bucketed by author date into
  today, this week (from Monday) and this month -- and hands them to the Touch
  Bar. Refreshed every ten minutes.
- Tap the figures for an overlay: commits by hour of day for the month, and
  the same month as a day-by-hour punchcard. `‹ ›` pages back through every
  month that has commits. Bar heights are scaled per month so a quiet month
  still shows its shape; colour is scaled across all months, so paging says
  something true about size.

**Spend**

- `ccfleet` runs [ccusage](https://github.com/ryoppippi/ccusage) on this
  machine and every fleet node, over every Claude config directory each has,
  and totals today and this month in dollars for the Touch Bar.
  It covers whatever ccusage detects -- Claude Code, Codex, OpenCode. Days are
  grouped in this machine's timezone. Refreshed every fifteen minutes.
- Tap the figures for an overlay: the month's days stacked by machine, and
  the month split by machine, model and agent. `‹ ›` pages back six months.
  Figures are ccusage's API list-price estimates, not what a subscription bills.

**Knowing it still works**

- `agentic-doctor` checks the whole chain, not just that things are installed:
  units running, the Touch Bar on the custom build, usage figures fresh, state
  files readable by `nobody`, the bridge holding an offset per source, hooks
  still present on remote hosts, and the live config still matching the repo.
- Runs every 30 minutes and pushes to the phone on a regression.

**Remote host durability**

- tmux-resurrect and tmux-continuum on the machine running the agents, saving
  every 15 minutes with pane contents, restoring on tmux server start. A reboot
  costs at most fifteen minutes of state instead of every session.

**Reproducibility**

- One repo, an install script that symlinks user files and prints the root and
  remote steps instead of running them.
- The tiny-dfr fork exported as patches, so the binary rebuilds from upstream
  master rather than from a vendored copy -- and published as a ready-to-build
  branch at openloopagentics/tiny-dfr.

## The parts

| Path | What it is |
|---|---|
| `bin/r` | `r alpha` attaches to the `alpha` tmux session on the remote host |
| `bin/climits` | Reads Claude usage limits from every account, plus Codex, into JSON or TOML |
| `bin/claude-rings` | Renders those limits as a standalone HTML page of fitness-style rings |
| `bin/claude-badged` | Streams remote agent events + Hyprland focus into a badge file |
| `bin/gitcommits` | Counts your commits on a remote host, for the Touch Bar and the by-hour overlay |
| `hypr/scripts/commitheat.py` | The commits-by-hour overlay |
| `bin/ccfleet` | Gathers ccusage spend from every machine, for the Touch Bar and the spend overlay |
| `hypr/scripts/ccdetail.py` | The agent spend overlay |
| `hypr/scripts/llmdetail.py` | The per-account usage detail overlay |
| `hypr/scripts/dfrbar.py` | The Touch Bar drawn on screen, for machines without one |
| `node/` | What `agentic-fleet install` puts on each node |
| `examples/` | Shareable Hyprland and Touch Bar config, with placeholder names |
| `hypr/` | Hyprland config: named project workspaces with sub-workspaces |
| `waybar/` | Bar config |
| `tiny-dfr/` | Touch Bar daemon config, the stock/custom switcher, and our patches |
| `systemd/user/` | The limits and commit-count timers, the badge bridge, the doctor |
| `remote/` | How a machine that runs agents becomes a node |

## Workspaces

Seven named Hyprland workspaces, one per project, each opening three terminals
attached to matching tmux sessions on the remote host:

    SUPER+SHIFT+O  alpha          SUPER+SHIFT+S  delta
    SUPER+SHIFT+V  beta     SUPER+SHIFT+H  epsilon
    SUPER+SHIFT+D  gamma           SUPER+SHIFT+L  zeta
    SUPER+SHIFT+C  eta

`SUPER+]` / `SUPER+[` move between sub-workspaces (`alpha.1`, `alpha.2`, …).
Only `.1` launches terminals; the rest are scratch space for that project.

Adding a project is one line in the `projects` table in `hypr/hyprland.lua` —
the workspace rule and the keybind are both generated from it.

## Touch Bar

Three layers, on a patched [tiny-dfr](https://github.com/AsahiLinux/tiny-dfr):

- **default** — the seven project buttons, the commit counter, then usage bars per account
- **hold Fn** — media keys, plus an `F1-12` button
- **tap `F1-12`** — real function keys, and a `back` button

Each project button carries a **badge**: a counted pill in the corner, pink
when an agent wants your input, green when one has finished. It clears when you
visit that workspace, and never appears for the workspace you are already in.

The usage buttons show three bars — 5-hourly, weekly, weekly-scoped — for each
account you list: two Claude accounts and Codex, in the example config.

Tapping a widget opens its overlay on the main screen. Each tap sends a key
combo, which the Hyprland config binds, so the keyboard reaches them too:

    SUPER+SHIFT+G        commits by hour
    SUPER+SHIFT+U / I / M  usage detail, one combo per account

A usage button can carry a provider mark above its tag: put an SVG at
`/etc/tiny-dfr/<name>.svg` and add `Logo = "<name>"` to the button. None ship
with this repo; provider logos are trademarks, not MIT-licensed code.

### The patches

`tiny-dfr/patches/` applies onto upstream `master`. Upstream has no colour, no
widgets, and exactly two layers; these add per-button colour and a palette,
sparkline/rings/bars widgets, N layers switched from a button, and badges.

The quickest route is the fork, whose default branch is upstream plus exactly
these patches:

    git clone https://github.com/openloopagentics/tiny-dfr ~/src/tiny-dfr
    cd ~/src/tiny-dfr && cargo build --release

Or apply them yourself onto upstream -- they were last rebased onto `eb711c8`;
if a newer `master` refuses one, check that commit out before `git am`:

    git clone https://github.com/AsahiLinux/tiny-dfr ~/src/tiny-dfr
    cd ~/src/tiny-dfr && git am /path/to/agentic-laptop/tiny-dfr/patches/*.patch
    cargo build --release

The patches here are the source of truth; the fork's branch is rebuilt from
them.

The stock package is never modified. `dfr-switch custom|stock|status` flips a
systemd drop-in between the two, verifies config keys before switching, and
rolls back automatically if the custom build fails to stay up.

## How the badge path works

    agent finishes / asks             (remote host, in tmux)
      -> Claude "Stop"/"Notification" hook, or Codex "notify"
      -> appends "<tmux-session> ask|done" to ~/.claude-badges.log
      -> claude-badged tails that log over one long-lived ssh
      -> maps session to workspace (alpha1 -> alpha)
      -> writes /var/lib/claude-limits/badges.toml
      -> tiny-dfr reads it on its 1s tick and draws the pill
      -> Hyprland focus event clears the badge on visit

The file handoff is not incidental: tiny-dfr drops privileges to `nobody` and
runs with `PrivateTmp`, so it cannot read a user's home directory or
`/run/user`. Anything it needs must arrive in a world-readable file.

## Install

    ./install.sh          # symlinks user files, enables the timers
                          # then run the root commands it prints
    agentic-fleet install <host>      # for each machine that runs agents

Hosts live in `~/.config/claude-badged/fleet`, one per line, which
`agentic-fleet install` maintains; no tool here names a host itself. The first
line is the default remote for `r` and `gitcommits`. See `remote/README.md`.

Copy `examples/hyprland.lua` and `examples/tiny-dfr.config.toml` to `local/`
and put your own project names and account addresses there -- `local/` is
git-ignored, and the installer prefers it.

For the commit counter, say where your repos are and who you are:

    # ~/.config/agentic-laptop/gitcommits.env
    # Host with the repos; default: the first line of the fleet file.
    GITCOMMITS_HOST=my-mac-mini
    # A directory of git checkouts on that host. Quoted, so ~ reaches the
    # host unexpanded.
    GITCOMMITS_ROOT='~/src'
    # Whose commits count; default: that host's git user.email.
    GITCOMMITS_AUTHORS=you@example.com,you@work.example.com

systemd reads this file too, and takes any `#` after a value as part of the
value, so keep comments on their own lines.

## Running this on a Mac

`docs/macos-port.md` is a specification for porting this to macOS: what
ports unchanged, what has to be rewritten, the constraints verified as of
September 2026, and the dead ends not worth repeating.

## Known rough edges

- Codex hooks must be trusted once, interactively, before they run. Run
  `codex` on the node and approve them when prompted; until then
  `hooks/list` reports `trustStatus: untrusted` and they are silently
  skipped. Trust is keyed by a hash of the hook, so editing one re-prompts.
  This is deliberate -- a hook runs arbitrary commands -- and there is no
  supported way to grant it from a config file.

- Tailscale SSH does not propagate remote exit codes -- `ssh host "exit 7"`
  returns 0. Everything here asserts on stdout markers instead; be careful
  adding checks that assume otherwise.

- Claude usage figures are cached per account and only move when that account
  makes a request; an idle account shows stale numbers. Windows whose reset
  time has passed are zeroed rather than shown stale.
- Live Claude figures come from the OAuth usage endpoint Claude Code itself
  calls, using the token it already stores. It is not a documented API, so its
  shape can change without notice; `climits` falls back to the cached figures
  when the call fails.
- External displays do not work: DisplayPort alt mode is still WIP on M1 under
  Asahi, and this model has no HDMI.

## License

MIT, see `LICENSE`.

The patches under `tiny-dfr/patches/` apply to
[AsahiLinux/tiny-dfr](https://github.com/AsahiLinux/tiny-dfr), which is itself
MIT / Apache-2.0; they carry that project's licensing, not this repo's.
