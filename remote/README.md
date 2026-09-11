# Remote host setup

Agents run in tmux on other machines -- nodes -- while the Touch Bar and the
overlays live on the laptop. A node needs Claude Code and/or Codex, tmux, and
the hooks that report when an agent wants you or has finished.

From the laptop, one command does all of it over ssh:

    agentic-fleet list                # what is on the tailnet, and what is a node
    agentic-fleet install <host>      # make <host> a node

It copies `node/` to `~/.agentic` on the host, appends the Claude Code hooks,
chains Codex's `notify`, starts the node's own action endpoint, and records the
host in `~/.config/claude-badged/fleet`. Every tool on the laptop reads its
hosts from that file, so none of them name a host themselves. `node/install.sh`
is the same setup run by hand on the node.

It is non-destructive by design: Claude hooks are **appended** to whatever is
already registered on those events, and an existing Codex `notify` program is
chained rather than replaced -- other tools got there first.

## After installing

- Restart any running `claude` session. Hooks are snapshotted when a session
  starts.
- Run `codex` once on the node and approve its hooks when prompted. Until then
  `hooks/list` reports them untrusted and they are silently skipped; editing a
  hook re-prompts, because trust is keyed by its hash.
- `agentic-doctor` checks the hooks are still present on every node.
