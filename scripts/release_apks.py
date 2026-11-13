#!/usr/bin/env python3
"""Build the reader APKs the website offers, and list them for its Download tray.

    python scripts/release_apks.py --base-url https://github.com/OWNER/REPO/releases/download/reader-apk/

One APK carries every finished language; then one for each language alone,
and one for English with each other language. The reader pairs any language
with English, but a congregation that reads Karen or Thai and no English
should not have to carry it, and a phone on a metered plan should not have to
fetch six Bibles to read one. The website lets the visitor pick among them.
Each is scripts/build_apk.py run with --langs, so each carries the search
model from site/model/ when it is there, and the table search when it is not.

Every one of those is also built a second time with --no-meaning: no model
and no runtime to run it, which takes most of the size away. The visitor
chooses, with the size of each shown, whether describing a passage in their
own words is worth the megabytes.

They are copied to dist/release/ under names that do not change from one
publish to the next (eBible-reader.apk, eBible-reader-th.apk,
eBible-reader-en-zh.apk, eBible-reader-en-zh-lite.apk), so the links on the
website keep working, and dist/release/apks.json lists what was made, how
large each is, and the version number it carries. The app's "Check for a
newer version" opens the website with its own number, and the page compares
it with these. The Pages
workflow uploads them to a GitHub Release, which takes files of up to 2 GB
and has no limit on the whole, where the site itself has 1 GB in all;
build_site.py --downloads --apks dist/release/apks.json gives the tray the
list. A variant that fails to build is left out and said so, and the others
are still offered: one broken language should not take the app away from
the rest.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "logs" / "apk_build.json"
OUT = ROOT / "dist" / "release"


def build(langs: list[str], meaning: bool) -> dict | None:
    """One APK by build_apk.py; what its state file says it made, or None."""
    cmd = [sys.executable, str(ROOT / "scripts" / "build_apk.py")]
    if langs:
        cmd += ["--langs", ",".join(langs)]
    if not meaning:
        cmd.append("--no-meaning")
    print("::group::" + (" + ".join(langs) or "every language") + ("" if meaning else ", no search by meaning"), flush=True)
    r = subprocess.run(cmd)
    print("::endgroup::", flush=True)
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    if r.returncode != 0 or st.get("state") != "done" or not Path(st.get("apk", "")).is_file():
        print(f"::warning::the APK for {', '.join(langs) or 'every language'} did not build: "
              f"{st.get('error') or 'build_apk.py exited ' + str(r.returncode)}", flush=True)
        return None
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True,
                    help="where the APKs will be downloaded from, ending in /: the Release's download URL")
    ap.add_argument("--only-all", action="store_true",
                    help="build the every-language APKs alone (a quick check, or a runner short of time)")
    ap.add_argument("--no-lite", action="store_true",
                    help="skip the copies without search by meaning, which halves the time")
    a = ap.parse_args()
    if not a.base_url.endswith("/"):
        raise SystemExit("--base-url must end in /, the file names are added to it")

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    made = []

    def keep(st: dict, langs: list[str], meaning: bool):
        name = "eBible-reader" + "".join("-" + c for c in langs) + ("" if meaning else "-lite") + ".apk"
        shutil.copy2(st["apk"], OUT / name)
        made.append({"langs": langs, "meaning": meaning, "file": name, "bytes": (OUT / name).stat().st_size,
                     "vcode": st.get("vcode") or 0})
        print(f"{name}: {made[-1]['bytes'] / 1048576:.1f} MB", flush=True)

    kinds = [True] if a.no_lite else [True, False]
    whole = build([], True)
    # Which languages are finished is what the every-language build carried;
    # build_site.py --complete-only decided it, and it is not decided twice.
    langs = []
    if whole:
        keep(whole, [], True)
        langs = [p.split("=")[0].strip() for p in (whole.get("chapters") or "").split(",") if "=" in p]
    sets = [[]] if not a.no_lite else []
    if not a.only_all and langs:
        sets += [[c] for c in langs]
        if "en" in langs:
            sets += [["en", c] for c in langs if c != "en"]
    for p in sets:
        for meaning in kinds:
            if not p and meaning:
                continue                    # the every-language APK with the model is built above
            st = build(p, meaning)
            if st:
                keep(st, p, meaning)
    if not made:
        raise SystemExit("no APK was built")
    (OUT / "apks.json").write_text(json.dumps({"base": a.base_url, "apks": made}, indent=1), encoding="utf-8")
    print(f"{len(made)} APK{'' if len(made) == 1 else 's'} in {OUT}, "
          f"{sum(m['bytes'] for m in made) / 1048576:.0f} MB in all", flush=True)


if __name__ == "__main__":
    main()
