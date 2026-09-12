#!/usr/bin/env python3
"""Clause roles and participants for the Greek New Testament and the Hebrew Bible.

    python scripts/build_syntax.py       # -> site/morph/syn_<Book>.js

Reads the MACULA linguistic datasets (Clear Bible / Biblica, CC BY 4.0):
`sources/macula/greek.tsv` for the SBLGNT, `sources/macula/hebrew.tsv` for the
Westminster Leningrad Codex. Both are keyed to the same texts this project
translates, so their word order matches ours one for one. For every word we
keep the syntactic role in its clause, the word class, the word a pronoun or
other referring word points back to, and a short gloss.

    SYN["John"] = {ch: {v: [[role, class, "", refTo, gloss], ...]}}
        refTo = "Book|ch|v|index" of the antecedent, or ""

NOT USED: the semantic-domain fields of either dataset (`domain`, `ln`,
`sdbh`, `lexdomain`, `coredomain`, `contextualdomain`). Their licences record
them as United Bible Societies material — Louw-Nida for Greek, the Semantic
Dictionary of Biblical Hebrew for Hebrew — "used with permission", permission
given to Clear Bible rather than passed on to everyone downstream. This project
ships only what is licensed to everyone, so those columns are never read.
Semantic grouping comes instead from our own lexicon, written from the text.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "macula"
OUT = ROOT / "site" / "morph"

MACULA_NT = ["MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH",
             "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"]
MACULA_OT = ["GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI", "1CH", "2CH",
             "EZR", "NEH", "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS",
             "JOL", "AMO", "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL"]
ORDER = [c for c, m in sorted(BOOKS.items(), key=lambda x: x[1]["num"])]
OT, NT = ORDER[:39], ORDER[39:]
NAME = {c: m["name"] for c, m in BOOKS.items()}
ROLE = {"v": "verb", "s": "subject", "o": "object", "o2": "second object", "io": "indirect object",
        "p": "predicate", "vc": "copula", "adv": "adverbial", "aux": "auxiliary", "apposition": "apposition"}
REF = re.compile(r"^(\w+) (\d+):(\d+)!(\d+)$")


def read(path, book_map, role_col, gloss_cols):
    """-> rows[book][ch][v][idx] = (role, class, refTo-id, gloss), ids[xml:id] = key"""
    rows = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    ids, raw_ref = {}, {}
    if not path.exists():
        return rows, ids, raw_ref
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            m = REF.match(r.get("ref") or "")
            if not m or m.group(1) not in book_map:
                continue
            book, ch, v, i = book_map[m.group(1)], int(m.group(2)), int(m.group(3)), int(m.group(4)) - 1
            gloss = next((r.get(c) or "" for c in gloss_cols if (r.get(c) or "").strip()), "").strip()
            rows[book][ch][v][i] = (ROLE.get(r.get(role_col, ""), (r.get(role_col) or "").strip()),
                                    (r.get("class") or r.get("pos") or "").strip(), gloss)
            ids[r["xml:id"]] = f"{NAME[book]}|{ch}|{v}|{i}"
            ref = (r.get("referent") or r.get("participantref") or r.get("subjref") or "").split()
            if ref:
                raw_ref[(book, ch, v, i)] = ref[0]
    return rows, ids, raw_ref


def emit(rows, ids, raw_ref):
    total = 0
    for book, chapters in rows.items():
        out = {}
        for ch, verses in chapters.items():
            out[str(ch)] = {}
            for v, words in verses.items():
                arr = []
                for i in range(max(words) + 1):
                    w = words.get(i)
                    if not w:
                        arr.append(None)
                        continue
                    arr.append([w[0], w[1], "", ids.get(raw_ref.get((book, ch, v, i), ""), ""), w[2]])
                out[str(ch)][str(v)] = arr
                total += len(arr)
        (OUT / f"syn_{slug(NAME[book])}.js").write_text(
            f"SYN[{json.dumps(NAME[book])}]=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    return total


def main():
    g_rows, g_ids, g_ref = read(SRC / "greek.tsv", dict(zip(MACULA_NT, NT)), "role", ["gloss", "english"])
    h_rows, h_ids, h_ref = read(SRC / "hebrew.tsv", dict(zip(MACULA_OT, OT)), "role", ["gloss", "english"])
    ng = emit(g_rows, g_ids, g_ref)
    nh = emit(h_rows, h_ids, h_ref)
    (OUT / "domains.js").unlink(missing_ok=True)        # UBS domain data is not ours to redistribute
    size = sum(p.stat().st_size for p in OUT.glob("syn_*.js"))
    print(f"syntax: {ng} Greek words across {len(g_rows)} books, {nh} Hebrew words across {len(h_rows)} books "
          f"(role, class, antecedent, gloss); {size / 1e6:.1f} MB. Semantic domains deliberately excluded — see LEGAL.md")


if __name__ == "__main__":
    main()
