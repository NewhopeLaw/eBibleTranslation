#!/usr/bin/env python3
"""A small test: can NLLB put our English into Sgaw Karen well enough to be worth more?

    python scripts/nllb_test.py                     # Genesis 1 and John 1
    python scripts/nllb_test.py Genesis_01 John_03  # other chapters, by file name
    python scripts/nllb_test.py --model facebook/nllb-200-3.3B

Qwen, the model in config.json, is not expected to write Sgaw: it has read almost
none, and a wrong answer in Myanmar script passes every check verify.py has,
because those look at script and length, not at whether the words are real. NLLB
lists Sgaw Karen (ksw_Mymr) among its languages, so it is the first thing to try.
It translates from English, not from Hebrew or Greek, so this pivots on the
English we already have, as translate.py does for the other languages.

What comes out goes to logs/nllb_ksw_test.md, English beside Sgaw, verse by
verse, for a Karen reader to mark. It is kept out of output/ on purpose: nothing
here has been read by anyone who knows the language, and build_site.py must not
pick it up as a translation. Needs: pip install torch transformers sentencepiece
"""
import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_JSON = ROOT / "output" / "en" / "json"
REPORT = ROOT / "logs" / "nllb_ksw_test.md"

SRC, TGT = "eng_Latn", "ksw_Mymr"
DEFAULT_MODEL = "facebook/nllb-200-distilled-1.3B"
MYANMAR = range(0x1000, 0x10A0)


def english_verses(chapter):
    data = json.loads((EN_JSON / f"{chapter}.json").read_text(encoding="utf-8"))
    return data["book"], data["chapter"], {int(n): t.strip() for n, t in data["verses"].items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters", nargs="*", default=["Genesis_01", "John_01"])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(args.model, src_lang=SRC)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model, torch_dtype=torch.float16 if device == "cuda" else None).to(device)
    forced = tok.convert_tokens_to_ids(TGT)
    if forced == tok.unk_token_id:
        raise SystemExit(f"{args.model} does not know {TGT} - pick a model that lists Sgaw Karen")

    lines = [f"# Sgaw Karen test - {args.model}", "",
             "Machine output for a Karen reader to mark. Not a translation anyone has read.", ""]
    for chapter in args.chapters:
        book, num, verses = english_verses(chapter)
        numbers = sorted(verses)
        started = time.time()
        out = {}
        for i in range(0, len(numbers), args.batch):
            group = numbers[i:i + args.batch]
            batch = tok([verses[n] for n in group], return_tensors="pt", padding=True, truncation=True, max_length=256).to(device)
            with torch.no_grad():
                gen = model.generate(**batch, forced_bos_token_id=forced, max_new_tokens=256, num_beams=4, no_repeat_ngram_size=4)
            for n, text in zip(group, tok.batch_decode(gen, skip_special_tokens=True)):
                out[n] = text
        # A verse with no Myanmar-block letters in it means the model fell back to
        # English or Latin; say so rather than let it read as a Karen answer.
        bare = [n for n in numbers if not any(ord(c) in MYANMAR for c in out[n])]
        lines += [f"## {book} {num}", "",
                  f"{len(numbers)} verses in {time.time() - started:.0f}s; "
                  f"{len(bare)} without any Myanmar script{' (v. ' + ', '.join(map(str, bare)) + ')' if bare else ''}.", ""]
        for n in numbers:
            lines += [f"**{n}** EN: {verses[n]}", f"    KSW: {out[n]}", ""]
        print(f"{book} {num}: {len(numbers)} verses, {len(bare)} without Myanmar script")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"written to {REPORT}")


if __name__ == "__main__":
    main()
