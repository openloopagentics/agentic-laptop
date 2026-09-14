#!/usr/bin/env python3
"""Everything known about one LLM account, as a layer-shell overlay.

Reads the JSON written by `climits --json`, which keeps what the Touch Bar's
three rings throw away: plan tier, where the figures were read from, whether
they are live, and per window the severity, the model scope and the reset
time. Re-running toggles it off; the chevrons, arrow keys and h/l move
between accounts, and escape dismisses.

An account may be named as an argument (email, or `codex`) to open on it.
`--png PATH` draws it to a file instead of the screen.
"""
import json
import os
import signal
import sys
from datetime import datetime, timezone

DATA = "/var/lib/claude-limits/limits-detail.json"
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "llmdetail.pid")
W, H = 1080, 600

# Catppuccin Mocha, matching the strip and the commit overlay.
BASE = (0.118, 0.118, 0.180)
SURFACE = (0.192, 0.196, 0.267)
OVERLAY = (0.271, 0.278, 0.353)
TEXT = (0.804, 0.839, 0.957)
SUBTEXT = (0.651, 0.678, 0.784)
BLUE = (0.537, 0.706, 0.980)
GREEN = (0.651, 0.890, 0.631)
PEACH = (0.980, 0.702, 0.529)
RED = (0.953, 0.545, 0.659)
MAUVE = (0.796, 0.651, 0.969)
TEAL = (0.580, 0.886, 0.835)

WINDOWS = [
    ("session", "5-hour session"),
    ("weekly_all", "Weekly · all models"),
    ("weekly_scoped", "Weekly · scoped"),
]

# An account can relabel the windows it reports. The Go plan's caps are
# 5-hourly, weekly and monthly, so reusing Claude's names would mislabel the
# third row as weekly while it shows thirty days.
WINDOW_LABELS = {
    "opencode-go": {
        "session": "5-hour cap",
        "weekly_all": "Weekly cap",
        "weekly_scoped": "Monthly cap",
    },
}

TIERS = {
    "default_claude_max_20x": "Claude Max 20×",
    "default_claude_max_5x": "Claude Max 5×",
    "default_claude_pro": "Claude Pro",
    "pro": "Pro",
}


def rounded(c, x, y, w, h, r):
    import math

    r = max(min(r, h / 2, w / 2), 0.01)
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    c.close_path()


def severity_color(sev, pct):
    """Trust the server's own judgement; fall back to the figure."""
    if sev in ("critical", "severe", "exceeded"):
        return RED
    if sev == "warning":
        return PEACH
    if sev == "normal":
        return GREEN if pct < 50 else BLUE
    return RED if pct >= 90 else PEACH if pct >= 75 else BLUE if pct >= 50 else GREEN


def human_delta(iso):
    """'in 8h 22m', or 'expired' once the window has rolled over."""
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return None
    secs = (when - datetime.now(timezone.utc)).total_seconds()
    if secs <= 0:
        return "due now"
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"in {d}d {h}h"
    if h:
        return f"in {h}h {m}m"
    return f"in {m}m"


def local_time(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%a %d %b, %H:%M")
    except ValueError:
        return None


def draw_resets(c, rc, y):
    """Banked rate-limit resets: how many, and when each one lapses."""
    live = [
        x for x in rc.get("credits", [])
        if x.get("status") == "available" and human_delta(x.get("expires_at")) != "due now"
    ]
    live.sort(key=lambda x: x.get("expires_at") or "")
    count = rc.get("available", len(live))

    c.set_source_rgb(*TEXT)
    c.set_font_size(17)
    c.move_to(62, y + 29)
    c.show_text("Rate-limit resets available")

    c.set_source_rgb(*(GREEN if count else SUBTEXT))
    c.set_font_size(38)
    fig = str(count)
    e = c.text_extents(fig)
    c.move_to(W - 62 - e.width - e.x_bearing, y + 41)
    c.show_text(fig)

    # One chip per credit, soonest to lapse first. Anything inside a week is
    # peach: that one is worth spending before the others.
    x = 62.0
    c.set_font_size(13)
    for cr in live:
        when = local_time(cr.get("expires_at"))
        label = f"{cr.get('title') or 'Reset'} · expires {human_delta(cr.get('expires_at'))}"
        if when:
            label += f" ({when.split(',')[0]})"
        tw = c.text_extents(label).x_advance + 22
        if x + tw > W - 62 - 90:
            break
        secs = 0
        try:
            secs = (datetime.fromisoformat(cr["expires_at"]) - datetime.now(timezone.utc)).total_seconds()
        except (KeyError, TypeError, ValueError):
            pass
        soon = 0 < secs < 7 * 86400
        c.set_source_rgb(*OVERLAY)
        rounded(c, x, y + 50, tw, 28, 8)
        c.fill()
        c.set_source_rgb(*(PEACH if soon else TEXT))
        c.move_to(x + 11, y + 69)
        c.show_text(label)
        x += tw + 10
    if not live:
        c.set_source_rgb(*SUBTEXT)
        c.move_to(62, y + 69)
        c.show_text("none banked")


def draw_breakdown(c, bd, y):
    """This week's usage split by where it was spent."""
    rows = [r for r in bd.get("rows", []) if r.get("percent") is not None]
    c.set_source_rgb(*TEXT)
    c.set_font_size(17)
    c.move_to(62, y + 29)
    c.show_text("This week by surface")

    as_of = local_time(bd.get("as_of"))
    if as_of:
        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(12)
        label = f"share of this week's usage · as of {as_of.split(', ')[-1]}"
        e = c.text_extents(label)
        c.move_to(W - 62 - e.width - e.x_bearing, y + 29)
        c.show_text(label)

    colours = [BLUE, MAUVE, TEAL, PEACH, GREEN]
    bx, bw, bh = 62.0, W - 124.0, 14.0
    c.set_source_rgb(*OVERLAY)
    rounded(c, bx, y + 45, bw, bh, bh / 2)
    c.fill()
    total = sum(r["percent"] for r in rows) or 1
    c.save()
    rounded(c, bx, y + 45, bw, bh, bh / 2)
    c.clip()
    x = bx
    for i, r in enumerate(rows):
        seg = bw * r["percent"] / total
        c.set_source_rgb(*colours[i % len(colours)])
        c.rectangle(x, y + 45, seg, bh)
        c.fill()
        x += seg
    c.restore()

    x = 62.0
    c.set_font_size(13)
    for i, r in enumerate(rows):
        c.set_source_rgb(*colours[i % len(colours)])
        c.arc(x + 5, y + 76, 5, 0, 6.2832)
        c.fill()
        label = f"{r.get('display_name') or r.get('key')} {r['percent']}%"
        c.set_source_rgb(*SUBTEXT)
        c.move_to(x + 15, y + 81)
        c.show_text(label)
        x += 15 + c.text_extents(label).x_advance + 26


OCSPEND = "/var/lib/claude-limits/ocspend.toml"


def load_ocspend():
    """The Go plan has no usage API, so its bars are spend against the
    published caps. Same three windows, a different quantity -- say so."""
    try:
        with open(OCSPEND) as fh:
            text = fh.read()
    except OSError:
        return None
    pct, spent = {}, None
    for line in text.splitlines():
        key, _, rest = line.partition("=")
        key = key.strip()
        if key in ("session", "weekly_all", "weekly_scoped"):
            try:
                pct[key] = float(rest.strip())
            except ValueError:
                pass
        elif line.startswith("# spent:"):
            spent = line[len("# spent:"):].strip()
    if not pct:
        return None
    return {
        "email": "opencode-go",
        "host": "node",
        "live": True,
        "tier": "OpenCode Go",
        "note": spent,
        "rings": {k: {"percent": pct.get(k, 0.0), "resets_at": None,
                      "severity": None, "model": None}
                  for k in ("session", "weekly_all", "weekly_scoped")},
    }


def load():
    try:
        with open(DATA) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    accounts = list(data.get("accounts", []))
    go = load_ocspend()
    if go:
        accounts.append(go)
    return accounts, data.get("updated", 0)


def draw(c, accounts, idx, updated=0):
    c.set_source_rgb(*BASE)
    rounded(c, 0, 0, W, H, 16)
    c.fill()
    c.select_font_face("sans")

    if not accounts:
        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(20)
        c.move_to(40, H / 2)
        c.show_text("No usage data yet -- run: systemctl --user start claude-limits")
        return {"prev": None, "next": None}

    a = accounts[idx]
    rings = a.get("rings") or {}

    # --- Header -----------------------------------------------------------
    c.set_source_rgb(*TEXT)
    c.set_font_size(28)
    c.move_to(40, 54)
    c.show_text(a.get("email") or "unknown")
    name_w = c.text_extents(a.get("email") or "unknown").x_advance

    tier = TIERS.get(a.get("tier"), a.get("tier") or "unknown plan")
    c.set_font_size(13)
    tw = c.text_extents(tier).width + 20
    c.set_source_rgb(*OVERLAY)
    rounded(c, 40 + name_w + 14, 34, tw, 24, 7)
    c.fill()
    c.set_source_rgb(*TEXT)
    c.move_to(40 + name_w + 24, 51)
    c.show_text(tier)

    age_min = int((datetime.now().timestamp() - updated) / 60) if updated else None
    live = a.get("live")
    bits = [f"read from {a.get('host', '?')}"]
    bits.append("live" if live else "cached")
    if age_min is not None:
        bits.append(f"{age_min} min ago" if age_min else "just now")
    spend = a.get("spend")
    if spend is not None:
        bits.append("extra usage " + ("on" if spend.get("enabled") else "off"))
    bits.append(f"{idx + 1} of {len(accounts)} accounts")
    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(14)
    c.move_to(40, 78)
    c.show_text(" · ".join(bits))

    if not live or (age_min is not None and age_min > 20):
        c.set_source_rgb(*PEACH)
        c.move_to(W - 250, 78)
        c.show_text("figures may be out of date")

    # --- Chevrons ---------------------------------------------------------
    btn, gap, by = 38.0, 10.0, 30.0
    bx_next = W - 40 - btn
    bx_prev = bx_next - btn - gap
    hits = {"prev": None, "next": None}
    for name, bx, glyph, on in (
        ("prev", bx_prev, "‹", idx > 0),
        ("next", bx_next, "›", idx < len(accounts) - 1),
    ):
        c.set_source_rgba(*SURFACE, 1.0 if on else 0.45)
        rounded(c, bx, by, btn, btn, 9)
        c.fill()
        c.set_source_rgba(*TEXT, 1.0 if on else 0.28)
        c.set_font_size(26)
        e = c.text_extents(glyph)
        c.move_to(
            bx + btn / 2 - e.width / 2 - e.x_bearing,
            by + btn / 2 - e.y_bearing - e.height / 2,
        )
        c.show_text(glyph)
        if on:
            hits[name] = (bx, by, btn, btn)

    # --- One block per window --------------------------------------------
    y = 120.0
    row_h = 112.0
    for key, title in WINDOWS:
        r = rings.get(key) or {}
        pct = r.get("percent")
        known = pct is not None
        pct = pct or 0
        col = severity_color(r.get("severity"), pct)

        c.set_source_rgb(*SURFACE)
        rounded(c, 40, y, W - 80, row_h - 18, 12)
        c.fill()

        label = WINDOW_LABELS.get(a.get("email"), {}).get(key, title)
        model = r.get("model")
        if key == "weekly_scoped" and model and a.get("email") not in WINDOW_LABELS:
            label = f"Weekly · {model}"
        c.set_source_rgb(*TEXT)
        c.set_font_size(17)
        c.move_to(62, y + 29)
        c.show_text(label)

        # The figure, large, in the colour the server's severity implies.
        c.set_source_rgb(*col)
        c.set_font_size(38)
        fig = f"{pct:.0f}%" if known else "--"
        e = c.text_extents(fig)
        c.move_to(W - 62 - e.width - e.x_bearing, y + 41)
        c.show_text(fig)

        # Bar
        bx, bw, bh = 62.0, W - 124.0 - 120.0, 14.0
        byy = y + 45
        c.set_source_rgb(*OVERLAY)
        rounded(c, bx, byy, bw, bh, bh / 2)
        c.fill()
        if known and pct > 0:
            c.set_source_rgb(*col)
            rounded(c, bx, byy, max(bw * min(pct, 100) / 100.0, bh), bh, bh / 2)
            c.fill()

        # Everything else known about the window, spelled out.
        detail = []
        if a.get("note") and key == "session":
            detail.append(a["note"])
        if known:
            detail.append(f"{100 - min(pct, 100):.0f}% headroom")
        sev = r.get("severity")
        if sev:
            detail.append(f"severity {sev}")
        if model:
            detail.append(f"scope {model}")
        resets = r.get("resets_at")
        if resets:
            delta = human_delta(resets)
            when = local_time(resets)
            if delta and when:
                detail.append(f"resets {delta} ({when})")
        elif not known:
            detail.append("not reported for this account")
        else:
            detail.append("no reset time reported")

        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(13)
        c.move_to(62, y + 80)
        c.show_text(" · ".join(detail))

        y += row_h

    c.set_source_rgb(*SURFACE)
    rounded(c, 40, y, W - 80, row_h - 18, 12)
    c.fill()
    if a.get("reset_credits") is not None:
        draw_resets(c, a["reset_credits"], y)
    elif a.get("breakdown"):
        draw_breakdown(c, a["breakdown"], y)
    else:
        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(13)
        c.move_to(62, y + 52)
        c.show_text("No further detail reported for this account")

    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(11)
    c.move_to(40, H - 16)
    c.show_text("‹ › or arrow keys to change account · esc to dismiss")
    return hits


def main():
    argv = [x for x in sys.argv[1:]]
    png = None
    if "--png" in argv:
        i = argv.index("--png")
        png = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    want = argv[0] if argv else None

    accounts, updated = load()
    idx = 0
    if want:
        idx = next(
            (i for i, a in enumerate(accounts) if a.get("email") == want), 0
        )

    if png:
        import cairo

        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        draw(cairo.Context(surf), accounts, idx, updated)
        surf.write_to_png(png)
        return 0

    # gtk4-layer-shell must precede libwayland-client in the link order; with
    # the Python bindings the only way to guarantee that is LD_PRELOAD.
    lib = "/usr/lib/libgtk4-layer-shell.so"
    if os.path.exists(lib) and lib not in os.environ.get("LD_PRELOAD", ""):
        os.environ["LD_PRELOAD"] = lib
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Toggle: a second tap on the same button closes it. Tapping a *different*
    # account's button should switch rather than close, so the pidfile carries
    # which account is open.
    try:
        with open(PIDFILE) as fh:
            pid, shown = (fh.read().strip().split(None, 1) + [""])[:2]
        os.kill(int(pid), 0)
        if want is None or want == shown:
            os.kill(int(pid), signal.SIGTERM)
            os.unlink(PIDFILE)
            return 0
        os.kill(int(pid), signal.SIGTERM)
        os.unlink(PIDFILE)
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        try:
            os.unlink(PIDFILE)
        except FileNotFoundError:
            pass

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk, Gdk, Gtk4LayerShell as LayerShell

    shown = accounts[idx].get("email", "") if accounts else ""
    with open(PIDFILE, "w") as fh:
        fh.write(f"{os.getpid()} {shown}")

    state = {"idx": idx, "hits": {"prev": None, "next": None}}

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.EXCLUSIVE)

        area = Gtk.DrawingArea()
        area.set_content_width(W)
        area.set_content_height(H)
        area.set_draw_func(
            lambda _a, c, _w, _h: state.update(
                hits=draw(c, accounts, state["idx"], updated)
            )
        )
        win.set_child(area)

        def step(delta):
            new = state["idx"] + delta
            if 0 <= new < len(accounts):
                state["idx"] = new
                area.queue_draw()
                return True
            return False

        def on_key(_c, kv, *_):
            if kv == Gdk.KEY_Escape:
                app.quit()
                return True
            if kv in (Gdk.KEY_Left, Gdk.KEY_h):
                return step(-1)
            if kv in (Gdk.KEY_Right, Gdk.KEY_l):
                return step(1)
            return False

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", on_key)
        win.add_controller(keys)

        def on_click(_g, _n, x, y):
            for name, rect in state["hits"].items():
                if rect and rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]:
                    step(-1 if name == "prev" else 1)
                    return
            app.quit()

        click = Gtk.GestureClick()
        click.connect("pressed", on_click)
        win.add_controller(click)
        win.present()

    app = Gtk.Application(application_id="dev.local.llmdetail")
    provider = Gtk.CssProvider()
    provider.load_from_data(b"window { background: transparent; }")

    def setup(a):
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        on_activate(a)

    app.connect("activate", setup)
    try:
        return app.run([])
    finally:
        try:
            os.unlink(PIDFILE)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    sys.exit(main())
