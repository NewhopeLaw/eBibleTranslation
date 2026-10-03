#!/usr/bin/env python3
"""Package eBible as one folder that runs on a PC with nothing installed.

    python scripts/package_app.py                  # the app, with the Android toolchain in it
    python scripts/package_app.py --shareable      # ...without it, for a copy you give away
    python scripts/package_app.py --out D:/eBible-app

What comes out is a folder holding its own Python, the reader, every translated
chapter, the study layers, the Android project and the scripts - the dashboard,
the reader, the translation driver and the APK builder - started by eBible.exe.
Nothing has to be installed on the machine that runs it. Translating also needs
Ollama and the model, which are not ours to bundle; reading and building APKs do
not.

    WITH the toolchain (the default) the folder is about 1.1 GB and builds an
    APK offline. It is for your own machines only: the Android SDK inside it is
    Google's, and its terms (https://developer.android.com/studio/terms, 3.4)
    forbid redistributing it or distributing software that incorporates it.

    --shareable leaves the SDK out, about 170 MB, and the APK button fetches it
    on the first build under the licence the person running it accepts. The JDK
    (Temurin, GPLv2 with the classpath exception) and Gradle (Apache 2.0) are
    both redistributable and stay in either way.

The big source clones under sources/ are not copied: they are only needed to
rebuild the study layers, and site/morph/ already holds what those layers
produced. sources/normalized/ is copied, because the translation driver and the
reader build read the text from it.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYV = platform.python_version()
PY_URL = f"https://www.python.org/ftp/python/{PYV}/python-{PYV}-embed-amd64.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"
DEPS = ["pywebview", "psutil", "requests"]          # the window, the process scan, the model calls

# What the app needs to run, as opposed to what the repository holds.
COPY = ["scripts", "prompts", "site", "output", "targets", "config.json",
        "README.md", "LEGAL.md", "docs"]
SKIP = {"__pycache__", ".gradle", "build", "reader-assets", "full-assets", "assets", ".git"}


def say(msg):
    print(msg, flush=True)


def fetch(url: str, dest: Path) -> Path:
    if dest.exists():
        say(f"  already here: {dest.name}")
        return dest
    say(f"  downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "eBibleTranslation-package_app"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as fh:
        shutil.copyfileobj(r, fh)
    say(f"  {dest.name}: {dest.stat().st_size >> 20} MB")
    return dest


def copy_tree(src: Path, dst: Path):
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=lambda d, names: [n for n in names if n in SKIP])


def embed_python(out: Path, cache: Path):
    """A Python of our own, so the machine running this needs none."""
    py = out / "python"
    if (py / "python.exe").exists():
        say("python: already unpacked")
    else:
        say(f"python {PYV}:")
        z = fetch(PY_URL, cache / f"python-{PYV}-embed-amd64.zip")
        py.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as f:
            f.extractall(py)
        # The embeddable build ignores site-packages until its ._pth says otherwise.
        for pth in py.glob("python*._pth"):
            text = pth.read_text(encoding="utf-8")
            if "site-packages" not in text:
                pth.write_text(text.replace("#import site", "import site").rstrip("\n")
                               + "\nLib\\site-packages\n", encoding="utf-8")
    exe = py / "python.exe"
    if not (py / "Lib" / "site-packages" / "pip").exists():
        say("  pip:")
        getpip = fetch(GETPIP_URL, cache / "get-pip.py")
        run([str(exe), str(getpip), "--no-warn-script-location"], "pip could not be installed")
    say("  " + ", ".join(DEPS) + ":")
    run([str(exe), "-m", "pip", "install", "--upgrade", "--no-warn-script-location", *DEPS],
        "the app's packages could not be installed")
    return py


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"{what}:\n{(r.stderr or r.stdout)[-800:]}")


def launcher(out: Path, cache: Path):
    """eBible.exe, or a .cmd when PyInstaller is not to be had."""
    cmd = out / "eBible.cmd"
    cmd.write_text('@echo off\r\nstart "" "%~dp0python\\pythonw.exe" "%~dp0scripts\\app.py"\r\n',
                   encoding="ascii")
    src = cache / "launcher.py"
    src.write_text(
        "# eBible.exe: start the app with the Python beside it, and get out of the way.\n"
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.executable).resolve().parent\n"
        "subprocess.Popen([str(root / 'python' / 'pythonw.exe'), str(root / 'scripts' / 'app.py')],\n"
        "                 cwd=str(root), creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)\n",
        encoding="utf-8")
    try:
        import PyInstaller                                    # noqa: F401
    except ImportError:
        say("  PyInstaller not installed; installing it for the launcher")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            say("  could not install PyInstaller - eBible.cmd is the launcher")
            return
    work = cache / "pyinstaller"
    r = subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--name", "eBible",
                        "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
                        "--specpath", str(work), str(src)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    exe = work / "dist" / "eBible.exe"
    if r.returncode != 0 or not exe.exists():
        say("  the launcher exe did not build - eBible.cmd is the launcher")
        return
    shutil.copy2(exe, out / "eBible.exe")
    say(f"  eBible.exe ({exe.stat().st_size >> 20} MB)")


def note(out: Path, with_tools: bool):
    (out / "READ ME FIRST.txt").write_text("\n".join([
        "eBible - the reader, the translation dashboard and the Android APK builder.",
        "",
        "Start it with eBible.exe (or eBible.cmd). Nothing needs installing: the",
        "Python it runs on is in python\\ beside it.",
        "",
        "  Read            the whole Bible as translated so far, in every language",
        "                  here, with the study layers behind the Everything switch.",
        "  Translate       needs Ollama running on this machine with the model named",
        "                  in config.json. Without it, everything else still works.",
        "  Make Android    builds an APK into dist\\. " + (
            "The build tools are in tools\\android\\." if with_tools
            else "The first build offers to fetch"),
        "" if with_tools else "                  the build tools (about 1 GB) under Google's SDK licence.",
        "",
        "WHAT MAY BE PASSED ON",
        "",
        "The Bible text, the translations and every layer here were made from public",
        "domain or permissively licensed sources; LEGAL.md lists each one and what it",
        "requires. They may be given away freely.",
        "" if not with_tools else
        "This copy also holds tools\\android\\, which contains Google's Android SDK.\n"
        "Google's terms (https://developer.android.com/studio/terms, 3.4) forbid\n"
        "redistributing the SDK or distributing software that incorporates it, so this\n"
        "copy is for your own machines. To hand the app to someone else, build it with\n"
        "  python scripts\\package_app.py --shareable\n"
        "which leaves the SDK out; their first APK build fetches it themselves.",
        "",
        "The Java runtime (Eclipse Temurin, GPLv2 with the classpath exception) and",
        "Gradle (Apache 2.0) may be passed on either way.",
    ]) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shareable", action="store_true",
                    help="leave out the Android SDK, which Google's terms forbid passing on")
    ap.add_argument("--out", default=str(ROOT / "dist" / "eBible-app"), help="where to build the folder")
    a = ap.parse_args()
    if os.name != "nt":
        sys.exit("This packages a Windows app; run it on the PC.")

    out = Path(a.out).resolve()
    cache = ROOT / "dist" / ".package-cache"
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    with_tools = not a.shareable

    embed_python(out, cache)

    say("the app's own files:")
    for name in COPY:
        src = ROOT / name
        if not src.exists():
            say(f"  missing, skipped: {name}")
            continue
        dst = out / name
        if src.is_dir():
            copy_tree(src, dst)
        else:
            shutil.copy2(src, dst)
        say(f"  {name}")
    # The Android project, without anything a build leaves behind.
    copy_tree(ROOT / "android", out / "android")
    say("  android (project only)")
    # The normalized text: what the translation driver and the reader build read.
    copy_tree(ROOT / "sources" / "normalized", out / "sources" / "normalized")
    say("  sources/normalized")
    (out / "logs").mkdir(exist_ok=True)

    tools = out / "tools" / "android"
    if with_tools:
        if not (ROOT / "tools" / "android").exists():
            sys.exit("tools/android is not here yet - run the APK build once first, or use --shareable")
        say("the Android toolchain (about 1.4 GB, a few minutes):")
        copy_tree(ROOT / "tools" / "android", tools)
        say("  tools/android")
        # Gradle's own downloads - the plugin and the androidx libraries - or
        # the first build on the other machine would need the network after all.
        gh = ROOT / "tools" / "gradle-home"
        if (gh / "caches").exists():
            copy_tree(gh, out / "tools" / "gradle-home")
            say("  tools/gradle-home (the libraries Gradle would otherwise fetch)")
        else:
            say("  no tools/gradle-home yet - build an APK once so its libraries are here to carry")
    else:
        shutil.rmtree(tools, ignore_errors=True)

    say("the launcher:")
    launcher(out, cache)
    note(out, with_tools)

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    say(f"\npackaged: {out} ({size / 1_073_741_824:.2f} GB)")
    say("start it with eBible.exe" + ("" if with_tools else "  (the APK button fetches its tools on first use)"))
    if with_tools:
        say("this copy holds Google's Android SDK: keep it to your own machines, "
            "and use --shareable for a copy to pass on")


if __name__ == "__main__":
    main()
