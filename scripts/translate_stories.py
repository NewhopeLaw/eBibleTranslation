#!/usr/bin/env python3
"""The chapter themes' passage descriptions, in each language search reads.

    python scripts/translate_stories.py                    # every finished language, resuming
    python scripts/translate_stories.py --langs th,zh
    python scripts/translate_stories.py --langs th --limit 200    # a trial

Search by meaning embeds a description of each passage beside its verses
(scripts/build_encoder.py), so a reader who describes a story finds it. The
descriptions are the chapter themes', written in English. Measured with
scripts/search_test.py, English questions found the passage first far more
often with them; Thai, Spanish and Chinese questions gained nothing, because a
question and a description in two languages sit further apart than either does
from a verse in the question's own language. So each language gets the
descriptions in its own words.

Each language is written the way its Bible was: the chat model config.json
names for it (translate.py model_for), forty descriptions to a request; a
language marked "mt" (Karen, Burmese) through mt_translate.py's translation
model. Like every job that asks a model, this runs on the PC.

Written to targets/search/stories/<lang>.jsonl, one {"en", "tr"} a line, and
resumed from there: a description already translated is not asked again. Then
`python scripts/build_encoder.py --stories-only` makes vecm_stories_<lang>.bin.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                            # noqa: E402
from books import TARGETS                                        # noqa: E402
from build_encoder import STORY_TR, story_rows                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BATCH = 40

SYSTEM = """You translate short English descriptions of Bible passages into {lang}, for a Bible app's search.
Write each the way an ordinary {lang} reader would say it, keeping names as that language's Bibles spell them.
You get a JSON object {{"1": "...", "2": "...", ...}}. Answer with the same keys, each holding its translation,
and nothing else."""


def chat(lang, texts):
    import urllib.request
    payload = {"model": T.model_for(lang), "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": 8192, "temperature": 0.2},
               "messages": [{"role": "system", "content": SYSTEM.format(lang=TARGETS[lang]["name"])},
                            {"role": "user", "content": json.dumps({str(i + 1): t for i, t in enumerate(texts)},
                                                                   ensure_ascii=False)}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1200) as r:
        resp = json.loads(r.read())
    T.log_work(resp, time.time() - t0)
    got = json.loads(resp.get("message", {}).get("content", "{}"))
    # A description left out or answered in English is left untranslated, and
    # asked again on the next run, rather than written down wrong.
    return [str(got.get(str(i + 1), "")).strip() if str(got.get(str(i + 1), "")).strip() != t else ""
            for i, t in enumerate(texts)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", default="", help="comma list (default: every finished translation but English)")
    ap.add_argument("--limit", type=int, default=0, help="at most this many descriptions a language (a trial)")
    a = ap.parse_args()
    whole = len(list((ROOT / "output" / "en" / "json").glob("*.json")))
    langs = [c.strip() for c in a.langs.split(",") if c.strip()] or [
        c for c in TARGETS if c != "en" and len(list((ROOT / "output" / c / "json").glob("*.json"))) >= whole]
    texts = sorted({t for _, _, t in story_rows()})
    if a.limit:
        texts = texts[:a.limit]
    STORY_TR.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        out = STORY_TR / f"{lang}.jsonl"
        done = set()
        if out.exists():
            done = {json.loads(ln)["en"] for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()}
        todo = [t for t in texts if t not in done]
        print(f"{lang}: {len(texts) - len(todo)} done, {len(todo)} to go", flush=True)
        if not todo:
            continue
        mt = None
        if TARGETS[lang].get("mt"):
            import mt_translate as M
            name = M.default_model(lang)
            if not name:
                print(f"  {lang}: no translation model on hand, so its passages stay in English")
                continue
            mt = M.Translator(name, lang, batch=16)
        t0 = time.time()
        for b in range(0, len(todo), BATCH):
            part = todo[b:b + BATCH]
            try:
                tr = mt.translate(part) if mt else chat(lang, part)
            except Exception as e:                                # noqa: BLE001 - one bad batch is asked again next run
                print(f"  {lang}: batch {b // BATCH + 1} failed: {e}", file=sys.stderr)
                continue
            with open(out, "a", encoding="utf-8", newline="\n") as f:
                for en, t in zip(part, tr):
                    if t:
                        f.write(json.dumps({"en": en, "tr": t}, ensure_ascii=False) + "\n")
            print(f"  {lang}: {min(b + BATCH, len(todo))}/{len(todo)} [{time.time() - t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()
