#!/usr/bin/env python3
"""Translate our lexicon into the target languages.

    python scripts/translate_lexicon.py --lang zh          # Chinese, resuming
    python scripts/translate_lexicon.py --lang all --min-count 10
    python scripts/translate_lexicon.py --pack             # only rebuild site/morph/lexx_<lang>.js

The English entries in targets/lexicon/entries.jsonl (written by
build_lexicon.py from the concordance) are translated entry by entry, keeping
the structure: sense labels, definitions, the usage note, idiom meanings,
how near-synonyms differ, and the caveat. Headwords, references and the Hebrew
or Greek words themselves are never translated.

Translations append to targets/lexicon/<lang>.jsonl and pack into
site/morph/lexx_<lang>.js, which the reader loads when that language is shown.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                     # noqa: E402
from books import TARGETS, parse_targets                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "targets" / "lexicon"
MORPH = ROOT / "site" / "morph"

SYSTEM = """You translate dictionary entries for a Hebrew, Aramaic and Greek lexicon into {LANGUAGE}.

You get one entry as JSON. Reply with JSON of exactly the same shape, with every English text field translated into {LANGUAGE}, and nothing else changed.

Rules:
- Translate: "gloss", every "sense" and "definition", "usage", every idiom "meaning", every "difference", and "note".
- Do NOT translate or alter: "refs" (verse references), "phrase" and "word" (they are Hebrew or Greek and stay in their own script), and the JSON keys.
- Write the way a dictionary in {LANGUAGE} is written: compact, plain, no padding. Keep a gloss to a few words.
- Where {LANGUAGE} has a settled rendering for a biblical term, use it.
- Do not add senses, examples or commentary of your own."""

FIELDS = ("gloss", "senses", "usage", "idioms", "near", "note")


def call(system, user):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": 0.2},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())
    T.log_work(resp, time.time() - t0)
    return json.loads(resp.get("message", {}).get("content", "{}"))


def keep_structure(src, out):
    """Take the translated strings, but keep our references, phrases and words."""
    res = {"gloss": str(out.get("gloss") or src.get("gloss") or "")}
    res["senses"] = []
    for i, s in enumerate(src.get("senses", [])):
        t = (out.get("senses") or [{}] * (i + 1))[i] if i < len(out.get("senses") or []) else {}
        res["senses"].append({"sense": str(t.get("sense") or s.get("sense", "")),
                              "definition": str(t.get("definition") or s.get("definition", "")),
                              "refs": s.get("refs", [])})
    res["usage"] = str(out.get("usage") or "")
    res["idioms"] = []
    for i, d in enumerate(src.get("idioms", [])):
        t = (out.get("idioms") or [{}] * (i + 1))[i] if i < len(out.get("idioms") or []) else {}
        res["idioms"].append({"phrase": d.get("phrase", ""), "meaning": str(t.get("meaning") or d.get("meaning", "")), "refs": d.get("refs", [])})
    res["near"] = []
    for i, nd in enumerate(src.get("near", [])):
        t = (out.get("near") or [{}] * (i + 1))[i] if i < len(out.get("near") or []) else {}
        res["near"].append({"word": nd.get("word", ""), "difference": str(t.get("difference") or nd.get("difference", ""))})
    res["note"] = str(out.get("note") or "")
    return res


def pack(lang):
    f = DIR / f"{lang}.jsonl"
    lex = {}
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                lex[e["tag"]] = {k: e[k] for k in FIELDS if k in e}
    (MORPH / f"lexx_{lang}.js").write_text(f"LEXXT[{json.dumps(lang)}]=" + json.dumps(lex, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"  {lang}: packed {len(lex)} entries -> site/morph/lexx_{lang}.js")
    return len(lex)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="zh", help="target code, a comma list, or 'all'")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-count", type=int, default=1, help="only lexemes occurring at least this often")
    ap.add_argument("--pack", action="store_true")
    a = ap.parse_args()
    langs = parse_targets(a.lang)
    langs = [l for l in langs if l != "en"]
    if a.pack:
        for lang in langs:
            pack(lang)
        return
    src_file = DIR / "entries.jsonl"
    entries = [json.loads(l) for l in src_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    entries = [e for e in entries if e.get("count", 0) >= a.min_count]
    entries.sort(key=lambda e: -e.get("count", 0))
    for lang in langs:
        out_file = DIR / f"{lang}.jsonl"
        done = set()
        if out_file.exists():
            for line in out_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    done.add(json.loads(line)["tag"])
        todo = [e for e in entries if e["tag"] not in done]
        if a.limit:
            todo = todo[:a.limit]
        system = SYSTEM.replace("{LANGUAGE}", TARGETS[lang]["name"])
        T.WORK_JOB = f"lexicon-{lang}"
        print(f"{TARGETS[lang]['name']}: {len(done)} done, {len(todo)} to do")
        t0, n = time.time(), 0
        with out_file.open("a", encoding="utf-8") as fh:
            for e in todo:
                src = {k: e.get(k) for k in FIELDS}
                try:
                    got = call(system, json.dumps(src, ensure_ascii=False))
                    rec = keep_structure(src, got)
                except Exception as ex:                              # noqa: BLE001
                    print(f"  {e['tag']}: FAILED {ex}", file=sys.stderr)
                    continue
                rec["tag"] = e["tag"]
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n += 1
                if n % 20 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)} [{(time.time() - t0) / n:.1f}s each]")
        pack(lang)


if __name__ == "__main__":
    main()
