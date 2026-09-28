#!/usr/bin/env python3
"""Put the English into a language the chat model cannot write, with MADLAD-400.

    python scripts/mt_translate.py --lang ksw --all         # the whole Bible, resuming
    python scripts/mt_translate.py --lang ksw Gen 1-3       # a book, or some chapters
    python scripts/mt_translate.py --lang ksw --force John  # redo what is already there
    python scripts/mt_translate.py --lang ksw --model google/madlad400-3b-mt

translate.py asks the model in config.json to read the Hebrew and Greek and
write the target language. That works for a language the model has read a
great deal of; it does not work for Sgaw Karen, which it has hardly seen, and
a wrong answer in Myanmar script passes every check verify.py has. So a
target marked "mt" in TARGETS comes through here instead, through a
translation model: from the English translation we already have, verse by
verse, never from the originals. The result is a second-hand translation,
written by a machine and so far read by nobody who knows the language, and it
is presented as one - the TARGETS note says so and the reader shows it.

No model on hand can write Karen yet. NLLB-200 knows Burmese and Shan but no
Karen; MADLAD-400 lists ksw, and what it writes under that tag is Shan with
Burmese mixed in and, now and then, a memorised line of the Karen Bible that
means something else (README, "Target languages"). The driver is written for
MADLAD's kind of model - a tag in front of the text - and waits for one
trained on the Karen Bible; the checks below caught the Shan, which is why
they stay.

The output has the same shape as translate.py's, so verify.py, build_site.py
and build_apk.py take it up unchanged:

  output/<lang>/<Book>/<Book>_<NN>.md   readable chapter
  output/<lang>/json/<Book>_<NN>.json   {verses, notes, raw, engine}
  logs/mt.jsonl                         one line per chapter: timing, verses flagged

A translation model reads one sentence at a time and grows unreliable past a
couple of hundred words, so a long prose verse is cut at sentence ends and
the pieces joined back afterwards; lines of poetry are translated as lines.
The 10B model's weights take 22 GB of the GPU and four beams over a batch of
sixteen took the rest and more: Windows then quietly spills CUDA memory into
system RAM and a chapter that should take half a minute takes an hour. The
batch is six by default for that reason, and the study queue has to be
stopped first. Needs: pip install torch transformers sentencepiece.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Let the allocator grow segments instead of fragmenting; must be set before torch loads.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, TARGETS, slug                                      # noqa: E402
from translate import PIVOT_LANG, find_loop, json_dir, out_dir, render_md   # noqa: E402
from verify import SCRIPTS                                                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "mt.jsonl"
# The model taught Karen by scripts/train_karen.py, when it exists; MADLAD as
# it comes otherwise, which writes Shan (see above) and is only a fallback.
_TAUGHT = [m for m in (ROOT / "models" / "madlad-ksw-names", ROOT / "models" / "madlad-ksw") if (m / "config.json").exists()]
DEFAULT_MODEL = str(_TAUGHT[0]) if _TAUGHT else "google/madlad400-3b-mt"
PIECE_CHARS = 240            # a prose stretch longer than this is cut at sentence ends
SENTENCE_END = re.compile(r"[.!?;:][\"”’')\]]*\s+")

# A Windows console still defaults to a code page that cannot hold a Karen
# letter, and a verse printed for information must not be what stops a run.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def pieces(text):
    """Cut one verse into stretches the model translates well; return (pieces, glue).

    Lines are kept as lines - the English keeps poetry that way, and a
    Karen reader deserves the same shape. A long prose line is cut at
    sentence ends and regrouped up to PIECE_CHARS; one sentence longer than
    that goes whole, since cutting mid-sentence would cost more than it saves.
    `glue` says how to put the pieces back: "\\n" before a piece that starts a
    new line, " " before one that continues a line, "" before the first.
    """
    out, glue = [], []
    for li, line in enumerate(text.strip().split("\n")):
        line = line.strip()
        sep = "\n" if li else ""
        if not line:                       # a blank line: nothing to translate, the break stays
            if glue:
                glue[-1] = glue[-1] or sep
            continue
        if len(line) <= PIECE_CHARS:
            out.append(line)
            glue.append(sep)
            continue
        sentences, start = [], 0
        for m in SENTENCE_END.finditer(line):
            sentences.append(line[start:m.end()].strip())
            start = m.end()
        if line[start:].strip():
            sentences.append(line[start:].strip())
        group = ""
        for s in sentences:
            if group and len(group) + 1 + len(s) > PIECE_CHARS:
                out.append(group)
                glue.append(sep)
                sep = " "
                group = s
            else:
                group = f"{group} {s}".strip()
        if group:
            out.append(group)
            glue.append(sep)
    return out, glue


STUTTER = re.compile(r"(.{3,40}?)\1{2,}")   # a unit of 3-40 characters said three or more times running


def stutter(text):
    """The repeated unit when a text stammers, else None. translate.py's loop
    guard was tuned for a chat model's long tirades and wants 150 characters
    of repetition; a model still learning a language stammers on a short
    unit, "ThingThingThing", well under that. A refrain ("holy, holy, holy")
    is let through by its length: three short sayings fall under the stretch
    a stammer covers."""
    m = STUTTER.search(text)
    if m and len(m.group(0)) >= 24:
        return m.group(1)
    return None


def unstutter(text):
    """Cut a stammer down to one saying of its unit: the last resort when the
    retry stammers too. A verse that trails off is better than one that says
    a word forty times, and the chapter log names it."""
    return STUTTER.sub(lambda m: m.group(1), text)


def engine_label(model_name):
    """What the reader's footer calls the model: a taught model by what it was
    taught from, not by the folder it sits in."""
    name = str(model_name).replace(chr(92), "/").rstrip("/").split("/")[-1]
    if name.startswith("madlad-"):
        return f"MADLAD-400 3B taught from the Karen Bible ({name})"
    return name


def english_chapters(book):
    """Chapter numbers the English has for this book - the pivot decides what exists."""
    name = slug(BOOKS[book]["name"])
    return sorted(int(p.stem.rsplit("_", 1)[1]) for p in json_dir(PIVOT_LANG).glob(f"{name}_*.json"))


def english_verses(book, ch):
    name = slug(BOOKS[book]["name"])
    data = json.loads((json_dir(PIVOT_LANG) / f"{name}_{ch:02d}.json").read_text(encoding="utf-8"))
    return {int(n): t for n, t in data["verses"].items() if t.strip()}


class Translator:
    """MADLAD-400 is a T5: the target is named by a tag in front of the text,
    "<2ksw> In the beginning...", and there is nothing to force at the start
    of the answer."""

    def __init__(self, model_name, lang, batch):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.torch = torch
        self.batch = batch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.tag = f"<2{TARGETS[lang]['mt']}> "
        if self.tag.strip() not in self.tok.get_vocab():
            raise SystemExit(f"{model_name} has no tag {self.tag.strip()} - it does not write {TARGETS[lang]['name']}")
        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name, torch_dtype=dtype).to(self.device).eval()
        own = SCRIPTS.get(lang)
        self.own = re.compile(f"[{own[0]}]") if own else None
        self.generated = 0

    def _run(self, texts, **extra):
        enc = self.tok([self.tag + t for t in texts], return_tensors="pt", padding=True,
                       truncation=True, max_length=512).to(self.device)
        longest = int(enc["input_ids"].shape[1])
        # Karen in this tokenizer runs to two or three times the English's tokens,
        # and a cap that cuts the beams off leaves a truncated one winning.
        opts = dict(num_beams=4, max_new_tokens=min(384, longest * 3 + 30))
        opts.update(extra)
        with self.torch.no_grad():
            gen = self.model.generate(**enc, **opts)
        self.generated += int(gen.numel())
        return [t.strip() for t in self.tok.batch_decode(gen, skip_special_tokens=True)]

    def translate(self, texts):
        """Every text, in order, with the ones the model stumbled on tried again.

        Sorted by length inside the run so a batch pads little; put back in
        order before returning. A piece that came back with none of the
        target script, or that trails off repeating itself, gets a second
        try with the repetition curbed - the first setting is left plain
        because a curb on repeated n-grams also spoils honest refrains.
        """
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = [""] * len(texts)
        for i in range(0, len(order), self.batch):
            idx = order[i:i + self.batch]
            for k, t in zip(idx, self._run([texts[j] for j in idx])):
                out[k] = t
        retry = [i for i, t in enumerate(out) if texts[i].strip() and self.stumbled(t)]
        for i in range(0, len(retry), self.batch):
            idx = retry[i:i + self.batch]
            second = self._run([texts[j] for j in idx], num_beams=5, no_repeat_ngram_size=3, repetition_penalty=1.2)
            for k, t in zip(idx, second):
                if not self.stumbled(t) or len(t) < len(out[k]):
                    out[k] = t
        return [unstutter(t) if stutter(t) else t for t in out]

    def stumbled(self, text):
        if self.own and not self.own.search(text):
            return True
        return bool(find_loop(text)) or bool(stutter(text))


def translate_chapter(tr, lang, book, ch, model_name, force):
    meta = BOOKS[book]
    name = slug(meta["name"])
    md_path = out_dir(lang) / name / f"{name}_{ch:02d}.md"
    json_path = json_dir(lang) / f"{name}_{ch:02d}.json"
    if json_path.exists() and not force:
        return None
    verses = english_verses(book, ch)
    if not verses:
        print(f"  {meta['name']} {ch}: the English has no verses; skipped")
        return None
    t0 = time.time()
    flat, spans, glues = [], {}, {}
    for n in sorted(verses):
        parts, glue = pieces(verses[n])
        spans[n] = (len(flat), len(flat) + len(parts))
        glues[n] = glue
        flat.extend(parts)
    done = tr.translate(flat)
    # Give the cached blocks back after every chapter. Windows cannot grow CUDA
    # segments in place, so the allocator fragments over a long run until it
    # spills into system RAM and a chapter takes five times as long: Esther 1
    # took 113 s with 28 GB of "GPU" memory in RAM.
    if tr.device == "cuda":
        tr.torch.cuda.empty_cache()
    parsed = {}
    for n, (a, b) in spans.items():
        text = ""
        for piece, glue in zip(done[a:b], glues[n]):
            text += glue + piece
        parsed[n] = text.strip()
    bare = [n for n, t in parsed.items() if tr.own and not tr.own.search(t)]
    loops = [n for n, t in parsed.items() if find_loop(t)]
    dt = time.time() - t0

    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_md(meta, ch, parsed, ""), encoding="utf-8")
    json_path.write_text(json.dumps(
        {"book": meta["name"], "chapter": ch, "lang": lang,
         "verses": {str(k): v for k, v in sorted(parsed.items())},
         "notes": "", "raw": "", "engine": engine_label(model_name), "pivot": PIVOT_LANG},
        ensure_ascii=False, indent=1), encoding="utf-8")
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "book": meta["name"], "chapter": ch,
                            "lang": lang, "model": model_name, "seconds": round(dt, 1),
                            "verses": len(parsed), "pieces": len(flat), "bare": bare, "loop": loops}) + "\n")
    status = "OK" if not (bare or loops) else "WARN " + " ".join(
        s for s in (f"no-script={bare}" if bare else "", f"loop={loops}" if loops else "") if s)
    print(f"  {meta['name']} {ch} [{lang}]: {len(parsed)} vv in {len(flat)} pieces, {dt:.0f}s [{status}]", flush=True)
    return parsed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("book", nargs="?", help="OSIS book code, e.g. Gen")
    ap.add_argument("chapters", nargs="?", help="chapter or range, e.g. 1-3")
    ap.add_argument("--all", action="store_true", help="every book in order")
    ap.add_argument("--lang", required=True, help="a target marked mt in TARGETS, e.g. ksw")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch", type=int, default=6, help="pieces per model call (memory: see above)")
    ap.add_argument("--force", action="store_true", help="redo chapters already written")
    args = ap.parse_args()
    if not (args.all or args.book):
        ap.error("give a book code or --all")
    target = TARGETS.get(args.lang, {})
    if not target.get("mt"):
        raise SystemExit(f"{args.lang!r} is not a machine-translation target; TARGETS in scripts/books.py "
                         f"marks those with an \"mt\" code (known: "
                         f"{', '.join(c for c, t in TARGETS.items() if t.get('mt')) or 'none'})")
    if args.book and args.book not in BOOKS:
        raise SystemExit(f"unknown book {args.book!r}")

    books = sorted(BOOKS, key=lambda c: BOOKS[c]["num"]) if args.all else [args.book]
    jobs = []
    for book in books:
        chapters = english_chapters(book)
        if args.chapters and not args.all:
            a, _, b = args.chapters.partition("-")
            want = set(range(int(a), int(b or a) + 1))
            chapters = [c for c in chapters if c in want]
        jobs += [(book, c) for c in chapters]
    pending = [(b, c) for b, c in jobs
               if args.force or not (json_dir(args.lang) / f"{slug(BOOKS[b]['name'])}_{c:02d}.json").exists()]
    print(f"{args.lang} <- {PIVOT_LANG} via {args.model}: {len(jobs)} chapters asked, "
          f"{len(jobs) - len(pending)} already there, {len(pending)} to do", flush=True)
    if not pending:
        return
    tr = Translator(args.model, args.lang, args.batch)
    started, verses, flagged = time.time(), 0, 0
    for i, (book, ch) in enumerate(pending, 1):
        parsed = translate_chapter(tr, args.lang, book, ch, args.model, args.force)
        if parsed:
            verses += len(parsed)
            flagged += sum(1 for t in parsed.values() if tr.stumbled(t))
        if i % 25 == 0 or i == len(pending):
            rate = (time.time() - started) / i
            print(f"-- {i}/{len(pending)} chapters, {verses} verses, {flagged} flagged, "
                  f"{rate:.1f}s per chapter, about {rate * (len(pending) - i) / 60:.0f} min left", flush=True)


if __name__ == "__main__":
    main()
