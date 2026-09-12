#!/usr/bin/env python3
"""The Touch Bar, on screen, for machines that have no Touch Bar.

Reads the same tiny-dfr config and the same state files the strip does, so a
machine with no Touch Bar shows the same buttons in a layer-shell bar along
the bottom of the screen. Re-running toggles it off.

Clicks are injected through a uinput virtual keyboard. Keys sent over the
Wayland virtual-keyboard protocol reach applications but never trigger
compositor keybinds, so a real kernel-level device is the only route that
makes a workspace or media button behave like the strip's.

Navigation is by tap, since there is no Fn key to hold: the `fn` chip at the
left toggles the media layer, buttons carrying a Layer key switch to it (the
stock config's `F1-12` and `back`), and `x` dismisses the bar.

    --png FILE   draw one frame to a file instead of the screen
    --dump       print the parsed layers and exit
    --force      show even on a machine that has a Touch Bar
"""
import os
import signal
import subprocess
import sys
import tomllib
from pathlib import Path

PIDFILE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dfrbar.pid"
HEIGHT = 72
PAD = 6
REPO = Path(__file__).resolve().parent.parent.parent

# Catppuccin Mocha, matching the strip and the overlays.
BASE = (0.118, 0.118, 0.180)
SURFACE = (0.192, 0.196, 0.267)
OVERLAY = (0.271, 0.278, 0.353)
TEXT = (0.804, 0.839, 0.957)
SUBTEXT = (0.651, 0.678, 0.784)
ASK = (0.953, 0.545, 0.659)
DONE = (0.651, 0.890, 0.631)
BLUE = (0.537, 0.706, 0.980)

# tiny-dfr names its actions after input-linux's Key enum. Most map onto
# evdev by uppercasing; these few do not.
KEY_ALIASES = {
    "IllumUp": "KBDILLUMUP",
    "IllumDown": "KBDILLUMDOWN",
    "Illum": "KBDILLUMTOGGLE",
}


def config_paths():
    """Stock config first, then /etc, then a user override; later wins.

    A machine with no Touch Bar has no tiny-dfr package, so the repo's own
    example is the last resort -- otherwise there would be nothing to draw.
    """
    out = []
    for p in ("/usr/share/tiny-dfr/config.toml", "/etc/tiny-dfr/config.toml",
              os.path.expanduser("~/.config/agentic-laptop/bar.toml")):
        if os.path.exists(p):
            out.append(p)
    if not out:
        ex = REPO / "examples/tiny-dfr.config.toml"
        if ex.exists():
            out.append(str(ex))
    return out


def load_config():
    merged = {}
    for p in config_paths():
        try:
            with open(p, "rb") as fh:
                merged.update(tomllib.load(fh))
        except (OSError, tomllib.TOMLDecodeError) as e:
            print(f"dfrbar: {p}: {e}", file=sys.stderr)
    return merged


def has_touchbar():
    """The strip is a connected DRM connector on Apple's display-pipe driver.

    The driver belongs to the card, not to the connector, so it is read from
    `cardN/device/driver` rather than from `cardN-DSI-1/device/driver`, which
    does not exist.
    """
    for conn in Path("/sys/class/drm").glob("card*-*"):
        card = conn.name.split("-", 1)[0]
        try:
            drv = (Path("/sys/class/drm") / card / "device/driver").resolve().name
            status = (conn / "status").read_text().strip()
        except OSError:
            continue
        if status == "connected" and drv in ("adp", "appletbdrm"):
            return True
    return False


def palette(cfg):
    pal = {}
    for name, hexv in (cfg.get("Palette") or {}).items():
        h = hexv.lstrip("#")
        if len(h) == 6:
            pal[name] = tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return pal


def layers(cfg):
    """Every layer, in the order the strip reaches them."""
    out = {
        "primary": list(cfg.get("PrimaryLayerKeys") or []),
        "media": list(cfg.get("MediaLayerKeys") or []),
    }
    for name, keys in (cfg.get("ExtraLayers") or {}).items():
        out[name] = list(keys)
    return out


def read_toml(path):
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


class Injector:
    """A uinput keyboard, created on first use and kept for the session.

    Without it the bar still draws and still switches layers; only sending
    keys is lost, and saying so once beats failing silently on every press.
    """

    def __init__(self, every_action):
        self.ui = None
        self.warned = False
        self.every = every_action

    @staticmethod
    def codes(names):
        from evdev import ecodes
        out = []
        for n in names:
            code = ecodes.ecodes.get("KEY_" + KEY_ALIASES.get(n, n).upper())
            if code is None:
                return None
            out.append(code)
        return out

    def open(self):
        from evdev import UInput, ecodes
        import time
        # The capability set is fixed when the device is created, so it has to
        # advertise every key any button might send, not just the first one.
        caps = set()
        for action in self.every:
            c = self.codes(action)
            if c:
                caps.update(c)
        self.ui = UInput({ecodes.EV_KEY: sorted(caps)}, name="agentic-dfrbar")
        time.sleep(0.3)              # let the compositor notice the device

    def send(self, names):
        if not names:
            return
        try:
            from evdev import ecodes as e
        except ImportError:
            return self.complain("python-evdev is not installed")
        codes = self.codes(names)
        if codes is None:
            return self.complain(f"no evdev code for {names}")
        if self.ui is None:
            try:
                self.open()
            except Exception as ex:
                return self.complain(f"cannot open /dev/uinput ({ex})")
        for c in codes:
            self.ui.write(e.EV_KEY, c, 1)
        self.ui.syn()
        for c in reversed(codes):
            self.ui.write(e.EV_KEY, c, 0)
        self.ui.syn()

    def complain(self, msg):
        if not self.warned:
            print(f"dfrbar: cannot send keys: {msg}", file=sys.stderr)
            self.warned = True


def actions_of(b):
    a = b.get("Action")
    if a is None:
        return []
    return list(a) if isinstance(a, list) else [a]


# tiny-dfr's own icons ship with the daemon, which a machine with no Touch Bar
# has no reason to install. Fall back to the freedesktop names for the same
# ideas, which any GTK desktop already has.
ICON_FALLBACKS = {
    "brightness_low": ["display-brightness-low-symbolic", "brightness-low",
                       "display-brightness-symbolic"],
    "brightness_high": ["display-brightness-high-symbolic", "brightness-high",
                        "display-brightness-symbolic"],
    "backlight_low": ["keyboard-brightness-symbolic", "display-brightness-low-symbolic"],
    "backlight_high": ["keyboard-brightness-symbolic", "display-brightness-high-symbolic"],
    "mic_off": ["microphone-sensitivity-muted-symbolic", "microphone-disabled-symbolic"],
    "search": ["system-search-symbolic", "edit-find-symbolic"],
    "fast_rewind": ["media-skip-backward-symbolic", "media-seek-backward-symbolic"],
    "play_pause": ["media-playback-start-symbolic"],
    "fast_forward": ["media-skip-forward-symbolic", "media-seek-forward-symbolic"],
    "volume_off": ["audio-volume-muted-symbolic"],
    "volume_down": ["audio-volume-low-symbolic"],
    "volume_up": ["audio-volume-high-symbolic"],
}


def icon_path(name):
    """tiny-dfr's icon first, then the icon theme's nearest equivalent."""
    for d in ("/etc/tiny-dfr", "/usr/share/tiny-dfr"):
        for ext in (".svg", ".png"):
            p = Path(d) / (name + ext)
            if p.exists():
                return str(p)
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk, Gdk
        display = Gdk.Display.get_default()
        theme = Gtk.IconTheme.get_for_display(display) if display else Gtk.IconTheme.new()
        for cand in [name.replace("_", "-")] + ICON_FALLBACKS.get(name, []):
            if theme.has_icon(cand):
                pi = theme.lookup_icon(cand, None, 32, 1, Gtk.TextDirection.NONE, 0)
                f = pi.get_file() if pi else None
                if f and f.get_path():
                    return f.get_path()
    except Exception:
        pass
    return None


def draw_icon(c, path, cx, cy, size, rgb=None):
    """Draw an icon in `rgb`, whatever colour the file itself uses.

    Theme icons are symbolic: black on transparent, which lands invisibly on
    a dark bar. Rendering to a scratch surface and using it as a mask paints
    our own colour through the icon's alpha instead, which works for both
    those and tiny-dfr's white ones. Returns False if it cannot be drawn, so
    the caller can fall back to a label.
    """
    import cairo
    try:
        side = max(int(size), 1)
        tmp = cairo.ImageSurface(cairo.FORMAT_ARGB32, side, side)
        t = cairo.Context(tmp)
        if path.endswith(".png"):
            img = cairo.ImageSurface.create_from_png(path)
            scale = side / max(img.get_width(), 1)
            t.scale(scale, scale)
            t.set_source_surface(img, 0, 0)
            t.paint()
        else:
            import gi
            gi.require_version("Rsvg", "2.0")
            from gi.repository import Rsvg
            handle = Rsvg.Handle.new_from_file(path)
            rect = Rsvg.Rectangle()
            rect.x, rect.y, rect.width, rect.height = 0, 0, side, side
            if not handle.render_document(t, rect):
                return False
        tmp.flush()
        c.save()
        c.set_source_rgb(*(rgb or TEXT))
        c.mask_surface(tmp, cx - side / 2, cy - side / 2)
        c.restore()
        return True
    except Exception:
        return False


def button_label(b):
    """What a button says when it is not a widget."""
    for k in ("Text", "Time", "Battery"):
        if b.get(k):
            return str(b[k])
    if b.get("Icon"):
        # tiny-dfr's icons ship with the daemon, which a machine without a
        # Touch Bar has no reason to install; the name reads well enough.
        return str(b["Icon"]).replace("_", " ")
    return ""


def rounded(c, x, y, w, h, r):
    import math
    r = max(min(r, h / 2, w / 2), 0.01)
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    c.close_path()


def centre_text(c, text, cx, cy, size, rgb, alpha=1.0, max_w=None):
    # Shrink to fit rather than spill: the media layer packs thirteen buttons
    # across, and "backlight high" does not fit at full size.
    c.set_font_size(size)
    if max_w:
        w = c.text_extents(text).width
        if w > max_w:
            size = max(size * max_w / w, 8.0)
            c.set_font_size(size)
    e = c.text_extents(text)
    c.set_source_rgba(*rgb, alpha)
    c.new_path()
    c.move_to(cx - e.width / 2 - e.x_bearing, cy - e.y_bearing - e.height / 2)
    c.show_text(text)


def draw_widget(c, b, x, y, w, h, colour):
    """The two widgets worth having away from the strip: usage bars, and the
    commit counts. Anything else falls back to its name."""
    kind = b.get("Widget")
    if kind == "commits":
        d = read_toml(b.get("Path", ""))
        for i, (key, tag) in enumerate((("today", "d"), ("week", "w"), ("month", "m"))):
            cx = x + w * (i + 0.5) / 3
            weight = (1.0, 0.72, 0.5)[i]
            centre_text(c, str(d.get(key, 0)), cx, y + h * 0.42, h * 0.40, colour, weight)
            centre_text(c, tag, cx, y + h * 0.78, h * 0.22, colour, weight * 0.55)
        return
    if kind == "bars":
        d = read_toml(b.get("Path", ""))
        want = b.get("Account")
        acct = next((a for a in d.get("account", [])
                     if want is None or a.get("email") == want), None)
        tag = str(b.get("Text") or "")
        bx = x + 6
        if tag:
            centre_text(c, tag, bx + 6, y + h / 2, h * 0.28, colour, 0.8)
            bx += 16
        bw = max(x + w - 6 - bx, 8)
        for i, key in enumerate(("session", "weekly_all", "weekly_scoped")):
            pct = float((acct or {}).get(key, 0) or 0)
            by = y + h * (0.24 + i * 0.22)
            bh = h * 0.13
            c.set_source_rgb(*OVERLAY)
            rounded(c, bx, by, bw, bh, bh / 2)
            c.fill()
            if pct > 0:
                c.set_source_rgb(*(ASK if pct >= 85 else BLUE if pct >= 50 else DONE))
                rounded(c, bx, by, max(bw * min(pct, 100) / 100, bh), bh, bh / 2)
                c.fill()
        return
    centre_text(c, str(kind or ""), x + w / 2, y + h / 2, h * 0.28, colour, 0.8)


def draw_badge(c, badge, x, y, w, h):
    """The same idiom the strip uses: a counted pill, or a dot while busy."""
    if not badge:
        return
    state = badge.get("state", "")
    if state == "busy":
        c.set_source_rgb(*BLUE)
        c.arc(x + 10, y + 10, 4, 0, 6.2832)
        c.fill()
        return
    count = int(badge.get("count", 0) or 0)
    if count <= 0:
        return
    r = h * 0.17
    cx, cy = x + w - r - 5, y + r + 5
    c.set_source_rgb(*(ASK if state == "ask" else DONE))
    c.arc(cx, cy, r, 0, 6.2832)
    c.fill()
    centre_text(c, str(min(count, 99)), cx, cy, r * 1.3, (0.12, 0.12, 0.18))


def draw(c, width, height, cfg, lay, layer, pal, badges):
    c.set_source_rgb(*BASE)
    rounded(c, 0, 0, width, height, 12)
    c.fill()
    c.select_font_face("sans")
    hits = []

    chip = 46.0
    # fn toggles the media layer, the way holding Fn does on the strip.
    fn_on = layer == "media"
    c.set_source_rgb(*(BLUE if fn_on else SURFACE))
    rounded(c, PAD, PAD, chip, height - 2 * PAD, 9)
    c.fill()
    centre_text(c, "fn", PAD + chip / 2, height / 2, 17,
                (0.12, 0.12, 0.18) if fn_on else TEXT)
    hits.append((PAD, PAD, chip, height - 2 * PAD, ("layer", "media" if not fn_on else "primary")))

    c.set_source_rgb(*SURFACE)
    rounded(c, width - PAD - chip, PAD, chip, height - 2 * PAD, 9)
    c.fill()
    centre_text(c, "x", width - PAD - chip / 2, height / 2, 18, SUBTEXT)
    hits.append((width - PAD - chip, PAD, chip, height - 2 * PAD, ("quit", None)))

    buttons = lay.get(layer, [])
    x0 = PAD * 2 + chip
    x1 = width - PAD * 2 - chip
    total = sum(max(int(b.get("Stretch", 1) or 1), 1) for b in buttons) or 1
    span = (x1 - x0) / total
    x = x0
    for b in buttons:
        w = span * max(int(b.get("Stretch", 1) or 1), 1) - 4
        y, h = PAD, height - 2 * PAD
        if not (b.get("Text") or b.get("Icon") or b.get("Widget")
                or b.get("Time") or b.get("Battery")):
            x += w + 4
            continue                      # a spacer: occupies room, does nothing
        colour = pal.get(b.get("Color"), TEXT)
        c.set_source_rgb(*SURFACE)
        rounded(c, x, y, w, h, 9)
        c.fill()
        drawn = False
        if b.get("Widget"):
            draw_widget(c, b, x, y, w, h, colour)
            drawn = True
        elif b.get("Icon"):
            path = icon_path(str(b["Icon"]))
            drawn = bool(path) and draw_icon(c, path, x + w / 2, height / 2, h * 0.55, colour)
        if not drawn:
            centre_text(c, button_label(b), x + w / 2, height / 2, 17, colour,
                        max_w=w - 10)
        draw_badge(c, badges.get(b.get("Badge")), x, y, w, h)
        target = ("layer", b["Layer"]) if b.get("Layer") else ("keys", actions_of(b))
        hits.append((x, y, w, h, target))
        x += w + 4
    return hits


def main():
    argv = sys.argv[1:]
    cfg = load_config()
    lay = layers(cfg)
    pal = palette(cfg)

    if "--dump" in argv:
        print("config:", ", ".join(config_paths()) or "(none found)")
        print("touch bar present:", has_touchbar())
        for name, keys in lay.items():
            print(f"  {name}: {len(keys)} buttons -> "
                  + ", ".join(button_label(b) or "-" for b in keys[:14]))
        return 0

    badges = read_toml(cfg.get("BadgeFile", "")) if cfg.get("BadgeFile") else {}
    start_layer = "media" if cfg.get("MediaLayerDefault") else "primary"

    if "--png" in argv:
        import cairo
        i = argv.index("--png")
        w = int(argv[i + 2]) if len(argv) > i + 2 and argv[i + 2].isdigit() else 1600
        which = os.environ.get("DFRBAR_LAYER", start_layer)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, HEIGHT)
        draw(cairo.Context(surf), w, HEIGHT, cfg, lay, which, pal, badges)
        surf.write_to_png(argv[i + 1])
        return 0

    if has_touchbar() and "--force" not in argv:
        print("dfrbar: this machine has a Touch Bar; use --force to show anyway",
              file=sys.stderr)
        return 0

    lib = "/usr/lib/libgtk4-layer-shell.so"
    if os.path.exists(lib) and lib not in os.environ.get("LD_PRELOAD", ""):
        os.environ["LD_PRELOAD"] = lib
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Re-running toggles the bar away -- but only if the pid still belongs to
    # this program. A stale file whose pid has since been reused would
    # otherwise kill an unrelated process.
    try:
        pid = int(PIDFILE.read_text().strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        if b"dfrbar" in cmdline:
            os.kill(pid, signal.SIGTERM)
            PIDFILE.unlink(missing_ok=True)
            return 0
        PIDFILE.unlink(missing_ok=True)
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        PIDFILE.unlink(missing_ok=True)

    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk, Gdk, GLib, Gtk4LayerShell as LayerShell

    PIDFILE.write_text(str(os.getpid()))
    def _bye(*_):
        # Remove the pidfile here rather than in a `finally`: while GTK's main
        # loop owns the thread, sys.exit from a handler does not unwind far
        # enough to run one, and the file outlives the bar.
        PIDFILE.unlink(missing_ok=True)
        os._exit(0)

    signal.signal(signal.SIGTERM, _bye)
    signal.signal(signal.SIGINT, _bye)
    inject = Injector([actions_of(b) for keys in lay.values() for b in keys])
    state = {"layer": start_layer, "hits": [], "badges": badges}

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
        # Never take the keyboard: the keys this bar sends must land in
        # whatever window is actually focused.
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
        for edge in (LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(win, edge, True)
        LayerShell.set_margin(win, LayerShell.Edge.BOTTOM, 8)

        area = Gtk.DrawingArea()
        area.set_content_height(HEIGHT)

        def on_draw(_a, c, w, h):
            state["hits"] = draw(c, w, h, cfg, lay, state["layer"], pal, state["badges"])

        area.set_draw_func(on_draw)
        win.set_child(area)

        def on_click(_g, _n, px, py):
            for x, y, w, h, target in state["hits"]:
                if x <= px <= x + w and y <= py <= y + h:
                    kind, val = target
                    if kind == "quit":
                        app.quit()
                    elif kind == "layer":
                        state["layer"] = val if val in lay else "primary"
                        area.queue_draw()
                    else:
                        inject.send(val)
                    return

        click = Gtk.GestureClick()
        click.connect("pressed", on_click)
        win.add_controller(click)

        def tick():
            if cfg.get("BadgeFile"):
                state["badges"] = read_toml(cfg["BadgeFile"])
            area.queue_draw()            # widgets read their files as they draw
            return True

        GLib.timeout_add_seconds(1, tick)
        win.present()

    app = Gtk.Application(application_id="dev.local.dfrbar")
    provider = Gtk.CssProvider()
    provider.load_from_data(b"window { background: transparent; }")

    def setup(a):
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        on_activate(a)

    app.connect("activate", setup)
    try:
        return app.run([])
    finally:
        PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
