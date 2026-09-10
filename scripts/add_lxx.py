#!/usr/bin/env python3
"""Add the Septuagint as a second source to the normalized Old Testament.

Reads Swete's Septuagint (First1KGreek TEI, CC BY-SA 4.0) from sources/lxx/
and writes each verse's Greek into sources/normalized/<NN>_<Book>.json as
"lxx" next to the Hebrew "text". Idempotent: re-run after re-fetching.

Fetch the files first (37 books, ~14 MB):
  python scripts/add_lxx.py --fetch

Alignment is by chapter and verse number with the standard block mappings
where the Greek numbering diverges (Psalms, Jeremiah, Ezra-Nehemiah as
2 Esdras, Daniel in Theodotion's version). Verses the mapping cannot place
simply carry no "lxx". Ecclesiastes has no file in the corpus.

Text cleaning: apparatus <note>s, page/line breaks, manuscript sigla (lone
Latin capitals), lacuna brackets and stray spacing are removed; NFC.
"""
import argparse
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug

ROOT = Path(__file__).resolve().parent.parent
LXX_DIR = ROOT / "sources" / "lxx"
NORM_DIR = ROOT / "sources" / "normalized"
RAW = "https://raw.githubusercontent.com/OpenGreekAndLatin/First1KGreek/master/data/tlg0527"
TEI = "{http://www.tei-c.org/ns/1.0}"

# OSIS code -> First1KGreek work number (tlg0527.tlgNNN). Daniel uses
# Theodotion (057), the form the churches read; 1-2 Sam / 1-2 Kgs are
# Regnorum I-IV; Ezra and Nehemiah share Esdras ii (018).
WORKS = {
    "Gen": "001", "Exod": "002", "Lev": "003", "Num": "004", "Deut": "005",
    "Josh": "006", "Judg": "008", "Ruth": "010", "1Sam": "011", "2Sam": "012",
    "1Kgs": "013", "2Kgs": "014", "1Chr": "015", "2Chr": "016", "Ezra": "018",
    "Neh": "018", "Esth": "019", "Job": "032", "Ps": "027", "Prov": "029",
    "Song": "031", "Isa": "048", "Jer": "049", "Lam": "051", "Ezek": "053",
    "Dan": "057", "Hos": "036", "Joel": "039", "Amos": "037", "Obad": "040",
    "Jonah": "041", "Mic": "038", "Nah": "042", "Hab": "043", "Zeph": "044",
    "Hag": "045", "Zech": "046", "Mal": "047",
    # "Eccl": no file in First1KGreek
}

SIGLA = re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z])")     # lone manuscript letters (A, B, S...)
BRACKETS = re.compile(r"[\[\]⟦⟧⌈⌉⌊⌋¶]")     # lacuna brackets, Swete's paragraph marks
SPACE_PUNCT = re.compile(r"\s+([,.;·:!?])")


def clean(text: str) -> str:
    text = BRACKETS.sub("", text)
    text = SIGLA.sub("", text)
    text = re.sub(r"\s+", " ", text)
    text = SPACE_PUNCT.sub(r"\1", text)
    return unicodedata.normalize("NFC", text.strip())


def verse_text(div) -> str:
    """Text of a verse div without apparatus notes."""
    parts = []

    def walk(el):
        tag = el.tag.replace(TEI, "")
        if tag == "note":
            if el.tail:
                parts.append(el.tail)
            return
        if el.text:
            parts.append(el.text)
        for child in el:
            walk(child)
        if el.tail:
            parts.append(el.tail)

    walk(div)
    if div.tail:                       # the div's own tail belongs to the parent, not the verse
        parts.pop()
    return clean("".join(parts))


def load_work(num: str) -> dict:
    """{chapter: {verse: text}} of one Swete book, in the Greek numbering."""
    path = LXX_DIR / f"tlg0527.tlg{num}.1st1K-grc1.xml"
    if not path.exists():
        return {}
    root = ET.parse(path).getroot()
    out = {}
    for ch in root.iter(TEI + "div"):
        if ch.get("subtype") != "chapter":
            continue
        try:
            cn = int(ch.get("n"))
        except (TypeError, ValueError):
            continue
        for v in ch.iter(TEI + "div"):
            if v.get("subtype") != "verse":
                continue
            try:
                vn = int(re.match(r"\d+", v.get("n") or "").group())
            except (AttributeError, ValueError):
                continue
            txt = verse_text(v)
            if txt:
                out.setdefault(cn, {})[vn] = txt
    return out


# ------------------------------------------------------------- chapter maps
def psalm_map(mt: int):
    """Masoretic psalm number -> Greek psalm number(s)."""
    if mt <= 8:
        return [mt]
    if mt in (9, 10):
        return [9]
    if 11 <= mt <= 113:
        return [mt - 1]
    if mt in (114, 115):
        return [113]
    if mt == 116:
        return [114, 115]
    if 117 <= mt <= 146:
        return [mt - 1]
    if mt == 147:
        return [146, 147]
    return [mt]


def jeremiah_map(mt: int):
    if mt <= 25:
        return [mt]
    if 26 <= mt <= 44:
        return [mt + 7]
    if mt == 45:
        return [51]
    return {46: [26], 47: [29], 48: [31], 49: [30, 25], 50: [27], 51: [28], 52: [52]}.get(mt, [])


def greek_chapters(code: str, mt_chapter: int):
    if code == "Ps":
        return psalm_map(mt_chapter)
    if code == "Jer":
        return jeremiah_map(mt_chapter)
    if code == "Neh":
        return [mt_chapter + 10]          # 2 Esdras 11-23
    return [mt_chapter]


def attach(code: str, meta: dict, greek: dict) -> tuple[int, int]:
    path = NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    total = hit = 0
    for ch, verses in data["chapters"].items():
        gch = greek_chapters(code, int(ch))
        for v in verses:
            total += 1
            v.pop("lxx", None)
            for g in gch:
                txt = greek.get(g, {}).get(v["v"])
                if txt:
                    v["lxx"] = txt
                    hit += 1
                    break
    data["lxx"] = {"edition": "Swete", "verses": hit}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return hit, total


def fetch():
    LXX_DIR.mkdir(parents=True, exist_ok=True)
    for num in sorted(set(WORKS.values())):
        name = f"tlg0527.tlg{num}.1st1K-grc1.xml"
        dest = LXX_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        print("fetching", name)
        urllib.request.urlretrieve(f"{RAW}/tlg{num}/{name}", dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download missing source files first")
    ap.add_argument("books", nargs="*", help="OSIS codes to (re)attach; default all OT")
    args = ap.parse_args()
    if args.fetch:
        fetch()
    cache = {}
    for code, meta in sorted(BOOKS.items(), key=lambda kv: kv[1]["num"]):
        if meta["testament"] != "OT" or (args.books and code not in args.books):
            continue
        num = WORKS.get(code)
        if not num:
            print(f"{meta['name']:<16} no Septuagint file")
            continue
        if num not in cache:
            cache[num] = load_work(num)
        hit, total = attach(code, meta, cache[num])
        print(f"{meta['name']:<16} {hit:>5}/{total:<5} verses aligned")


if __name__ == "__main__":
    main()
