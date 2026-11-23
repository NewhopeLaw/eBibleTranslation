#!/usr/bin/env python3
"""Put eBible on this PC's Desktop and Start menu, with its own icon.

    python scripts/shortcuts.py                         # say which shortcuts there are, as JSON
    python scripts/shortcuts.py make dashboard desktop  # the dashboard on the Desktop
    python scripts/shortcuts.py make reader start       # the reader in the Start menu
    python scripts/shortcuts.py remove dashboard desktop

The README has long spoken of an "eBible dashboard" Desktop shortcut, but
nothing made one: it had to be made by hand, and on this PC it was gone. The
dashboard's header now has a button for it, and this is what the button runs.

Two shortcuts, each for the Desktop, the Start menu or both:

  eBible dashboard   pythonw scripts\\app.py           (what start_dashboard.cmd starts)
  eBible reader      pythonw scripts\\app.py --reader  (what start_reader.cmd starts)

They start pythonw directly rather than the .cmd files, because a shortcut to
a .cmd flashes a console window on every double-click. The pythonw is the one
running the dashboard, so the shortcut opens the same Python with the same
packages (pywebview above all) that the dashboard was started with.

The icons are the open book of the Android launcher icon
(android/app/src/main/res/drawable/ic_mark_foreground.xml) drawn here at every
size Windows asks for: the reader in the app's colours, cream pages on the
purple, and the dashboard the other way about, so the two can be told apart
on a Desktop at a glance. They are written to tools/icons/ (machine-local and
gitignored, like the Android toolchain beside it) and drawn again whenever one
is missing.

A shortcut is only removed when it points at this copy of the project. One of
the same name pointing elsewhere - an older checkout, or one the user made by
hand - is reported as such and only replaced if asked to make it here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "tools" / "icons"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PURPLE, CREAM = (0x7c, 0x5c, 0xbf), (0xfa, 0xf8, 0xf4)      # icon_bg and icon_page in android/.../colors.xml
KINDS = {
    "dashboard": {"name": "eBible dashboard", "args": r"scripts\app.py", "bg": CREAM, "fg": PURPLE,
                  "what": "The live translation dashboard, with the reader built in"},
    "reader": {"name": "eBible reader", "args": r"scripts\app.py --reader", "bg": PURPLE, "fg": CREAM,
               "what": "The eBible reader, offline, in its own window"},
}
PLACES = {"desktop": "Desktop", "start": "Programs"}         # [Environment]::GetFolderPath names
PLACE_NAMES = {"desktop": "Desktop", "start": "Start menu"}

# The two pages of the launcher icon, on its 108-unit canvas, as cubic curves.
PAGES = [
    [(52, 38), ("C", (45, 32.5), (35, 29.5), (24, 29.5)), ("L", (24, 71.5)), ("C", (35, 71.5), (45, 74.5), (52, 80))],
    [(56, 38), ("C", (63, 32.5), (73, 29.5), (84, 29.5)), ("L", (84, 71.5)), ("C", (73, 71.5), (63, 74.5), (56, 80))],
]


def supported() -> bool:
    return os.name == "nt"


def _outline(page, scale, dx, dy, steps=24):
    """A page's outline as a polygon: each curve sampled along its length."""
    pts = [page[0]]
    for seg in page[1:]:
        if seg[0] == "L":
            pts.append(seg[1])
            continue
        p0, (c1, c2, p3) = pts[-1], seg[1:]
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            pts.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0],
                        u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]))
    return [(x * scale + dx, y * scale + dy) for x, y in pts]


def draw_icon(kind: str) -> Path:
    """tools/icons/eBible-<kind>.ico, drawn now if it is not there."""
    out = ICONS / f"eBible-{kind}.ico"
    if out.exists():
        return out
    from PIL import Image, ImageDraw
    k = KINDS[kind]
    big = 1024                                   # drawn large and shrunk, which is the antialiasing
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # A rounded square, as Windows draws its own app tiles: the cream one has
    # a hairline of the purple so it does not vanish on a white Desktop.
    d.rounded_rectangle((16, 16, big - 16, big - 16), radius=200, fill=k["bg"] + (255,),
                        outline=PURPLE + (255,) if k["bg"] == CREAM else None, width=28)
    # The book fills more of the tile than on Android: there is no round mask
    # to keep clear of here, and at 16 px every pixel of the pages counts.
    scale = big / 108 * 1.22
    off = big / 2 - 54 * scale
    for page in PAGES:
        d.polygon(_outline(page, scale, off, off + 4 * scale / 1.22), fill=k["fg"] + (255,))
    ICONS.mkdir(parents=True, exist_ok=True)
    img.save(out, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
    return out


def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def _ps(script: str, env: dict) -> str:
    """Run PowerShell with values passed through the environment, never
    spliced into the script, so a path with a quote or a space in it is safe."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, **env}, creationflags=NO_WINDOW, timeout=30)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                           else f"PowerShell exited {r.returncode}")
    return r.stdout


def status() -> dict:
    """Where each shortcut is and whether it opens this copy of the project."""
    if not supported():
        return {"supported": False, "shortcuts": []}
    names = [(kind, place, k["name"]) for kind, k in KINDS.items() for place in PLACES]
    script = (
        "$sh = New-Object -ComObject WScript.Shell; $out = @();"
        "foreach ($row in ($env:EB_ROWS | ConvertFrom-Json)) {"
        "  $dir = [Environment]::GetFolderPath($row.folder);"
        "  $lnk = Join-Path $dir ($row.name + '.lnk');"
        "  $o = [ordered]@{kind=$row.kind; place=$row.place; path=$lnk; exists=(Test-Path -LiteralPath $lnk); target=''; args=''; dir=''};"
        "  if ($o.exists) { $s = $sh.CreateShortcut($lnk); $o.target = $s.TargetPath; $o.args = $s.Arguments; $o.dir = $s.WorkingDirectory };"
        "  $out += [pscustomobject]$o };"
        "ConvertTo-Json -InputObject @($out) -Compress")
    rows = [{"kind": kind, "place": place, "folder": PLACES[place], "name": name} for kind, place, name in names]
    got = json.loads(_ps(script, {"EB_ROWS": json.dumps(rows)}) or "[]")
    here = str(ROOT).rstrip("\\").lower()
    for g in got:
        g["label"] = f'{KINDS[g["kind"]]["name"]} · {PLACE_NAMES[g["place"]]}'
        # "here" is a shortcut that starts app.py from this checkout, whichever
        # Python it names: one made before Python was upgraded still counts.
        g["state"] = ("none" if not g["exists"]
                      else "here" if (g["dir"] or "").rstrip("\\").lower() == here
                      and g["args"].strip() == KINDS[g["kind"]]["args"] else "elsewhere")
    return {"supported": True, "root": str(ROOT), "shortcuts": got}


def make(kind: str, place: str) -> dict:
    if kind not in KINDS or place not in PLACES:
        raise ValueError(f"unknown shortcut: {kind} {place}")
    if not supported():
        raise RuntimeError("shortcuts are made on Windows only")
    k = KINDS[kind]
    icon = draw_icon(kind)
    _ps("$dir = [Environment]::GetFolderPath($env:EB_FOLDER);"
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $dir ($env:EB_NAME + '.lnk')));"
        "$s.TargetPath = $env:EB_TARGET; $s.Arguments = $env:EB_ARGS; $s.WorkingDirectory = $env:EB_DIR;"
        "$s.IconLocation = $env:EB_ICON + ',0'; $s.Description = $env:EB_WHAT; $s.WindowStyle = 1; $s.Save()",
        {"EB_FOLDER": PLACES[place], "EB_NAME": k["name"], "EB_TARGET": pythonw(), "EB_ARGS": k["args"],
         "EB_DIR": str(ROOT), "EB_ICON": str(icon), "EB_WHAT": k["what"]})
    return status()


def remove(kind: str, place: str) -> dict:
    """Removes the shortcut only if it opens this copy; anything else is not ours to delete."""
    row = next((s for s in status()["shortcuts"] if s["kind"] == kind and s["place"] == place), None)
    if row is None:
        raise ValueError(f"unknown shortcut: {kind} {place}")
    if row["state"] == "elsewhere":
        raise RuntimeError(f'"{row["label"]}" opens another copy ({row["dir"] or row["target"]}), so it is left as it is')
    if row["state"] == "here":
        Path(row["path"]).unlink()
    return status()


def main():
    a = sys.argv[1:]
    if not a:
        print(json.dumps(status(), indent=1))
        return
    if len(a) != 3 or a[0] not in ("make", "remove"):
        raise SystemExit(__doc__)
    s = (make if a[0] == "make" else remove)(a[1], a[2])
    for r in s["shortcuts"]:      # a plain dash: a Windows console prints the label's middle dot as "?"
        print(f'{KINDS[r["kind"]]["name"] + " - " + PLACE_NAMES[r["place"]]:32} {r["state"]:9} {r["path"]}')


if __name__ == "__main__":
    main()
