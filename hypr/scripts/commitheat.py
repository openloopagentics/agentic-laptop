#!/usr/bin/env python3
"""Commits by hour of day, month by month, as a layer-shell overlay.

Reads the JSON written by `gitcommits --hours`, which carries every month
that has commits, so paging between them costs nothing. Re-running toggles
the overlay off, the way the F-key overlay does; the chevrons, the arrow
keys and h/l move between months, and escape dismisses.

`--png PATH` draws it to a file instead of the screen, so the layout can be
checked without a compositor; `--month YYYY-MM` picks which one.
"""
import json
import os
import signal
import sys
from calendar import month_name
from datetime import datetime

DATA = "/var/lib/claude-limits/commit-hours.json"
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "commitheat.pid")
W, H = 1080, 600

# Catppuccin Mocha, matching the strip and the F-key overlay.
BASE = (0.118, 0.118, 0.180)
SURFACE = (0.192, 0.196, 0.267)
TEXT = (0.804, 0.839, 0.957)
SUBTEXT = (0.651, 0.678, 0.784)
BLUE = (0.537, 0.706, 0.980)
MAUVE = (0.796, 0.651, 0.969)
PEACH = (0.980, 0.702, 0.529)
RED = (0.953, 0.545, 0.659)


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def heat(frac):
    """Dark surface through blue to red: cold hours recede, peaks shout."""
    if frac <= 0:
        return SURFACE
    if frac < 0.5:
        return lerp(SURFACE, BLUE, frac / 0.5)
    if frac < 0.8:
        return lerp(BLUE, MAUVE, (frac - 0.5) / 0.3)
    return lerp(MAUVE, RED, (frac - 0.8) / 0.2)


def load():
    """Every month with commits, oldest first, plus the file's own age."""
    try:
        with open(DATA) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return [], 0
    # An older collector wrote a single month at the top level.
    months = data.get("months")
    if months is None:
        months = [data] if data.get("hours") else []
    return months, data.get("updated", 0)


def rounded(c, x, y, w, h, r):
    import math

    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    c.close_path()


def scales(months):
    """Peak hour and peak day-cell across every month.

    Bar heights are scaled per month, so a quiet month still shows its shape.
    Colour is scaled across all of them, so paging between months says
    something true about size: one commit an hour must not glow like four
    hundred.
    """
    hour_peak = max((max(m["hours"]) for m in months if m["hours"]), default=1)
    day_peak = max(
        (max(max(d) for d in m["days"]) for m in months if m["days"]), default=1
    )
    return max(hour_peak, 1), max(day_peak, 1)


def draw(c, months, idx, updated=0, scale=None):
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
        c.show_text("No commit data yet -- run: systemctl --user start git-commits")
        return {"prev": None, "next": None}

    data = months[idx]
    hours = data["hours"]
    days = data["days"]
    hour_peak, day_peak_all = scale or scales(months)
    total = data.get("total", sum(hours))
    year, mon = (int(x) for x in data["month"].split("-"))

    # Header
    c.set_source_rgb(*TEXT)
    c.set_font_size(26)
    c.move_to(40, 52)
    c.show_text(f"Commits by hour · {month_name[mon]} {year}")

    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(14)
    busiest = max(range(24), key=lambda h: hours[h])
    active = sum(1 for d in days if sum(d))
    c.move_to(40, 76)
    c.show_text(
        f"{total} commits · {active} active days · "
        f"busiest hour {busiest:02d}:00 with {hours[busiest]} · "
        f"{idx + 1} of {len(months)} months"
    )

    age = (datetime.now().timestamp() - updated) / 60
    if age > 45:
        c.set_source_rgb(*PEACH)
        c.move_to(W - 220, 76)
        c.show_text(f"stale: {int(age)} min old")

    # Chevrons, top right. Dimmed to unusable at either end of the run rather
    # than hidden, so the control does not move under the pointer.
    btn = 38.0
    gap = 10.0
    by = 30.0
    bx_next = W - 40 - btn
    bx_prev = bx_next - btn - gap
    hits = {"prev": None, "next": None}
    for name, bx, glyph, live in (
        ("prev", bx_prev, "\u2039", idx > 0),
        ("next", bx_next, "\u203a", idx < len(months) - 1),
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

    # --- Histogram: the headline, commits per hour of day ------------------
    hx, hy, hw, hh = 40, 100, W - 80, 210
    peak = max(hours) or 1
    slot = hw / 24

    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(11)
    for frac in (0.5, 1.0):
        gy = hy + hh - hh * frac
        c.set_source_rgba(1, 1, 1, 0.07)
        c.set_line_width(1)
        c.move_to(hx, gy)
        c.line_to(hx + hw, gy)
        c.stroke()
        c.set_source_rgb(*SUBTEXT)
        c.move_to(hx + hw + 6, gy + 4)
        c.show_text(str(int(peak * frac)))

    for h in range(24):
        v = hours[h]
        bh = hh * (v / peak)
        bx = hx + slot * h + slot * 0.18
        bw = slot * 0.64
        c.set_source_rgb(*heat(max(v / hour_peak, 0.10) if v else 0))
        rounded(c, bx, hy + hh - bh, bw, max(bh, 2), min(4, bw / 2))
        c.fill()

        if v:
            c.set_source_rgb(*TEXT)
            c.set_font_size(12)
            e = c.text_extents(str(v))
            c.move_to(bx + bw / 2 - e.width / 2, hy + hh - bh - 6)
            c.show_text(str(v))

        c.set_source_rgb(*SUBTEXT)
        c.set_font_size(12)
        lbl = f"{h:02d}"
        e = c.text_extents(lbl)
        c.move_to(bx + bw / 2 - e.width / 2, hy + hh + 18)
        c.show_text(lbl)

    # --- Punchcard: the same month broken out by day -----------------------
    # Only as far as today: the rest of the month has not happened yet, and
    # padding it with empty rows just squeezes the ones that carry data.
    now = datetime.now()
    if (now.year, now.month) == (year, mon):
        days = days[: now.day]
    px, py = 40, 368
    cell = (W - 80 - 34) / 24
    rows = max(len(days), 1)
    ch = min(16.0, (H - py - 34) / rows)
    dpeak = day_peak_all

    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(12)
    c.move_to(px, py - 10)
    c.show_text("by day")

    for i, row in enumerate(days):
        y = py + i * ch
        last = i == len(days) - 1
        if (i + 1) % 7 == 1 or (last and (i + 1) % 7 > 3):
            c.set_source_rgb(*SUBTEXT)
            c.set_font_size(10)
            c.move_to(px, y + ch - 3)
            c.show_text(f"{i + 1:02d}")
        for h in range(24):
            v = row[h]
            c.set_source_rgb(*heat(max(v / dpeak, 0.10) if v else 0))
            rounded(
                c,
                px + 26 + h * cell,
                y,
                cell - 2.5,
                max(ch - 2.5, 2.0),
                min(2.5, (ch - 2.5) / 2),
            )
            c.fill()

    c.set_source_rgb(*SUBTEXT)
    c.set_font_size(11)
    c.move_to(px, H - 16)
    c.show_text("\u2039 \u203a or arrow keys to change month · esc to dismiss")

    return hits


def main():
    if "--png" in sys.argv:
        import cairo

        months, updated = load()
        idx = len(months) - 1
        if "--month" in sys.argv:
            want = sys.argv[sys.argv.index("--month") + 1]
            idx = next(
                (i for i, m in enumerate(months) if m["month"] == want), idx
            )
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        draw(cairo.Context(surf), months, max(idx, 0), updated)
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

    months, updated = load()
    # Opens on the newest month; paging walks back through the run.
    state = {"idx": max(len(months) - 1, 0), "hits": {"prev": None, "next": None}}

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        # Unlike the F-key bar this one is read, not typed through, so it may
        # hold the keyboard -- that is what makes Escape work.
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.EXCLUSIVE)

        area = Gtk.DrawingArea()
        area.set_content_width(W)
        area.set_content_height(H)

        def on_draw(_a, c, _w, _h):
            state["hits"] = draw(c, months, state["idx"], updated)

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
            # A chevron navigates; anywhere else dismisses, as it did before
            # there was anything on the overlay worth clicking.
            for name, rect in state["hits"].items():
                if rect and rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]:
                    step(-1 if name == "prev" else 1)
                    return
            app.quit()

        click = Gtk.GestureClick()
        click.connect("pressed", on_click)
        win.add_controller(click)

        win.present()

    app = Gtk.Application(application_id="dev.local.commitheat")
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
