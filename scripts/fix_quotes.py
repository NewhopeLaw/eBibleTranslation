#!/usr/bin/env python3
"""Remove closing quotation marks that close nothing.

Usage:
  fix_quotes.py                 show what would change, in every language
  fix_quotes.py --lang zh       one language
  fix_quotes.py --write         make the change

A speech in the Bible runs on for verses at a time. The model is handed one
verse at a time to write, and it keeps shutting the quotation at the end of
each one, so verse after verse ends with a mark that opened nowhere:

    1  ...对他说:"我是全能的神...作完全的人。"
    2  我要与你立约,使你的后裔极其繁多。"      <- nothing opened this
    5  你的名字不再叫亚伯兰...多国之父。"       <- nor this

The reverse - more opens than closes - is left alone, because that is how the
published editions set a long speech: it reopens at each paragraph and closes
once at the end. The 和合本 has 228 chapters like that and not one of the kind
above, which is what marks this as an error rather than a convention.

The repair is mechanical and needs no judgement: read the chapter in verse
order, count depth, and drop a closing mark found at depth zero. Nothing else
in the text is touched, and a chapter with nothing wrong is not rewritten.

The `raw` field in each JSON keeps the model's own words untouched - it is the
record of what was actually said, and the repair is ours, not its.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, TARGETS, parse_targets
from translate import render_md

ROOT = Path(__file__).resolve().parent.parent
# Opening and closing marks that come in pairs. The straight " is deliberately
# absent: it is its own opposite, so depth cannot be counted for it.
PAIRS = [("“", "”"), ("「", "」"), ("『", "』"),
         ("«", "»"), ("‘", "’")]


def strip_strays(verses, opener, closer):
    """-> (repaired verses, [verse numbers that lost a mark])."""
    out, touched, depth = {}, [], 0
    for n in sorted(verses, key=int):
        kept = []
        for c in verses[n]:
            if c == opener:
                depth += 1
            elif c == closer:
                if depth > 0:
                    depth -= 1
                else:
                    touched.append(n)          # a close with nothing open: drop it
                    continue
            kept.append(c)
        out[n] = "".join(kept)
    return out, touched


def repair_language(lang, write):
    latin = TARGETS[lang]["latin"]
    files = sorted((ROOT / "output" / lang / "json").glob("*.json"))
    changed, marks, shown = 0, 0, 0
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        verses, hits = dict(d["verses"]), []
        for opener, closer in PAIRS:
            # An apostrophe is the same character as a closing single quote in
            # a Latin script - David's, don't - so that pair is only counted
            # where the script has no apostrophes to confuse it with.
            if latin and opener == "‘":
                continue
            verses, touched = strip_strays(verses, opener, closer)
            hits += [(n, closer) for n in touched]
        if not hits:
            continue
        changed += 1
        marks += len(hits)
        if shown < 6:
            shown += 1
            where = ", ".join(n for n, _c in hits[:6]) + ("..." if len(hits) > 6 else "")
            print(f"   {d['book']} {d['chapter']}: {len(hits)} stray (v. {where})")
        if write:
            meta = next(m for m in BOOKS.values() if m["name"] == d["book"])
            d["verses"] = verses
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            md = ROOT / "output" / lang / d["book"].replace(" ", "_") / f"{f.stem}.md"
            if md.exists():
                md.write_text(render_md(meta, d["chapter"], verses, d.get("notes", "")),
                              encoding="utf-8")
    verb = "repaired" if write else "would repair"
    print(f"  {lang}: {verb} {changed} chapters, {marks} stray closing marks"
          + ("" if changed else " — nothing to do"))
    return marks


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", default="all", help="target code, comma list, or 'all'")
    ap.add_argument("--write", action="store_true", help="make the change (default: only report)")
    a = ap.parse_args()
    total = 0
    for lang in parse_targets(a.lang):
        if (ROOT / "output" / lang / "json").exists():
            total += repair_language(lang, a.write)
    if total and not a.write:
        print("\nnothing written — run again with --write")


if __name__ == "__main__":
    main()
