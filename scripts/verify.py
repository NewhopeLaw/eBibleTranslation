#!/usr/bin/env python3
"""Verification pass: check translated chapters against the source.

Usage:
  verify.py            check everything in output/json/
  verify.py Gen        check one book
  verify.py Gen 1-3    check a chapter range

Checks (flags, never auto-fixes):
  - verse count mismatch, missing or duplicated verse numbers
  - empty verses
  - untranslated source-script (Hebrew/Greek) characters in the English
  - suspicious length ratio (English far shorter than source = possible truncation)
  - proper-name spelling inconsistencies across chapters (near-duplicate
    capitalized tokens, e.g. Rebekah/Rebecca)

Writes logs/verify_report.md and prints a summary. Exit code 1 if any flags.
"""
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug

ROOT = Path(__file__).resolve().parent.parent
NORM_DIR = ROOT / "sources" / "normalized"
JSON_DIR = ROOT / "output" / "json"
REPORT = ROOT / "logs" / "verify_report.md"

HEBREW = re.compile(r"[֐-׿]")
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
CAP_TOKEN = re.compile(r"\b[A-Z][a-z]{2,}\b")

# Common sentence-initial words that are not proper names.
STOP = {"The", "And", "But", "Then", "When", "Now", "For", "God", "Lord",
        "You", "Your", "They", "She", "His", "Her", "Him", "Its", "This",
        "That", "There", "These", "Those", "Let", "May", "All", "Who",
        "What", "Why", "How", "From", "Into", "After", "Before", "While",
        "Notes", "Chapter", "Yes", "See", "Look", "Listen", "Take", "Come",
        "Because", "Since", "Every", "Each", "Here", "Where", "With"}


def load_source(code):
    meta = BOOKS[code]
    path = NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def check_chapter(code, ch, out, src_verses, flags):
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

    src_by_num = {v["v"]: v["text"] for v in src_verses}
    for n in got:
        text = out["verses"][str(n)]
        if not text.strip():
            flags.append(f"{ref}:{n}: EMPTY verse")
            continue
        if HEBREW.search(text) or GREEK.search(text):
            flags.append(f"{ref}:{n}: UNTRANSLATED source characters remain")
        src = src_by_num.get(n)
        if src and len(text) < 0.5 * len(src) and len(src) > 60:
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


def check_names(names, flags):
    toks = sorted(names)
    for i, a in enumerate(toks):
        for b in toks[i + 1:]:
            if abs(len(a) - len(b)) > 2:
                continue
            if difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
                flags.append(f"NAME? '{a}' ({names[a]}x) vs '{b}' ({names[b]}x) — "
                             "same person/place spelled two ways?")


def main():
    book_arg = sys.argv[1] if len(sys.argv) > 1 else None
    ch_arg = sys.argv[2] if len(sys.argv) > 2 else None

    files = sorted(JSON_DIR.glob("*.json"))
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
        print("nothing to verify")
        return

    flags, per_book = [], {}
    for f in files:
        out = json.loads(f.read_text(encoding="utf-8"))
        code = next(c for c, m in BOOKS.items() if m["name"] == out["book"])
        src = load_source(code)
        src_verses = src["chapters"][str(out["chapter"])]
        check_chapter(code, out["chapter"], out, src_verses, flags)
        per_book.setdefault(code, []).append(out)

    for code, outs in per_book.items():
        check_names(name_inventory(outs), flags)

    REPORT.parent.mkdir(exist_ok=True)
    lines = [f"# Verification report", f"Chapters checked: {len(files)}",
             f"Flags: {len(flags)}", ""]
    lines += [f"- {fl}" for fl in flags] or ["All checks passed."]
    REPORT.write_text("\n".join(lines) + "\n")

    print(f"{len(files)} chapters checked, {len(flags)} flags -> {REPORT}")
    for fl in flags:
        print(" ", fl)
    sys.exit(1 if flags else 0)


if __name__ == "__main__":
    main()
