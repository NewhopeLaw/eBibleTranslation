#!/usr/bin/env python3
"""More questions for scripts/search_test.py, written by the model on the PC.

    python scripts/make_search_tests.py --n 200                  # 200 passages, every finished language
    python scripts/make_search_tests.py --n 50 --langs th,ksw    # a few, in two languages
    python scripts/make_search_tests.py --train --n 3000         # questions to train on, not to test with

The hundred questions written by hand cover the stories everyone knows. A
reader also looks for the ones they half remember, and in languages nobody
here writes by hand - Karen above all. So this picks passages across the whole
Bible (the runs of verses the chapter themes mark, chosen at random but the
same every run), shows the model the verses themselves in the language, and
asks how a reader who remembers the passage vaguely would type it into a
search box: once in their own words, and once without any name from it.

It is shown the verses and never the chapter theme's description of them.
Search by meaning embeds those descriptions (scripts/build_encoder.py), and a
question written from one would be measured against itself.

Each question is appended to targets/search/tests.jsonl with "by" set to the
model's name, so search_test.py --by hand still scores the hand-written ones
alone. A passage already asked about in a language is skipped, so the job can
be stopped and run again. Like every job that asks the model, this runs on the
PC, with Ollama.

With --train the questions are for scripts/train_search.py instead, and go to
targets/search/train.jsonl. They are taken from the other end of the same
shuffled list, and never from a passage the hand-written questions ask about,
so no test question is about a passage the model was trained on.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                            # noqa: E402
from books import BOOKS, TARGETS                                 # noqa: E402
from build_encoder import STORIES                                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "targets" / "search" / "tests.jsonl"
TRAIN = ROOT / "targets" / "search" / "train.jsonl"

SYSTEM = """You help test a Bible app's search box. You are shown a passage of the Bible in {lang}.
Write two things a reader might type into the search box to find this passage again, in {lang},
the way an ordinary person types: short, plain, half-remembered, not a quotation.

- "own": in their own words; names from the passage are allowed.
- "noname": with no personal or place name from the passage at all, only what happens or what is said.

Each is at most fifteen words. Answer in JSON: {{"own": "...", "noname": "..."}}"""


def call(system, user):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": 8192, "temperature": 0.7},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.loads(r.read())
    T.log_work(resp, time.time() - t0)
    return json.loads(resp.get("message", {}).get("content", "{}"))


def passages():
    """[(book, chapter, first verse, last verse)] - the theme runs of three verses or more."""
    out = []
    for line in STORIES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        for t in r.get("themes") or []:
            for run in str(t.get("verses", "")).split(","):
                a, _, b = run.strip().partition("-")
                if a.strip().isdigit() and b.strip().isdigit() and int(b) - int(a) >= 2:
                    out.append((r["book"], int(r["chapter"]), int(a), min(int(b), int(a) + 14)))
    return sorted(set(out))


def text_of(lang, book, ch, lo, hi):
    f = ROOT / "output" / lang / "json" / f"{book.replace(' ', '_')}_{ch:02d}.json"
    if not f.exists():
        f = f.with_name(f"{book.replace(' ', '_')}_{ch:03d}.json")
    if not f.exists():
        return ""
    vs = json.loads(f.read_text(encoding="utf-8"))["verses"]
    return "\n".join(f"{v} {vs[str(v)]}" for v in range(lo, hi + 1) if str(v) in vs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=100, help="how many passages (default 100)")
    ap.add_argument("--langs", default="", help="comma list (default: every finished translation)")
    ap.add_argument("--train", action="store_true", help="questions to train on, written to train.jsonl")
    a = ap.parse_args()
    dest = TRAIN if a.train else TESTS
    whole = len(list((ROOT / "output" / "en" / "json").glob("*.json")))
    langs = [c.strip() for c in a.langs.split(",") if c.strip()] or [
        c for c in TARGETS if len(list((ROOT / "output" / c / "json").glob("*.json"))) >= whole]
    pool = passages()
    random.Random(7).shuffle(pool)
    if a.train:
        from search_test import ranges
        hold = []
        for ln in TESTS.read_text(encoding="utf-8").splitlines():
            if ln.strip() and json.loads(ln).get("by") == "hand":
                hold += ranges(json.loads(ln)["refs"])
        num = {m["name"]: m["num"] for m in BOOKS.values()}
        near = lambda b, c, lo, hi: any(num[b] * 1000000 + c * 1000 + lo <= y and x <= num[b] * 1000000 + c * 1000 + hi
                                        for x, y in hold)
        pick = [p for p in reversed(pool) if not near(*p)][:a.n]
    else:
        pick = pool[:a.n]
    have = set()
    if dest.exists():
        for ln in dest.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                have.add((r["lang"], r["id"].rsplit("-", 1)[0]))
    name = T.CONFIG["model"]
    made = 0
    for lang in langs:
        sys_ = SYSTEM.format(lang=TARGETS[lang]["name"])
        for book, ch, lo, hi in pick:
            pid = f"m-{book.replace(' ', '_')}-{ch}-{lo}"
            if (lang, pid) in have:
                continue
            body = text_of(lang, book, ch, lo, hi)
            if not body:
                continue
            try:
                got = call(sys_, body)
            except Exception as e:                                # noqa: BLE001 - one bad answer skips one passage
                print(f"  {lang} {book} {ch}:{lo}-{hi}: {e}", file=sys.stderr)
                continue
            ref = f"{book} {ch}:{lo}-{hi}"
            with open(dest, "a", encoding="utf-8", newline="\n") as f:
                for kind in ("own", "noname"):
                    q = str(got.get(kind, "")).strip()
                    if q:
                        f.write(json.dumps({"id": f"{pid}-{kind}", "lang": lang, "q": q, "refs": [ref], "by": name},
                                           ensure_ascii=False) + "\n")
                        made += 1
            print(f"  {lang} {ref}: {got.get('own', '')} | {got.get('noname', '')}", flush=True)
    print(f"{made} questions added to {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
