#!/usr/bin/env python3
"""Clickable F1-F12 overlay for a Touch Bar Mac with no physical function row.

Runs as a layer-shell surface with KeyboardMode.NONE, so it never takes
keyboard focus -- the app underneath stays focused and receives the keys.
Clicks are injected through Hyprland's send_shortcut dispatcher.

Re-running toggles it off.
"""
import os
import signal
import subprocess
import sys

# gtk4-layer-shell must precede libwayland-client in the link order; with the
# Python bindings the only way to guarantee that is LD_PRELOAD, so re-exec once.
_LIB = "/usr/lib/libgtk4-layer-shell.so"
if os.path.exists(_LIB) and _LIB not in os.environ.get("LD_PRELOAD", ""):
    os.environ["LD_PRELOAD"] = _LIB
    os.execv(sys.executable, [sys.executable] + sys.argv)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gtk4LayerShell as LayerShell  # noqa: E402

PIDFILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "fkeys-overlay.pid"
)

CSS = b"""
window { background: transparent; }
box.bar {
    background: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 10px;
    padding: 8px;
}
button {
    background: #313244;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    min-width: 52px;
    min-height: 34px;
    margin: 0 3px;
    font-weight: bold;
}
button:hover { background: #45475a; }
button:active { background: #89b4fa; color: #1e1e2e; }
button.close { background: transparent; color: #6c7086; min-width: 30px; }
button.close:hover { background: #f38ba8; color: #1e1e2e; }
"""


def already_running():
    """Toggle: if a live instance owns the pidfile, kill it and stop."""
    try:
        with open(PIDFILE) as fh:
            pid = int(fh.read().strip())
        os.kill(pid, signal.SIGTERM)
        os.unlink(PIDFILE)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError):
        # stale or absent pidfile
        try:
            os.unlink(PIDFILE)
        except FileNotFoundError:
            pass
        return False


def send(key):
    # send_shortcut targets the focused window; the overlay is not it.
    subprocess.Popen(
        ["hyprctl", "dispatch", f'hl.dsp.send_shortcut({{mods = "", key = "{key}"}})'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def on_activate(app):
    win = Gtk.ApplicationWindow(application=app)
    LayerShell.init_for_window(win)
    LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
    # Never take keyboard focus, or send_shortcut would land on us.
    LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
    LayerShell.set_anchor(win, LayerShell.Edge.BOTTOM, True)
    LayerShell.set_margin(win, LayerShell.Edge.BOTTOM, 60)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    bar.add_css_class("bar")
    for i in range(1, 13):
        key = f"F{i}"
        btn = Gtk.Button(label=key)
        btn.connect("clicked", lambda _b, k=key: send(k))
        bar.append(btn)

    close = Gtk.Button(label="×")
    close.add_css_class("close")
    close.connect("clicked", lambda _b: app.quit())
    bar.append(close)

    win.set_child(bar)
    win.present()


def main():
    if already_running():
        return 0

    with open(PIDFILE, "w") as fh:
        fh.write(str(os.getpid()))

    app = Gtk.Application(application_id="dev.local.fkeys-overlay")
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)

    def setup(a):
        Gtk.StyleContext.add_provider_for_display(
            __import__("gi").repository.Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
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
