#!/usr/bin/env python3
"""Mine the Karen Bible for how it spells the names: a name table for Sgaw Karen.

    python scripts/karen_names.py               # writes targets/ksw/names.en.json and logs/karen_names.md
    python scripts/karen_names.py --min 3       # rarer names too (noisier)

The model taught Karen from the verse pairs (scripts/train_karen.py) learns
the grammar fast and the names slowly: at a third of an epoch it called Sarai
"Israel's father". Names are rare and arbitrary, the worst case for learning
by exposure, and the best case for a table - and the table is in the corpus
already, since Mason spelled every name of the Bible in Karen and our English
spells the same names in the same verses.

For each English name (a capitalised word that is capitalised wherever it
occurs, in enough verses to trust) the Karen syllable string that appears in
the same verses and nowhere much else is its spelling: Dice's coefficient
between the verses holding the name and the verses holding the string, with
the longest string kept among those that score within a hair of the best, so
that "Abram" gets all of စီၤအၤဘြၣ် and not its first syllable. The Karen
name-prefixes - စီၤ for a man, နီၢ် for a woman - come along by themselves,
because Mason wrote them every time.

The table is keyed by our English spelling, unlike the other languages' name
tables, which are keyed by the Hebrew: this one is for teaching the model
(the pairs go into the fine-tune) and for the reader's eye, not for a prompt.
Every entry has its score and count in the report, for a Karen reader to check.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "NGAW KAREN TTS"))
from karen_phonemes import SYLLABLE   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "sources" / "ksw-mason" / "pairs.jsonl"
OUT = ROOT / "targets" / "ksw" / "names.en.json"
REPORT = ROOT / "logs" / "karen_names.md"
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
MAX_SYL = 7
# Capitalised words that are not names: the start-of-sentence problem is
# handled by counting, these are the ones capitalised for other reasons.
NOT_NAMES = {"I", "O", "The", "And", "But", "For", "So", "Then", "Now", "Yet", "Or", "If", "When", "You", "He",
             "She", "It", "We", "They", "Who", "What", "Why", "How", "Let", "Do", "Go", "See", "Look", "Behold",
             "LORD's", "God's", "Lord's", "King", "Son", "Father", "Spirit", "Holy", "Most", "High", "Almighty"}

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def syllables(text):
    out, i = [], 0
    while i < len(text):
        m = SYLLABLE.match(text, i)
        if m:
            out.append(m.group(0))
            i = m.end()
        else:
            if text[i] in " ,.;:!?":
                out.append(" ")             # a boundary a name will not cross
            i += 1
    return out


def ngrams(syls):
    out = set()
    for i, s in enumerate(syls):
        if s == " ":
            continue
        g = ""
        for j in range(i, min(len(syls), i + MAX_SYL)):
            if syls[j] == " ":
                break
            g += syls[j]
            out.add(g)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=5, help="verses a name must appear in")
    a = ap.parse_args()
    rows = [json.loads(l) for l in PAIRS.read_text(encoding="utf-8").splitlines() if l.strip()]

    # English: which capitalised words are names (capitalised everywhere they occur)
    cap, low, verses_with = Counter(), Counter(), defaultdict(set)
    for k, r in enumerate(rows):
        seen = set()
        for m in WORD.finditer(r["en"]):
            w = m.group(0).rstrip("'’")
            if w[0].isupper():
                cap[w] += 1
                seen.add(w)
            else:
                low[w.capitalize()] += 1
        for w in seen:
            verses_with[w].add(k)
    names = [w for w, c in cap.items() if c >= a.min and low[w] == 0 and w not in NOT_NAMES and len(w) > 1]
    print(f"{len(names)} English names in {a.min}+ verses", flush=True)

    # Karen: syllable strings per verse, and how many verses each string is in
    grams = [ngrams(syllables(r["ksw"])) for r in rows]
    total = Counter()
    for g in grams:
        total.update(g)

    table, report = {}, []
    for name in sorted(names, key=lambda w: -cap[w]):
        vs = verses_with[name]
        local = Counter()
        for k in vs:
            local.update(grams[k])
        best = []
        for g, c in local.items():
            if c < 2:
                continue
            dice = 2 * c / (len(vs) + total[g])
            best.append((dice, len(g), g, c))
        if not best:
            continue
        best.sort(reverse=True)
        top = best[0][0]
        # the longest string within a hair of the best score: the whole name
        pick = max((b for b in best if b[0] >= top - 0.03), key=lambda b: (b[1], b[0]))
        dice, _, karen, c = pick
        if dice < 0.35:
            report.append((name, len(vs), karen, dice, c, "weak - left out"))
            continue
        table[name] = karen
        report.append((name, len(vs), karen, dice, c, ""))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"_note": "English name -> Karen spelling, mined from Mason's Karen Bible beside our "
                                        "English by scripts/karen_names.py; unread by a Karen speaker",
                               "names": table}, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# Karen names mined from the Karen Bible", "",
             f"{len(table)} names kept, {sum(1 for r in report if r[5])} left out as weak. "
             "Score is Dice between the verses holding the English name and those holding the Karen string.", "",
             "| English | verses | Karen | score | together | |", "|---|---|---|---|---|---|"]
    lines += [f"| {n} | {v} | {k} | {d:.2f} | {c} | {note} |" for n, v, k, d, c, note in report]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(table)} names -> {OUT}; report {REPORT}")
    for n, v, k, d, c, note in report[:25]:
        print(f"  {n:14} {k:22} {d:.2f}  ({c}/{v}) {note}")


if __name__ == "__main__":
    main()
