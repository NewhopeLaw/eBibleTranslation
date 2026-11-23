#!/usr/bin/env python3
"""How well search by meaning finds what a reader describes, measured.

    python scripts/search_test.py                     # every language with questions, verses and passages
    python scripts/search_test.py --langs th --misses # one language, and the questions it got wrong
    python scripts/search_test.py --compare           # verses alone against verses with passages

The questions are targets/search/tests.jsonl, one a line:

    {"id": "s001", "lang": "th", "q": "...", "refs": ["Daniel 6:17-24"], "by": "hand"}

Each says what a reader might type and where the answer is, in this project's
verse numbering (the Hebrew, so Jonah's fish is 2:1). A question is found when
any of the first k verses search returns falls inside one of its refs. The
first hundred, in English, Thai, Spanish and Chinese, were written by hand
and each ref was checked against the text; "by" says who wrote a question, so
those made by the model on the PC (scripts/make_search_tests.py) can be told
apart, and scored apart.

The search is the phone's: the int8 encoder in site/model/, the projection,
the verse vectors and the passage vectors, read from the same files the APK
carries, and combined the way Meaning.java combines them. Eight questions
were enough to see the model beat the table in Thai; they were not enough to
tell a small change from luck, which is what this is for.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS                                          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "targets" / "search" / "tests.jsonl"
KS = (1, 5, 10)
REF = re.compile(r"^(.+?) (\d+):(\d+)(?:-(?:(\d+):)?(\d+))?$")
# What Meaning.java takes off a passage's score before it lifts its verses,
# kept here so the two cannot drift. Measured with --sweep on the hand-written
# questions, 0 and 0.02 found the same (English right first 43% and 42%), but
# at 0 a question about nothing - "wifi password" - rose to 0.511 on some
# passage and over the page's floor of 0.5 (MODELFLOOR in build_site.py),
# where verses alone left it at 0.365. 0.02 keeps it under.
STORY_GAP = 0.02


def ranges(refs):
    """'Job 1:13-2:10' -> [(1018001013, 1018002010)] as verse ids."""
    num = {m["name"]: m["num"] for m in BOOKS.values()}
    out = []
    for r in refs:
        m = REF.match(r.strip())
        if not m or m.group(1) not in num:
            raise SystemExit(f"cannot read the ref {r!r}")
        b, c, v, c2, v2 = m.groups()
        base = num[b] * 1000000
        lo = base + int(c) * 1000 + int(v)
        hi = base + int(c2 or c) * 1000 + int(v2 or v)
        out.append((lo, hi))
    return out


def ranked(qv, ids, vv, story, gap, n=60, scores=False):
    """The verse ids search returns for one question, best first.

    Verses alone when story is None. Otherwise a passage that matches the
    question better than any of its own verses lifts its run as a block: the
    run's best verse rises to the passage's score less gap, and the others
    rise with it by the same amount, so they keep their order and their
    distance below it. The page shows what is near the top score, so a
    passage found this way shows its best few verses, not all thirty.
    """
    import numpy as np
    own = vv @ qv
    score = own.copy()
    if story is not None:
        lo, hi, sv = story
        ss = sv @ qv - gap
        # Only a passage scoring above the n-th verse can bring anything into
        # view; the rest are not spread over their verses at all.
        floor = np.partition(own, -n)[-n]
        start = np.searchsorted(ids, lo[ss > floor])
        end = np.searchsorted(ids, hi[ss > floor], side="right")
        for s_, a, b in zip(ss[ss > floor], start, end):
            if b <= a:
                continue
            lift = s_ - own[a:b].max()
            if lift > 0:
                np.maximum(score[a:b], own[a:b] + lift, out=score[a:b])
    top = np.argsort(-score)[:n]
    if scores:
        return [(float(score[i]), int(ids[i])) for i in top]
    return [int(ids[i]) for i in top]


def rank_of(got, want):
    for r, vid in enumerate(got, 1):
        if any(lo <= vid <= hi for lo, hi in want):
            return r
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", default="", help="comma list (default: every language with questions)")
    ap.add_argument("--by", default="", help="only questions written by this (hand, or the model's name)")
    ap.add_argument("--no-stories", action="store_true", help="the verses alone, as before passages")
    ap.add_argument("--compare", action="store_true", help="verses alone and with passages, side by side")
    ap.add_argument("--sweep", default="", help="comma list of gaps to try, e.g. 0,0.02,0.04")
    ap.add_argument("--english-stories", action="store_true",
                    help="every language against the English descriptions, as if none were translated")
    ap.add_argument("--misses", action="store_true", help="list the questions not found in the first 10")
    ap.add_argument("--json", default="", help="also write the scores to this file")
    a = ap.parse_args()

    import numpy as np
    from transformers import AutoTokenizer
    import build_encoder as E

    rows = [json.loads(ln) for ln in TESTS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    want_langs = [c.strip() for c in a.langs.split(",") if c.strip()]
    rows = [r for r in rows if (not want_langs or r["lang"] in want_langs) and (not a.by or r.get("by") == a.by)]
    if not rows:
        raise SystemExit("no questions match")
    tok = AutoTokenizer.from_pretrained(E.TEACHER)
    run, mu, proj = E.built(tok, np)
    # One question at a time, as the phone asks: the int8 model sets its scale
    # from what it is given at once, so a question embedded in a batch of 400
    # comes out a little different, and the scores here were not the phone's.
    q = (np.concatenate([run([E.QUERY + r["q"]], batch=1) for r in rows]) - mu) @ proj
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    story = {r["lang"]: E.read_stories(np, r["lang"]) for r in rows}
    story_en = E.read_stories(np) if a.english_stories else None

    if a.sweep:
        variants = [(f"gap {g}", float(g)) for g in a.sweep.split(",")]
    elif a.compare:
        variants = [("verses", None), ("+ passages", STORY_GAP)]
    else:
        variants = [("verses" if a.no_stories else "+ passages", None if a.no_stories else STORY_GAP)]
    if all(v is None for v in story.values()) and any(g is not None for _, g in variants):
        raise SystemExit("no passage vectors - run scripts/build_encoder.py --stories-only")

    langs = sorted({r["lang"] for r in rows}, key=lambda c: [r["lang"] for r in rows].index(c))
    vecs = {c: E.read_lang(c, np) for c in langs if (E.OUT / f"vecm_{c}.bin").exists()}
    result = {}
    print(f"{len(rows)} questions; found in the first 1 / 5 / 10, and the mean of 1/rank")
    for name, gap in variants:
        per = defaultdict(lambda: {"n": 0, **{k: 0 for k in KS}, "mrr": 0.0})
        missed = []
        for i, r in enumerate(rows):
            if r["lang"] not in vecs:
                continue
            ids, vv = vecs[r["lang"]]
            st = story_en if a.english_stories else story[r["lang"]]
            got = ranked(q[i], ids, vv, None if gap is None else st, gap or 0.0)
            rk = rank_of(got, ranges(r["refs"]))
            p = per[r["lang"]]
            p["n"] += 1
            for k in KS:
                p[k] += bool(rk and rk <= k)
            p["mrr"] += 1 / rk if rk else 0
            if not rk or rk > 10:
                missed.append((r, rk, got[:3]))
        print(f"\n{name}")
        tot = {"n": 0, **{k: 0 for k in KS}, "mrr": 0.0}
        for c in langs:
            if c not in per:
                print(f"  {c:4} no verse vectors built")
                continue
            p = per[c]
            for k in tot:
                tot[k] += p[k]
            print(f"  {c:4} {p['n']:4}   " + "  ".join(f"{p[k] / p['n']:5.0%}" for k in KS) + f"   {p['mrr'] / p['n']:.3f}")
        if len(per) > 1:
            print(f"  all  {tot['n']:4}   " + "  ".join(f"{tot[k] / tot['n']:5.0%}" for k in KS) + f"   {tot['mrr'] / tot['n']:.3f}")
        result[name] = {c: {str(k): v for k, v in p.items()} for c, p in per.items()}
        if a.misses:
            bynum = {m["num"]: m["name"] for m in BOOKS.values()}
            say = lambda v: f"{bynum.get(v // 1000000, '?')} {v // 1000 % 1000}:{v % 1000}"
            for r, rk, top in missed:
                print(f"    miss {r['lang']} {r['id']} rank {rk or '>60'}: {r['q']}  -> {', '.join(map(say, top))}"
                      f"  (want {'; '.join(r['refs'])})")
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
