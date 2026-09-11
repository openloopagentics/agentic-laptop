#!/usr/bin/env python3
"""Render a keybind cheatsheet from the running compositor.

Every bind in hyprland.lua carries a `description`, so `hyprctl binds -j`
is the source of truth: no parsing of the config, nothing to keep in sync.
"""
import json
import os
import subprocess
import sys

if sys.stdout.isatty():
    BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
    BLUE, MAUVE, TEAL = "\033[38;5;111m", "\033[38;5;183m", "\033[38;5;115m"
else:
    BOLD = DIM = RESET = BLUE = MAUVE = TEAL = ""

# X11 modmask bits, in display order.
MODS = [(64, "SUPER"), (4, "CTRL"), (8, "ALT"), (1, "SHIFT")]

PRETTY_KEY = {
    "SPACE": "Space", "ESCAPE": "Esc", "Return": "Enter", "Tab": "Tab",
    "Print": "PrtSc", "Delete": "Del", "comma": ",", "minus": "-",
    "equal": "=", "slash": "/", "BackSpace": "Backspace",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
    "mouse_up": "Scroll up", "mouse_down": "Scroll down",
    "mouse:272": "Left click", "mouse:273": "Right click",
}


def pretty(bind):
    key = bind["key"] or f"code:{bind['keycode']}"
    key = PRETTY_KEY.get(key, key)
    if key.startswith("XF86"):
        key = key[4:]
    mods = [name for bit, name in MODS if bind["modmask"] & bit]
    return " + ".join(mods + [key])


def section(bind):
    if (bind["key"] or "").startswith("XF86"):
        return "Media & hardware keys"
    if "mouse" in (bind["key"] or ""):
        return "Mouse"
    mods = [name for bit, name in MODS if bind["modmask"] & bit]
    if not mods:
        return "No modifier"
    return " + ".join(m.title() for m in mods)


def main():
    try:
        out = subprocess.run(["hyprctl", "binds", "-j"],
                             capture_output=True, text=True, timeout=5, check=True).stdout
        binds = json.loads(out)
    except Exception as e:  # noqa: BLE001 - cheatsheet, not a service
        sys.exit(f"cannot read binds from hyprctl: {e}")

    rows, seen = [], set()
    for b in binds:
        desc = b.get("description") or ""
        if not desc:
            continue
        combo = pretty(b)
        if (combo, desc) in seen:
            continue
        seen.add((combo, desc))
        rows.append((section(b), combo, desc))

    if not rows:
        sys.exit("no binds with descriptions found")

    order = ["Super", "Super + Shift", "Super + Ctrl", "Super + Alt",
             "Super + Ctrl + Alt", "Super + Ctrl + Shift", "Super + Alt + Shift",
             "Ctrl + Alt", "Ctrl + Alt + Shift", "Alt", "Alt + Shift",
             "No modifier", "Shift", "Mouse", "Media & hardware keys"]
    buckets = {}
    for sec, combo, desc in rows:
        buckets.setdefault(sec, []).append((combo, desc))
    for sec in buckets:
        if sec not in order:
            order.append(sec)

    width = max(len(c) for _, c, _ in rows)
    print(f"\n{BOLD}{MAUVE}  Hyprland keybindings{RESET}"
          f"{DIM}   ({len(rows)} binds · Omarchy layout){RESET}\n")
    for sec in order:
        items = buckets.get(sec)
        if not items:
            continue
        print(f"{BOLD}{TEAL}  {sec}{RESET}")
        for combo, desc in sorted(items, key=lambda r: r[0]):
            print(f"    {BLUE}{combo.ljust(width)}{RESET}  {DIM}·{RESET}  {desc}")
        print()


if __name__ == "__main__":
    main()
