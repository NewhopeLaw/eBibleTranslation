#!/usr/bin/env python3
"""Fetch public-domain reference Bibles, to learn each language's names from.

Usage:
  get_references.py --list              what is available, per target language
  get_references.py --lang zh,vi,ko     fetch those
  get_references.py --all               fetch every public-domain one there is

Why
---
scripts/build_names.py learns the proper names a language's readers already
know by reading a published translation in that language. It needs one per
target language, and the licence rule here is strict: public domain, CC0,
CC BY, MIT or Apache, nothing share-alike and nothing unlicensed.

eBible.org publishes a catalogue with the copyright of each edition stated,
and a useful number of them are public domain and complete - the American
Standard Version, the 新标点和合本, the Vietnamese Kinh Thánh of 1934, the
Persian ترجمه قدیم. Those are real translations that readers actually know,
which is the whole point: a name is a habit, and only a Bible people have
read can testify to it.

Nothing fetched here is published from this repository. It is a reference,
read on this machine, and what leaves it is a list of spellings - which is a
convention, not a text. The downloads land in sources/references/ and are
gitignored; the licence of each is recorded in the JSON it produces.

Format
------
eBible ships USFM, one file per book. This reduces it to the same shape
build_names.py already reads:
  [{"id", "name", "english", "chapters", "verses":[{"chapter","verse","text"}]}]
"""
import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, TARGETS

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "sources" / "references"
CATALOGUE = "https://ebible.org/Scriptures/translations.csv"
DOWNLOAD = "https://ebible.org/Scriptures/{id}_usfm.zip"

# Our target codes to the ISO 639-3 codes eBible files them under.
ISO = {"en": ["eng"], "es": ["spa"], "zh": ["cmn"], "yue": ["yue"], "ja": ["jpn"],
       "ja-easy": ["jpn"], "ko": ["kor"], "th": ["tha"], "vi": ["vie"], "id": ["ind"],
       "ms": ["zsm", "msa"], "fa": ["pes", "fas"], "tr": ["tur"], "nan": ["nan"],
       "hak": ["hak"]}
# USFM book ids, in canon order, against our own book names.
USFM = {"GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
        "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
        "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
        "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
        "EST": "Esther", "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs",
        "ECC": "Ecclesiastes", "SNG": "Song of Songs", "ISA": "Isaiah", "JER": "Jeremiah",
        "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea",
        "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah", "MIC": "Micah",
        "NAM": "Nahum", "HAB": "Habakkuk", "ZEP": "Zephaniah", "HAG": "Haggai",
        "ZEC": "Zechariah", "MAL": "Malachi", "MAT": "Matthew", "MRK": "Mark",
        "LUK": "Luke", "JHN": "John", "ACT": "Acts", "ROM": "Romans",
        "1CO": "1 Corinthians", "2CO": "2 Corinthians", "GAL": "Galatians",
        "EPH": "Ephesians", "PHP": "Philippians", "COL": "Colossians",
        "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy",
        "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
        "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John",
        "2JN": "2 John", "3JN": "3 John", "JUD": "Jude", "REV": "Revelation"}

MARKUP = re.compile(r"\\[a-z]+\d*\*?\s?")          # \add \nd \w ... and their closers
FOOTNOTE = re.compile(r"\\f .*?\\f\*|\\x .*?\\x\*", re.S)
# A USFM word can carry attributes: \w And|strong="G2532"\w*. The word is the
# text; the attributes are apparatus, and left in they become part of it - the
# ASV came out as And|strong="G2532"they|strong="G2532"led...
ATTRS = re.compile(r'\|(?:[a-z\-]+="[^"]*"|[a-z\-]+:[^\s|\\]*|[^\s|\\"]+)')


def fetch(url, timeout=300):
    """Bytes from a URL.

    Not urllib: the certificate store Python finds on this machine is out of
    date and rejects ebible.org outright. requests with certifi's bundle is
    what the rest of the project already depends on, so it is what is used.
    """
    import requests
    try:
        import certifi
        verify = certifi.where()
    except ImportError:                       # certifi absent: let requests decide
        verify = True
    r = requests.get(url, timeout=timeout, verify=verify)
    r.raise_for_status()
    return r.content


def catalogue():
    return list(csv.DictReader(io.StringIO(fetch(CATALOGUE, 120).decode("utf-8-sig"))))


def public_domain(rows, lang):
    out = []
    for r in rows:
        if r.get("languageCode") not in ISO.get(lang, []):
            continue
        if "public domain" not in (r.get("Copyright") or "").lower():
            continue
        out.append(r)
    # the fullest first: a reference with five books of the Old Testament is
    # not much of a reference
    return sorted(out, key=lambda r: -(int(r.get("OTbooks") or 0) + int(r.get("NTbooks") or 0)))


def parse_usfm(text):
    """-> (usfm book id, {chapter: {verse: text}})"""
    text = ATTRS.sub("", FOOTNOTE.sub("", text))
    book = None
    m = re.search(r"\\id\s+(\w+)", text)
    if m:
        book = m.group(1).upper()
    chapters, ch, verse, buf = {}, None, None, []

    def flush():
        if ch is not None and verse is not None:
            # A space, not nothing: \w And\w*\w while\w* has no space of its
            # own between the words, and the run-together is collapsed below.
            t = MARKUP.sub(" ", " ".join(buf)).strip()
            t = re.sub(r"\s+", " ", t)
            if t:
                chapters.setdefault(ch, {})[verse] = t

    for line in text.splitlines():
        line = line.strip()
        mc = re.match(r"\\c\s+(\d+)", line)
        if mc:
            flush(); buf = []; ch, verse = int(mc.group(1)), None
            continue
        mv = re.match(r"\\v\s+([\d\-,]+)\s*(.*)", line)
        if mv:
            flush(); buf = [mv.group(2)]; verse = mv.group(1)
            continue
        if verse is not None and line and not line.startswith("\\id") and not line.startswith("\\h"):
            buf.append(line)
    flush()
    return book, chapters


def build(lang, row, blob):
    books = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        parsed = {}
        for name in z.namelist():
            if not name.lower().endswith(".usfm"):
                continue
            book, chapters = parse_usfm(z.read(name).decode("utf-8", "replace"))
            if book in USFM and chapters:
                parsed[book] = chapters
    order = {m["name"]: m["num"] for m in BOOKS.values()}
    for usfm_id, english in USFM.items():
        chapters = parsed.get(usfm_id)
        if not chapters:
            continue
        verses = [{"chapter": c, "verse": v, "text": t}
                  for c in sorted(chapters) for v, t in chapters[c].items()]
        books.append({"id": order.get(english, 0), "name": english, "english": english,
                      "chapters": max(chapters), "verses": verses})
    books.sort(key=lambda b: b["id"])
    return books


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", default="", help="target codes, comma separated")
    ap.add_argument("--all", action="store_true", help="every public-domain reference there is")
    ap.add_argument("--list", action="store_true", help="show what is available and stop")
    a = ap.parse_args()

    rows = catalogue()
    langs = list(TARGETS) if (a.all or a.list) else [x.strip() for x in a.lang.split(",") if x.strip()]
    if not langs:
        raise SystemExit("nothing asked for: use --lang, --all or --list")

    for lang in langs:
        hits = public_domain(rows, lang)
        if not hits:
            print(f"{lang:<9} no public-domain edition on eBible")
            continue
        best = hits[0]
        books = f"{best.get('OTbooks')}/{best.get('NTbooks')} OT/NT books"
        print(f"{lang:<9} {best['translationId']:<11} {(best.get('title') or '')[:30]:<32} {books}")
        if a.list:
            continue
        DEST.mkdir(parents=True, exist_ok=True)
        url = DOWNLOAD.format(id=best["translationId"])
        blob = fetch(url)
        data = build(lang, best, blob)
        out = DEST / f"{lang}.json"
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        meta = DEST / f"{lang}.source.json"
        meta.write_text(json.dumps({
            "target": lang, "translationId": best["translationId"], "title": best.get("title"),
            "copyright": best.get("Copyright"), "source": url, "books": len(data),
            "verses": sum(len(b["verses"]) for b in data),
            "_note": "A reference read on this machine to learn proper-name spellings from. "
                     "Not published from this repository; see scripts/build_names.py.",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"          -> {out.name}: {len(data)} books, "
              f"{sum(len(b['verses']) for b in data):,} verses ({best.get('Copyright')})")


if __name__ == "__main__":
    main()
