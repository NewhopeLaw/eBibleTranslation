#!/usr/bin/env python3
"""A second translation of every language, by Tencent's Hy-MT2, to set beside ours.

    python scripts/hy_translate.py --lang en --all          # English, from the Hebrew and the Greek
    python scripts/hy_translate.py --lang my --all          # Burmese, from our English
    python scripts/hy_translate.py --lang en Ps 23          # a chapter, or a range: Gen 1-3
    python scripts/hy_translate.py --list                   # which languages it writes, and how far

Hy-MT2 1.8B (Apache 2.0) is a model built only for translation: a sentence in,
the sentence in another language out, at a tenth of a second a verse. It is
not asked to replace anything. What it writes goes to versions/<lang>/hy-mt2/,
in the shape translate.py writes, so the two can be read side by side
(scripts/build_compare.py) and a reader can judge where a small translation
model is enough and where the chat model reading the whole chapter is not.

English is made from the originals, the way ours is, so the difference shows
where it is largest. Hy-MT2 was trained on modern Hebrew and has no Greek at
all, and on a first try it turned Psalm 23:1 into "A song for David ... I will
not fail to sing it". Every other language is made from our English, the
direction it was built for. Its own "reference the following translations"
instruction carries the chapter's names in the target language, from
targets/<lang>/names.map.json where one exists, so Moses is spelt as our own
translation spells him.

It runs through Ollama as hy-mt2:1.8b, made from models/hy-mt2/Modelfile:
Ollama's own reading of the GGUF's chat template loses the user and assistant
markers and the model answers "onse" to everything.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                              # noqa: E402
from books import BOOKS, TARGETS, slug, verse_lang                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL = "hy-mt2:1.8b"
ENGINE = "Hy-MT2 1.8B (Tencent), Q8_0"
VERSIONS = ROOT / "versions"
LOG_PATH = ROOT / "logs" / "hy.jsonl"
API = T.CONFIG["api_url"]

# Our targets that Hy-MT2 lists among its languages, by the name it knows them
# by. Hakka, Taiwanese, Easy Japanese and Sgaw Karen are not among them.
SUPPORTED = {"en": "English", "zh": "Simplified Chinese", "es": "Spanish", "ja": "Japanese", "th": "Thai",
             "yue": "Cantonese", "vi": "Vietnamese", "ko": "Korean", "fa": "Persian", "tr": "Turkish",
             "id": "Indonesian", "ms": "Malay", "my": "Burmese"}
SOURCE_NAME = {"hbo": "Biblical Hebrew", "arc": "Biblical Aramaic", "grc": "Koine Greek"}
# Where a language needs its register named. Burmese is the one we know of:
# NLLB slipped into spoken Burmese in one verse in eight (trials/my/report.md).
STYLE = {"my": " Use the formal literary Burmese of the Bible, not spoken Burmese."}

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def json_dir(lang):
    return VERSIONS / lang / "hy-mt2" / "json"


def ask(prompt):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False,
            "keep_alive": "30m", "options": {"num_predict": 1024, "num_ctx": 4096}}
    req = urllib.request.Request(API, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["message"]["content"].strip()


def names_for(lang, meta, ch, text):
    """The chapter's names in the target language, those this verse uses."""
    if lang == "en":
        return {}
    return {en: tr for en, tr in T.chapter_names(meta, ch, lang).items() if en in text}


def prompt_for(lang, text, source, names):
    """Hy-MT2's own templates: the terminology one when there are names to
    hold, its default otherwise; a source in an ancient language is named."""
    target = SUPPORTED[lang]
    head = ""
    if names:
        head = "Reference the following translations:\n" + "\n".join(
            f"{a} translates to {b}" for a, b in names.items()) + "\n\n"
    what = f"the following {SOURCE_NAME[source]} text" if source in SOURCE_NAME else "the following text"
    return (f"{head}Translate {what} into {target}, without additional explanation."
            f"{STYLE.get(lang, '')}\n\n{text}")


def chapter_sources(lang, meta, ch):
    """[(verse, text, source language)]: the originals for English, our English otherwise."""
    if lang == "en":
        src = json.loads((T.NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json").read_text(encoding="utf-8"))
        return [(v["v"], v["text"], verse_lang(meta, v)) for v in src["chapters"][ch]]
    f = T.json_dir("en") / f"{slug(meta['name'])}_{int(ch):02d}.json"
    if not f.exists():
        return []
    verses = json.loads(f.read_text(encoding="utf-8"))["verses"]
    return [(int(n), t, "en") for n, t in verses.items() if t.strip()]


SHOW = False      # --show: print every verse's source and translation as it is made


def translate_chapter(lang, code, ch, force=False):
    meta = BOOKS[code]
    out = json_dir(lang) / f"{slug(meta['name'])}_{int(ch):02d}.json"
    if out.exists() and not force:
        return None
    items = chapter_sources(lang, meta, ch)
    if not items:
        return None
    t0, verses, bad = time.time(), {}, []
    for n, text, source in items:
        names = names_for(lang, meta, ch, text)
        answer = ask(prompt_for(lang, text, source, names))
        # Answered in the wrong script, or not at all: once more before it is kept and named.
        if not answer or (lang != "en" and lang in T.TARGETS and not in_script(lang, answer)):
            answer = ask(prompt_for(lang, text, source, names)) or answer
            if not answer or not in_script(lang, answer):
                bad.append(n)
        verses[str(n)] = answer
        if SHOW:
            print(f"    {meta['name']} {ch}:{n}\n      {text}\n    → {answer}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"book": meta["name"], "chapter": int(ch), "lang": lang, "verses": verses,
                               "notes": "", "raw": "", "engine": ENGINE,
                               "from": "the Hebrew and Greek" if lang == "en" else "our English"},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    dt = time.time() - t0
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "book": meta["name"], "chapter": int(ch),
                             "lang": lang, "seconds": round(dt, 1), "verses": len(verses), "flagged": bad}) + "\n")
    print(f"  {meta['name']} {ch} [{lang}]: {len(verses)} vv, {dt:.0f}s" + (f" [WARN script={bad}]" if bad else ""),
          flush=True)
    return verses


SCRIPT = {"zh": r"[一-鿿]", "yue": r"[一-鿿]", "ja": r"[぀-ヿ一-鿿]",
          "ko": r"[가-힯]", "th": r"[฀-๿]", "fa": r"[؀-ۿ]", "my": r"[က-႟]"}


def in_script(lang, text):
    """True when an answer is in the target's own script (or the target writes Latin)."""
    pat = SCRIPT.get(lang)
    return bool(re.search(pat, text)) if pat else True


def chapters_of(code):
    meta = BOOKS[code]
    src = json.loads((T.NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json").read_text(encoding="utf-8"))
    return sorted(src["chapters"], key=int)


def done_count(lang):
    d = json_dir(lang)
    return len(list(d.glob("*.json"))) if d.exists() else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("book", nargs="?")
    ap.add_argument("chapters", nargs="?", help="a chapter or a range, e.g. 1-3")
    ap.add_argument("--lang", default="en", help=f"one of {', '.join(SUPPORTED)}, a comma list, or all")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", action="store_true", help="print each verse's source and translation as it goes")
    a = ap.parse_args()
    global SHOW
    SHOW = a.show
    if a.list:
        for lang in SUPPORTED:
            print(f"{lang:<5}{done_count(lang):>6} / 1189   {SUPPORTED[lang]}"
                  f"   from {'the Hebrew and Greek' if lang == 'en' else 'our English'}")
        return
    langs = list(SUPPORTED) if a.lang == "all" else [x.strip() for x in a.lang.split(",") if x.strip()]
    bad = [x for x in langs if x not in SUPPORTED]
    if bad:
        raise SystemExit(f"Hy-MT2 does not write {', '.join(bad)}; it writes {', '.join(SUPPORTED)}")
    if not (a.all or a.book):
        ap.error("give a book code or --all")
    books = sorted(BOOKS, key=lambda c: BOOKS[c]["num"]) if a.all else [a.book]
    for lang in langs:
        print(f"[{lang}] {MODEL}, from {'the Hebrew and Greek' if lang == 'en' else 'our English'}", flush=True)
        started, n = time.time(), 0
        for code in books:
            chs = chapters_of(code)
            if a.chapters and not a.all:
                lo, _, hi = a.chapters.partition("-")
                chs = [c for c in chs if int(lo) <= int(c) <= int(hi or lo)]
            for ch in chs:
                if translate_chapter(lang, code, ch, a.force) is not None:
                    n += 1
                    if n % 50 == 0:
                        print(f"-- {n} chapters, {(time.time() - started) / n:.1f}s per chapter, "
                              f"{done_count(lang)}/1189 written", flush=True)


if __name__ == "__main__":
    main()
