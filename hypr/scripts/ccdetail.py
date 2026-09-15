#!/usr/bin/env python3
"""Agent spend, month by month, as a layer-shell overlay.

Reads the JSON written by `ccfleet --json`: ccusage's daily figures from every
machine, split by model and by agent. The month's days are drawn as bars
stacked by machine, with where the money went beneath. Re-running toggles the
overlay off; the chevrons, the arrow keys and h/l move between months, and
escape dismisses.

`--png PATH` draws it to a file instead of the screen, so the layout can be
checked without a compositor; `--month YYYY-MM` picks which one.
"""
import json
import os
import signal
import sys
from calendar import month_name, monthrange
from datetime import datetime

DATA = "/var/lib/claude-limits/ccusage.json"
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ccdetail.pid")
W, H = 1080, 600

# Catppuccin Mocha, matching the strip and the other overlays.
BASE = (0.118, 0.118, 0.180)
SURFACE = (0.192, 0.196, 0.267)
OVERLAY = (0.271, 0.278, 0.353)
TEXT = (0.804, 0.839, 0.957)
SUBTEXT = (0.651, 0.678, 0.784)
PEACH = (0.980, 0.702, 0.529)
# One colour per machine, in the order they are listed.
SERIES = [
    (0.537, 0.706, 0.980),  # blue
    (0.796, 0.651, 0.969),  # mauve
    (0.651, 0.890, 0.631),  # green
    (0.980, 0.702, 0.529),  # peach
    (0.580, 0.886, 0.835),  # teal
    (0.953, 0.545, 0.659),  # red
]


def money(v):
    if v >= 10_000:
        return f"${v / 1000:.0f}k"
    if v >= 1000:
        return f"${v / 1000:.1f}k"
    if v >= 10:
        return f"${v:.0f}"
    return f"${v:.2f}"


def load():
    """Months that have any spend, oldest first, each already summed."""
    try:
        with open(DATA) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return [], [], 0, []
    hosts = data.get("hosts", {})
    names = list(hosts)
    months = {}
    for host, h in hosts.items():
        for day, v in h.get("days", {}).items():
            key = day[:7]
            m = months.setdefault(key, {"month": key, "days": {}, "hosts": {},
                                        "models": {}, "agents": {}, "total": 0.0})
            cell = m["days"].setdefault(int(day[8:10]), {})
            cell[host] = cell.get(host, 0) + v["cost"]
            m["hosts"][host] = m["hosts"].get(host, 0) + v["cost"]
            for k, c in v.get("models", {}).items():
                m["models"][k] = m["models"].get(k, 0) + c
            for k, c in v.get("agents", {}).items():
                m["agents"][k] = m["agents"].get(k, 0) + c
            m["total"] += v["cost"]
    ordered = [months[k] for k in sorted(months) if months[k]["total"] > 0]
    failed = [n for n, h in hosts.items() if not h.get("ok")]
    return ordered, names, data.get("updated", 0), failed


def rounded(c, x, y, w, h, r):
    import math

    r = max(min(r, w / 2, h / 2), 0)
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    c.close_path()


def draw(c, months, names, idx, updated=0, failed=()):
    """Draw one month. Returns {"prev": rect, "next": rect} for hit-testing,
    with a rect of None where that direction is not available."""
    c.set_source_rgb(*BASE)
    rounded(c, 0, 0, W, H, 16)
    c.fill()
    c.select_font_face("sans")

    if not months:
        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(20)
        c.move_to(40, H / 2)
        c.show_text("No spend data yet -- run: systemctl --user start cc-usage")
        return {"prev": None, "next": None}

    m = months[idx]
    year, mon = (int(x) for x in m["month"].split("-"))
    colour = {n: SERIES[i % len(SERIES)] for i, n in enumerate(names)}

    # --- Header -----------------------------------------------------------
    c.set_source_rgb(*TEXT)
    c.set_font_size(26)
    c.move_to(40, 52)
    c.show_text(f"Agent spend · {month_name[mon]} {year}")

    now = datetime.now()
    current = (now.year, now.month) == (year, mon)
    active = sum(1 for d in m["days"].values() if sum(d.values()) > 0)
    bits = [f"{money(m['total'])} total"]
    if current:
        today = sum(m["days"].get(now.day, {}).values())
        bits.append(f"{money(today)} today")
    bits.append(f"{money(m['total'] / max(active, 1))} per active day")
    bits.append(f"{idx + 1} of {len(months)} months")
    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(14)
    c.move_to(40, 76)
    c.show_text(" · ".join(bits))

    age = (datetime.now().timestamp() - updated) / 60
    warn = []
    if age > 45:
        warn.append(f"stale: {int(age)} min old")
    if failed:
        warn.append("no data from " + ", ".join(failed))
    if warn:
        c.set_source_rgb(*PEACH)
        text = " · ".join(warn)
        c.move_to(W - 150 - c.text_extents(text).x_advance, 76)
        c.show_text(text)

    # Chevrons, top right; dimmed rather than hidden at either end.
    btn, gap, by = 38.0, 10.0, 30.0
    bx_next = W - 40 - btn
    bx_prev = bx_next - btn - gap
    hits = {"prev": None, "next": None}
    for name, bx, glyph, live in (
        ("prev", bx_prev, "‹", idx > 0),
        ("next", bx_next, "›", idx < len(months) - 1),
    ):
        c.set_source_rgba(*SURFACE, 1.0 if live else 0.45)
        rounded(c, bx, by, btn, btn, 9)
        c.fill()
        c.set_source_rgba(*TEXT, 1.0 if live else 0.28)
        c.set_font_size(26)
        e = c.text_extents(glyph)
        c.move_to(bx + btn / 2 - e.width / 2 - e.x_bearing, by + btn / 2 - e.y_bearing - e.height / 2)
        c.show_text(glyph)
        if live:
            hits[name] = (bx, by, btn, btn)

    # --- Days, stacked by machine -------------------------------------------
    days_in = monthrange(year, mon)[1]
    hx, hy, hw, hh = 40, 118, W - 110, 220
    peak = max((sum(d.values()) for d in m["days"].values()), default=1) or 1
    slot = hw / days_in

    for frac in (0.5, 1.0):
        gy = hy + hh - hh * frac
        c.set_source_rgba(1, 1, 1, 0.07)
        c.set_line_width(1)
        c.move_to(hx, gy)
        c.line_to(hx + hw, gy)
        c.stroke()
        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(11)
        c.move_to(hx + hw + 8, gy + 4)
        c.show_text(money(peak * frac))

    bw = slot * 0.66
    for day in range(1, days_in + 1):
        bx = hx + slot * (day - 1) + (slot - bw) / 2
        cell = m["days"].get(day, {})
        total = sum(cell.values())
        future = current and day > now.day
        if total <= 0:
            c.set_source_rgba(*SURFACE, 0.4 if future else 1.0)
            rounded(c, bx, hy + hh - 2, bw, 2, 1)
            c.fill()
        else:
            # Clip to the whole bar's rounded outline, then fill the stack.
            full = hh * total / peak
            c.save()
            rounded(c, bx, hy + hh - full, bw, max(full, 2), min(3, bw / 2))
            c.clip()
            top = hy + hh
            for n in names:
                v = cell.get(n, 0)
                if v <= 0:
                    continue
                seg = hh * v / peak
                c.set_source_rgb(*colour[n])
                c.rectangle(bx, top - seg, bw, seg + 0.5)
                c.fill()
                top -= seg
            c.restore()
            if total >= peak * 0.999:
                c.set_source_rgb(*TEXT)
                c.set_font_size(12)
                label = money(total)
                e = c.text_extents(label)
                c.move_to(bx + bw / 2 - e.width / 2, hy + hh - full - 7)
                c.show_text(label)

        is_today = current and day == now.day
        near_today = current and abs(day - now.day) == 1
        if is_today or ((day == 1 or day % 5 == 0) and not near_today):
            c.set_source_rgb(*(TEXT if is_today else SUBTEXT))
            c.set_font_size(11)
            lbl = f"{day:02d}"
            e = c.text_extents(lbl)
            c.move_to(bx + bw / 2 - e.width / 2, hy + hh + 17)
            c.show_text(lbl)

    # --- Where it went: machine, model, agent ------------------------------
    py = 392
    colw = (W - 80 - 40) / 3
    groups = (
        ("by machine", m["hosts"], True),
        ("by model", m["models"], False),
        ("by agent", m["agents"], False),
    )
    for gi, (title, values, keyed) in enumerate(groups):
        gx = 40 + gi * (colw + 20)
        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(12)
        c.move_to(gx, py - 12)
        c.show_text(title)
        rows = sorted(((k, v) for k, v in values.items() if v > 0.005), key=lambda kv: -kv[1])
        shown = rows[:6]
        if len(rows) > 6:
            shown = rows[:5] + [(f"{len(rows) - 5} more", sum(v for _, v in rows[5:]))]
        top_v = shown[0][1] if shown else 1
        for ri, (k, v) in enumerate(shown):
            ry = py + ri * 28
            c.set_source_rgb(*SURFACE)
            rounded(c, gx, ry, colw, 22, 6)
            c.fill()
            c.set_source_rgb(*OVERLAY)
            rounded(c, gx, ry, max(colw * v / top_v, 6), 22, 6)
            c.fill()
            indent = 8
            if keyed:
                # The machine's colour as a swatch: the key to the stacks above.
                c.set_source_rgb(*colour.get(k, SERIES[0]))
                rounded(c, gx + 7, ry + 6, 10, 10, 3)
                c.fill()
                indent = 24
            c.set_source_rgb(*TEXT)
            c.set_font_size(12)
            name = k.replace("claude-", "")
            c.move_to(gx + indent, ry + 15)
            c.show_text(name[:26])
            label = f"{money(v)} · {100 * v / max(m['total'], 1e-9):.0f}%"
            c.set_source_rgb(*TEXT)
            e = c.text_extents(label)
            c.move_to(gx + colw - 8 - e.x_advance, ry + 15)
            c.show_text(label)

    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(11)
    c.move_to(40, H - 16)
    c.show_text("‹ › or arrow keys to change month · esc to dismiss · figures from ccusage, API list prices")

    return hits


def main():
    if "--png" in sys.argv:
        import cairo

        months, names, updated, failed = load()
        idx = len(months) - 1
        if "--month" in sys.argv:
            want = sys.argv[sys.argv.index("--month") + 1]
            idx = next((i for i, m in enumerate(months) if m["month"] == want), idx)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        draw(cairo.Context(surf), months, names, max(idx, 0), updated, failed)
        surf.write_to_png(sys.argv[sys.argv.index("--png") + 1])
        return 0

    # gtk4-layer-shell must precede libwayland-client in the link order; with
    # the Python bindings the only way to guarantee that is LD_PRELOAD.
    lib = "/usr/lib/libgtk4-layer-shell.so"
    if os.path.exists(lib) and lib not in os.environ.get("LD_PRELOAD", ""):
        os.environ["LD_PRELOAD"] = lib
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Toggle: if a live instance owns the pidfile, kill it and stop.
    try:
        with open(PIDFILE) as fh:
            os.kill(int(fh.read().strip()), signal.SIGTERM)
        os.unlink(PIDFILE)
        return 0
    except (FileNotFoundError, ValueError, ProcessLookupError):
        try:
            os.unlink(PIDFILE)
        except FileNotFoundError:
            pass

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk, Gdk, Gtk4LayerShell as LayerShell

    with open(PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))

    months, names, updated, failed = load()
    state = {"idx": max(len(months) - 1, 0), "hits": {"prev": None, "next": None}}

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.EXCLUSIVE)

        area = Gtk.DrawingArea()
        area.set_content_width(W)
        area.set_content_height(H)

        def on_draw(_a, c, _w, _h):
            state["hits"] = draw(c, months, names, state["idx"], updated, failed)

        area.set_draw_func(on_draw)
        win.set_child(area)

        def step(delta):
            new = state["idx"] + delta
            if 0 <= new < len(months):
                state["idx"] = new
                area.queue_draw()
                return True
            return False

        def on_key(_c, keyval, *_):
            if keyval == Gdk.KEY_Escape:
                app.quit()
                return True
            if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
                return step(-1)
            if keyval in (Gdk.KEY_Right, Gdk.KEY_l):
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

    app = Gtk.Application(application_id="dev.local.ccdetail")
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
