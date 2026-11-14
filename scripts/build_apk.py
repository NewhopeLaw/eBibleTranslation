#!/usr/bin/env python3
"""Build the Android reader APK: the text alone, in the reader, on a phone.

    python scripts/build_apk.py                  # the reader alone (the toolchain must be there)
    python scripts/build_apk.py --full           # the reader with every study layer
    python scripts/build_apk.py --langs en,zh    # only these languages (default: every finished one)
    python scripts/build_apk.py --check          # say what is installed, as JSON
    python scripts/build_apk.py --setup --accept-android-sdk-license
                                                 # fetch the toolchain into tools/android/, then build

The reader APK carries the page built with --reader-only - always basic mode,
no study layers - and the search indexes beside it, both the word indexes and
what searches by meaning: the model and its verses from site/model/ where
scripts/build_encoder.py has made them (about 40 MB for the model and 6 MB a
language, and ONNX Runtime in the app to run it), else the table from
build_vectors.py (about 4 MB a language and a 7 MB table the page computes
with). --full carries the same page with the "Everything" switch and the whole
of site/morph/ behind it - word tags, lexicon, concordance, syntax,
cross-references, apparatus, themes, places, chronology - which is a 26 MB APK
and 78 MB installed. It freezes those layers as they stand: the jobs still
running (themes, the lexicon, the lexemes) will be partial in an APK built
today.

Both are built with --complete-only, so they carry a language only once the
whole Bible has been translated into it. Nobody reading on a phone can tell
which books are missing, and a translation still being written should not be
read as though it were finished; the build says what it left out and how far
that language has got. --langs narrows that to the ones named - a copy for
one congregation need not carry every language the project has - and naming
one that is not finished stops the build rather than leave it out unseen. An
APK of chosen languages is named after them, so it does not overwrite the
one that carries them all.

Either variant is staged in its own folder, android/reader-assets/ or
android/full-assets/, so android/app/src/main/assets/ - what sync_assets.sh
fills for a Play upload - is left alone. Both carry the same application id, so
installing one replaces the other on a phone.

The toolchain is looked for where Android Studio or an earlier --setup would
have put it. --setup fetches a JDK 17 (Eclipse Temurin), Gradle and the
Android command-line tools into tools/android/ (gitignored), about a gigabyte
once the SDK platform is in. Installing the SDK platform means accepting the
Android SDK License (https://developer.android.com/studio/terms), which is why
--setup will not run without --accept-android-sdk-license: the dashboard asks
the user first and passes it only on a yes.

Without android/keystore.properties the APK is a debug build, signed with the
debug key Gradle makes for itself: it installs on any phone that allows apps
from outside Play, which is what a copy for testing or handing round needs.
With the upload key set up (see android/README.md) it is a signed release, and
a quarter smaller - R8 and the resource shrinker only run on release, which
takes the reader from 11 MB to about 8 MB.

Progress goes to logs/apk_build.log, and a one-line state to logs/apk_build.json
that the dashboard reads for its button.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID = ROOT / "android"
TOOLS = ROOT / "tools" / "android"
STAGE = {False: ANDROID / "reader-assets", True: ANDROID / "full-assets"}
DIST = ROOT / "dist"
LOG = ROOT / "logs" / "apk_build.log"
STATE = ROOT / "logs" / "apk_build.json"

GRADLE_VERSION = "8.13"          # what Android Gradle Plugin 8.13 (android/build.gradle) needs
PLATFORM = "platforms;android-36"
JDK_URL = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"
GRADLE_URL = f"https://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip"
SDK_REPO = "https://dl.google.com/android/repository/"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ------------------------------------------------------------------ state for the dashboard
def say(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


def state(**kw):
    STATE.parent.mkdir(exist_ok=True)
    cur = {}
    if STATE.exists():
        try:
            cur = json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            cur = {}
    cur.update(kw, at=time.time())
    STATE.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")


def fail(msg: str, code: int = 1, **kw):
    say("FAILED: " + msg)
    state(state="failed", step="", error=msg, finished=time.time(), **kw)
    sys.exit(code)


# ------------------------------------------------------------------ finding the toolchain
def java_major(home: Path) -> int:
    rel = home / "release"
    if rel.exists():
        m = re.search(r'JAVA_VERSION="(\d+)', rel.read_text(encoding="utf-8", errors="replace"))
        if m:
            return int(m.group(1))
    return 0


def find_jdk() -> Path | None:
    cands = []
    if os.environ.get("JAVA_HOME"):
        cands.append(Path(os.environ["JAVA_HOME"]))
    cands += sorted(TOOLS.glob("jdk*"), reverse=True)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "") + r"\Programs"):
        cands.append(Path(base) / "Android" / "Android Studio" / "jbr")
        cands.append(Path(base) / "Android Studio" / "jbr")
    for home in cands:
        if (home / "bin" / "java.exe").exists() and java_major(home) >= 17:
            return home
    return None


def find_sdk() -> Path | None:
    cands = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
             str(TOOLS / "sdk"), os.environ.get("LOCALAPPDATA", "") + r"\Android\Sdk"]
    for c in cands:
        # The licence files are what let Gradle fetch the platform and build
        # tools it needs by itself; an SDK without them cannot build anything.
        if c and (Path(c) / "licenses" / "android-sdk-license").exists():
            return Path(c)
    return None


def find_gradle() -> Path | None:
    local = TOOLS / f"gradle-{GRADLE_VERSION}" / "bin" / "gradle.bat"
    if local.exists():
        return local
    on_path = shutil.which("gradle")
    return Path(on_path) if on_path else None


def check() -> dict:
    jdk, sdk, gradle = find_jdk(), find_sdk(), find_gradle()
    missing = [n for n, v in (("JDK 17", jdk), ("Android SDK", sdk), ("Gradle", gradle)) if not v]
    return {"jdk": str(jdk or ""), "sdk": str(sdk or ""), "gradle": str(gradle or ""),
            "missing": missing, "ready": not missing,
            "signed": (ANDROID / "keystore.properties").exists()}


# ------------------------------------------------------------------ fetching it
def download(url: str, dest: Path, what: str, checksum: tuple[str, str] | None = None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    say(f"downloading {what}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "eBibleTranslation-build_apk"})
    # Google says in its package list which digest it published; taking that at
    # its word means a switch from sha1 does not read here as a bad download.
    h = hashlib.new(checksum[0] if checksum else "sha1")
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, 0.0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if time.time() - last > 2:
                last = time.time()
                pct = f"{100 * got / total:.0f}%" if total else f"{got >> 20} MB"
                state(step=f"downloading {what} ({pct})")
    if checksum and h.hexdigest() != checksum[1]:
        part.unlink(missing_ok=True)
        fail(f"{what} did not match its published {checksum[0]}; nothing was installed")
    part.replace(dest)
    say(f"  {what}: {dest.stat().st_size >> 20} MB")


def unzip(archive: Path, into: Path, what: str):
    state(step=f"unpacking {what}")
    with zipfile.ZipFile(archive) as z:
        z.extractall(into)
    archive.unlink()


def cmdline_tools_url() -> tuple[str, tuple[str, str] | None]:
    """The current Windows command-line tools, from Google's own package list."""
    with urllib.request.urlopen(SDK_REPO + "repository2-3.xml", timeout=60) as r:
        root = ET.fromstring(r.read())
    for pkg in root.iter("remotePackage"):
        if pkg.get("path") != "cmdline-tools;latest":
            continue
        for arc in pkg.iter("archive"):
            if (arc.findtext("host-os") or "") == "windows":
                el = arc.find("complete/checksum")
                kind = (el.get("type") if el is not None else None) or "sha1"
                digest = (el.text if el is not None else "") or ""
                return SDK_REPO + arc.findtext("complete/url"), (kind, digest) if digest else None
    fail("could not find the Android command-line tools in Google's package list")


def setup():
    TOOLS.mkdir(parents=True, exist_ok=True)
    if not find_jdk():
        state(step="fetching a JDK 17")
        download(JDK_URL, TOOLS / "jdk.zip", "JDK 17 (Eclipse Temurin)")
        unzip(TOOLS / "jdk.zip", TOOLS, "the JDK")
    jdk = find_jdk() or fail("the JDK was unpacked but no java.exe of version 17 or later was found")

    if not (TOOLS / f"gradle-{GRADLE_VERSION}").exists():
        download(GRADLE_URL, TOOLS / "gradle.zip", f"Gradle {GRADLE_VERSION}")
        unzip(TOOLS / "gradle.zip", TOOLS, "Gradle")

    sdk = find_sdk() or TOOLS / "sdk"
    tools_bin = sdk / "cmdline-tools" / "latest" / "bin"
    if not (tools_bin / "sdkmanager.bat").exists() and not (tools_bin / "android.exe").exists():
        url, sha1 = cmdline_tools_url()
        download(url, TOOLS / "cmdline-tools.zip", "the Android command-line tools", sha1)
        tmp = TOOLS / "cmdline-tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        unzip(TOOLS / "cmdline-tools.zip", tmp, "the command-line tools")
        # The archive holds cmdline-tools/; the tools insist on living in
        # cmdline-tools/latest/ or they cannot work out where the SDK is.
        dest = sdk / "cmdline-tools" / "latest"
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp / "cmdline-tools"), str(dest))
        shutil.rmtree(tmp, ignore_errors=True)

    env = {**os.environ, "JAVA_HOME": str(jdk), "ANDROID_HOME": str(sdk)}
    if (sdk / "platforms" / PLATFORM.split(";")[1]).exists() and (sdk / "licenses" / "android-sdk-license").exists():
        say("the SDK platform and its licence are already in place")
        return                                            # a second --setup has nothing to do
    state(step="installing the Android 16 SDK platform")
    say(f"installing {PLATFORM}")
    android, sdkmanager = tools_bin / "android.exe", tools_bin / "sdkmanager.bat"
    if android.exists():
        # The command-line tools from 2026 replace sdkmanager with the android
        # CLI: there is no --licenses step any more (it shows the terms on its
        # first run and records the licence when it installs), and it reports
        # usage to Google unless --no-metrics says otherwise, which it should
        # not do on the strength of a build button.
        cmd = [str(android), "--no-metrics", "sdk", "install", PLATFORM, f"--sdk={sdk}"]
    else:
        cmd = [str(sdkmanager), f"--sdk_root={sdk}", PLATFORM]
    r = subprocess.run(cmd, input="y\n" * 40, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, creationflags=NO_WINDOW)
    out = (r.stdout or "") + (r.stderr or "")
    say(out.strip()[-600:])
    # The android CLI downloads and unpacks the platform correctly and then
    # exits 0xC0000409 when it has no console of its own, which is what it has
    # here. Its exit code therefore says nothing; what it left on disk does.
    if not (sdk / PLATFORM.split(";")[1]).exists() and not (sdk / "platforms" / PLATFORM.split(";")[1]).exists():
        fail(f"the platform could not be installed (exit {r.returncode}): " + out[-400:])
    # Installing is also what records the licence, and the licence is what lets
    # Gradle fetch the build tools it wants without a prompt no one would see.
    if not (sdk / "licenses" / "android-sdk-license").exists():
        fail("the SDK is installed but its licence was not recorded, so Gradle cannot fetch what it needs: " + out[-300:])
    say("toolchain ready in " + str(TOOLS))


# ------------------------------------------------------------------ building
def stage_page(full: bool, langs_wanted: list[str]):
    """The page and the data files that variant needs, and nothing else.

    The reader takes the search indexes only; the full app takes all of
    site/morph/, which is the study layers as they stand at this moment.
    """
    stage = STAGE[full]
    state(step="building the " + ("full" if full else "reader") + " page")
    shutil.rmtree(stage, ignore_errors=True)
    # --complete-only: an APK is something someone reads on a bus, with no way
    # to know which books are missing, so it carries only the languages the
    # whole Bible has been translated into.
    cmd = [sys.executable, str(ROOT / "scripts" / "build_site.py"), "--out", str(stage), "--complete-only"]
    if not full:
        cmd.insert(2, "--reader-only")
    if langs_wanted:
        cmd += ["--langs", ",".join(langs_wanted)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    say(r.stdout.strip() or r.stderr.strip())
    page = stage / "index.html"
    if r.returncode != 0 or not page.exists():
        fail("the reader page did not build: " + (r.stderr.strip() or r.stdout.strip())[-400:])
    # The same guard as sync_assets.sh: a page this small is a checkout that is
    # behind on output/, and would ship a Bible with books missing.
    if page.stat().st_size < 4_000_000:
        fail(f"the reader page is only {page.stat().st_size} bytes - not a full reader. Build on the PC that holds output/.")
    m = re.search(r"translated chapters: ([^;]+);", r.stdout)
    chapters = m.group(1) if m else ""
    langs = [p.split("=")[0].strip() for p in chapters.split(",") if "=" in p]
    morph = ROOT / "site" / "morph"
    # Search by meaning comes in two kinds. Where scripts/build_encoder.py has
    # been run, the app carries the model and the verses it measures against
    # (site/model/), and the app's shell runs it; that is much the better of the
    # two, in Thai above all. A language the model has no verses for keeps the
    # table that build_vectors.py makes, which the page computes with alone.
    # Never both for one language: the table's files would be twenty-odd
    # megabytes nobody opens.
    model = ROOT / "site" / "model"
    modelled = [c for c in langs if (model / f"vecm_{c}.bin").exists()] if (model / "encoder.onnx").exists() else []
    # The reader carries both halves of its search: the word indexes, and the
    # verse vectors that let a reader describe a passage and be taken to it.
    files = sorted(f for f in (morph.glob("*.js") if full else [*morph.glob("idx_*.js"), *morph.glob("vec_*.js")])
                   if f.is_file())
    # A search index or a translated lexicon for a language the page no longer
    # offers is weight with nothing to open it. The Hebrew and Greek ones stay:
    # they are the text itself, not a translation of it. vec_table.js is shared
    # by every language, and has no code in its name to be dropped by: it goes
    # when every language is answered by the model.
    def wanted(f):
        if f.name == "vec_table.js":
            return any(c not in modelled for c in langs)
        for prefix in ("idx_", "lexx_", "vec_"):
            if f.name.startswith(prefix):
                code = f.name[len(prefix):-3]
                if prefix == "vec_" and code in modelled:
                    return False
                return code in ("hbo", "grc") or code in langs
        return True
    files = [f for f in files if wanted(f)]
    if modelled:
        (stage / "model").mkdir()
        # The passages: the English descriptions, and each carried language's
        # own where they have been translated (Meaning.java prefers those).
        passages = [n for n in ["vecm_stories.bin", *(f"vecm_stories_{c}.bin" for c in modelled)]
                    if (model / n).exists()]
        for name in ["encoder.onnx", "vocab.tsv", "proj.bin", *(f"vecm_{c}.bin" for c in modelled), *passages]:
            shutil.copy2(model / name, stage / "model" / name)
        say(f"search by meaning with the model for {', '.join(modelled)}")
    elif langs:
        say("search by meaning from the table only - run scripts/build_encoder.py for the model, "
            "which is much better in Thai")
    if full and not files:
        fail("site/morph is empty - build the study layers first (scripts/build_all.py)")
    (stage / "morph").mkdir()
    for f in files:
        shutil.copy2(f, stage / "morph" / f.name)
    size = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file())
    say(f"staged {page.stat().st_size >> 20} MB page + {len(files)} data file{'' if len(files) == 1 else 's'} "
        f"({size >> 20} MB in all)")
    say("languages in this APK: " + (", ".join(langs) if langs else "none complete - the original text alone"))
    return chapters


def build(tc: dict, chapters: str, full: bool, langs_wanted: list[str]):
    signed = tc["signed"]
    task = "assembleRelease" if signed else "assembleDebug"
    now = dt.datetime.now()
    # Minutes since the start of 2026: always rising, so every APK installs over
    # the one before it, and far below Android's two-billion ceiling.
    # A phone refuses to install an APK whose number is lower than the one it
    # has, so a clock set before 2026 must not produce a negative or tiny one.
    vcode = max(1, int((now - dt.datetime(2026, 1, 1)).total_seconds() // 60))
    vname = f"1.0.{now:%Y%m%d}"
    (ANDROID / "local.properties").write_text(f"sdk.dir={tc['sdk'].replace(chr(92), '/')}\n", encoding="utf-8")
    # Gradle keeps the libraries it downloads in a home of its own, which is
    # normally the user profile. Keeping it here instead means the packaged app
    # (scripts/package_app.py) can carry it and build an APK with no network,
    # and that nothing of ours is left behind on a machine that only ran it.
    gradle_home = ROOT / "tools" / "gradle-home"
    gradle_home.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "JAVA_HOME": tc["jdk"], "ANDROID_HOME": tc["sdk"],
           "GRADLE_USER_HOME": str(gradle_home)}
    cmd = [tc["gradle"], "-p", str(ANDROID), task, "--no-daemon", "--console=plain",
           f"-PappAssets={STAGE[full].as_posix()}", f"-PversionCode={vcode}", f"-PversionName={vname}"]
    say("gradle " + " ".join(cmd[1:]))
    state(step=f"gradle {task} (the first build fetches its libraries and takes a few minutes)")
    proc = subprocess.Popen(cmd, cwd=str(ANDROID), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    tail = []
    for line in proc.stdout:
        line = line.rstrip()
        print(line, flush=True)
        tail = (tail + [line])[-40:]
        m = re.match(r"> Task :app:(\w+)", line)
        if m:
            state(step=f"gradle: {m.group(1)}")
    if proc.wait() != 0:
        err = next((l for l in tail if "What went wrong" in l), "")
        i = tail.index(err) if err else max(0, len(tail) - 8)
        fail("gradle failed: " + " ".join(l.strip() for l in tail[i:i + 6] if l.strip())[:600])

    kind = "release" if signed else "debug"
    out = ANDROID / "app" / "build" / "outputs" / "apk" / kind
    apks = sorted(out.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    if not apks:
        fail(f"gradle finished but no APK is in {out}")
    # keystore.properties can exist and still not name a key, and the build
    # file then quietly leaves the release unsigned. An unsigned APK installs
    # nowhere, so say it here rather than let it be found on a phone.
    if signed and "unsigned" in apks[-1].name:
        fail("keystore.properties is there but the release came out unsigned - check that it names "
             "storeFile, storePassword, keyAlias and keyPassword (see android/keystore.properties.example)")
    DIST.mkdir(exist_ok=True)
    only = ("-" + "-".join(langs_wanted)) if langs_wanted else ""
    dest = DIST / f"eBible-{'full' if full else 'reader'}{only}-{vname}{'' if signed else '-debug'}.apk"
    shutil.copy2(apks[-1], dest)
    say(f"APK: {dest} ({dest.stat().st_size / 1048576:.1f} MB, {kind}, versionCode {vcode})")
    state(state="done", step="", apk=str(dest), size=dest.stat().st_size, kind=kind, version=vname,
          variant="full" if full else "reader", langs=langs_wanted, chapters=chapters, finished=time.time(), error="")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true",
                    help="carry the study layers too: every file in site/morph/, as they stand now")
    ap.add_argument("--langs", default="",
                    help="comma list of languages to carry, e.g. en,zh (default: every finished one)")
    ap.add_argument("--check", action="store_true", help="print what is installed, as JSON, and stop")
    ap.add_argument("--setup", action="store_true", help="fetch the toolchain into tools/android/ first")
    ap.add_argument("--accept-android-sdk-license", action="store_true",
                    help="required with --setup: the SDK platform is only installed on this licence")
    a = ap.parse_args()
    langs_wanted = [c.strip() for c in a.langs.split(",") if c.strip()]

    if a.check:
        print(json.dumps(check(), indent=1))
        return
    state(state="running", step="starting", started=time.time(), error="", apk="",
          variant="full" if a.full else "reader", langs=langs_wanted)
    if a.setup:
        if not a.accept_android_sdk_license:
            fail("--setup installs the Android SDK, which needs --accept-android-sdk-license "
                 "(https://developer.android.com/studio/terms)")
        setup()
    tc = check()
    if not tc["ready"]:
        say("missing: " + ", ".join(tc["missing"]))
        state(state="needs-setup", step="", error="missing: " + ", ".join(tc["missing"]), finished=time.time())
        sys.exit(2)
    chapters = stage_page(a.full, langs_wanted)
    build(tc, chapters, a.full, langs_wanted)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                              # noqa: BLE001 - the dashboard must hear about it
        fail(f"{type(e).__name__}: {e}")
