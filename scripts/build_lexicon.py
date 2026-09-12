#!/usr/bin/env python3
"""Our own Hebrew / Aramaic / Greek lexicon, written by the model from the text itself.

    python scripts/build_lexicon.py --limit 20        # pilot: the 20 most frequent lexemes
    python scripts/build_lexicon.py                   # every lexeme, resuming
    python scripts/build_lexicon.py --min-count 5     # skip the rarest
    python scripts/build_lexicon.py --pack            # only rebuild site/morph/lexx.js from what exists

For each lexeme the concordance (site/morph/conc.js, built from the STEPBible
tags) supplies every occurrence. A sample spread across the canon — Torah,
Former Prophets, Latter Prophets, Writings; Gospels, Acts, Paul, General — is
put in front of qwen3:32b with the verse text and the parsing of the word in
each verse, and the model writes the entry: senses with glosses and anchor
verses, how the usage shifts across the corpus, idioms, near-synonyms, and a
note on what is uncertain. Nothing from any existing dictionary is supplied.

Entries accumulate in targets/lexicon/entries.jsonl (one JSON object per line,
resumable and appendable); --pack writes site/morph/lexx.js for the reader.
"""
import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                    # noqa: E402  (same Ollama call, config, retries)
import manifest                                       # noqa: E402
from books import BOOKS, slug                            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MORPH = ROOT / "site" / "morph"
OUT_DIR = ROOT / "targets" / "lexicon"
ENTRIES = OUT_DIR / "entries.jsonl"
NORM = ROOT / "sources" / "normalized"

NAME = {m["num"]: m["name"] for m in BOOKS.values()}
NUM = {m["name"]: m["num"] for m in BOOKS.values()}
SECTIONS = [("Torah", 1, 5), ("Former Prophets / history", 6, 17), ("Writings", 18, 22),
            ("Latter Prophets", 23, 39), ("Gospels and Acts", 40, 44), ("Paul", 45, 57), ("General letters and Revelation", 58, 66)]
PER_SECTION = 4
MAX_CITED = 18

SYSTEM = """You are a lexicographer of Biblical Hebrew, Aramaic and Koine Greek. You are given one lexeme and a sample of the verses where it occurs, each with the form used there and its parsing.

Write the lexicon entry from this evidence alone. Do not reproduce or paraphrase any published dictionary, and do not rely on a remembered gloss where the citations disagree with it: the citations are the evidence.

Reply with JSON only, in this shape:
{"gloss": "two or three words", "senses": [{"sense": "short label", "definition": "one sentence", "refs": ["Gen 1:1", "Isa 40:3"]}], "usage": "one or two sentences on how the use shifts across the corpus, or \\"\\" if it does not", "idioms": [{"phrase": "the Hebrew or Greek phrase", "meaning": "what it means", "refs": ["1 Sam 3:10"]}], "near": [{"word": "the other lexeme in its own script", "difference": "how it differs"}], "note": "what is uncertain or disputed, or \\"\\""}

Rules:
- Senses come from the citations: order them by how common they are in the sample, most common first. Two to five senses for a common word, one for a narrow one.
- Every sense must cite at least one reference, and every reference must be one of the verses supplied.
- "idioms" and "near" may be empty lists. Never invent a reference or a form.
- Write in plain English. No theology, no devotional comment, no etymology you cannot see in the citations."""


def load_js(path, var):
    s = path.read_text(encoding="utf-8")
    i = s.index(var + "=") + len(var) + 1
    j = s.index(";\n" + ("MORPHX=" if var == "LEX" else ""), i) if var == "LEX" else len(s.rstrip().rstrip(";"))
    return json.loads(s[i:j] if var == "LEX" else s[i:].rstrip().rstrip(";\n").rstrip(";"))


def verse_text(cache, book_num, ch, v):
    name = NAME[book_num]
    if name not in cache:
        f = NORM / f"{book_num:02d}_{slug(name)}.json"
        cache[name] = json.loads(f.read_text(encoding="utf-8"))["chapters"] if f.exists() else {}
    for rec in cache[name].get(str(ch), []):
        if rec["v"] == v:
            return rec["text"]
    return ""


def sample_refs(refs):
    """Up to PER_SECTION occurrences from each part of the canon, in canonical order."""
    by_sec = defaultdict(list)
    for r in refs:
        for label, lo, hi in SECTIONS:
            if lo <= r[0] <= hi:
                by_sec[label].append(r)
                break
    out = []
    for label, _, _ in SECTIONS:
        lst = by_sec.get(label, [])
        if not lst:
            continue
        step = max(1, len(lst) // PER_SECTION)
        out += [(label, r) for r in lst[::step][:PER_SECTION]]
    return out[:MAX_CITED]


def build_prompt(tag, headword, refs, morph_cache, vcache):
    lines = []
    for label, (bn, ch, v, idx) in refs:
        text = verse_text(vcache, bn, ch, v)
        if not text:
            continue
        name = NAME[bn]
        mm = morph_cache.get(name)
        if mm is None:
            f = MORPH / f"{slug(name)}.js"
            s = f.read_text(encoding="utf-8") if f.exists() else "={}"
            mm = morph_cache[name] = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";\n").rstrip(";"))
        w = ((mm.get(str(ch)) or {}).get(str(v)) or [None] * (idx + 1))[idx] if mm else None
        form = re.findall(r"[\w֐-׿Ͱ-Ͽἀ-῿']+", text)
        surface = form[idx] if idx < len(form) else ""
        parse = (w[1] if w else "") or ""
        lines.append(f"{name} {ch}:{v} [{label}] — form {surface} ({parse})\n    {text}")
    return (f"Lexeme: {headword}   (tag {tag}, {len(lines)} of its occurrences shown, {len(refs)} sampled from the whole text)\n\n"
            + "\n".join(lines) + "\n\nWrite the entry as JSON.")


def call_model(system, user):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": 0.2},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    import urllib.request
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())
    return resp.get("message", {}).get("content", ""), resp


def clean(entry, allowed):
    """Keep only references the model was actually shown."""
    ok = set(allowed)

    def filt(refs):
        return [r for r in refs if r in ok]
    entry["senses"] = [s for s in entry.get("senses", []) if isinstance(s, dict) and (s.setdefault("refs", []) or True)
                       and (s.update(refs=filt(s.get("refs", []))) or s["refs"])]
    entry["idioms"] = [i for i in entry.get("idioms", []) if isinstance(i, dict) and (i.update(refs=filt(i.get("refs", []))) or i.get("refs"))]
    entry["near"] = [n for n in entry.get("near", []) if isinstance(n, dict) and n.get("word")]
    for k in ("gloss", "usage", "note"):
        entry[k] = str(entry.get(k) or "").strip()
    return entry


def pack():
    lex = {}
    if ENTRIES.exists():
        for line in ENTRIES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                lex[e["tag"]] = {k: e[k] for k in ("headword", "gloss", "senses", "usage", "idioms", "near", "note", "count") if k in e}
    (MORPH / "lexx.js").write_text("LEXX=" + json.dumps(lex, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    manifest.record("lexicon", len(lex), "entries", "our own lexicon, written from the text", "build_lexicon.py")
    print(f"packed {len(lex)} entries -> site/morph/lexx.js")
    return lex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new entries")
    ap.add_argument("--min-count", type=int, default=1, help="skip lexemes occurring fewer times")
    ap.add_argument("--pack", action="store_true", help="only rebuild site/morph/lexx.js")
    ap.add_argument("--force", action="store_true", help="rewrite entries that already exist")
    ap.add_argument("--tag", default="", help="comma-separated tags to do first (e.g. H2617,G3056)")
    a = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if a.pack:
        pack()
        return
    conc = load_js(MORPH / "conc.js", "CONC")
    brief = load_js(MORPH / "lex.js", "LEX")          # headwords only, so the model sees the word in its own script
    done = set()
    if ENTRIES.exists():
        for line in ENTRIES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["tag"])
    todo = sorted(((len(refs), tag) for tag, refs in conc.items() if len(refs) >= a.min_count), reverse=True)
    todo = [(n, t) for n, t in todo if a.force or t not in done]
    if a.tag:
        want = [t.strip() for t in a.tag.split(",") if t.strip()]
        todo = [(len(conc.get(t, [])), t) for t in want if t in conc]
    if a.limit:
        todo = todo[:a.limit]
    print(f"lexicon: {len(done)} entries written, {len(todo)} to do (model {T.CONFIG['model']})")
    morph_cache, vcache, t0, n = {}, {}, time.time(), 0
    with ENTRIES.open("a", encoding="utf-8") as fh:
        for count, tag in todo:
            head = (brief.get(tag) or ["", "", "", ""])[0] or tag
            refs = sample_refs(conc[tag])
            prompt = build_prompt(tag, head, refs, morph_cache, vcache)
            allowed = [f"{NAME[r[0]]} {r[1]}:{r[2]}" for _, r in refs]
            allowed += [f"{NAME[r[0]].replace('1 ', '1').replace('2 ', '2')} {r[1]}:{r[2]}" for _, r in refs]
            try:
                raw, resp = call_model(SYSTEM, prompt)
                entry = clean(json.loads(raw), allowed)
            except Exception as e:                                   # noqa: BLE001 — keep going, resume skips what is written
                print(f"  {tag} ({head}): FAILED {e}", file=sys.stderr)
                continue
            entry.update(tag=tag, headword=head, count=count, model=T.CONFIG["model"],
                         seconds=round(resp.get("total_duration", 0) / 1e9, 1) or None)
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            print(f"  {tag} {head}: {len(entry.get('senses', []))} senses, {count} occurrences"
                  f" [{n}/{len(todo)}, {(time.time() - t0) / n:.0f}s each]")
    pack()


if __name__ == "__main__":
    main()
