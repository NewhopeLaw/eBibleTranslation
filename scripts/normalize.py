#!/usr/bin/env python3
"""Normalize the source texts into one JSON file per book.

Output: sources/normalized/<NN>_<Book>.json
  {"code": "Gen", "name": "Genesis", "testament": "OT",
   "chapters": {"1": [{"v": 1, "text": "...", "lang": "hbo"}, ...], ...}}

OT: Westminster Leningrad Codex OSIS XML (sources/morphhb/wlc/).
    - morphology attributes dropped, morpheme dividers ('/') removed
    - cantillation accents (U+0591-U+05AF) stripped, vowel points kept
    - qere read in place of ketiv
NT: SBLGNT plain text (sources/SBLGNT/data/sblgnt/text/).
    - critical sigla (word-swap half-brackets etc.) stripped
"""
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, is_aramaic, slug

ROOT = Path(__file__).resolve().parent.parent
WLC_DIR = ROOT / "sources" / "morphhb" / "wlc"
SBL_DIR = ROOT / "sources" / "SBLGNT" / "data" / "sblgnt" / "text"
OUT_DIR = ROOT / "sources" / "normalized"

OSIS_NS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"

# Cantillation accents. Vowel points (U+05B0-U+05BC), meteg (U+05BD),
# and letters are kept.
CANTILLATION = re.compile("[֑-֯]")

# SBLGNT critical sigla: half-brackets and related editorial marks.
SBL_SIGLA = re.compile("[⸀-⸍⁅⁆⸀⸁⸂⸃⸄⸅⸆⸇]")


def clean_hebrew(word: str) -> str:
    word = word.replace("/", "")          # morpheme divider
    word = CANTILLATION.sub("", word)
    return word


def wlc_verse_text(verse_el) -> str:
    """Assemble one verse from <w> and <seg> children, reading qere for ketiv."""
    parts = []          # list of (text, joined_to_previous)
    join_next = False

    def add(text, join=False):
        nonlocal join_next
        parts.append((text, join or join_next))
        join_next = False

    for el in verse_el:
        tag = el.tag.replace(OSIS_NS, "")
        if tag == "w":
            if el.get("type") == "x-ketiv":
                continue  # the qere in the following <note> is read instead
            add(clean_hebrew("".join(el.itertext())))
        elif tag == "seg":
            st = el.get("type", "")
            txt = clean_hebrew("".join(el.itertext()))
            if st == "x-maqqef":
                # join surrounding words with the maqqef, no spaces
                if parts:
                    t, j = parts[-1]
                    parts[-1] = (t + txt, j)
                    join_next = True
            elif st == "x-sof-pasuq":
                if parts:
                    t, j = parts[-1]
                    parts[-1] = (t + txt, j)
            elif st == "x-paseq":
                add(txt)
            # x-pe / x-samekh section markers dropped
        elif tag == "note":
            for rdg in el.iter(OSIS_NS + "rdg"):
                if rdg.get("type") == "x-qere":
                    for w in rdg.iter(OSIS_NS + "w"):
                        add(clean_hebrew("".join(w.itertext())))
    out = ""
    for text, joined in parts:
        if not text:
            continue
        out += text if (joined or not out) else " " + text
    return unicodedata.normalize("NFC", out.strip())


def normalize_wlc(code: str) -> dict:
    tree = ET.parse(WLC_DIR / f"{code}.xml")
    chapters = {}
    for verse in tree.iter(OSIS_NS + "verse"):
        osis_id = verse.get("osisID")          # e.g. "Gen.1.1"
        _, ch, v = osis_id.split(".")
        ch, v = int(ch), int(v)
        entry = {"v": v, "text": wlc_verse_text(verse)}
        if is_aramaic(code, ch, v):
            entry["lang"] = "arc"
        chapters.setdefault(str(ch), []).append(entry)
    return chapters


def normalize_sblgnt(code: str) -> dict:
    chapters = {}
    ref_re = re.compile(r"^(\S+)\s+(\d+):(\d+)\t(.*)$")
    for line in (SBL_DIR / f"{code}.txt").read_text(encoding="utf-8-sig").splitlines():
        m = ref_re.match(line)
        if not m:
            continue  # book title line
        ch, v, text = int(m.group(2)), int(m.group(3)), m.group(4)
        text = SBL_SIGLA.sub("", text)
        text = unicodedata.normalize("NFC", re.sub(r"\s+", " ", text).strip())
        chapters.setdefault(str(ch), []).append({"v": v, "text": text})
    return chapters


def main():
    only = set(sys.argv[1:])  # optional list of book codes
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for code, meta in sorted(BOOKS.items(), key=lambda kv: kv[1]["num"]):
        if only and code not in only:
            continue
        chapters = normalize_wlc(code) if meta["testament"] == "OT" else normalize_sblgnt(code)
        nverses = sum(len(v) for v in chapters.values())
        out = {"code": code, "name": meta["name"], "testament": meta["testament"],
               "chapters": chapters}
        path = OUT_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{meta['name']:<18} {len(chapters):>3} ch  {nverses:>5} vv  -> {path.name}")


if __name__ == "__main__":
    main()
