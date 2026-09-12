#!/usr/bin/env python3
"""Cross-references and parallels (harmonies) for the reader.

    python scripts/build_refs.py       # -> site/morph/xref_<Book>.js, site/morph/parallels.js, logs/parallels_report.md

Cross-references: the OpenBible.info set (CC BY 4.0, sources/openbible/
cross_references.txt — the Treasury of Scripture Knowledge extended by
community votes), one file per book, best-voted first:
    XREF["Genesis"] = {ch: {v: [[book, ch, v, endVerse|0, votes], ...]}}

Parallels: computed from the word tags in site/morph (STEPBible, CC BY 4.0),
not from any harmony book. Verses in the Gospels, in Samuel–Kings–Chronicles
(with Isaiah, Jeremiah, Psalms, Micah) and in the Torah are compared by the
lexemes they share, weighted by rarity (idf-weighted cosine over content
words), so a "harmony" is whatever the text itself supports:
    PAR["Matthew"] = {ch: {v: [[book, ch, v, score], ...]}}   (symmetric, top matches per other book)
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                       # noqa: E402
from books import BOOKS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MORPH = ROOT / "site" / "morph"
XREF_SRC = ROOT / "sources" / "openbible" / "cross_references.txt"
NAME = {c: m["name"] for c, m in BOOKS.items()}

SETS = {
    "gospels": ["Matt", "Mark", "Luke", "John"],
    "kingdoms": ["1Sam", "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr", "Isa", "Jer", "Ps", "Mic"],
    "torah": ["Exod", "Lev", "Num", "Deut"],
}
MAX_DF = 0.03          # lexemes in more than 3% of a set's verses carry no signal
MIN_SHARED = 3
MIN_SCORE = 0.30
SHORT_SHARED = 2        # short verses (a beatitude, a commandment) can only share two content words
SHORT_SCORE = 0.50
PER_BOOK = 3


# ---------------------------------------------------------------- cross-references
def parse_ref(r):
    m = re.match(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)$", r)
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None


def build_xrefs():
    per_book = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    n = 0
    for line in XREF_SRC.read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 3:
            continue
        try:
            votes = int(f[2])
        except ValueError:
            continue
        if votes < 1:
            continue
        a = parse_ref(f[0])
        to = f[1].split("-")
        b = parse_ref(to[0])
        e = parse_ref(to[1]) if len(to) > 1 else None
        if not a or not b or a[0] not in NAME or b[0] not in NAME:
            continue
        per_book[a[0]][a[1]][a[2]].append([NAME[b[0]], b[1], b[2], e[2] if e and e[0] == b[0] and e[1] == b[1] else 0, votes])
        n += 1
    for code, chapters in per_book.items():
        out = {}
        for ch, verses in chapters.items():
            out[str(ch)] = {str(v): sorted(refs, key=lambda r: -r[4])[:40] for v, refs in verses.items()}
        (MORPH / f"xref_{slug(NAME[code])}.js").write_text(
            f"XREF[{json.dumps(NAME[code])}]=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    return n, len(per_book)


# ---------------------------------------------------------------- parallels
def load_morph(code):
    f = MORPH / f"{slug(NAME[code])}.js"
    if not f.exists():
        return {}
    s = f.read_text(encoding="utf-8")
    return json.loads(s[s.index("=") + 1:].rstrip().rstrip(";"))


def content_lexemes(words, greek):
    out = set()
    for w in words:
        if not w:
            continue
        tags, morph = w[0], w[1] or ""
        if greek:
            if not re.match(r"^(N-|V-|A-|ADV)", morph):
                continue
            out.add(tags.split("/")[0])
        else:
            last = morph.split("/")[-1]
            if not last or last[0] not in "NVAD" and not (last[:2] in ("HN", "HV", "HA", "HD", "AN", "AV", "AA", "AD")):
                continue
            m = re.search(r"\{([^}]+)\}", tags)
            out.add(m.group(1) if m else tags.split("/")[0])
    return out


def build_parallels():
    par = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    report = ["# Parallels report", ""]
    for setname, codes in SETS.items():
        greek = setname == "gospels"
        verses = []                                   # (code, ch, v, lexeme set)
        for code in codes:
            m = load_morph(code)
            for ch, vs in m.items():
                for v, words in vs.items():
                    lex = content_lexemes(words, greek)
                    if lex:
                        verses.append((code, int(ch), int(v), lex))
        n = len(verses)
        df = defaultdict(int)
        for _, _, _, lex in verses:
            for t in lex:
                df[t] += 1
        idf = {t: math.log(n / d) for t, d in df.items() if d <= MAX_DF * n}
        index = defaultdict(list)
        for i, (_, _, _, lex) in enumerate(verses):
            for t in lex:
                if t in idf:
                    index[t].append(i)
        norms = [math.sqrt(sum(idf[t] ** 2 for t in lex if t in idf)) or 1.0 for _, _, _, lex in verses]
        pairs = 0
        for i, (code, ch, v, lex) in enumerate(verses):
            shared = defaultdict(float)
            count = defaultdict(int)
            for t in lex:
                if t not in idf:
                    continue
                for j in index[t]:
                    if verses[j][0] != code:
                        shared[j] += idf[t] ** 2
                        count[j] += 1
            best = defaultdict(list)
            for j, s in shared.items():
                if count[j] < SHORT_SHARED:
                    continue
                score = s / (norms[i] * norms[j])
                if score >= MIN_SCORE if count[j] >= MIN_SHARED else score >= SHORT_SCORE:
                    best[verses[j][0]].append((score, j))
            hits = []
            for other, lst in best.items():
                for score, j in sorted(lst, reverse=True)[:PER_BOOK]:
                    hits.append([NAME[verses[j][0]], verses[j][1], verses[j][2], round(score, 2)])
            if hits:
                hits.sort(key=lambda h: -h[3])
                par[NAME[code]][str(ch)][str(v)] = hits
                pairs += len(hits)
        report.append(f"- {setname}: {n} verses compared, {pairs} parallel links")
    (MORPH / "parallels.js").write_text("PAR=" + json.dumps(par, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (ROOT / "logs" / "parallels_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    manifest.record("parallels", sum(len(v) for ch in par.values() for v in ch.values()), "links",
                    "passages that share their wording", "build_refs.py")
    return report


def main():
    n, books = build_xrefs()
    print(f"cross-references: {n} links with positive votes across {books} books -> site/morph/xref_*.js")
    manifest.record("cross-references", n, "links", "shown when a verse number is clicked", "build_refs.py")
    for line in build_parallels():
        print(line)


if __name__ == "__main__":
    main()
