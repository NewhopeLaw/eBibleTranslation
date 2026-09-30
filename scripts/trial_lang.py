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
           "script": (0x1000, 0x109F)},
}
NLLB_DIR = ROOT / "models" / "nllb-200-distilled-1.3B"

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
    who = plan["models"] + (["nllb-200"] if NLLB_DIR.exists() else [])
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


def run_nllb(lang, plan):
    """NLLB-200 from our English, one verse at a time, in translate.py's file shape."""
    out = model_dir(lang, "nllb-200") / lang / "json"
    todo = [(c, ch) for c, ch in chapters(plan)
            if not (out / f"{slug(BOOKS[c]['name'])}_{int(ch):02d}.json").exists()]
    if not todo:
        return
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(NLLB_DIR, src_lang="eng_Latn")
    model = AutoModelForSeq2SeqLM.from_pretrained(
        NLLB_DIR, torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32).to(device).eval()
    bos = tok.convert_tokens_to_ids(plan["nllb"])
    out.mkdir(parents=True, exist_ok=True)
    for code, ch in todo:
        name = slug(BOOKS[code]["name"])
        en = json.loads((ROOT / "output" / "en" / "json" / f"{name}_{int(ch):02d}.json")
                        .read_text(encoding="utf-8"))["verses"]
        t0, verses = time.time(), {}
        for v, text in en.items():
            enc = tok(" ".join(text.split()), return_tensors="pt", truncation=True, max_length=400).to(device)
            with torch.no_grad():
                gen = model.generate(**enc, forced_bos_token_id=bos, num_beams=4,
                                     max_new_tokens=min(512, enc["input_ids"].shape[1] * 4 + 30))
            verses[v] = tok.batch_decode(gen, skip_special_tokens=True)[0]
        (out / f"{name}_{int(ch):02d}.json").write_text(json.dumps(
            {"book": BOOKS[code]["name"], "chapter": int(ch), "lang": lang, "verses": verses,
             "notes": "", "engine": "nllb-200-distilled-1.3B, from our English"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {BOOKS[code]['name']} {ch} [{lang}] nllb-200: {len(verses)} vv, {time.time() - t0:.0f}s")


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
    rows = []
    # Each reference Bible is also scored as if it were a candidate, against
    # the others: what two human translations score against each other is the
    # best a model can be expected to reach, and puts the models' numbers in
    # proportion.
    entrants = [(d.name, lambda meta, ch, d=d: (
                    json.loads(f.read_text(encoding="utf-8"))["verses"]
                    if (f := d / lang / "json" / f"{slug(meta['name'])}_{int(ch):02d}.json").exists() else None))
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
                "zawgyi": sum(1 for t in vv.values() if ZAWGYI.search(t)),
                "spoken": sum(t.count(w) for t in vv.values() for w in SPOKEN)})
    return rows, list(refs), chrf is not None


def report(lang):
    plan = PLANS[lang]
    rows, have, have_chrf = score(lang)
    name = TARGETS[lang]["name"]
    lines = [f"# {name} trial", "",
             f"Written {time.strftime('%Y-%m-%d %H:%M')} by scripts/trial_lang.py. "
             f"Each model translated the same chapters; chrF is measured against "
             f"{' and '.join(have) or 'no reference'} and ranks the models rather than grading them "
             "(see the script's docstring).", ""]
    for ref_name, p in plan["references"]:
        if ref_name not in have:
            lines += [f"Missing reference: {p.relative_to(ROOT)}, so no chrF against {ref_name}.", ""]
    if not have_chrf:
        lines += ["sacrebleu is not installed (pip install sacrebleu), so there is no chrF.", ""]
    lines += ["| model | chapter | verses | " + " | ".join(f"chrF {n}" for n in have)
              + " | in script % | Zawgyi verses | spoken-register words |",
              "|---|---|---|" + "---|" * len(have) + "---|---|---|"]
    for r in rows:
        lines.append(f"| {r['model']} | {r['chapter']} | {r['verses']} | "
                     + "".join(f"{r['chrf'].get(n, '-')} | " for n in have)
                     + f"{r['script']} | {r['zawgyi']} | {r['spoken']} |")
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
            run_nllb(a.lang, plan)
        else:
            print(f"[{a.lang}] nllb-200: not on disk ({NLLB_DIR.relative_to(ROOT)}), left out")
    report(a.lang)


if __name__ == "__main__":
    main()
