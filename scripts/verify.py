#!/usr/bin/env python3
"""Verification pass: check translated chapters against the source.

Usage:
  verify.py                    check everything in output/en/json/
  verify.py Gen                check one book
  verify.py Gen 1-3            check a chapter range
  verify.py --lang zh [Gen]    another target language ('all' for every one)

Checks (flags, never auto-fixes):
  - verse count mismatch, missing or duplicated verse numbers
  - empty verses
  - untranslated source-script (Hebrew/Greek) characters in the translation
  - a verse that trails off repeating the same words (a model loop, e.g.
    "and barley, and meal, and roasted grain, and barley, ...")
  - suspicious length ratio (translation far shorter than source = possible
    truncation; the threshold is looser for CJK/Thai, which are denser)
  - proper-name spelling inconsistencies across chapters (near-duplicate
    capitalised tokens, e.g. Rebekah/Rebecca) — Latin-script targets
  - names that depart from the spellings readers of the language already know,
    where targets/<lang>/names.map.json has been built (scripts/build_names.py)

Writes logs/verify_<lang>.md and prints a summary. Exit code 1 if any flags.
"""
import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, DEFAULT_TARGET, TARGETS, parse_targets, slug
from translate import find_loop

ROOT = Path(__file__).resolve().parent.parent
NORM_DIR = ROOT / "sources" / "normalized"

HEBREW = re.compile(r"[֐-׿]")
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
MARKS = re.compile(r"[֑-ׇ̀-ͯ]")   # Hebrew points/accents, Greek combining marks
CAP_TOKEN = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b")

# Common sentence-initial words that are not proper names (English + Spanish).
STOP = {"The", "And", "But", "Then", "When", "Now", "For", "God", "Lord",
        "You", "Your", "They", "She", "His", "Her", "Him", "Its", "This",
        "That", "There", "These", "Those", "Let", "May", "All", "Who",
        "What", "Why", "How", "From", "Into", "After", "Before", "While",
        "Notes", "Chapter", "Yes", "See", "Look", "Listen", "Take", "Come",
        "Because", "Since", "Every", "Each", "Here", "Where", "With",
        "Los", "Las", "Una", "Uno", "Pero", "Entonces", "Cuando", "Ahora",
        "Dios", "Señor", "Ustedes", "Ellos", "Ellas", "Ella", "Este", "Esta",
        "Estos", "Estas", "Aquel", "Porque", "Pues", "Para", "Por", "Con",
        "Sin", "Sobre", "Desde", "Hasta", "Todo", "Toda", "Todos", "Todas",
        "Que", "Qué", "Quién", "Cómo", "Dónde", "Así", "Sea", "Sean", "Haya",
        "Notas", "Capítulo", "Miren", "Mira", "Vengan", "Ven", "Escuchen"}


def load_source(code):
    meta = BOOKS[code]
    path = NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def check_chapter(code, ch, out, src_verses, flags, ratio):
    ref = f"{BOOKS[code]['name']} {ch}"
    expected = [v["v"] for v in src_verses]
    got = sorted(int(k) for k in out["verses"])

    missing = sorted(set(expected) - set(got))
    extra = sorted(set(got) - set(expected))
    if missing:
        flags.append(f"{ref}: MISSING verses {missing}")
    if extra:
        flags.append(f"{ref}: EXTRA verse numbers {extra}")
    if len(got) != len(set(got)):
        dups = [n for n, c in Counter(got).items() if c > 1]
        flags.append(f"{ref}: DUPLICATED verse numbers {dups}")

    src_by_num = {v["v"]: MARKS.sub("", v["text"]) for v in src_verses}   # consonantal length
    for n in got:
        text = out["verses"][str(n)]
        if not text.strip():
            flags.append(f"{ref}:{n}: EMPTY verse")
            continue
        if HEBREW.search(text) or GREEK.search(text):
            flags.append(f"{ref}:{n}: UNTRANSLATED source characters remain")
        unit = find_loop(text)
        if unit:
            flags.append(f"{ref}:{n}: LOOP — repeats {unit.strip()[:60]!r} over and over")
        src = src_by_num.get(n)
        if src and len(text) < ratio * len(src) and len(src) > 30:
            flags.append(f"{ref}:{n}: SHORT — {len(text)} chars vs {len(src)} source "
                         f"(possible truncation)")


def name_inventory(chapters_out):
    names = Counter()
    for out in chapters_out:
        for text in out["verses"].values():
            for tok in CAP_TOKEN.findall(text):
                if tok not in STOP:
                    names[tok] += 1
    return names


def check_established(lang, outs, flags):
    """Names a reader of this language would not recognise.

    A near-duplicate check cannot see this: 斯提反 and 司提反 are both
    plausible Chinese, and nothing inside our own text says which one the
    Bibles of that language have used for a century. The answer is not in our
    output at all, so it is looked up - names.map.json holds the established
    spelling, learned from a reference edition, and the English of the same
    chapter says which names the chapter contains.
    """
    table = ROOT / "targets" / lang / "names.map.json"
    if not table.exists():
        return
    known = json.loads(table.read_text(encoding="utf-8"))["names"]
    for out in outs:
        pivot = ROOT / "output" / "en" / "json" / f"{slug(out['book'])}_{int(out['chapter']):02d}.json"
        if not pivot.exists():
            continue
        eng = " ".join(json.loads(pivot.read_text(encoding="utf-8"))["verses"].values())
        text = "".join(out["verses"].values())
        for n in sorted(set(CAP_TOKEN.findall(eng)) | set(re.findall(r"[A-Z][a-z]+-[A-Z]?[a-z]+", eng))):
            want = known.get(n)
            if want and want not in text:
                flags.append(f"{out['book']} {out['chapter']}: NAME — {n} is {want} in the Bibles "
                             f"this language already reads; this chapter does not use it")


def check_names(names, flags):
    toks = sorted(names)
    for i, a in enumerate(toks):
        for b in toks[i + 1:]:
            if abs(len(a) - len(b)) > 2:
                continue
            if difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
                flags.append(f"NAME? '{a}' ({names[a]}x) vs '{b}' ({names[b]}x) — "
                             "same person/place spelled two ways?")


def verify_lang(lang, book_arg, ch_arg):
    json_dir = ROOT / "output" / lang / "json"
    report = ROOT / "logs" / f"verify_{lang}.md"
    latin = TARGETS[lang]["latin"]

    files = sorted(json_dir.glob("*.json"))
    if book_arg:
        name = slug(BOOKS[book_arg]["name"])
        files = [f for f in files if f.stem.rsplit("_", 1)[0] == name]
        if ch_arg:
            if "-" in ch_arg:
                a, b = map(int, ch_arg.split("-"))
                keep = set(range(a, b + 1))
            else:
                keep = {int(ch_arg)}
            files = [f for f in files if int(f.stem.rsplit("_", 1)[1]) in keep]
    if not files:
        print(f"[{lang}] nothing to verify")
        return 0

    flags, per_book = [], {}
    for f in files:
        out = json.loads(f.read_text(encoding="utf-8"))
        code = next(c for c, m in BOOKS.items() if m["name"] == out["book"])
        src = load_source(code)
        src_verses = src["chapters"][str(out["chapter"])]
        check_chapter(code, out["chapter"], out, src_verses, flags, TARGETS[lang]["ratio"])
        per_book.setdefault(code, []).append(out)

    for code, outs in per_book.items():
        if latin:
            check_names(name_inventory(outs), flags)
        check_established(lang, outs, flags)

    report.parent.mkdir(exist_ok=True)
    lines = [f"# Verification report — {TARGETS[lang]['name']} ({lang})",
             f"Chapters checked: {len(files)}", f"Flags: {len(flags)}", ""]
    lines += [f"- {fl}" for fl in flags] or ["All checks passed."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[{lang}] {len(files)} chapters checked, {len(flags)} flags -> {report}")
    for fl in flags:
        print(" ", fl)
    return len(flags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?")
    ap.add_argument("chapters", nargs="?")
    ap.add_argument("--lang", default=DEFAULT_TARGET, help="target code, comma list, or 'all'")
    args = ap.parse_args()
    total = sum(verify_lang(lang, args.book, args.chapters) for lang in parse_targets(args.lang))
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
