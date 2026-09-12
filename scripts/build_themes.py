#!/usr/bin/env python3
"""Themes, found by the model from the text rather than taken from a tradition.

    python scripts/build_themes.py --chapters --limit 20    # phase 1 on a few chapters
    python scripts/build_themes.py --chapters               # phase 1, every chapter, resuming
    python scripts/build_themes.py --consolidate            # phase 2: one canonical list
    python scripts/build_themes.py --pack                   # -> site/morph/themes.js

The whole Bible is about 944,000 tokens and the model holds 40,960, so nothing
here asks it to read everything at once. Themes are built from the bottom up,
the way a reader builds them:

  1. Chapter by chapter (a chapter is ~2,300 tokens, so it fits many times
     over): what is this chapter about? Two to five themes, each with the
     verses that carry it and the words the chapter actually uses.
  2. Those labels — several thousand of them — are then folded into one
     canonical list, in batches, each batch measured against the list so far.
     A chapter theme either joins a theme that already exists or starts a new
     one.
  3. Packing writes the canonical themes with every passage under them.

Every theme cites the verses it came from, so a reader can check it against
the text. Themes are interpretation, not data: the reader labels them as the
model's reading, and they sit apart from the tagged layers.

    THEMES  = {id: [label, description, passages, vocabulary, [phrase, translit, gloss, why]]}
    CHTHEME = {"Book|ch": [[id, "v-v", note], ...]}
    THEMEWORD = {lexeme: [theme id, ...]}

The fourth field of a theme is the vocabulary its passages happen to use, ranked
by how much more often a lexeme stands there than across the Bible at large. It
is there to be read against James Barr's warning that a word is not a concept:
a theme runs on many unrelated words, and one word turns up under many themes.
The two tables let a reader see both rather than take it on trust.
"""
import argparse
import json
import re
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
EN = ROOT / "output" / "en" / "json"
NORM = ROOT / "sources" / "normalized"
MORPH = ROOT / "site" / "morph"
DIR = ROOT / "targets" / "themes"
CHAPTERS = DIR / "chapters.jsonl"
CANON = DIR / "canonical.json"
FACES = DIR / "faces.jsonl"

SYSTEM_CH = """You read one chapter of the Bible in its original language, with a translation under each verse, and say what it is about.

Reply with JSON only:
{"themes": [{"theme": "a short label, three to six words", "what": "one sentence saying what the chapter does with it", "verses": "the verses that carry it, as 3-9 or 12", "words": "two or three words the chapter itself uses for it"}]}

Rules:
- Two to five themes for a chapter. One is enough for a short or single-minded chapter.
- Label the theme from what this chapter says, in plain words. Do not reach for the standard headings of a tradition or a creed unless the chapter's own wording puts them there.
- Every theme must name the verses it comes from, and they must be verses of this chapter.
- Describe, do not preach. No application, no devotional comment, no doctrine the chapter does not state.
- The Hebrew, Aramaic or Greek is the text; the translation is help, not authority. Where the original says something the translation blurs, follow the original.
- "words" are words of the original that actually stand in the chapter, in their own script. They are evidence, not the theme itself: a theme is what the passage does, and one theme is usually carried by several unrelated words while one word serves several themes. Never define a theme as "the word X"."""

SYSTEM_FACE = """You give a theme its name in the language of the Bible itself.

You get a theme, the words its passages use most distinctively (Hebrew, Aramaic or Greek, with glosses), and a few of its passages.

Reply with JSON only:
{"phrase": "two to five words in the original script, as the text itself would put it", "translit": "a plain transliteration", "gloss": "the same phrase in two to five English words", "why": "one sentence: which passages put it this way"}

Rules:
- The phrase must be the language of the text, not a modern coinage: build it from words that actually stand in these passages, in a form the text uses.
- Prefer a phrase over a single word. A theme is not a word, and a one-word name will mislead. Only use one word if the text itself names the theme in one word.
- Hebrew or Aramaic for an Old Testament theme, Greek for a New Testament one. If the passages are on both sides, give the phrase in the language of the majority.
- Do not invent vocabulary, do not add vowel points you cannot see, and do not translate the phrase into the other original language."""

SYSTEM_MERGE = """You are folding chapter-level themes into one list of themes for the whole Bible.

You get the list of themes so far, numbered, and a batch of new chapter themes. For each new one, say which existing theme it belongs to, or that it starts a new one.

Reply with JSON only:
{"assign": {"1": 12, "2": "new: a short label for the new theme", "3": 4, ...}}

Rules:
- Join an existing theme whenever the new one is the same subject in other words. Prefer joining: the list should stay in the low hundreds, not thousands.
- Start a new theme only when nothing in the list covers it.
- A new label is three to six plain words, of the same kind as those already in the list."""


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


def phase_chapters(limit):
    T.WORK_JOB = "themes"
    DIR.mkdir(parents=True, exist_ok=True)
    done = set()
    if CHAPTERS.exists():
        for line in CHAPTERS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["book"], r["chapter"]))
    todo = [(m, f) for m, f in chapter_files()
            if (m["name"], int(f.stem.rsplit("_", 1)[1])) not in done]
    if limit:
        todo = todo[:limit]
    print(f"themes, chapter pass: {len(done)} chapters done, {len(todo)} to do")
    t0, n = time.time(), 0
    with CHAPTERS.open("a", encoding="utf-8") as fh:
        for meta, f in todo:
            d = json.loads(f.read_text(encoding="utf-8"))
            src = source_chapter(meta, d["chapter"])
            lang = "Greek" if meta["testament"] == "NT" else "Hebrew or Aramaic"
            body = "\n".join(
                (f"[{v}] {src[int(v)]}\n     {t}" if int(v) in src else f"[{v}] {t}")
                for v, t in sorted(d["verses"].items(), key=lambda kv: int(kv[0])))
            user = (f"{d['book']} {d['chapter']} — each verse in {lang}, with the translation under it\n\n"
                    f"{body}\n\nWhat is this chapter about?")
            try:
                got = call(SYSTEM_CH, user)
                themes = [t for t in (got.get("themes") or []) if isinstance(t, dict) and t.get("theme")]
            except Exception as e:                                # noqa: BLE001
                print(f"  {d['book']} {d['chapter']}: FAILED {e}", file=sys.stderr)
                continue
            fh.write(json.dumps({"book": d["book"], "chapter": d["chapter"],
                                 "themes": [{"theme": str(t.get("theme"))[:80], "what": str(t.get("what", ""))[:300],
                                             "verses": str(t.get("verses", ""))[:40], "words": str(t.get("words", ""))[:80]}
                                            for t in themes[:5]]}, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 20 == 0 or n == len(todo):
                el = time.time() - t0
                print(f"  {n}/{len(todo)} chapters [{el / n:.1f}s each, {el / 60:.0f} min]", flush=True)
    print(f"chapter pass done: {n} chapters")


def phase_consolidate(batch=30):
    T.WORK_JOB = "themes"
    rows =[json.loads(l) for l in CHAPTERS.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = []                                        # (book, chapter, theme dict)
    for r in rows:
        for t in r["themes"]:
            items.append((r["book"], r["chapter"], t))
    state = json.loads(CANON.read_text(encoding="utf-8")) if CANON.exists() else {"themes": [], "assigned": {}}
    themes, assigned = state["themes"], state["assigned"]
    todo = [(i, it) for i, it in enumerate(items) if str(i) not in assigned]
    print(f"themes, consolidation: {len(themes)} themes so far, {len(assigned)} of {len(items)} chapter themes placed")
    t0 = time.time()
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(themes)) or "(the list is empty)"
        newones = "\n".join(f"{k + 1}. {it[2]['theme']} — {it[2].get('what', '')[:120]} ({it[0]} {it[1]})"
                            for k, (_, it) in enumerate(chunk))
        try:
            got = call(SYSTEM_MERGE, f"THEMES SO FAR:\n{listing}\n\nNEW CHAPTER THEMES:\n{newones}\n\nPlace each.", 0.1)
            a = got.get("assign") or {}
        except Exception as e:                                    # noqa: BLE001
            print(f"  batch {start}: FAILED {e}", file=sys.stderr)
            continue
        for k, (idx, it) in enumerate(chunk, 1):
            val = a.get(str(k))
            if isinstance(val, (int, float)) and 1 <= int(val) <= len(themes):
                assigned[str(idx)] = int(val) - 1
            elif isinstance(val, str) and val.lower().startswith("new"):
                label = val.split(":", 1)[1].strip() if ":" in val else it[2]["theme"]
                themes.append(label[:60])
                assigned[str(idx)] = len(themes) - 1
            else:
                themes.append(it[2]["theme"][:60])
                assigned[str(idx)] = len(themes) - 1
        CANON.write_text(json.dumps({"themes": themes, "assigned": assigned}, ensure_ascii=False), encoding="utf-8")
        el = time.time() - t0
        print(f"  {len(assigned)}/{len(items)} placed, {len(themes)} themes [{el / 60:.0f} min]", flush=True)
    print(f"consolidation done: {len(themes)} themes over {len(assigned)} chapter themes")


def parse_verses(spec):
    """'3-9', '12', '1-4,7' -> the verse numbers it names."""
    out = []
    for part in re.split(r"[,;]", str(spec or "")):
        part = part.strip()
        m = re.match(r"^(\d+)\s*[-\u2013]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b >= a and b - a < 200:
                out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def theme_vocabulary(passages):
    """The lexemes a theme's passages use, ranked by how distinctive they are there.

    Evidence, not definition: a theme is not a word. What this shows is the
    breadth of vocabulary a theme runs on, and (through THEMEWORD) how one word
    serves several themes.
    """
    conc_f, lex_f = MORPH / "conc.js", MORPH / "lex.js"
    if not conc_f.exists() or not lex_f.exists():
        return {}, {}
    t = conc_f.read_text(encoding="utf-8")
    conc = json.loads(t[t.index("=") + 1:].rstrip().rstrip(";\n").rstrip(";"))
    t = lex_f.read_text(encoding="utf-8")
    lex = json.loads(t[t.index("LEX=") + 4:t.index(";\nMORPHX=")])
    num = {m["name"]: m["num"] for m in BOOKS.values()}
    verse_lex, total = defaultdict(set), defaultdict(int)
    for tag, refs in conc.items():
        for bn, ch, v, _ in refs:
            verse_lex[(bn, ch, v)].add(tag)
            total[tag] += 1
    grand = sum(total.values()) or 1
    out, byword = {}, defaultdict(set)
    for key, plist in passages.items():
        here, n = defaultdict(int), 0
        for book, ch, vspec, *_ in plist:          # faces pass passes a fourth field (the note)
            bn = num.get(book)
            if not bn:
                continue
            for v in parse_verses(vspec):
                for tag in verse_lex.get((bn, int(ch), v), ()):
                    here[tag] += 1
                    n += 1
        if not n:
            continue
        scored = []
        for tag, c in here.items():
            if c < 2 or tag not in lex:
                continue
            lift = (c / n) / max(1e-9, total[tag] / grand)
            if lift > 1.5:
                scored.append([tag, lex[tag][0], lex[tag][3], round(lift, 1), c])
        scored.sort(key=lambda x: -x[4] * x[3])
        out[key] = scored[:40]
        for row in out[key]:
            byword[row[0]].add(key)
    return out, {k: sorted(v) for k, v in byword.items()}


def phase_faces(limit):
    """Name each canonical theme in the language of the text, from its own words."""
    T.WORK_JOB = "theme-names"
    passages, themes = theme_passages_for_faces()
    vocab = theme_vocabulary(passages)[0]
    done = set()
    if FACES.exists():
        for line in FACES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    todo = [k for k, v in sorted(passages.items(), key=lambda kv: -len(kv[1])) if k not in done]
    if limit:
        todo = todo[:limit]
    print(f"theme names in the original: {len(done)} done, {len(todo)} to do")
    t0 = time.time()
    with FACES.open("a", encoding="utf-8") as fh:
        for n, key in enumerate(todo, 1):
            tid = int(key[1:])
            label = themes[tid] if tid < len(themes) else key
            words = vocab.get(key, [])[:18]
            plist = passages[key][:8]
            user = (f"Theme as read in English: {label}\n\n"
                    + "Its most distinctive words:\n"
                    + "\n".join(f"  {w[1]} — {w[2]}" for w in words)
                    + "\n\nSome of its passages:\n"
                    + "\n".join(f"  {b} {c}{':' + v if v else ''} — {w[:120]}" for b, c, v, w in plist)
                    + "\n\nName this theme in the language of the text.")
            try:
                got = call(SYSTEM_FACE, user, 0.1)
            except Exception as e:                                # noqa: BLE001
                print(f"  {label}: FAILED {e}", file=sys.stderr)
                continue
            rec = {"id": key, "label": label,
                   "phrase": str(got.get("phrase", ""))[:80], "translit": str(got.get("translit", ""))[:80],
                   "gloss": str(got.get("gloss", ""))[:80], "why": str(got.get("why", ""))[:240]}
            if not rec["phrase"]:
                continue
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {label}: {rec['phrase']} ({rec['gloss']}) [{n}/{len(todo)}, {(time.time() - t0) / n:.0f}s each]", flush=True)


def theme_passages_for_faces():
    rows = [json.loads(l) for l in CHAPTERS.read_text(encoding="utf-8").splitlines() if l.strip()] if CHAPTERS.exists() else []
    items = [(r["book"], r["chapter"], t) for r in rows for t in r["themes"]]
    state = json.loads(CANON.read_text(encoding="utf-8")) if CANON.exists() else {"themes": [], "assigned": {}}
    out = defaultdict(list)
    for i, (book, ch, t) in enumerate(items):
        tid = state["assigned"].get(str(i))
        if tid is None:
            continue
        out[f"t{tid:04d}"].append((book, ch, t.get("verses", ""), t.get("what", "")))
    return out, state["themes"]


def pack():
    rows = [json.loads(l) for l in CHAPTERS.read_text(encoding="utf-8").splitlines() if l.strip()] if CHAPTERS.exists() else []
    items = [(r["book"], r["chapter"], t) for r in rows for t in r["themes"]]
    state = json.loads(CANON.read_text(encoding="utf-8")) if CANON.exists() else {"themes": [], "assigned": {}}
    themes, assigned = state["themes"], state["assigned"]
    out, ch_index = {}, defaultdict(list)
    passages = defaultdict(list)
    whats = defaultdict(list)
    for i, (book, ch, t) in enumerate(items):
        tid = assigned.get(str(i))
        if tid is None:                                # not consolidated yet: stands on its own
            continue
        key = f"t{tid:04d}"
        passages[key].append([book, ch, t.get("verses", "")])
        whats[key].append(t.get("what", ""))
        ch_index[f"{book}|{ch}"].append([key, t.get("verses", ""), t.get("theme", "")])
    vocab, byword = theme_vocabulary(passages)
    faces = {}
    if FACES.exists():
        for line in FACES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                faces[r["id"]] = [r.get("phrase", ""), r.get("translit", ""), r.get("gloss", ""), r.get("why", "")]
    for key, plist in passages.items():
        tid = int(key[1:])
        out[key] = [themes[tid] if tid < len(themes) else key,
                    max(whats[key], key=len)[:240] if whats[key] else "",
                    sorted(plist, key=lambda p: (next((m["num"] for m in BOOKS.values() if m["name"] == p[0]), 99), p[1])),
                    vocab.get(key, []), faces.get(key, [])]
    body = ("THEMES=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "CHTHEME=" + json.dumps(ch_index, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "THEMEWORD=" + json.dumps(byword, ensure_ascii=False, separators=(",", ":")) + ";\n")
    MORPH.mkdir(parents=True, exist_ok=True)
    (MORPH / "themes.js").write_text(body, encoding="utf-8")
    manifest.record("themes", len(out), "themes", "what the chapters are about", "build_themes.py")
    print(f"themes: {len(out)} themes over {sum(len(v[2]) for v in out.values())} passages "
          f"from {len(rows)} chapters -> site/morph/themes.js")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", action="store_true", help="phase 1: read every chapter")
    ap.add_argument("--consolidate", action="store_true", help="phase 2: fold the labels into one list")
    ap.add_argument("--faces", action="store_true", help="phase 3: name each theme in the language of the text")
    ap.add_argument("--pack", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=30)
    a = ap.parse_args()
    if a.chapters:
        phase_chapters(a.limit)
    if a.consolidate:
        phase_consolidate(a.batch)
    if a.faces:
        phase_faces(a.limit)
    if a.pack or not (a.chapters or a.consolidate or a.faces):
        pack()


if __name__ == "__main__":
    main()
