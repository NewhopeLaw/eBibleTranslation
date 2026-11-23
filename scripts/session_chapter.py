#!/usr/bin/env python3
"""What an agent in a Claude Code session needs to write a chapter: the source
out, and the chapter back in, checked.

    session_chapter.py units --lang shn --verses 80      the chapters not yet written, in parcels
    session_chapter.py rules --lang shn                  the style rules, key terms and pinned names
    session_chapter.py source Ruth 1 --lang shn          the chapter as translate.py would put it to a model
    session_chapter.py save Ruth 1 draft.txt --lang shn  check a draft and write it to output/
    session_chapter.py names-out --lang shn --size 250   the names in our English, in batches to be spelled
    session_chapter.py names-in --lang shn               gather the spelled batches into names.map.json

Shan (Tai Yai) is the language this was written for. Neither chat model that
runs here can write it (README, "Target languages"), and the four chapters
Claude wrote for the trial were written by hand in a session, so nothing could
be run again and nothing checked them. This is the part of translate.py that
does not need Ollama, turned to face an agent instead: the same source text
and verse list, the same rules file, glossary and names, and the same rule that
a chapter is only written when every verse of the source is in it.

A draft is the model's reply as translate.py expects it: one "[n] text" per
verse, poetry on continuation lines, an optional "---" and notes. `save`
refuses, and writes nothing, when a verse is missing, when one has no letter of
the language's own, when one holds another script's letters or Latin ones, or
when one loops. The agent mends the draft and saves again.

The engine line in each chapter says who wrote it, and scripts/build_site.py
carries that to the reader's footer.
"""
import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                  # noqa: E402
from books import BOOKS, TARGETS, slug                 # noqa: E402

ROOT = T.ROOT
LOG_PATH = ROOT / "logs" / "session.jsonl"
# The Septuagint column is for a model that may misread a hard Hebrew line and
# has room to spare; here it would double what every agent reads.
T.CONFIG["consult_lxx"] = False
# A language that shares a Unicode block with another is told from it by its
# letters (see trial_lang.py's Shan plan, which these are taken from).
OWN = {"shn": "ၵ-ႊ"}
FOREIGN = {"shn": "ကခစဆညနဖဟအ"}
LATIN = re.compile(r"[A-Za-z]{2,}")
BY_NAME = {slug(m["name"]).lower(): c for c, m in BOOKS.items()}


def book_code(arg):
    if arg in BOOKS:
        return arg
    code = BY_NAME.get(arg.lower())
    if not code:
        raise SystemExit(f"unknown book {arg!r}")
    return code


def source(code):
    meta = BOOKS[code]
    return json.loads((T.NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json").read_text(encoding="utf-8"))


def paths(lang, meta, ch):
    name = slug(meta["name"])
    return (T.out_dir(lang) / name / f"{name}_{int(ch):02d}.md", T.json_dir(lang) / f"{name}_{int(ch):02d}.json")


def units(lang, size):
    """The chapters still to write, in canonical order, a book at a time, in
    parcels of about `size` verses: one agent's sitting. A chapter longer than
    that is a parcel of its own."""
    out = []
    for code in sorted(BOOKS, key=lambda c: BOOKS[c]["num"]):
        chapters = source(code)["chapters"]
        cur, n = [], 0
        for ch in sorted(chapters, key=int):
            if paths(lang, BOOKS[code], ch)[0].exists():
                continue
            if cur and n + len(chapters[ch]) > size:
                out.append({"book": code, "chapters": cur, "verses": n})
                cur, n = [], 0
            cur.append(int(ch))
            n += len(chapters[ch])
        if cur:
            out.append({"book": code, "chapters": cur, "verses": n})
    return out


def save(lang, code, ch, draft, engine):
    meta = BOOKS[code]
    verses = source(code)["chapters"][str(int(ch))]
    expected = [v["v"] for v in verses]
    raw = Path(draft).read_text(encoding="utf-8-sig")
    parsed, notes, missing, extra = T.parse_output(raw, expected)
    own = re.compile(f"[{OWN[lang]}]") if lang in OWN else None
    foreign = re.compile(f"[{FOREIGN[lang]}]") if lang in FOREIGN else None
    wrong = []
    if missing:
        wrong.append(f"missing verses {missing}")
    empty = [n for n, t in parsed.items() if not t.strip()]
    if empty:
        wrong.append(f"empty verses {empty}")
    if own:
        bare = [n for n, t in parsed.items() if t.strip() and not own.search(t)]
        if bare:
            wrong.append(f"no {TARGETS[lang]['name']} letters in verses {bare}")
    if foreign:
        other = {n: "".join(sorted(set(foreign.findall(t)))) for n, t in parsed.items() if foreign.search(t)}
        if other:
            wrong.append(f"letters of another language in verses {other}")
    latin = [n for n, t in parsed.items() if LATIN.search(t)]
    if latin and not TARGETS[lang].get("latin"):
        wrong.append(f"Latin letters in verses {latin}")
    loops = [n for n, t in parsed.items() if T.find_loop(t)]
    if loops:
        wrong.append(f"verses that loop {loops}")
    if wrong:
        print(f"NOT SAVED {meta['name']} {ch}: " + "; ".join(wrong))
        return 1
    md_path, json_path = paths(lang, meta, ch)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(T.render_md(meta, ch, parsed, notes), encoding="utf-8")
    json_path.write_text(json.dumps(
        {"book": meta["name"], "chapter": int(ch), "lang": lang,
         "verses": {str(k): v for k, v in sorted(parsed.items())},
         "notes": notes, "raw": raw, "engine": engine}, ensure_ascii=False, indent=1), encoding="utf-8")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "book": meta["name"], "chapter": int(ch),
                            "lang": lang, "model": engine, "verses": len(parsed), "dropped": extra}) + "\n")
    print(f"saved {meta['name']} {ch}: {len(parsed)}/{len(expected)} verses"
          + (f" (dropped numbers the source has not: {extra})" if extra else ""))
    return 0


def english_names():
    """The proper names in our English: a capitalised word that is never met
    in lower case, and is met at least once away from the start of a sentence."""
    cap, low = collections.Counter(), collections.Counter()
    for f in sorted((ROOT / "output" / "en" / "json").glob("*.json")):
        for t in json.loads(f.read_text(encoding="utf-8"))["verses"].values():
            for m in re.finditer(r"(?<![.!?:;\"“‘'(\n] )(?<!^)\b[A-Z][a-z]+(?:-[A-Z]?[a-z]+)*", t):
                cap[m.group()] += 1
            low.update(re.findall(r"\b[a-z]+\b", t))
    return sorted(n for n in cap if not low[n.lower()])


def names_out(lang, size):
    parts = ROOT / "targets" / lang / "names.parts"
    parts.mkdir(parents=True, exist_ok=True)
    names = english_names()
    n = 0
    for i in range(0, len(names), size):
        n += 1
        (parts / f"in_{n:02d}.txt").write_text("\n".join(names[i:i + size]) + "\n", encoding="utf-8")
    print(json.dumps({"names": len(names), "batches": n}))


def names_in(lang, engine):
    parts = ROOT / "targets" / lang / "names.parts"
    own = re.compile(f"[{OWN[lang]}]") if lang in OWN else None
    table, lacking = {}, []
    for f in sorted(parts.glob("in_*.txt")):
        want = f.read_text(encoding="utf-8").split()
        out = parts / f.name.replace("in_", "out_").replace(".txt", ".json")
        got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        for name in want:
            v = str(got.get(name, "")).strip()
            # Latin letters mean the name was left in English, except in a
            # language that is written in them.
            if v and (not own or own.search(v)) and (TARGETS[lang].get("latin") or not LATIN.search(v)):
                table[name] = v
            else:
                lacking.append(name)
    (ROOT / "targets" / lang / "names.map.json").write_text(json.dumps(
        {"_comment": f"English name -> {TARGETS[lang]['name']} spelling, so every chapter agrees. Not taken from a "
                     f"published Bible: spelled by {engine} from the sound of the Hebrew and Greek, and unread by a "
                     "speaker. A name a reader knows otherwise is to be corrected here and in the chapters.",
         "names": dict(sorted(table.items()))}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(table)} names written" + (f", {len(lacking)} lacking: {lacking[:40]}" if lacking else ""))
    return 1 if lacking else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["units", "rules", "source", "save", "names-out", "names-in"])
    ap.add_argument("book", nargs="?")
    ap.add_argument("chapter", nargs="?")
    ap.add_argument("draft", nargs="?")
    ap.add_argument("--lang", default="shn")
    ap.add_argument("--verses", type=int, default=80, help="units: verses to a parcel")
    ap.add_argument("--size", type=int, default=250, help="names-out: names to a batch")
    ap.add_argument("--engine", default="Claude, an agent in a Claude Code session, from the Hebrew and Greek")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.what == "units":
        print(json.dumps(units(a.lang, a.verses)))
    elif a.what == "rules":
        print(T.build_system_prompt(a.lang))
    elif a.what == "names-out":
        names_out(a.lang, a.size)
    elif a.what == "names-in":
        sys.exit(names_in(a.lang, a.engine))
    else:
        code = book_code(a.book)
        if a.what == "source":
            verses = source(code)["chapters"][str(int(a.chapter))]
            print(T.build_user_prompt(BOOKS[code], a.chapter, verses, None, a.lang))
        else:
            sys.exit(save(a.lang, code, a.chapter, a.draft, a.engine))


if __name__ == "__main__":
    main()
