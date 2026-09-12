# macOS port — specification

Status: **design, not started.** Written 2026-09-11 on the Linux side, to be
executed from a Mac.

## 0. How to use this document

Everything in §3 was verified on the dates shown. Re-verify anything older than
a macOS point release before relying on it, but do not re-research it from
scratch — the dead ends are recorded in §9 on purpose.

## 1. Goal

Run this system on macOS with the same daily feel it has under Hyprland:
named per-project workspaces on one keystroke, agent attention badges, live
usage limits, commit counts, and the detail overlays behind them.

Explicit non-goal: matching Hyprland exactly. §7 states what is given up.

## 2. What exists today

27 tracked scripts. By coupling:

| Coupling | Count | Files |
|---|---|---|
| Portable already | 11 | `climits`, `ask`, `agentic-index`, `agentic-extract`, `agentic-costs`, `agentic-fleet`, `claude-actiond`, `claude-rings`, `r`, `node/bin/*` |
| systemd only | 1 | `gitcommits` (timer, not the script) |
| Hyprland-coupled | 9 | `claude-badged`, `ws-attention`, `windowswitcher.py`, `ws-sub.sh`, `keybinds.py`, `powermenu.sh`, `wallpaper.sh`, `workspace-terminals.sh`, `agentic-doctor` |
| GTK layer-shell UI | 4 | `commitheat.py`, `llmdetail.py`, `fkeys-overlay.py`, `dfrbar.py` |
| Linux input stack | 2 | `dfrbar.py`, `dfrbar-launch` (uinput, sysfs) |
| Not portable at all | 22 patches | `tiny-dfr/patches/*` — see §7 |

The collectors, the hooks and the fleet layer — most of the actual value — are
already OS-agnostic. The node half runs on macOS today.

## 3. Verified constraints

**Touch Bar hardware is gone.** The last Mac with one was the 13-inch M2
MacBook Pro, discontinued October 2023. No current Mac has a strip, and where
one exists macOS owns it through `NSTouchBar`. The 22 tiny-dfr patches have no
target on macOS. *(verified 2026-09-11)*

**Synthesised keystrokes cannot be relied on to trigger shortcuts.** On macOS
26.5, WindowServer's `CGXSenderCanSynthesizeEvents()` drops modifier-bearing
synthetic events aimed at hotkey listeners from processes without the private
`hid-control` entitlement; bare keys to the focused app still land. Sources
disagree on whether Developer ID signing lifts this. **Design around it: buttons
invoke actions directly** (shell command, URL scheme, `yabai -m ...`), never by
faking a key combo. *(verified 2026-09-11)*

**yabai does the core workflow with SIP enabled**, as of:
- 7.1.19 (2026-04-18) — `space --focus` works with SIP enabled
- 7.1.25 (2026-05-08) — moving windows between spaces works with SIP enabled
- 7.1.21–7.1.23 — native space-switch animation removed on that path

**Still requires the scripting addition, and therefore partially disabled SIP:**
create/destroy space, scratchpad windows, sticky windows, window
transparency/shadows/animations, window layer control, PiP toggle. The wiki also
lists "move space", which the 7.1.25 changelog contradicts; trust the changelog.
On Apple Silicon + Tahoe the addition additionally needs an NVRAM boot-arg
exception, and users reported `nvram` writes blocked even from Recovery as late
as April 2026. *(verified 2026-09-11)*

**yabai moved owner.** `koekeishiya/yabai` now redirects to `asmvik/yabai`,
and the project's own wiki documents `brew install asmvik/formulae/yabai`.
Expect older blog posts, issues and this document's links to use the old name.

**Component health** *(2026-09-11)*: yabai pushed 2026-06-14 (29.6k★);
AeroSpace 2026-09-05 (23k★); SketchyBar v2.24.0, 2026-06-04 (12.4k★);
upstream `skhd` pushed 2025-12-09, no releases, 152 open issues — **use
`jackielii/skhd.zig`** (v0.2.0, 2026-07-22, config-compatible) instead.

**Event taps work**: `CGEventTap` sees `flagsChanged`, and Fn carries the
`0x800000` secondary-fn flag. Needs Input Monitoring *and* Accessibility. Note
Fn alone is the 🌐 key on Mac keyboards, so a double-tap of Ctrl is the better
trigger there, matching what the Linux side settled on.

## 4. Architecture

Four layers, three of which already exist:

1. **Collectors** (unchanged Python): `climits`, `gitcommits`, `agentic-index`.
   Scheduled by launchd instead of systemd timers. Keep writing the same
   world-readable files under `/usr/local/var/agentic/` (macOS has no reason
   for `/var/lib/claude-limits`, but keeping one path constant is simpler —
   decide in P1 and keep it in one constant).
2. **Window management**: yabai + skhd.zig.
3. **Bar**: SketchyBar, hosting the badge, usage and commit widgets.
4. **Overlays + on-screen bar**: one Swift app (§6).

## 5. Component mapping

| Linux | macOS | Notes |
|---|---|---|
| Hyprland workspaces | yabai spaces | §6 decision gates dynamic creation |
| Hyprland keybinds | skhd.zig | config-compatible with skhd |
| waybar | SketchyBar | also hosts badges/usage/commits |
| systemd user timers | launchd agents | mechanical |
| GTK4 layer-shell overlays | non-activating `NSPanel` | `.nonactivatingPanel`, `.canJoinAllSpaces` |
| uinput injection | direct action invocation | never synthesise keys — §3 |
| `hyprctl` focus events | `NSWorkspace` notifications | badge clearing on visit |
| tiny-dfr + 22 patches | dropped | no hardware — §7 |
| `dfrbar.py` | Swift panel | same layout, same state files |
| trackpad gestures | BetterTouchTool | no native equivalent — §7 |

## 6. The one open decision: SIP

Everything else follows from this.

**Option A — SIP enabled (recommended default).** Full tiling, space focus,
moving windows between spaces, no security trade, survives macOS updates far
better. **Lost**: dynamic sub-workspaces (`project.1`, `project.2` created on
demand) and the scratchpad. Mitigation: pre-create a fixed set of spaces, one
per project, and drop sub-workspaces.

**Option B — SIP partially disabled.** Adds dynamic space creation, scratchpad,
sticky windows and the cosmetic controls. **Costs**: an NVRAM boot-arg exception
on Apple Silicon, `yabai --load-sa` after every macOS update, and a real
security reduction.

Decide before P2. The rest of the spec assumes A, and marks what B would add.

## 7. Non-goals

- **The Touch Bar strip.** No hardware. Drop the 22 patches entirely.
- **Trackpad gestures.** The Linux config binds 3- and 4-finger swipes; macOS
  has no third-party equivalent. BetterTouchTool can supply them if wanted.
- **Exact Hyprland parity.** Every macOS WM reverse-engineers a closed window
  server, so updates can break it. That is structural, not fixable here.

## 8. Plan

**P0 — verify the environment (first hour).** Run §9's checklist. Confirm the
yabai version actually does `space --focus` with SIP on, on *this* Mac and *this*
macOS build. Nothing else starts until this passes.

*Acceptance:* `yabai -m space --focus 2` switches spaces with `csrutil status`
reporting SIP enabled.

**P1 — collectors under launchd.** Port the three timers. No new code: the
scripts are already portable. Pick the state directory and put it in one
constant shared by collectors and UI.

*Acceptance:* limits, commit counts and the index refresh on schedule, and the
files are readable by the UI user.

**P2 — window management.** yabai + skhd.zig with one space per project and the
same keystrokes (`CMD+SHIFT+<letter>` in place of `SUPER+SHIFT+<letter>`).

*Acceptance:* every project workspace reachable by its own chord; terminals
reattach to the right tmux sessions via `r`.

**P3 — SketchyBar.** Badges, usage bars and commit counts as widgets, reading
the same files. This subsumes waybar *and* most of what the Touch Bar did.

*Acceptance:* an agent finishing on a node shows a badge within one second, and
it clears on visiting that space.

**P4 — the Swift app.** Non-activating panel for the on-screen bar, plus the
two overlays. `CGEventTap` for double-tap Ctrl. Buttons call commands directly.

*Acceptance:* double-tap Ctrl shows the bar; a click switches space; the commit
and usage overlays render the same data as the Linux versions.

## 9. First-hour checklist

    csrutil status                         # SIP state, before changing anything
    sw_vers                                # macOS build, for §3 re-verification
    brew install asmvik/formulae/yabai      # old koekeishiya/formulae also resolves
    brew install jackielii/tap/skhd-zig     # a CASK, not a formula -- see below
    brew install sketchybar                 # FelixKratz/formulae/sketchybar also works
    yabai --version
    yabai -m query --spaces | head         # does it see spaces at all?
    yabai -m space --focus 2               # THE test: does this work with SIP on?
    # Grant Accessibility + Input Monitoring when prompted, then re-run.

Record the results at the top of this file before going further.

Two naming traps, both verified 2026-09-11:

- `skhd-zig` ships as a **cask** (the release artifact is a self-contained
  `skhd.app`). `brew install jackielii/tap/skhd-zig` works on the CLI, but in a
  Brewfile it must be `cask "jackielii/tap/skhd-zig"`, not `brew "..."`.
- That tap also contains `Formula/my-skhd.rb`, which is a **different project**
  -- a fork of the original C skhd, not the Zig port. Do not install it by
  mistake.

## 10. Dead ends — do not repeat

- **Synthesising key combos to trigger shortcuts.** Fails on Linux via the
  Wayland virtual-keyboard protocol (reaches apps, never compositor binds) and
  is gated on macOS 26 (§3). Invoke actions directly instead.
- **`yabai-tahoe` fork** (`tbiehn/yabai-tahoe`): archived 2026-05-22, no Tahoe
  support. Use upstream.
- **AeroSpace**: emulated workspaces cause the compromises — no Mission Control
  overview, native-fullscreen breakage, unavoidable switch animation. Structural.
- **Mosaico**: MIT, no SIP, native-Spaces-aware, but v0.2.0 and moves windows
  between spaces by simulating a Mission Control drag. Watch, do not adopt yet.
