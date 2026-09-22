#!/usr/bin/env python3
"""One index over everything the study layers know, so one search can reach it.

    python scripts/build_entries.py            # -> site/morph/entries.js
    python scripts/build_entries.py --probe love

The reader has a lexicon of 22,717 entries, a concordance of 16,967 lexemes,
89 fields of meaning, the themes and 1,111 places. A reader can walk into any
of them from the tools tray, and the search box reaches none of them: type
"love" and you get the verses where a translator happened to write the word,
while ἀγάπη and φιλέω sit two taps away with every occurrence already counted.

This puts them all in one index, keyed by the words a reader would type. Each
entry says what kind of thing it is, what to call it, and what the reader
already has a page for, so the search box can offer them beside the verses
without knowing anything about any particular layer.

    ENTRIES = [[kind, id, label, sub, count, source], ...]
              an idiom carries a seventh: the verses it stands in, ["Ezekiel 1:4", ...]
    ENTIDX  = {term: "delta-encoded entry numbers, base 16, dot separated"}
    ENTKEY  = {term: the same, for terms standing in the name or the gloss}

Two indexes, because where a word matched decides how much it means. A
dictionary definition of "staff" mentions a shepherd, so indexing definitions
alone put the word for a tribal staff above the word for a shepherd. ENTKEY
holds only what an entry calls itself; a hit there outranks a hit anywhere
else, and the long definitions stay searchable without taking over.

`kind` is what the reader opens: a lexeme goes to showLexeme, a field to
showDomain, a theme to showTheme, a place to the map. An idiom is the one kind
that is its own answer: what the reader wants from "a stone of stumbling" is the
verses, so the entry brings them with it rather than a page to go and look on. `count` is how often the
thing occurs, which is the only ranking worth having here - a reader searching
"love" wants ἀγάπη before a hapax whose gloss happens to say loving.

`source` says where an entry came from: "" for the layers built from the text,
"ref" for the ones resting on the STEPBible tagging. The reader labels those as
the reference's, which is what docs/from-the-text.md asks for - the reference is
kept beside our own and named, never folded into it silently. Our own lexicon is
263 entries of 16,967 today; when it overtakes, the reference entries can be
dropped by building with --ours.

Nothing here calls the model. It reads the layers that the model already built
and writes an index over them, which is exact work and belongs in code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                              # noqa: E402
from build_index import encode, terms_of                     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MORPH = ROOT / "site" / "morph"
DEFN = 400          # how much of a long dictionary definition is worth indexing: the
                    # opening says what the word means, the rest is citations and cognates


def layer(name, var):
    """One variable out of a built layer, or None when that layer is not built."""
    p = MORPH / name
    if not p.exists():
        return None
    s = p.read_text(encoding="utf-8")
    key = var + "="
    if key not in s:
        return None
    i = s.index(key) + len(key)
    try:
        return json.loads(s[i:s.index(";\n", i)])
    except (ValueError, json.JSONDecodeError):
        return None


def gather(ours_only=False):
    """-> [(kind, id, label, sub, count, source, searchable text)], and after the
    text whatever else the entry itself should carry"""
    out = []
    conc = layer("conc.js", "CONC") or {}
    occurrences = {k: len(v) for k, v in conc.items()}

    # ---- our own lexicon: entries written from the occurrences themselves
    lexx = layer("lexx.js", "LEXX") or {}
    for tag, rec in lexx.items():
        senses = rec.get("senses") or []
        text = " ".join([rec.get("headword", ""), rec.get("gloss", "")]
                        + [s.get("sense", "") for s in senses]
                        + [str(s.get("definition", ""))[:DEFN] for s in senses])
        out.append(("lexeme", tag, rec.get("headword", tag), rec.get("gloss", ""),
                    occurrences.get(tag, 0), "", text))

    # ---- the phrases those entries record. An idiom is what a search of the text
    # cannot find: the verse says "lift up the face" and the reader is looking for
    # favour. The meaning is what it is found by, the phrase is what it is called,
    # and its verses come along. The model also files single inflected forms under
    # idioms (שַׁבְּתֹתֶיהָ, "its sabbaths"); those are the word itself, which the word's
    # own entry already answers for, so a phrase here is two words or more.
    for tag, rec in lexx.items():
        for n, idiom in enumerate(rec.get("idioms") or []):
            if not isinstance(idiom, dict):
                continue
            phrase, meaning = str(idiom.get("phrase") or "").strip(), str(idiom.get("meaning") or "").strip()
            refs = [str(r) for r in idiom.get("refs") or [] if r]
            if not (meaning and refs and len(re.split(r"[\s־]+", phrase)) > 1):
                continue
            out.append(("idiom", f"{tag}#{n}", phrase, meaning, len(refs), "", f"{phrase} {meaning}", refs))

    # ---- our own lexeme inventory: the forms, before any entry has been written
    for lid, rec in (layer("lexemes.js", "LEXEME") or {}).items():
        head, pos, gloss, root, count = (list(rec) + ["", "", "", "", 0])[:5]
        out.append(("lexeme", lid, head, gloss, count or 0, "",
                    " ".join([head, pos or "", gloss or "", root or ""])))

    # ---- the reference lexicon, named as such
    if not ours_only:
        have = set(lexx)
        for tag, rec in (layer("lex.js", "LEX") or {}).items():
            if tag in have:                                   # ours has spoken for this one
                continue
            head, translit, _code, gloss, defn = (list(rec) + ["", "", "", "", ""])[:5]
            out.append(("lexeme", tag, head, gloss, occurrences.get(tag, 0), "ref",
                        " ".join([head, translit or "", gloss or "", str(defn or "")[:DEFN]])))

    # ---- fields of meaning: searchable by the field's name and by what is in it
    for field, members in (layer("domains.js", "DOMAINS") or {}).items():
        words = " ".join(f"{m[1]} {m[2]}" for m in members if len(m) > 2)
        out.append(("field", field, field, f"{len(members)} lexemes", len(members), "",
                    f"{field} {words}"))

    # ---- themes: the model's reading of what the chapters are about
    for tid, rec in (layer("themes.js", "THEMES") or {}).items():
        label, desc, passages, vocab = (list(rec) + ["", "", [], []])[:4]
        out.append(("theme", tid, label, str(desc)[:120], len(passages or []), "",
                    f"{label} {desc}"))

    # ---- places: what a reader types is the name, or the modern one
    for name, rec in (layer("places.js", "PLACES") or {}).items():
        modern = " ".join(str(x) for x in rec[2:] if x)
        out.append(("place", name, name, modern, 1, "", f"{name} {modern}"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ours", action="store_true", help="leave the reference lexicon out")
    ap.add_argument("--probe", default="", help="run a query against what was built")
    a = ap.parse_args()
    if a.probe:
        return probe(a.probe)

    rows = gather(a.ours)
    if not rows:
        raise SystemExit("no study layer is built yet — run scripts/build_all.py first")

    # Ranked before they are numbered, so that a reader who stops reading after
    # three results has been given the three that matter: a lexeme standing in
    # six thousand verses before one standing in two.
    rows.sort(key=lambda r: -(r[4] or 0))
    postings, key = defaultdict(set), defaultdict(set)
    for n, (_k, _i, label, sub, _c, _src, text, *_more) in enumerate(rows):
        for t in terms_of(text, "la"):
            postings[t].add(n)
        for t in terms_of(f"{label} {sub}", "la"):
            key[t].add(n)                                     # what the entry calls itself
        for t in terms_of(label, "he" if re.search(r"[֐-׿]", label) else "gr"):
            postings[t].add(n)                                # the headword in its own script
            key[t].add(n)

    entries = [[k, i, lab, sub, c, src, *more] for k, i, lab, sub, c, src, _t, *more in rows]
    body = ("ENTRIES=" + json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "ENTIDX=" + json.dumps({t: encode(v) for t, v in postings.items()},
                                     ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "ENTKEY=" + json.dumps({t: encode(v) for t, v in key.items()},
                                     ensure_ascii=False, separators=(",", ":")) + ";\n")
    p = MORPH / "entries.js"
    p.write_text(body, encoding="utf-8")
    kinds = defaultdict(int)
    for r in rows:
        kinds[r[0]] += 1
    print(f"entries: {len(rows)} things, {len(postings)} terms, {p.stat().st_size / 1e6:.1f} MB -> {p.name}")
    print("  " + ", ".join(f"{v} {k}s" for k, v in sorted(kinds.items())))
    manifest.record("entries", len(rows), "things", "the study layers, searchable", "build_entries.py")


def probe(query):
    """Ask the built index a question, the way the reader will ask it."""
    p = MORPH / "entries.js"
    if not p.exists():
        raise SystemExit("nothing built yet — run scripts/build_entries.py first")
    s = p.read_text(encoding="utf-8")

    def grab(name):
        i = s.index(name + "=") + len(name) + 1
        return json.loads(s[i:s.index(";\n", i)])
    ent, idx, key = grab("ENTRIES"), grab("ENTIDX"), grab("ENTKEY")

    def hits(index):
        acc = None
        for w in terms_of(query, "la"):
            got = index.get(w)
            if not got:
                return set()
            nums, run = set(), 0
            for x in got.split("."):
                run += int(x, 16)
                nums.add(run)
            acc = nums if acc is None else acc & nums
        return acc or set()

    # What an entry calls itself first, everything else after it, each already
    # in order of how often the thing occurs.
    named, anywhere = hits(key), hits(idx)
    if not (named or anywhere):
        print(f"nothing in the study layers answers “{query}”")
        return
    for n in sorted(named) + [n for n in sorted(anywhere) if n not in named]:
        kind, _id, label, sub, count, src = ent[n][:6]
        print(f"  {kind:7} {label:20} {str(sub)[:42]:42} {count:>6}"
              + ("  ref" if src == "ref" else "     ")
              + ("  named" if n in named else "")
              + ("  " + ", ".join(ent[n][6]) if len(ent[n]) > 6 else ""))


if __name__ == "__main__":
    main()
