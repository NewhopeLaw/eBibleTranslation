#!/usr/bin/env python3
"""Try a new language on a few chapters before any model is given the whole Bible.

    python scripts/trial_lang.py --lang my              # translate what is missing, then score
    python scripts/trial_lang.py --lang my --score      # score what is already written
    python scripts/trial_lang.py --lang my --models qwen3:32b --chapters Gen.1,John.1

The verifier can tell that every verse is there and in the right script. It
cannot tell good Burmese from broken Burmese: qwen3 wrote Burmese when asked
for Karen and every check passed. So before a language is started, each
candidate model writes the same handful of chapters (a narrative, a psalm, a
gospel), and they are measured against a published Bible in that language:

- chrF against each reference, verse by verse (characters, not words: Burmese
  and Thai do not put spaces between words, which makes BLEU meaningless).
  Two Bibles translated independently of each other score well short of 100
  against one another, so the number ranks candidates; it does not grade
  them.
- how much of each verse is in the language's own script, and for Burmese how
  many verses look like Zawgyi, the pre-Unicode encoding still common online,
  which a model trained on web text may have learned.
- verses missing or doubled, as translate.py reports them.

Shan has no published Bible to be had as text, so its plan measures two other
things instead: whether a verse is in Shan's own letters or in Burmese's, and
how much of our English is left when the chapter is put back into English
(see the plan below). MADLAD-400 as it comes is a candidate there too.

Each model writes into trials/<lang>/<model>/, never into output/, so a trial
is not mistaken for the translation. The chat models go through translate.py
exactly as a real run would (same prompt, glossary, names, retries). NLLB-200,
where it is on disk, translates our English, as a dedicated translation model
for the chat models to beat. The report is trials/<lang>/report.md.

Resumable like everything in the queue: a chapter already written is skipped.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                  # noqa: E402
from books import BOOKS, TARGETS, slug                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRIALS = ROOT / "trials"

# What each language is tried with. "reference" is a verse-per-line (VPL) file
# as eBible.org distributes it ("GEN 1:1 text"); "nllb" is NLLB-200's code.
PLANS = {
    "my": {"models": ["qwen3:32b", "qwen3.5:35b-a3b"],
           "chapters": ["Gen.1", "Ruth.1", "Ps.23", "John.1"],
           # Judson is the Bible Burmese churches grew up on; the Bible Society's
           # Common Language Bible (2005) is modern Burmese, closer to what the
           # rules ask for. A model near both is writing Bible Burmese.
           "references": [("Judson 1835", ROOT / "sources" / "mya-judson" / "myajvb_vpl.txt"),
                          ("Common Language 2005", ROOT / "sources" / "mya-cl" / "mya_vpl.txt")],
           "nllb": "mya_Mymr",
           "burmese": True,
           "script": (0x1000, 0x109F)},
    # Shan (Tai Yai). No Shan Bible could be had as text - Cushing's of 1892
    # is public domain and nowhere digitised, the Bible Society's and OMF's are
    # theirs - so there is no chrF here, and two things stand in for it.
    # One is the letters. Shan shares the Myanmar block with Burmese but not
    # its alphabet: it writes ၵ ၶ ၸ ၼ ၽ ႁ ဢ where Burmese writes က ခ စ န ဖ ဟ အ,
    # and marks its tones with ႇ ႈ ႉ ႊ. "in script %" cannot tell the two apart,
    # which is how Burmese once passed for Karen; a verse with Burmese's own
    # letters in it is not Shan, whatever the block.
    # The other is the way back: every candidate's Shan is put into English
    # again by NLLB-200 and measured against the English it started from. That
    # says whether the meaning survived, roughly, and it flatters NLLB's own
    # chapters, since the same model reads what it wrote. It ranks; a Shan
    # reader decides.
    # MADLAD-400 is a candidate as well as NLLB: it lists Shan, and what it
    # wrote under Karen's tag was Shan (README, "Target languages").
    "shn": {"models": ["qwen3:32b", "qwen3.5:35b-a3b"],
            "chapters": ["Gen.1", "Ruth.1", "Ps.23", "John.1"],
            "references": [],
            "nllb": "shn_Mymr",
            "madlad": "shn",
            "back": "shn_Mymr",
            "own": ("ၵ-ႊ", "Shan"),
            "foreign": ("ကခစဆညနဖဟအ", "Burmese"),
            "script": (0x1000, 0x109F)},
}
NLLB_DIR = ROOT / "models" / "nllb-200-distilled-1.3B"
MADLAD = "google/madlad400-3b-mt"      # from the Hugging Face cache, where train_karen.py left it

USFM = ("GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER "
        "LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL "
        "EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV").split()
# Older VPL files, Judson's among them, use the BibleWorks codes for some books.
VPL_ALIASES = {"SOL": "SNG", "EZE": "EZK", "JOE": "JOL", "NAH": "NAM", "MAR": "MRK", "JOH": "JHN",
               "PHI": "PHP", "JAM": "JAS", "1JO": "1JN", "2JO": "2JN", "3JO": "3JN"}

# Zawgyi keeps ေ and ြ in the order they are drawn, before the consonant;
# Unicode stores them after it. So one at the start of a word, or ေ followed by
# ြ, means the text was typed in Zawgyi, whatever font shows it.
ZAWGYI = re.compile(r"(^|[\s၊။])[ေျ]|ေျ")
# The spoken register, which the rules keep out of narrative. Not မှာ: both
# reference Bibles use it in narrative ("ရေမျက်နှာပြင်ပေါ်မှာ", Judson Gen 1:2).
SPOKEN = ("တယ်", "ရဲ့", "နေတာ")


def model_dir(lang, model):
    return TRIALS / lang / re.sub(r"[^\w.-]+", "-", model)


def chapters(plan):
    out = []
    for c in plan["chapters"]:
        code, ch = c.split(".")
        out.append((code, ch))
    return out


def trial_total(lang):
    """How many chapters the whole trial writes, and how many are written."""
    plan = PLANS[lang]
    who = (plan["models"] + (["nllb-200"] if NLLB_DIR.exists() else [])
           + (["madlad-400"] if plan.get("madlad") else []))
    want = [(m, slug(BOOKS[c]["name"]), ch) for m in who for c, ch in chapters(plan)]
    done = sum(1 for m, name, ch in want
               if (model_dir(lang, m) / lang / "json" / f"{name}_{int(ch):02d}.json").exists())
    return done, len(want)


# ------------------------------------------------------------------ writing
def run_chat_model(lang, model, plan):
    T.MODEL = model
    T.OUT_ROOT = model_dir(lang, model)
    system = T.build_system_prompt(lang)
    for code, ch in chapters(plan):
        meta = BOOKS[code]
        src = json.loads((T.NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json").read_text(encoding="utf-8"))
        T.translate_chapter(meta, ch, src["chapters"][ch], None, system, False, lang)


def load_mt(model_name, src_lang=None):
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(model_name, **({"src_lang": src_lang} if src_lang else {}))
    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_name, torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32).to(device).eval()

    def put(text, tag="", bos=None):
        enc = tok(tag + " ".join(text.split()), return_tensors="pt", truncation=True, max_length=400).to(device)
        with torch.no_grad():
            gen = model.generate(**enc, num_beams=4, max_new_tokens=min(512, enc["input_ids"].shape[1] * 4 + 30),
                                 **({"forced_bos_token_id": tok.convert_tokens_to_ids(bos)} if bos else {}))
        return tok.batch_decode(gen, skip_special_tokens=True)[0].strip()
    return tok, put


def unload():
    """Give the GPU back before the next model: two translation models and
    Ollama's do not fit side by side, and Windows spills into system RAM
    without saying so (mt_translate.py)."""
    import gc
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_mt(lang, plan, who, model_name, engine, tag="", bos=None):
    """A translation model from our English, one verse at a time, in
    translate.py's file shape. NLLB-200 is told the target by the first token
    of its answer (bos), MADLAD-400 by a tag in front of the text."""
    out = model_dir(lang, who) / lang / "json"
    todo = [(c, ch) for c, ch in chapters(plan)
            if not (out / f"{slug(BOOKS[c]['name'])}_{int(ch):02d}.json").exists()]
    if not todo:
        return
    tok, put = load_mt(model_name, "eng_Latn" if bos else None)
    if (bos or tag.strip()) not in tok.get_vocab():
        print(f"  {who}: no code {bos or tag.strip()}, so it does not write {TARGETS[lang]['name']}; left out")
        return
    out.mkdir(parents=True, exist_ok=True)
    for code, ch in todo:
        name = slug(BOOKS[code]["name"])
        en = json.loads((ROOT / "output" / "en" / "json" / f"{name}_{int(ch):02d}.json")
                        .read_text(encoding="utf-8"))["verses"]
        t0 = time.time()
        verses = {v: put(text, tag, bos) for v, text in en.items()}
        (out / f"{name}_{int(ch):02d}.json").write_text(json.dumps(
            {"book": BOOKS[code]["name"], "chapter": int(ch), "lang": lang, "verses": verses,
             "notes": "", "engine": engine},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {BOOKS[code]['name']} {ch} [{lang}] {who}: {len(verses)} vv, {time.time() - t0:.0f}s")
    del tok, put
    unload()


def run_back(lang, plan):
    """Every candidate's chapters put back into English by NLLB-200, beside
    the chapter (back/), for the report to measure against our English. The
    only reading of the meaning a trial can have where no published Bible in
    the language is to hand - see the Shan plan above for what it is worth."""
    todo = []
    for d in sorted(p for p in (TRIALS / lang).iterdir() if p.is_dir()):
        for f in sorted((d / lang / "json").glob("*.json")):
            back = d / lang / "back" / f.name
            if not back.exists():
                todo.append((d.name, f, back))
    if not todo:
        return
    _, put = load_mt(NLLB_DIR, plan["back"])
    for who, f, back in todo:
        t0 = time.time()
        verses = {v: put(text, bos="eng_Latn") if text.strip() else ""
                  for v, text in json.loads(f.read_text(encoding="utf-8"))["verses"].items()}
        back.parent.mkdir(parents=True, exist_ok=True)
        back.write_text(json.dumps({"verses": verses, "engine": "nllb-200-distilled-1.3B, back into English"},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {f.stem} [{lang}] {who}, back into English: {time.time() - t0:.0f}s")
    del put
    unload()


# ------------------------------------------------------------------ scoring
def read_reference(path):
    """{(USFM book, chapter, verse): text} from a VPL file.

    eBible's Common Language Burmese puts a zero-width space between every
    syllable and ends each paragraph with "-"; neither is text, and left in
    they would count against every model that writes plain Burmese."""
    ref = {}
    line_re = re.compile(r"^([1-3A-Z]{3})\s+(\d+):(\d+)\s+(.*)$")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = line_re.match(line.strip())
        if m:
            text = m[4].replace("​", "").strip().rstrip("-").strip()
            ref[(VPL_ALIASES.get(m[1], m[1]), int(m[2]), int(m[3]))] = text
    return ref


def aligned(vv, ref, book, ch, want):
    """(ours, theirs) pairs for one chapter, merged where the reference merges.

    A common-language Bible joins verses it reads better together: Genesis 1:6
    carries 6 and 7, and 1:7 is simply absent. So a reference verse is matched
    with all of ours from its number up to the next verse the reference has."""
    have = [int(v) for v in want if (book, ch, int(v)) in ref]
    last = max(int(v) for v in want)
    pairs = []
    for i, v in enumerate(have):
        upto = have[i + 1] if i + 1 < len(have) else last + 1
        ours = [vv[str(n)] for n in range(v, upto) if str(n) in vv]
        if ours:
            pairs.append((" ".join(ours), ref[(book, ch, v)]))
    return pairs


def chrf_scorer():
    try:
        from sacrebleu.metrics import CHRF
        c = CHRF(word_order=0)
        return lambda hyps, refs: c.corpus_score(hyps, [refs]).score
    except ImportError:
        return None


def script_share(text, lo_hi):
    letters = [c for c in text if c.isalpha() or lo_hi[0] <= ord(c) <= lo_hi[1]]
    return sum(1 for c in letters if lo_hi[0] <= ord(c) <= lo_hi[1]) / len(letters) if letters else 0.0


def score(lang):
    plan = PLANS[lang]
    refs = {name: read_reference(p) for name, p in plan["references"] if p.exists()}
    chrf = chrf_scorer()
    own = re.compile(f"[{plan['own'][0]}]") if plan.get("own") else None
    foreign = re.compile(f"[{plan['foreign'][0]}]") if plan.get("foreign") else None
    rows = []
    # Each reference Bible is also scored as if it were a candidate, against
    # the others: what two human translations score against each other is the
    # best a model can be expected to reach, and puts the models' numbers in
    # proportion.
    entrants = [(d.name, lambda meta, ch, d=d, kind="json": (
                    json.loads(f.read_text(encoding="utf-8"))["verses"]
                    if (f := d / lang / kind / f"{slug(meta['name'])}_{int(ch):02d}.json").exists() else None))
                for d in (sorted(p for p in (TRIALS / lang).iterdir() if p.is_dir())
                          if (TRIALS / lang).exists() else [])]
    if len(refs) > 1:
        entrants += [(f"({name}, a human translation)", lambda meta, ch, ref=ref: {
                        str(v): t for (b, c, v), t in ref.items()
                        if b == USFM[meta["num"] - 1] and c == int(ch)} or None)
                     for name, ref in refs.items()]
    for who, verses_of in entrants:
        for code, ch in chapters(plan):
            meta = BOOKS[code]
            vv = verses_of(meta, ch)
            if vv is None:
                continue
            # The way back: this chapter in English again, against the English it came from.
            back = None
            if chrf and plan.get("back") and not who.startswith("("):
                again = verses_of(meta, ch, kind="back")
                en = json.loads((ROOT / "output" / "en" / "json" / f"{slug(meta['name'])}_{int(ch):02d}.json")
                                .read_text(encoding="utf-8"))["verses"]
                both = [v for v in en if again and again.get(v)]
                if both:
                    back = round(chrf([again[v] for v in both], [" ".join(en[v].split()) for v in both]), 1)
            src = json.loads((T.NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json")
                             .read_text(encoding="utf-8"))["chapters"][ch]
            want = [str(v["v"]) for v in src]
            text = " ".join(vv.values())
            scores = {}
            for name, ref in refs.items():
                if who.startswith(f"({name},"):
                    continue                    # a Bible against itself scores 100 and says nothing
                pairs = aligned(vv, ref, USFM[meta["num"] - 1], int(ch), want)
                if chrf and pairs:
                    scores[name] = round(chrf([h for h, _ in pairs], [r for _, r in pairs]), 1)
            rows.append({
                "model": who, "chapter": f"{meta['name']} {ch}",
                "verses": f"{sum(1 for v in want if v in vv)}/{len(want)}",
                "chrf": scores,
                "script": round(100 * script_share(text, plan["script"])),
                "back": back,
                "own": sum(1 for t in vv.values() if own.search(t)) if own else None,
                "foreign": sum(1 for t in vv.values() if foreign.search(t)) if foreign else None,
                "zawgyi": sum(1 for t in vv.values() if ZAWGYI.search(t)),
                "spoken": sum(t.count(w) for t in vv.values() for w in SPOKEN)})
    return rows, list(refs), chrf is not None


def report(lang):
    plan = PLANS[lang]
    rows, have, have_chrf = score(lang)
    name = TARGETS[lang]["name"]
    lines = [f"# {name} trial", "",
             f"Written {time.strftime('%Y-%m-%d %H:%M')} by scripts/trial_lang.py. "
             "Each model translated the same chapters; "
             + (f"chrF is measured against {' and '.join(have)} and ranks the models rather than grading them "
                if have else "there is no published Bible to measure them against, so nothing here grades them ")
             + "(see the script's docstring).", ""]
    for ref_name, p in plan["references"]:
        if ref_name not in have:
            lines += [f"Missing reference: {p.relative_to(ROOT)}, so no chrF against {ref_name}.", ""]
    if not have_chrf:
        lines += ["sacrebleu is not installed (pip install sacrebleu), so there is no chrF.", ""]
    # What is worth a column differs by language: Zawgyi and the spoken
    # register are Burmese's faults; a language that shares its block with
    # another is told from it by its own letters; the way back to English is
    # for a language with no Bible to measure against.
    cols = [(f"chrF {n}", lambda r, n=n: r["chrf"].get(n, "-")) for n in have]
    if plan.get("back"):
        cols.append(("chrF back to English", lambda r: "-" if r["back"] is None else r["back"]))
        lines += ['"chrF back to English" is the chapter put into English again by NLLB-200 and measured '
                  "against our English: a rough reading of whether the meaning survived, kinder to NLLB's own "
                  "chapters than to the others'.", ""]
    cols.append(("in script %", lambda r: r["script"]))
    if plan.get("own"):
        cols.append((f"verses with {plan['own'][1]} letters", lambda r: r["own"]))
    if plan.get("foreign"):
        cols.append((f"verses with {plan['foreign'][1]} letters", lambda r: r["foreign"]))
    if plan.get("burmese"):
        cols += [("Zawgyi verses", lambda r: r["zawgyi"]), ("spoken-register words", lambda r: r["spoken"])]
    lines += ["| model | chapter | verses | " + " | ".join(h for h, _ in cols) + " |",
              "|---|---|---|" + "---|" * len(cols)]
    for r in rows:
        lines.append(f"| {r['model']} | {r['chapter']} | {r['verses']} | "
                     + " | ".join(str(get(r)) for _, get in cols) + " |")
    if plan.get("back"):
        by_model = {}
        for r in rows:
            if r["back"] is not None:
                by_model.setdefault(r["model"], []).append(r["back"])
        if by_model:
            lines += ["", "Mean chrF back to English: " + ", ".join(
                f"{m} {sum(v) / len(v):.1f}" for m, v in
                sorted(by_model.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])))]
    for n in have:
        by_model = {}
        for r in rows:
            if n in r["chrf"]:
                by_model.setdefault(r["model"], []).append(r["chrf"][n])
        if by_model:
            lines += ["", f"Mean chrF against {n}: " + ", ".join(
                f"{m} {sum(s) / len(s):.1f}" for m, s in
                sorted(by_model.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])))]
    out = TRIALS / lang / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten to {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True, help=f"a language with a trial plan: {', '.join(PLANS)}")
    ap.add_argument("--models", help="comma list of Ollama models, instead of the plan's")
    ap.add_argument("--chapters", help="comma list like Gen.1,John.1, instead of the plan's")
    ap.add_argument("--score", action="store_true", help="only score what is written")
    a = ap.parse_args()
    if a.lang not in PLANS:
        raise SystemExit(f"no trial plan for {a.lang!r}; known: {', '.join(PLANS)}")
    plan = dict(PLANS[a.lang])
    if a.models:
        plan["models"] = [m.strip() for m in a.models.split(",") if m.strip()]
    if a.chapters:
        plan["chapters"] = [c.strip() for c in a.chapters.split(",") if c.strip()]
    if not a.score:
        for model in plan["models"]:
            print(f"[{a.lang}] {model}")
            run_chat_model(a.lang, model, plan)
        if NLLB_DIR.exists():
            print(f"[{a.lang}] nllb-200")
            run_mt(a.lang, plan, "nllb-200", NLLB_DIR, "nllb-200-distilled-1.3B, from our English", bos=plan["nllb"])
        else:
            print(f"[{a.lang}] nllb-200: not on disk ({NLLB_DIR.relative_to(ROOT)}), left out")
        if plan.get("madlad"):
            print(f"[{a.lang}] madlad-400")
            run_mt(a.lang, plan, "madlad-400", MADLAD, "MADLAD-400 3B as it comes, from our English",
                   tag=f"<2{plan['madlad']}> ")
        if plan.get("back") and NLLB_DIR.exists():
            print(f"[{a.lang}] back into English")
            run_back(a.lang, plan)
    report(a.lang)


if __name__ == "__main__":
    main()
