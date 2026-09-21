#!/usr/bin/env python3
"""The line that lets a verse be found by someone who cannot quote it.

    python scripts/build_topics.py --limit 20      # a first pass over a few chapters
    python scripts/build_topics.py                 # every chapter, resuming
    python scripts/build_topics.py --show Daniel 5 # read back what was written

Search can only match words that are there. A reader looking for the writing on
the wall types "writing on the wall"; Daniel 5:5 says that the fingers of a
human hand wrote on the plaster of the wall opposite the lampstand, and the two
have almost nothing in common. Measured against the verse vectors built from
the text alone, Daniel 5:5 came back 16,941st of 31,152 for that query, and the
son who wasted his money 22,167th. Neither verse is obscure. They are simply
written in words nobody searches with.

So this writes the missing words. For every verse the model says, in one plain
modern line, what is happening and what it concerns — who is there, what the
scene is, and the words a reader would reach for that the verse itself never
uses. Those lines are not shown to anyone. They are embedded beside the verse
by scripts/build_vectors.py and folded into the search index by
scripts/build_index.py, so that a reader's vocabulary has something to land on.

Because nothing here is displayed, the line is built to be searched rather than
read: it may be a list, it need not be a sentence, and repeating a name is a
virtue. What it must not do is interpret. A line that says what a passage
teaches, or what it means for the reader, would put a reading into the search
results where the text should be — and unlike the themes, which are labelled as
the model's reading and cite their verses, this layer is invisible and could not
be checked. Describe the scene and name the subject; nothing further.

Written to targets/search/topics.jsonl, one line per chapter, resumable:

    {"book": "Daniel", "chapter": 5, "topics": {"5": "Belshazzar's feast; ..."}}

This is a PC job: it needs Ollama and the model named in config.json.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                     # noqa: E402
from books import BOOKS, slug                             # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "output" / "en" / "json"
NORM = ROOT / "sources" / "normalized"
DIR = ROOT / "targets" / "search"
TOPICS = DIR / "topics.jsonl"

SYSTEM = """You write the search line for each verse of a chapter: the words that would let a reader find this verse when they cannot remember how it is worded.

You get a chapter, verse by verse, each verse in its original language with the English translation under it.

Reply with JSON only:
{"topics": {"1": "the line for verse 1", "2": "the line for verse 2", ...}}

One line for every verse you are given, keyed by its verse number.

What a line contains, in eight to twenty words:
- What is happening, in plain modern English. Name the people, the place and the event, even when the verse only says "he" or "there".
- The everyday words someone would search with that this verse does not use. A verse about being anxious should carry worry, stress, fear; a verse about a debt forgiven should carry money, mercy, letting go.
- The name the episode is known by, when it has one: the writing on the wall, the prodigal son, the burning bush, the golden calf, the good Samaritan, feeding the five thousand.

Rules:
- Describe, do not interpret. Say what happens and what it concerns. No application, no lesson, no doctrine, no devotional comment. Nobody will read these lines; they exist only to be matched against, and a reading smuggled in here would surface as though it were the text.
- Do not repeat the verse's own wording. The line is worth its cost only where it adds words the verse lacks. If the verse already says "do not be anxious", the line should say worry, stress, panic, fear — not "do not be anxious".
- Carry the context down. In a genealogy or a list of offerings, every verse gets the chapter's subject named again, because a reader searching for it may land on any of them.
- Use today's vocabulary, not the translation's. Write money rather than mammon, tent rather than tabernacle, bribe rather than gift — and when the modern word would mislead, give both.
- Proper names in full, as a reader would type them: Belshazzar, Nebuchadnezzar, the Sea of Galilee.
- No verse numbers, no book names, no quotation marks inside the line."""


def call(system, user, temp=0.3):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": temp},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())
    T.log_work(resp, time.time() - t0)
    return json.loads(resp.get("message", {}).get("content", "{}"))


def chapter_files():
    out = []
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        for f in sorted(EN.glob(f"{slug(meta['name'])}_*.json")):
            out.append((meta, f))
    return out


def source_chapter(meta, ch):
    """{verse: the original text} for one chapter."""
    f = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
    if not f.exists():
        return {}
    chapters = json.loads(f.read_text(encoding="utf-8"))["chapters"]
    return {rec["v"]: rec["text"] for rec in chapters.get(str(ch), [])}


def done_chapters():
    got = set()
    if TOPICS.exists():
        for line in TOPICS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                got.add((r["book"], int(r["chapter"])))
    return got


def run(limit=0, redo=False, only=None):
    """Every chapter that has no line yet, one call each.

    A chapter that comes back short of verses is kept as far as it got rather
    than thrown away: a verse with no line is only a verse that searches as it
    does today, whereas discarding the chapter would cost another call to get
    back what is already right. The count of missing lines is reported, so a
    chapter that failed badly can be seen and redone with --redo.
    """
    T.WORK_JOB = "topics"
    DIR.mkdir(parents=True, exist_ok=True)
    done = set() if redo else done_chapters()
    todo = [(m, f) for m, f in chapter_files()
            if (m["name"], int(f.stem.rsplit("_", 1)[1])) not in done]
    if only:
        book, ch = only
        todo = [(m, f) for m, f in chapter_files()
                if m["name"].lower() == book.lower() and int(f.stem.rsplit("_", 1)[1]) == ch]
        if not todo:
            raise SystemExit(f"no translated chapter {book} {ch}")
    if limit:
        todo = todo[:limit]
    print(f"topics: {len(done)} chapters done, {len(todo)} to do")
    t0, n, short = time.time(), 0, 0
    with TOPICS.open("a", encoding="utf-8") as fh:
        for meta, f in todo:
            d = json.loads(f.read_text(encoding="utf-8"))
            src = source_chapter(meta, d["chapter"])
            lang = "Greek" if meta["testament"] == "NT" else "Hebrew or Aramaic"
            verses = sorted(d["verses"].items(), key=lambda kv: int(kv[0]))
            body = "\n".join(
                (f"[{v}] {src[int(v)]}\n     {t}" if int(v) in src else f"[{v}] {t}")
                for v, t in verses)
            user = (f"{d['book']} {d['chapter']} — each verse in {lang}, with the translation under it\n\n"
                    f"{body}\n\nWrite the search line for each of these {len(verses)} verses.")
            try:
                got = call(SYSTEM, user)
                # Asked for {"topics": {...}} the model as often returns the map
                # on its own, the verse numbers at the top level. Both say the
                # same thing, and rejecting one of them would throw away a good
                # answer over its wrapping.
                body_of = got.get("topics") if isinstance(got.get("topics"), dict) else got
                lines = {str(k): str(v)[:300] for k, v in (body_of or {}).items()
                         if isinstance(v, str) and v.strip() and str(k) in d["verses"]}
            except Exception as e:                                # noqa: BLE001
                print(f"  {d['book']} {d['chapter']}: FAILED {e}", file=sys.stderr)
                continue
            if not lines:
                print(f"  {d['book']} {d['chapter']}: nothing usable came back", file=sys.stderr)
                continue
            missing = len(verses) - len(lines)
            if missing:
                short += 1
                print(f"  {d['book']} {d['chapter']}: {missing} of {len(verses)} verses got no line",
                      file=sys.stderr)
            fh.write(json.dumps({"book": d["book"], "chapter": d["chapter"], "topics": lines},
                                ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 10 == 0 or n == len(todo):
                el = time.time() - t0
                left = (len(todo) - n) * el / n / 3600
                print(f"  {n}/{len(todo)} chapters [{el / n:.1f}s each, {el / 60:.0f} min, "
                      f"{left:.1f} h left]", flush=True)
    print(f"topics done: {n} chapters written"
          + (f", {short} of them short of a line for every verse" if short else ""))


def show(book, ch):
    """Read back what was written for one chapter, beside the verses themselves."""
    for line in (TOPICS.read_text(encoding="utf-8").splitlines() if TOPICS.exists() else []):
        if not line.strip():
            continue
        r = json.loads(line)
        if r["book"].lower() == book.lower() and int(r["chapter"]) == ch:
            f = EN / f"{slug(r['book'])}_{ch:02d}.json"
            said = json.loads(f.read_text(encoding="utf-8"))["verses"] if f.exists() else {}
            for v in sorted(r["topics"], key=int):
                print(f"\n{r['book']} {ch}:{v}")
                print(f"  text   {said.get(v, '')[:150]}")
                print(f"  line   {r['topics'][v]}")
            return
    print(f"no lines written for {book} {ch} yet")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=0, help="stop after this many chapters")
    ap.add_argument("--redo", action="store_true", help="write every chapter again, ignoring what is done")
    ap.add_argument("--only", nargs=2, metavar=("BOOK", "CHAPTER"), help="write just this chapter")
    ap.add_argument("--show", nargs=2, metavar=("BOOK", "CHAPTER"), help="print what was written for one chapter")
    a = ap.parse_args()
    if a.show:
        return show(a.show[0], int(a.show[1]))
    run(a.limit, a.redo, (a.only[0], int(a.only[1])) if a.only else None)


if __name__ == "__main__":
    main()
