#!/usr/bin/env python3
"""Chronology: the numbers the text itself gives, and the dates history anchors them to.

    python scripts/build_chronology.py      # -> site/morph/chron.js

Two separate things, kept separate on purpose:

1. **What the text says.** Every explicit chronological statement is extracted
   from our own English translation (output/en/json) by pattern, never by
   guess, and every record carries the verse it came from: ages at fathering
   and at death (Genesis 5, 11), lengths of reign, accession synchronisms
   ("in the Nth year of X"), and spans ("N years after…"). Nothing is summed
   into a date here: the reader sees the datum and its verse.

2. **Anchors.** A short hand-entered table of events datable from Assyrian,
   Babylonian, Persian and Roman records, each with the reason it is datable.
   These are the only absolute dates asserted, and they are marked as
   externally attested, not derived from the text.

    CHRON = {"data": [[book, ch, v, kind, who, number, unit, of, text], ...],
             "anchors": [[year, label, basis], ...]}
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                       # noqa: E402
from books import BOOKS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "output" / "en" / "json"
OUT = ROOT / "site" / "morph" / "chron.js"
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
       "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
       "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
       "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000}

# externally attested dates: the only absolute years this project asserts
ANCHORS = [
    [-853, "Battle of Qarqar", "Assyrian: the Kurkh Monolith of Shalmaneser III names Ahab of Israel among the coalition; the date is fixed by the Assyrian eponym list and the solar eclipse of 763 BC"],
    [-841, "Jehu pays tribute to Shalmaneser III", "Assyrian: the Black Obelisk, dated by the same eponym list"],
    [-722, "Fall of Samaria", "Assyrian: the annals of Shalmaneser V and Sargon II; the Babylonian Chronicle"],
    [-701, "Sennacherib's campaign against Judah", "Assyrian: Sennacherib's own annals (the Taylor Prism) name Hezekiah"],
    [-605, "Battle of Carchemish", "Babylonian Chronicle (BM 21946)"],
    [-597, "First deportation from Jerusalem", "Babylonian Chronicle: the capture of the city is dated to 2 Adar, the seventh year of Nebuchadnezzar"],
    [-587, "Fall of Jerusalem", "Babylonian Chronicle and the eponym dating of Nebuchadnezzar's reign; 586 is also argued"],
    [-539, "Cyrus takes Babylon", "Babylonian: the Nabonidus Chronicle and the Cyrus Cylinder"],
    [-538, "Decree permitting the return", "Persian: dated to Cyrus's first year over Babylon"],
    [-465, "Accession of Artaxerxes I", "Persian and Babylonian records; fixes the years counted in Ezra and Nehemiah"],
    [-332, "Alexander in the Levant", "Greek historians; the end of Persian rule"],
    [-167, "Desecration of the temple by Antiochus IV", "Seleucid records and 1 Maccabees; dated by the Seleucid era"],
    [-63, "Pompey takes Jerusalem", "Roman historians"],
    [-4, "Death of Herod the Great", "Josephus, with the lunar eclipse he mentions; 1 BC is also argued"],
    [14, "Death of Augustus, accession of Tiberius", "Roman records; fixes the fifteenth year counted in Luke 3:1"],
    [51, "Gallio proconsul of Achaia", "the Delphi inscription of Claudius, which dates Paul's hearing in Acts 18"],
    [70, "Destruction of the temple", "Josephus and Roman records"],
]

PATTERNS = [
    # Abram lived seventy-five years; Adam lived 130 years and fathered...
    ("age-father", re.compile(r"\b([A-Z][a-zA-Z\-]+)\s+(?:had\s+lived|lived|was)\s+(?:for\s+)?([\w\- ]{1,40}?)\s+years?(?:\s+old)?[,;]?\s+(?:and\s+)?(?:he\s+)?(?:fathered|became the father of|begot)\b")),
    ("lifespan", re.compile(r"\b(?:[Aa]ll the days (?:of|that)|[Tt]he (?:total )?length of)\s+([A-Z][a-zA-Z\-\u2019']+?)(?:\u2019s|'s)?\s+(?:life\s+)?(?:lived\s+)?(?:totaled|was|were|came to)\s+([\w\- ]{1,40}?)\s+years?\b")),
    ("age-at", re.compile(r"\b([A-Z][a-zA-Z\-]+)\s+was\s+([\w\- ]{1,40}?)\s+years?\s+old\s+when\b")),
    ("reigned", re.compile(r"\b(?:he|she|[A-Z][a-zA-Z\-]+)\s+(?:reigned|ruled)\s+(?:for\s+)?([\w\- ]{1,40}?)\s+years?\b")),
    ("synchronism", re.compile(r"\b[Ii]n\s+the\s+([\w\- ]{1,40}?)\s+year\s+of\s+(?:the\s+reign\s+of\s+)?([A-Z][a-zA-Z\- ]{2,30}?)(?=[,\s])")),
    ("span", re.compile(r"\b(?:for|was|were)\s+([\w\- ]{1,40}?)\s+years?\b(?!\s+old)")),
    ("since", re.compile(r"\b[Ii]n\s+the\s+([\w\- ]{1,40}?)\s+year\s+after\b")),
]


ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
       "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
       "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
       "fortieth": 40, "fiftieth": 50, "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90,
       "hundredth": 100, "thousandth": 1000}


def to_number(s):
    s = s.lower().replace("-", " ").strip()
    s = re.sub(r"(\d+)(?:st|nd|rd|th)", r"", s)
    if re.fullmatch(r"\d[\d,]*", s):
        return int(s.replace(",", ""))
    words = [ORD.get(w, w) for w in re.split(r"[\s]+", s) if w and w != "and"]
    words = [w for w in words if w != ""]
    if not words or any(not isinstance(w, int) and w not in NUM for w in words):
        return None
    total, cur = 0, 0
    for w in words:
        n = w if isinstance(w, int) else NUM[w]
        if n in (100, 1000):
            cur = (cur or 1) * n
            total += cur
            cur = 0
        else:
            cur += n
    return (total + cur) or None


def main():
    data = []
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        name = slug(meta["name"])
        for f in sorted(EN.glob(f"{name}_*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for v, text in d["verses"].items():
                flat = re.sub(r"\s+", " ", text)
                for kind, rx in PATTERNS:
                    for m in rx.finditer(flat):
                        g = m.groups()
                        who, raw, of = "", "", ""
                        if kind in ("age-father", "age-at"):
                            who, raw = g[0], g[1]
                        elif kind == "lifespan":
                            who, raw = g[0], g[1]
                        elif kind == "reigned":
                            raw = g[0]
                        elif kind == "synchronism":
                            raw, of = g[0], g[1].strip()
                        elif kind == "since":
                            raw = g[0]
                        else:
                            raw = g[0]
                        n = to_number(raw)
                        if n is None or n > 3000:
                            continue
                        snippet = flat[max(0, m.start() - 30):m.end() + 40].strip()
                        data.append([meta["name"], d["chapter"], int(v), kind, who, n, "years", of, snippet])
    data.sort(key=lambda r: (BOOKS and 0, r[0], r[1], r[2]))
    body = "CHRON=" + json.dumps({"data": data, "anchors": ANCHORS}, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(body, encoding="utf-8")
    kinds = {}
    for r in data:
        kinds[r[3]] = kinds.get(r[3], 0) + 1
    manifest.record("chronology", len(data), "statements", "the chronology tab", "build_chronology.py")
    print(f"chronology: {len(data)} statements from the text ({', '.join(f'{k} {n}' for k, n in sorted(kinds.items()))}), "
          f"{len(ANCHORS)} externally attested anchors; {OUT.stat().st_size / 1000:.0f} KB")


if __name__ == "__main__":
    main()
