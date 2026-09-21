#!/usr/bin/env python3
"""Search index: every word of every text, mapped to the verses it stands in.

    python scripts/build_index.py              # -> site/morph/idx_<lang>.js

Exact work, done in code: the postings must list every occurrence and no
others, which is precisely what a language model should not be asked to do.
The model's part is the layer above this one — grouping the forms of a word in
each modern language (scripts/build_wordforms.py) — which the reader folds in
at search time when it exists.

For each text (the Hebrew/Aramaic and Greek sources, and each translation) the
index holds:

    IDX["en"] = {term: "delta-encoded verse ids, base 36, dot separated"}

A verse id is book*1000000 + chapter*1000 + verse. Terms are lower-cased and
stripped of accents for Latin and Greek scripts, and of vowel points for
Hebrew, so a search matches what a reader types. Languages that do not space
their words (Chinese, Japanese, Thai) are indexed by character bigrams as well
as by run, which is what makes substring search work for them.
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                       # noqa: E402
from books import BOOKS, TARGETS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOPICS = ROOT / "targets" / "search" / "topics.jsonl"
NORM = ROOT / "sources" / "normalized"
OUT = ROOT / "site" / "morph"
NOSPACE = re.compile(r"[㐀-鿿豈-﫿぀-ヿ฀-๿]")
WORD = re.compile(r"[\w֐-׿Ͱ-Ͽἀ-῿]+", re.UNICODE)


def fold(term, script):
    term = unicodedata.normalize("NFD", term)
    if script == "he":
        term = "".join(c for c in term if not ("֑" <= c <= "ׇ"))
    else:
        term = "".join(c for c in term if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", term).lower()


def terms_of(text, script):
    """-> set of searchable terms: whole words, plus bigrams for unspaced scripts."""
    out = set()
    for m in WORD.finditer(text):
        w = m.group(0)
        if NOSPACE.search(w):
            for i in range(len(w)):
                out.add(w[i])
                if i + 1 < len(w):
                    out.add(w[i:i + 2])
                if i + 2 < len(w):
                    out.add(w[i:i + 3])
        else:
            f = fold(w, script)
            if f:
                out.add(f)
    return out


def encode(ids):
    out, prev = [], 0
    for i in sorted(ids):
        out.append(format(i - prev, "x"))
        prev = i
    return ".".join(out)


TOTALS = {}


def write_index(name, postings, note):
    body = f"IDX[{json.dumps(name)}]=" + json.dumps({t: encode(v) for t, v in postings.items()},
                                                    ensure_ascii=False, separators=(",", ":")) + ";\n"
    p = OUT / f"idx_{name}.js"
    p.write_text(body, encoding="utf-8")
    TOTALS[name] = sum(len(v) for v in postings.values())
    print(f"  {name}: {len(postings)} terms, {sum(len(v) for v in postings.values())} postings, "
          f"{p.stat().st_size / 1e6:.1f} MB{note}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # ---- the source texts
    heb, grk = defaultdict(set), defaultdict(set)
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        f = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
        if not f.exists():
            continue
        target = grk if meta["testament"] == "NT" else heb
        script = "gr" if meta["testament"] == "NT" else "he"
        for ch, verses in json.loads(f.read_text(encoding="utf-8"))["chapters"].items():
            for rec in verses:
                vid = meta["num"] * 1000000 + int(ch) * 1000 + rec["v"]
                for t in terms_of(rec["text"], script):
                    target[t].add(vid)
                if rec.get("lxx"):
                    for t in terms_of(rec["lxx"], "gr"):
                        grk["lxx:" + t].add(vid)
    write_index("hbo", heb, " (Hebrew and Aramaic, vowel points folded)")
    write_index("grc", grk, " (Greek, accents folded; Septuagint terms prefixed lxx:)")
    # ---- the translations
    for code in TARGETS:
        d = ROOT / "output" / code / "json"
        if not d.exists():
            continue
        postings = defaultdict(set)
        n = 0
        for f in sorted(d.glob("*.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            meta = next((m for m in BOOKS.values() if m["name"] == rec["book"]), None)
            if not meta:
                continue
            n += 1
            for v, text in rec["verses"].items():
                vid = meta["num"] * 1000000 + int(rec["chapter"]) * 1000 + int(v)
                clean = re.sub(r"\{([^{}|\]]+)\|[^{}\]]+[}\]]", r"\1", text)      # furigana notation
                for t in terms_of(clean, "la"):
                    postings[t].add(vid)
        if postings:
            write_index(code, postings, f" ({TARGETS[code]['name']}, {n} chapters)")
    # ---- the words the verses do not use
    # scripts/build_topics.py writes, for every verse, a line of the plain modern
    # words a reader would look with - the writing on the wall for a verse that
    # says fingers wrote on the plaster. They are indexed on their own rather
    # than mixed into each language: the postings are verse ids, which every
    # translation shares, so one index serves them all and no language file
    # grows by an English vocabulary it has no other use for.
    if TOPICS.exists():
        bynum = {m["name"]: m["num"] for m in BOOKS.values()}
        postings = defaultdict(set)
        chapters = 0
        for line in TOPICS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            num = bynum.get(rec["book"])
            if not num:
                continue
            chapters += 1
            for v, said in (rec.get("topics") or {}).items():
                vid = num * 1000000 + int(rec["chapter"]) * 1000 + int(v)
                for t in terms_of(said, "la"):
                    postings[t].add(vid)
        if postings:
            write_index("topics", postings, f" (what each verse is about, {chapters} chapters)")


if __name__ == "__main__":
    main()
    manifest.record("search-index", sum(TOTALS.values()), "postings",
                    f"{len(TOTALS)} texts indexed for search", "build_index.py")
