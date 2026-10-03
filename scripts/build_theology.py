#!/usr/bin/env python3
"""The two rungs above themes: what each book argues, and how a theme develops.

    python scripts/build_theology.py --books           # one argument per book, resuming
    python scripts/build_theology.py --trajectories    # one development per theme, resuming
    python scripts/build_theology.py --pack            # -> site/morph/theology.js

Both are built from the layer below, never from a published theology:

  * A book's argument is aggregated from the themes already read out of that
    book's chapters (scripts/build_themes.py), plus the book's shape. The model
    is asked for the sections, the line of thought, and what the book keeps
    returning to — each section naming its chapters.

  * A theme's trajectory takes that theme's passages in canonical order and
    asks where it begins, how it changes, where it comes to a head, and where
    passages pull against each other. Every stage must cite passages from the
    list it was given.

This is the reasoning rung, not a data rung: it is a reading, it is labelled as
one in the reader, and it cites what it is built on so a reader can disagree at
the step where they actually disagree. The tensions field exists so that
synthesis does not quietly paper over the places the text does not agree with
itself.

    BOOKARG = {book: [sections, argument, concerns]}
    TRAJ    = {theme id: [beginning, stages, culmination, tensions, unresolved]}
"""
import argparse
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                          # noqa: E402
import translate as T                                    # noqa: E402
from books import BOOKS, slug                            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MORPH = ROOT / "site" / "morph"
DIR = ROOT / "targets" / "themes"
CHAPTERS = DIR / "chapters.jsonl"
CANON = DIR / "canonical.json"
BOOKS_OUT = DIR / "books.jsonl"
TRAJ_OUT = DIR / "trajectories.jsonl"
NUM = {m["name"]: m["num"] for m in BOOKS.values()}

SYSTEM_BOOK = """You are given the themes already read out of every chapter of one biblical book, chapter by chapter, and nothing else.

Say what the book is doing, from that evidence.

Reply with JSON only:
{"sections": [{"section": "a short title", "chapters": "1-11", "what": "one sentence"}],
 "argument": "three to six sentences: the line of thought from the start of the book to its end",
 "concerns": ["the three to six things this book keeps returning to"]}

Rules:
- Build only on the chapter themes in front of you. Do not add episodes, doctrines or structures the list does not show.
- Sections must cover the whole book and name real chapter ranges.
- Write plainly, as a description of the book, not as preaching or as a creed.
- Where the book's own shape is disputed, describe the shape the themes actually show."""

SYSTEM_TRAJ = """You are given one theme and every passage in the Bible where it was found, in canonical order, each with a note on what that passage does with it.

Say how the theme develops across the canon, from that evidence.

Reply with JSON only:
{"beginning": "one or two sentences: where and how it first appears, with references",
 "stages": [{"stage": "a short label", "refs": "the passages, e.g. Gen 12; Exod 6", "what": "one or two sentences"}],
 "culmination": "one or two sentences on where it comes to a head, with references, or \\"\\" if it does not",
 "tensions": [{"tension": "one sentence on where passages pull against each other", "refs": "the passages on each side"}],
 "unresolved": "one sentence on what the text leaves open, or \\"\\""}

Rules:
- Three to six stages. Every stage and tension must cite passages from the list you were given, and no others.
- A stage is a change in what the text does with the theme, not a restatement of the theme.
- Record real tensions where the list shows them. Do not invent them, and do not smooth them away either.
- Describe what the passages say. Do not resolve them with a doctrine from outside them, and do not preach."""


def call(system, user, temp=0.2):
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


def chapter_rows():
    if not CHAPTERS.exists():
        return []
    return [json.loads(l) for l in CHAPTERS.read_text(encoding="utf-8").splitlines() if l.strip()]


def done_keys(path, key):
    out = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.add(json.loads(line)[key])
    return out


def phase_books(limit, min_share=0.9):
    T.WORK_JOB = "book-arguments"
    rows = chapter_rows()
    by_book = defaultdict(list)
    for r in rows:
        by_book[r["book"]].append(r)
    total_ch = {}
    for meta in BOOKS.values():
        total_ch[meta["name"]] = len(list((ROOT / "output" / "en" / "json").glob(f"{slug(meta['name'])}_*.json")))
    done = done_keys(BOOKS_OUT, "book")
    todo = [b for b in sorted(by_book, key=lambda b: NUM.get(b, 99))
            if b not in done and total_ch.get(b) and len(by_book[b]) >= min_share * total_ch[b]]
    if limit:
        todo = todo[:limit]
    print(f"book arguments: {len(done)} done, {len(todo)} ready "
          f"({len(by_book) - len(done) - len(todo)} books still being read chapter by chapter)")
    t0 = time.time()
    with BOOKS_OUT.open("a", encoding="utf-8") as fh:
        for n, book in enumerate(todo, 1):
            chs = sorted(by_book[book], key=lambda r: r["chapter"])
            lines = [f"ch {r['chapter']}: " + "; ".join(f"{t['theme']} ({t['verses']})" for t in r["themes"])
                     for r in chs]
            user = f"{book}, {len(chs)} chapters\n\n" + "\n".join(lines) + "\n\nWhat is this book doing?"
            try:
                got = call(SYSTEM_BOOK, user)
            except Exception as e:                                # noqa: BLE001
                print(f"  {book}: FAILED {e}", file=sys.stderr)
                continue
            rec = {"book": book,
                   "sections": [{"section": str(s.get("section", ""))[:80], "chapters": str(s.get("chapters", ""))[:24],
                                 "what": str(s.get("what", ""))[:240]}
                                for s in (got.get("sections") or [])[:12] if isinstance(s, dict)],
                   "argument": str(got.get("argument", ""))[:1200],
                   "concerns": [str(c)[:80] for c in (got.get("concerns") or [])[:8]]}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {book}: {len(rec['sections'])} sections, {len(rec['concerns'])} concerns "
                  f"[{n}/{len(todo)}, {(time.time() - t0) / n:.0f}s each]", flush=True)


def theme_passages():
    """-> {theme id: [(book, chapter, verses, note), ...]} in canonical order, and the labels."""
    rows = chapter_rows()
    items = [(r["book"], r["chapter"], t) for r in rows for t in r["themes"]]
    state = json.loads(CANON.read_text(encoding="utf-8")) if CANON.exists() else {"themes": [], "assigned": {}}
    themes, assigned = state["themes"], state["assigned"]
    out = defaultdict(list)
    for i, (book, ch, t) in enumerate(items):
        tid = assigned.get(str(i))
        if tid is None:
            continue
        out[f"t{tid:04d}"].append((book, ch, t.get("verses", ""), t.get("what", "")))
    for key in out:
        out[key].sort(key=lambda p: (NUM.get(p[0], 99), p[1]))
    return out, themes


def phase_trajectories(limit, min_passages=4):
    T.WORK_JOB = "trajectories"
    passages, themes = theme_passages()
    done = done_keys(TRAJ_OUT, "id")
    todo = [k for k, v in sorted(passages.items(), key=lambda kv: -len(kv[1]))
            if k not in done and len(v) >= min_passages]
    if limit:
        todo = todo[:limit]
    print(f"theme trajectories: {len(done)} done, {len(todo)} to do "
          f"(themes with at least {min_passages} passages)")
    t0 = time.time()
    with TRAJ_OUT.open("a", encoding="utf-8") as fh:
        for n, key in enumerate(todo, 1):
            tid = int(key[1:])
            label = themes[tid] if tid < len(themes) else key
            plist = passages[key][:160]
            lines = [f"{b} {c}{':' + v if v else ''} — {w[:150]}" for b, c, v, w in plist]
            user = (f'Theme: {label}\n{len(plist)} passages in canonical order\n\n' + "\n".join(lines)
                    + "\n\nHow does this theme develop?")
            try:
                got = call(SYSTEM_TRAJ, user)
            except Exception as e:                                # noqa: BLE001
                print(f"  {label}: FAILED {e}", file=sys.stderr)
                continue
            rec = {"id": key, "label": label, "passages": len(passages[key]),
                   "beginning": str(got.get("beginning", ""))[:500],
                   "stages": [{"stage": str(s.get("stage", ""))[:80], "refs": str(s.get("refs", ""))[:160],
                               "what": str(s.get("what", ""))[:400]}
                              for s in (got.get("stages") or [])[:8] if isinstance(s, dict)],
                   "culmination": str(got.get("culmination", ""))[:500],
                   "tensions": [{"tension": str(t.get("tension", ""))[:300], "refs": str(t.get("refs", ""))[:160]}
                                for t in (got.get("tensions") or [])[:6] if isinstance(t, dict)],
                   "unresolved": str(got.get("unresolved", ""))[:300]}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {label}: {len(rec['stages'])} stages, {len(rec['tensions'])} tensions "
                  f"[{n}/{len(todo)}, {(time.time() - t0) / n:.0f}s each]", flush=True)


def pack():
    bookarg = {}
    if BOOKS_OUT.exists():
        for line in BOOKS_OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                bookarg[r["book"]] = [r["sections"], r["argument"], r["concerns"]]
    traj = {}
    if TRAJ_OUT.exists():
        for line in TRAJ_OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                traj[r["id"]] = [r["beginning"], r["stages"], r["culmination"], r["tensions"], r["unresolved"]]
    body = ("BOOKARG=" + json.dumps(bookarg, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "TRAJ=" + json.dumps(traj, ensure_ascii=False, separators=(",", ":")) + ";\n")
    MORPH.mkdir(parents=True, exist_ok=True)
    (MORPH / "theology.js").write_text(body, encoding="utf-8")
    manifest.record("book-arguments", len(bookarg), "books", "what each book argues", "build_theology.py")
    manifest.record("trajectories", len(traj), "themes", "how a theme develops across the canon", "build_theology.py")
    print(f"theology: {len(bookarg)} book arguments, {len(traj)} theme trajectories -> site/morph/theology.js")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--trajectories", action="store_true")
    ap.add_argument("--pack", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-passages", type=int, default=4)
    a = ap.parse_args()
    DIR.mkdir(parents=True, exist_ok=True)
    if a.books:
        phase_books(a.limit)
    if a.trajectories:
        phase_trajectories(a.limit, a.min_passages)
    if a.pack or not (a.books or a.trajectories):
        pack()


if __name__ == "__main__":
    main()
