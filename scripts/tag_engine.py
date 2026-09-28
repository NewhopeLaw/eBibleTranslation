#!/usr/bin/env python3
"""Stamp each chapter file with the model that wrote it.

    python scripts/tag_engine.py                       # every language, files not yet stamped
    python scripts/tag_engine.py --lang th --force     # restamp one language
    python scripts/tag_engine.py --default qwen3:32b   # what to write when the log is silent

For a year every chapter was written by the one model in config.json, and the
files did not say so - the name was in logs/translate.jsonl, one line per run,
and nowhere a reader could see. Now that a second engine writes a language
(MADLAD-400 for Sgaw Karen, from the English), each chapter's JSON carries an
"engine": the model that produced the verses in it. translate.py and
mt_translate.py write it as they go; this stamps what was written before,
taking the last model the log records for that chapter, and --default for a
chapter the log never saw. It changes nothing else in the file.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import TARGETS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "translate.jsonl"


def logged_models():
    """(lang, book, chapter) -> the model of the last run the log records.
    The earliest lines carry no lang; they were English, the only target then."""
    last = {}
    if not LOG.exists():
        return last
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("model"):
            last[(r.get("lang") or "en", r.get("book"), r.get("chapter"))] = r["model"]
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="", help="one language code (default: every target)")
    ap.add_argument("--default", default="", help="engine for chapters the log does not mention")
    ap.add_argument("--force", action="store_true", help="restamp files that already carry an engine")
    a = ap.parse_args()
    langs = [a.lang] if a.lang else list(TARGETS)
    last = logged_models()
    for lang in langs:
        done = skipped = unknown = 0
        for f in sorted((ROOT / "output" / lang / "json").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("engine") and not a.force:
                skipped += 1
                continue
            model = last.get((lang, d["book"], d["chapter"])) or a.default
            if not model:
                unknown += 1
                continue
            d["engine"] = model
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            done += 1
        if done or skipped or unknown:
            print(f"{lang}: {done} stamped, {skipped} already stamped, {unknown} not in the log"
                  + (" (give --default)" if unknown else ""))


if __name__ == "__main__":
    main()
