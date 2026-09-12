#!/usr/bin/env python3
"""Syntax, participants and semantic domains for the Greek New Testament.

    python scripts/build_syntax.py       # -> site/morph/syn_<Book>.js, site/morph/domains.js

Reads the MACULA Greek linguistic dataset for the SBLGNT (Clear Bible / Biblica,
CC BY 4.0, sources/macula/greek.tsv). For every word it carries the syntactic
role in its clause (subject, object, verb, adverbial…), the word class, the
Louw-Nida semantic domain number, and — for pronouns and other referring words —
the word it refers back to. Our base text is the same SBLGNT, so the word order
matches ours one for one.

    SYN["John"] = {ch: {v: [[role, class, domain, refTo], ...]}}     refTo = "ch.v.i" or ""
    DOMAINS = {domain: [[strong, headword, gloss], ...]}             lexemes sharing a domain

Only the domain NUMBER is used. Louw-Nida's domain titles are copyrighted and
are not reproduced; the reader shows the words that share a domain, so the
grouping speaks for itself.
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
TSV = ROOT / "sources" / "macula" / "greek.tsv"
OUT = ROOT / "site" / "morph"

# MACULA uses three-letter book ids in canonical order for the NT
MACULA = ["MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH",
          "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"]
NT = [c for c, m in sorted(BOOKS.items(), key=lambda x: x[1]["num"]) if m["testament"] == "NT"]
M2OURS = dict(zip(MACULA, NT))
NAME = {c: m["name"] for c, m in BOOKS.items()}
ROLE = {"v": "verb", "s": "subject", "o": "object", "o2": "second object", "io": "indirect object",
        "p": "predicate", "vc": "copula", "adv": "adverbial", "aux": "auxiliary", "apposition": "apposition"}
REF = re.compile(r"^(\w+) (\d+):(\d+)!(\d+)$")


def main():
    rows = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))     # book -> ch -> v -> idx -> fields
    ids = {}                                                               # xml:id -> "book|ch|v|idx"
    domains = defaultdict(dict)
    with TSV.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            m = REF.match(r["ref"] or "")
            if not m or m.group(1) not in M2OURS:
                continue
            book, ch, v, i = M2OURS[m.group(1)], int(m.group(2)), int(m.group(3)), int(m.group(4)) - 1
            rows[book][ch][v][i] = r
            ids[r["xml:id"]] = f"{NAME[book]}|{ch}|{v}|{i}"
            if r["domain"] and r["strong"]:
                tag = "G" + r["strong"].zfill(4)
                domains[r["domain"]].setdefault(tag, [r["lemma"], (r["gloss"] or "").strip()])
    total = 0
    for book, chapters in rows.items():
        out = {}
        for ch, verses in chapters.items():
            out[str(ch)] = {}
            for v, words in verses.items():
                n = max(words) + 1
                arr = []
                for i in range(n):
                    r = words.get(i)
                    if not r:
                        arr.append(None)
                        continue
                    ref_to = ids.get((r["referent"] or "").split()[0]) if r["referent"] else ""
                    arr.append([ROLE.get(r["role"], r["role"] or ""), r["class"] or "", r["domain"] or "",
                                ref_to or "", (r["gloss"] or "").strip()])
                out[str(ch)][str(v)] = arr
                total += n
        (OUT / f"syn_{slug(NAME[book])}.js").write_text(
            f"SYN[{json.dumps(NAME[book])}]=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    dom = {d: sorted(([t] + v for t, v in lex.items()), key=lambda x: x[1]) for d, lex in domains.items() if len(lex) > 1}
    (OUT / "domains.js").write_text("DOMAINS=" + json.dumps(dom, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.glob("syn_*.js")) + (OUT / "domains.js").stat().st_size
    print(f"syntax: {total} Greek words tagged with role, class, domain and referent across {len(rows)} books; "
          f"{len(dom)} semantic domains with more than one lexeme; {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
