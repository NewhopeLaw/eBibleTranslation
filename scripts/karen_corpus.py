#!/usr/bin/env python3
"""The Karen Bible as a parallel corpus: Mason's 1853 Sgaw Karen beside our English.

    python scripts/karen_corpus.py            # writes sources/ksw-mason/verses.jsonl and pairs.jsonl
    python scripts/karen_corpus.py --check    # print Genesis 1 so it can be read against a printed copy

No model on hand can write Sgaw Karen (README, "Target languages"), so one
has to be taught, and the teacher is the Karen Bible itself: Francis Mason's
translation of 1853, public domain, digitised by the Myanmar Bible Society and
distributed as the SWORD module KswSKMB (sources/ksw-mason/). Every verse of
it stands beside the same verse of our English, and those pairs are what a
translation model is fine-tuned on (scripts/train_karen.py).

The module follows the KJV's verse numbering and our English the Hebrew's, so
they part company where those two do - the Psalm superscriptions, Joel 3,
Malachi 4 and a few dozen others. A chapter whose verse counts differ is left
out of the pairs rather than paired wrongly, and named at the end; a few
hundred verses fewer is a small price against a model taught that Psalm 51:1
means "for the choirmaster".

  sources/ksw-mason/verses.jsonl   {book, chapter, verse, ksw}    the whole Karen Bible
  sources/ksw-mason/pairs.jsonl    {book, chapter, verse, en, ksw} where the numbering agrees
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = ROOT / "sources" / "ksw-mason"
EN_JSON = ROOT / "output" / "en" / "json"
VERSES = MODULE_DIR / "verses.jsonl"
PAIRS = MODULE_DIR / "pairs.jsonl"

# pysword names books the way the SWORD KJV canon does; ours are BOOKS' names.
SWORD_NAMES = {"Song of Solomon": "Song of Songs", "Revelation of John": "Revelation",
               "I Samuel": "1 Samuel", "II Samuel": "2 Samuel", "I Kings": "1 Kings", "II Kings": "2 Kings",
               "I Chronicles": "1 Chronicles", "II Chronicles": "2 Chronicles",
               "I Corinthians": "1 Corinthians", "II Corinthians": "2 Corinthians",
               "I Thessalonians": "1 Thessalonians", "II Thessalonians": "2 Thessalonians",
               "I Timothy": "1 Timothy", "II Timothy": "2 Timothy", "I Peter": "1 Peter", "II Peter": "2 Peter",
               "I John": "1 John", "II John": "2 John", "III John": "3 John"}
for _m in BOOKS.values():
    SWORD_NAMES.setdefault(_m["name"], _m["name"])

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def clean(text):
    """Verse text alone: the module's footnotes and headings are markup pysword
    strips when asked, but a stray tag or doubled space still gets through."""
    text = re.sub(r"<[^>]+>", "", text or "")
    # The module runs its clauses together after a comma or a full stop; the
    # printed Bible, and the pasted page it was checked against, put a space
    # there, and a model should learn to write what a reader is used to.
    text = re.sub(r"([,.;:?!])(?=[^\s,.;:?!])", r"\1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def read_module():
    from pysword.modules import SwordModules

    mods = SwordModules(str(MODULE_DIR))
    found = mods.parse_modules()
    name = next(iter(found))
    bible = mods.get_bible_from_module(name)
    out = []
    for testament, books in bible.get_structure().get_books().items():
        for book in books:
            ours = SWORD_NAMES.get(book.name)
            if ours is None:
                print(f"skipping {book.name!r}: not one of our sixty-six", file=sys.stderr)
                continue
            for ch in range(1, book.num_chapters + 1):
                for v in range(1, book.chapter_lengths[ch - 1] + 1):
                    try:
                        text = clean(bible.get(books=[book.name], chapters=[ch], verses=[v], clean=True))
                    except Exception:            # noqa: BLE001 - a verse the module leaves empty
                        text = ""
                    if text:
                        out.append({"book": ours, "chapter": ch, "verse": v, "ksw": text})
    return out


def english():
    """{(book, chapter): {verse: text}} of our own translation."""
    out = {}
    for f in EN_JSON.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        out[(d["book"], int(d["chapter"]))] = {int(n): t.strip() for n, t in d["verses"].items() if t.strip()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="print Genesis 1 and stop")
    a = ap.parse_args()
    verses = read_module()
    if a.check:
        for r in verses:
            if r["book"] == "Genesis" and r["chapter"] == 1:
                print(r["verse"], r["ksw"])
        return
    VERSES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in verses), encoding="utf-8")
    by_chapter = {}
    for r in verses:
        by_chapter.setdefault((r["book"], r["chapter"]), {})[r["verse"]] = r["ksw"]
    en = english()
    pairs, left_out = [], []
    for key in sorted(by_chapter, key=lambda k: (BOOKS[next(c for c, m in BOOKS.items() if m["name"] == k[0])]["num"], k[1])):
        ksw, ours = by_chapter[key], en.get(key)
        if not ours:
            left_out.append(f"{key[0]} {key[1]} (no English yet)")
            continue
        if set(ksw) != set(ours):
            left_out.append(f"{key[0]} {key[1]} ({len(ksw)} Karen vv, {len(ours)} English)")
            continue
        pairs += [{"book": key[0], "chapter": key[1], "verse": v, "en": ours[v], "ksw": ksw[v]} for v in sorted(ksw)]
    PAIRS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pairs), encoding="utf-8")
    print(f"{len(verses)} Karen verses in {len(by_chapter)} chapters -> {VERSES.name}")
    print(f"{len(pairs)} verse pairs from {len(by_chapter) - len(left_out)} chapters -> {PAIRS.name}")
    if left_out:
        print(f"{len(left_out)} chapters left out because the numbering differs: " + "; ".join(left_out[:12])
              + (" ..." if len(left_out) > 12 else ""))


if __name__ == "__main__":
    main()
