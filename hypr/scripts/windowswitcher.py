#!/usr/bin/env python3
"""Jump to any window on any workspace, picked through hyprlauncher.

Stands in for a workspace-overview plugin: as of Hyprland 0.56.2 none exists.
hyprexpo was dropped from hyprwm/hyprland-plugins, and Hyprspace still pins
0.50.1, so neither builds here.
"""
import json
import subprocess
import sys


def hyprctl(*args, parse=False):
    out = subprocess.run(["hyprctl", *args], capture_output=True, text=True,
                         timeout=5, check=True).stdout
    return json.loads(out) if parse else out


def main():
    clients = hyprctl("clients", "-j", parse=True)
    rows = []
    for c in clients:
        if not c.get("mapped") or c["workspace"]["id"] < 0:
            continue
        label = "{:>3}  {:<18}  {}".format(
            c["workspace"]["id"],
            c["class"][:18],
            (c["title"] or "(untitled)")[:70],
        )
        rows.append((label, c["address"]))

    if not rows:
        sys.exit(0)
    rows.sort()

    menu = subprocess.run(["hyprlauncher", "--dmenu"],
                          input="\n".join(r[0] for r in rows),
                          capture_output=True, text=True)
    choice = menu.stdout.strip()
    if not choice:
        sys.exit(0)

    for label, addr in rows:
        if label.strip() == choice.strip():
            hyprctl("dispatch", 'hl.dsp.focus({ window = "address:%s" })' % addr)
            return


if __name__ == "__main__":
    main()
