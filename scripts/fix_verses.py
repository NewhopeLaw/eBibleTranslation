#!/usr/bin/env python3
"""Remove verses the source does not have, and report verses left blank.

Usage:
  fix_verses.py                 show what would change, every language
  fix_verses.py --lang zh       one language
  fix_verses.py --write         make the change

A verse number that is not in the source has no source text behind it. It is
there because the model remembered it from the Bible it was trained on: Acts
8:37, Acts 15:34, Matthew 18:11 and the rest of the verses the Textus Receptus
keeps and the critical text does not. Telling it not to does not work - the
closed list of verse numbers is in the prompt now and Acts 8:37 still came
back on the second attempt and the third - so translate.py drops them as it
parses, and this does the same to what was translated before that.

Nothing is lost by removing them: there is no source, so there was never
anything to translate. The numbering around them is already right, because
the source skips the number and so does what is left.

Verses left blank are a different matter and are only reported. They happen
when the model folds one verse into the one before it, which loses no text but
puts it under the wrong number - and which of the two verses the words belong
to is a judgement this cannot make. scripts/verify.py reports them too, and
the chapter needs translating again.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, parse_targets, slug
from translate import render_md

ROOT = Path(__file__).resolve().parent.parent
NORM = ROOT / "sources" / "normalized"


def source_verses():
    want = {}
    for m in BOOKS.values():
        f = NORM / f"{m['num']:02d}_{slug(m['name'])}.json"
        if not f.exists():
            continue
        for ch, vs in json.loads(f.read_text(encoding="utf-8"))["chapters"].items():
            want[(m["name"], int(ch))] = {str(v["v"]) for v in vs}
    return want


def fix_language(lang, want, write):
    dropped, blank, chapters = 0, [], 0
    for f in sorted((ROOT / "output" / lang / "json").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        w = want.get((d["book"], int(d["chapter"])))
        if not w:
            continue
        extra = [n for n in d["verses"] if n not in w]
        blank += [f"{d['book']} {d['chapter']}:{n}" for n, t in d["verses"].items()
                  if n in w and not t.strip()]
        if not extra:
            continue
        chapters += 1
        dropped += len(extra)
        print(f"   {d['book']} {d['chapter']}: {', '.join(sorted(extra, key=int))} "
              f"not in the source")
        if write:
            for n in extra:
                d["verses"].pop(n, None)
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            meta = next(m for m in BOOKS.values() if m["name"] == d["book"])
            md = ROOT / "output" / lang / d["book"].replace(" ", "_") / f"{f.stem}.md"
            if md.exists():
                md.write_text(render_md(meta, d["chapter"], d["verses"], d.get("notes", "")),
                              encoding="utf-8")
    verb = "removed" if write else "would remove"
    print(f"  {lang}: {verb} {dropped} source-less verses from {chapters} chapters"
          + (f"; {len(blank)} verses are blank and need the chapter translating again" if blank else ""))
    for b in blank[:8]:
        print(f"       blank: {b}")
    return dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", default="all")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    want = source_verses()
    total = 0
    for lang in parse_targets(a.lang):
        if (ROOT / "output" / lang / "json").exists():
            total += fix_language(lang, want, a.write)
    if total and not a.write:
        print("\nnothing written — run again with --write")


if __name__ == "__main__":
    main()
