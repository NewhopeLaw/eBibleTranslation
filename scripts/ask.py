#!/usr/bin/env python3
"""The PC's search: the question goes to the model, and the text answers it.

    python scripts/ask.py "the writing on the wall at a feast"
    python scripts/ask.py --lang zh "那个离开九十九只羊去找一只的牧人"

The reader's own search is built to run on a phone with nothing behind it: an
index of letters, the topical lines, arithmetic. On this machine there is a
model behind it, and a reader who can only describe what they are looking for
- in a sentence, in any language - can be understood rather than matched.

What the model is not is a concordance. Asked where something is written, a
32B model names Daniel 5:5 correctly and Habakkuk 4:2 just as confidently, and
it numbers the Psalms the way the English Bibles do while this text keeps the
Masoretic count. So nothing it says from memory reaches the reader unchecked.
A search is three steps, and the model's word is never the last one:

  1. The model reads the question and answers with the passages it believes
     hold the answer, and with the words a verse like that would be described
     with - in English for the topical lines, and in the reader's own language
     for the translation.
  2. Code gathers the verses: every reference that exists in the source (one
     that does not is dropped, and said to have been), a verse either side of
     each to absorb the numbering, and the best matches for the words from the
     topical lines and the translation.
  3. The model is shown those verses as they stand in this translation and
     picks the ones that answer the question. It can only pick from the list,
     so every verse the reader is given exists, and was read before it was
     offered.

The answer is verse ids and where each came from. The reader draws them from
its own text, so nothing the model wrote is ever displayed as scripture.

Same model and num_ctx as the translation run, so Ollama does not reload it;
which also means a question waits its turn behind a chapter being translated.
Answers are kept under logs/ask/, which stays on this machine: what someone
searched their Bible for is not the repository's business.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, DEFAULT_TARGET, TARGETS, slug           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
NORM = ROOT / "sources" / "normalized"
TOPICS = ROOT / "targets" / "search" / "topics.jsonl"
CACHE = ROOT / "logs" / "ask"

NAMED_MAX = 12        # references taken from the model's memory
SPAN_MAX = 30         # verses of one reference: "Psalm 119" must not become the whole list
NAMED_VERSES = 70     # and of all of them together, which is what the model has to read through
FOUND_MAX = 40        # verses taken from the indexes
PICKS_MAX = 20
LOCK = threading.Lock()                     # one question at a time; the cache file stays whole

NOSPACE = re.compile(r"[㐀-鿿豈-﫿぀-ヿ฀-๿]")
WORD = re.compile(r"[\w֐-׿Ͱ-Ͽἀ-῿]+", re.UNICODE)
FURI = re.compile(r"\{([^{}|\]]+)\|[^{}\]]+[}\]]")               # furigana notation, as build_index.py strips it
STOPW = set(("a an the of on in at to and or for with by from is are was were be his her their its who "
             "that which this it as he she they them him not what when where how").split())

BYNUM = {m["num"]: m for m in BOOKS.values()}
# What the model may call a book. It is asked for the names used here, and
# mostly obliges; these are the ones it reaches for anyway.
ALIASES = {"psalm": "Psalms", "song of solomon": "Song of Songs", "canticles": "Song of Songs",
           "revelations": "Revelation", "qoheleth": "Ecclesiastes"}
BOOKNAME = {m["name"].lower(): m for m in BOOKS.values()}
for _a, _n in ALIASES.items():
    BOOKNAME[_a] = BOOKNAME[_n.lower()]


# ------------------------------------------------------------------ the text

def fold(term):
    term = unicodedata.normalize("NFD", term)
    term = "".join(c for c in term if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", term).lower()


def stem(w):
    """The reader's stemOf, so that the two searches fold English the same way."""
    if not re.fullmatch(r"[a-z]+", w):
        return w
    if len(w) > 4:
        for s in ("ing", "ed", "es", "s", "ly"):
            if w.endswith(s) and len(w) - len(s) >= 3:
                w = w[:-len(s)]
                break
        if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiouls":
            w = w[:-1]
    elif len(w) == 4 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w[:-1] if len(w) > 3 and w.endswith("e") else w


_shape = {}


def shape():
    """{verse id: True} for every verse of the source, which is what 'exists' means here."""
    if not _shape:
        for meta in BOOKS.values():
            f = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
            if not f.exists():
                continue
            for ch, verses in json.loads(f.read_text(encoding="utf-8"))["chapters"].items():
                for rec in verses:
                    _shape[meta["num"] * 1000000 + int(ch) * 1000 + rec["v"]] = True
    return _shape


_files = {}           # path -> (mtime, {verse id: text}); a chapter translated since is read again


def corpus(lang):
    """-> {verse id: text} for one translation, as it stands on disk now."""
    out = {}
    d = ROOT / "output" / lang / "json"
    if not d.exists():
        return out
    for f in d.glob("*.json"):
        mt = f.stat().st_mtime
        hit = _files.get(f)
        if not hit or hit[0] != mt:
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            meta = BOOKNAME.get(str(rec.get("book", "")).lower())
            verses = {}
            if meta:
                for v, text in (rec.get("verses") or {}).items():
                    if str(v).isdigit() and isinstance(text, str) and text.strip():
                        verses[meta["num"] * 1000000 + int(rec["chapter"]) * 1000 + int(v)] = FURI.sub(r"\1", text)
            hit = _files[f] = (mt, verses)
        out.update(hit[1])
    return out


_topics = {"mtime": None, "lines": {}}


def topics():
    """-> {verse id: the line build_topics.py wrote for it}"""
    if not TOPICS.exists():
        return {}
    mt = TOPICS.stat().st_mtime
    if _topics["mtime"] != mt:
        lines = {}
        for raw in TOPICS.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            meta = BOOKNAME.get(str(rec.get("book", "")).lower())
            if not meta:
                continue
            for v, said in (rec.get("topics") or {}).items():
                if str(v).isdigit() and isinstance(said, str):
                    lines[meta["num"] * 1000000 + int(rec["chapter"]) * 1000 + int(v)] = said
        _topics.update(mtime=mt, lines=lines)
    return _topics["lines"]


def ref_of(vid):
    return f"{BYNUM[vid // 1000000]['name']} {vid // 1000 % 1000}:{vid % 1000}"


# ------------------------------------------------------------ the references

REF = re.compile(r"^\s*([1-3]?\s*[A-Za-z][A-Za-z ]*?)\.?\s*(\d+)(?:\s*[:.]\s*(\d+))?"
                 r"(?:\s*[-–—]\s*(?:(\d+)\s*[:.]\s*)?(\d+))?\s*$")


def verses_of(ref):
    """'Luke 15:4-7' -> the verse ids of it that exist, or [] when it names nothing here.

    "Jonah 1:1-2:10" and a bare "Psalm 23" are passages too. A long one is read
    from its start as far as SPAN_MAX: the fish is seventeen verses into Jonah,
    and a reference cut to its opening lines never reached it.
    """
    m = REF.match(str(ref))
    if not m:
        return []
    meta = BOOKNAME.get(re.sub(r"\s+", " ", m.group(1)).strip().lower())
    if not meta:
        return []
    book, ch = meta["num"] * 1000000, int(m.group(2))
    if m.group(3) is None:                                  # "Psalm 23", or "Psalm 23-24"
        first, last = book + ch * 1000 + 1, book + int(m.group(5) or ch) * 1000 + 999
    else:
        first = book + ch * 1000 + int(m.group(3))
        last = book + int(m.group(4) or ch) * 1000 + int(m.group(5) or m.group(3))
    have = shape()
    if first not in have:
        return []
    vids = _order()
    at = bisect.bisect_left(vids, first)
    return [vid for vid in vids[at:at + SPAN_MAX] if vid <= last]


_sorted = []


def _order():
    if not _sorted:
        _sorted.extend(sorted(shape()))
    return _sorted


# ------------------------------------------------------------------ the model

PLAN_SYSTEM = """You help a reader find passages in the Bible. You are given what they typed into a search box. It may be a description, a question, a half-remembered story or a subject, in any language.

Reply with JSON only, of the form {"passages": [...], "english": [...], "words": [...]}.

- "passages": up to 12 places where the Bible says or tells what they are looking for, the most fitting first. Write each as the English book name, chapter and verse or verses: "Daniel 5:5", "Luke 15:4-7", "1 Samuel 17:49". If it is told in more than one book, name each telling. Name only passages you are sure of. Every one will be checked against the text, and an empty list is better than a guess.
- "english": up to 8 plain English words that a one-line description of such a verse would contain: the people, the things, what is done. Single words, no phrases, and only words that tell this passage from others - not "God", "king", "said", "people".
- "words": up to 6 words in the language named below that a Bible in that language would itself use in such a verse, single words as they would stand in the text. When the language is English, leave this list empty."""

PICK_SYSTEM = """You are given what a reader is looking for in the Bible, and a numbered list of verses as they stand in the reader's translation. The list was gathered widely and most of it is usually beside the point.

Reply with JSON only, of the form {"picks": [numbers]}: the numbers of the verses that are what the reader is looking for, the best first, at most 20.

Judge each verse by what its text says, not by its reference. Keep a verse only if someone who read it would say "yes, this is the passage" or "yes, this speaks to exactly that". A verse that shares a word or a mood with the question but is about something else is left out, and so is one from the same chapter that has moved on to other matters. Two or three right verses are a better answer than twenty loose ones. If no verse fits, reply {"picks": []}."""


class ModelError(Exception):
    pass


def chat(system, user):
    payload = {"model": CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": CONFIG["num_ctx"], "temperature": 0},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    rq = urllib.request.Request(CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=900) as r:           # may queue behind a running chapter
            content = json.loads(r.read()).get("message", {}).get("content", "")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as ex:
        raise ModelError(f"{CONFIG['model']} did not answer ({ex})")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
    return data if isinstance(data, dict) else {}


def strings(x, cap):
    return [s.strip() for s in (x if isinstance(x, list) else []) if isinstance(s, str) and s.strip()][:cap]


# ---------------------------------------------------------------- the indexes

def found_by_words(english, words, text, lang):
    """-> [(verse id, score)], best first: the verses the model's words point at.

    Each word counts for how rare it is, so that a verse with the wall and the
    feast stands above the thousand with a king in them. English words are
    looked for in the topical lines (and in the text, when that is English)
    with their endings folded; the reader's own words are looked for in the
    translation as they were written, by run for the scripts that do not space.
    """
    lines = topics()
    n = max(len(text), len(lines), 1)
    score = defaultdict(float)

    def count(hits):
        if hits and len(hits) < n / 4:                     # a word in a quarter of all verses tells nothing apart
            w = math.log(n / len(hits))
            for vid in hits:
                score[vid] += w

    stems = {stem(fold(w)) for e in english for w in WORD.findall(e)} - {stem(s) for s in STOPW}
    if stems:
        hits = defaultdict(set)
        for src in ([lines, text] if lang == "en" else [lines]):
            for vid, said in src.items():
                for w in WORD.findall(said):
                    s = stem(fold(w))
                    if s in stems:
                        hits[s].add(vid)
        for s in stems:
            count(hits[s])
    if lang != "en":
        for w in {fold(w) for w in words}:
            if NOSPACE.search(w):
                count({vid for vid, t in text.items() if w in t})
            elif len(w) > 2:
                rx = re.compile(r"(?<!\w)" + re.escape(w), re.U)      # a word, or the start of one: amor finds amoroso
                count({vid for vid, t in text.items() if rx.search(fold(t))})
    return sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:FOUND_MAX]


# ------------------------------------------------------------------- the search

def cache_path(lang):
    return CACHE / f"{lang}.json"


def ask(q, lang=DEFAULT_TARGET, fresh=False):
    """-> (payload, http status)."""
    q = re.sub(r"\s+", " ", str(q or "")).strip()
    if lang not in TARGETS:
        return {"error": "unknown language"}, 400
    if len(q) < 2 or len(q) > 400:
        return {"error": "a question of 2 to 400 characters"}, 400
    key = hashlib.sha1(json.dumps([fold(q), lang, CONFIG["model"]], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    with LOCK:
        path = cache_path(lang)
        try:
            cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except json.JSONDecodeError:
            cache = {}
        if key in cache and not fresh:
            return {**cache[key], "cached": True}, 200
        text = corpus(lang)
        if not text:
            return {"error": f"nothing is translated into {TARGETS[lang]['name']} yet"}, 409
        if lang != "en":
            # Where this language has not reached a verse yet, the model reads it
            # in English, and the reader is shown it in the original as ever.
            text = {**corpus("en"), **text}
        t0 = time.time()
        try:
            out = _search(q, lang, text)
        except ModelError as ex:
            return {"error": str(ex)}, 502
        out.update(q=q, lang=lang, model=CONFIG["model"], seconds=round(time.time() - t0, 1))
        cache[key] = out
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        return {**out, "cached": False}, 200


def _search(q, lang, text):
    name = TARGETS[lang]["name"]
    plan = chat(PLAN_SYSTEM, f"Language: {name}\n\nThe reader typed:\n{q}")
    passages = strings(plan.get("passages"), NAMED_MAX)
    english = strings(plan.get("english"), 8)
    words = [] if lang == "en" else strings(plan.get("words"), 6)
    if not (passages or english or words):
        # The plan came back empty or unreadable. The question's own words are
        # still worth looking with, and the second step still reads the verses.
        english = [w for w in WORD.findall(q) if fold(w) not in STOPW][:8]
        words = [] if lang == "en" else english

    # The model's references, in its order; then a verse either side of each,
    # because it counts the Psalms' titles and the ends of Joel and Malachi the
    # English way and this text does not. Then what the words found.
    have, order, origin, dropped = shape(), [], {}, []

    def take(vid, how):
        if vid in have and vid in text and vid not in origin:
            origin[vid] = how
            order.append(vid)

    named = []
    for ref in passages:
        vids = verses_of(ref)
        if vids:
            named.append(vids)
        else:
            dropped.append(ref)
    for vids in named:
        for vid in vids:
            if len(order) < NAMED_VERSES:
                take(vid, "named")
    for vids in named:
        take(vids[0] - 1, "beside")
        take(vids[-1] + 1, "beside")
    for vid, _ in found_by_words(english, words, text, lang):
        take(vid, "found")

    picks = []
    if order:
        listing = "\n".join(f"{i}. {ref_of(vid)} - {' '.join(text[vid].split())}" for i, vid in enumerate(order, 1))
        got = chat(PICK_SYSTEM, f"The reader is looking for:\n{q}\n\nThe verses ({name}):\n{listing}\n\n"
                                'Reply with JSON only: {"picks": [numbers]}')
        seen = set()
        for x in got.get("picks") if isinstance(got.get("picks"), list) else []:
            try:
                i = int(re.sub(r"\D", "", str(x)) or 0)
            except ValueError:
                continue
            if 1 <= i <= len(order) and i not in seen:
                seen.add(i)
                picks.append(order[i - 1])
    return {"hits": [{"id": vid, "from": origin[vid]} for vid in picks[:PICKS_MAX]],
            "read": len(order), "named": sum(1 for v in origin.values() if v == "named"),
            "dropped": dropped, "english": english, "words": words}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("question")
    ap.add_argument("--lang", default=DEFAULT_TARGET)
    ap.add_argument("--fresh", action="store_true", help="ask the model again even if this was asked before")
    a = ap.parse_args()
    out, code = ask(a.question, a.lang, a.fresh)
    if code != 200:
        raise SystemExit(out["error"])
    text = corpus(a.lang)
    print(f"{out['model']}, {out['seconds']}s{' (kept from before)' if out['cached'] else ''}: "
          f"read {out['read']} verses, {out['named']} of them named from memory; "
          f"looked with {', '.join(out['english'] + out['words']) or 'nothing'}")
    if out["dropped"]:
        print("named, but not in the text: " + ", ".join(out["dropped"]))
    for h in out["hits"]:
        print(f"  [{h['from']:6}] {ref_of(h['id'])}  {' '.join(text.get(h['id'], '').split())[:110]}")
    if not out["hits"]:
        print("  no verse was picked")


if __name__ == "__main__":
    main()
