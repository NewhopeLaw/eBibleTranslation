#!/usr/bin/env python3
"""Teach a translation model Sgaw Karen from the Karen Bible.

    python scripts/train_karen.py                          # MADLAD-400 3B, full fine-tune
    python scripts/train_karen.py --base google/madlad400-10b-mt --lora
    python scripts/train_karen.py --epochs 5 --eval-every 500
    python scripts/train_karen.py --base models/madlad-ksw --names --epochs 1 --lr 2e-5 --out models/madlad-ksw-names

No model on hand writes Sgaw Karen (README, "Target languages"). MADLAD-400's
tokenizer, though, spells Karen fluently - ယွၤ, လီၤ, ဟီၣ်ခိၣ် are single
pieces - which says its training data held real Karen under some wrong label,
and a model that has seen a language is far quicker to teach than one that
has not. So MADLAD is the base, and the lessons are the 27,500 verse pairs
scripts/karen_corpus.py makes from Mason's 1853 Karen Bible and our English:
our English in, because that is what the model will be given afterwards,
Mason's Karen out.

What it learns, then, is Mason's Karen - the register Karen churches have
read for a hundred and seventy years - said of our English's meaning. That
is the right target for a first test in the villages: familiar language,
our translation's content.

Held out, never trained on: every thirtieth chapter in canonical order, about
forty chapters across the genres, so the score means something. The score is
chrF (character F-score; BLEU is unfair to a language without spaces between
words), printed with three sample verses at every evaluation, and the best
checkpoint goes to models/madlad-ksw/ (gitignored: it is several gigabytes),
which mt_translate.py can then be pointed at with --model.

Names are learnt slowest - rare, arbitrary, and at a third of an epoch the
model called Sarai "Israel's father" - so --names adds the table that
scripts/karen_names.py mined from the same Bible (targets/ksw/names.en.json),
each name as a pair of its own, several times over, on top of the verses. It
is meant as a short second pass over a model already trained on the verses,
--base pointing at that model.

The 3B is trained whole, in bfloat16 with Adafactor, about 15 GB of GPU.
The 10B does not fit that way; --lora trains low-rank adapters on it instead
(peft) and merges them into the saved model, so the result loads like any
other. Needs: pip install torch transformers sentencepiece sacrebleu peft.
"""
import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "sources" / "ksw-mason" / "pairs.jsonl"
NAMES = ROOT / "targets" / "ksw" / "names.en.json"
OUT = ROOT / "models" / "madlad-ksw"
LOG = ROOT / "logs" / "train_karen.log"
TAG = "<2ksw> "
HOLD_EVERY = 30          # every thirtieth chapter is kept back for scoring

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_pairs():
    """(train, dev): dev is every HOLD_EVERY-th chapter of the canon."""
    order = {m["name"]: m["num"] for m in BOOKS.values()}
    rows = [json.loads(l) for l in PAIRS.read_text(encoding="utf-8").splitlines() if l.strip()]
    chapters = sorted({(r["book"], r["chapter"]) for r in rows}, key=lambda k: (order[k[0]], k[1]))
    held = {c for i, c in enumerate(chapters) if i % HOLD_EVERY == HOLD_EVERY // 2}
    train = [r for r in rows if (r["book"], r["chapter"]) not in held]
    dev = [r for r in rows if (r["book"], r["chapter"]) in held]
    return train, dev, sorted(held, key=lambda k: (order[k[0]], k[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="google/madlad400-3b-mt")
    ap.add_argument("--lora", action="store_true", help="train adapters instead of the whole model (for the 10B)")
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--batch", type=int, default=8, help="pairs per step")
    ap.add_argument("--accum", type=int, default=4, help="steps per optimiser update")
    ap.add_argument("--lr", type=float, default=0)
    ap.add_argument("--max-len", type=int, default=256)
    ap.add_argument("--eval-every", type=int, default=400, help="optimiser updates between scorings")
    ap.add_argument("--dev-size", type=int, default=240, help="verses scored each time (the whole dev set at the end)")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--names", action="store_true", help="add the mined name table as training pairs")
    ap.add_argument("--name-repeats", type=int, default=4, help="times each name pair is added")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    lr = a.lr or (2e-4 if a.lora else 5e-5)

    import torch
    from sacrebleu.metrics import CHRF
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    from transformers.optimization import Adafactor

    random.seed(a.seed)
    torch.manual_seed(a.seed)
    train, dev, held = load_pairs()
    if a.names:
        names = json.loads(NAMES.read_text(encoding="utf-8"))["names"]
        train += [{"book": "names", "chapter": 0, "verse": 0, "en": en, "ksw": ksw}
                  for en, ksw in names.items() for _ in range(a.name_repeats)]
        log(f"names: {len(names)} added {a.name_repeats} times each from {NAMES.name}")
    log(f"start: base {a.base}{' +lora' if a.lora else ''}, {len(train)} training pairs, {len(dev)} held out "
        f"from {len(held)} chapters ({held[0][0]} {held[0][1]} ... {held[-1][0]} {held[-1][1]}), "
        f"{a.epochs} epochs, batch {a.batch}x{a.accum}, lr {lr}")

    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForSeq2SeqLM.from_pretrained(a.base, dtype=torch.bfloat16).to("cuda")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    if a.lora:
        from peft import LoraConfig, get_peft_model
        model.enable_input_require_grads()      # checkpointing needs a gradient at the input when the weights themselves are frozen
        model = get_peft_model(model, LoraConfig(r=64, lora_alpha=128, lora_dropout=0.05, task_type="SEQ_2_SEQ_LM",
                                                 target_modules=["q", "k", "v", "o", "wi_0", "wi_1", "wo"]))
        model.print_trainable_parameters()
    params = [p for p in model.parameters() if p.requires_grad]
    opt = Adafactor(params, lr=lr, scale_parameter=False, relative_step=False, warmup_init=False, weight_decay=0.0)
    chrf = CHRF(word_order=0)

    def encode(rows):
        enc = tok([TAG + r["en"] for r in rows], text_target=[r["ksw"] for r in rows], return_tensors="pt",
                  padding=True, truncation=True, max_length=a.max_len)
        enc["labels"][enc["labels"] == tok.pad_token_id] = -100
        return {k: v.to("cuda") for k, v in enc.items()}

    def score(rows, show=3):
        """Small batches on purpose: four beams over sixteen verses kept a cache
        that, with this vocabulary, spilled past the GPU into system RAM and
        turned a two-minute scoring into an hour."""
        model.eval()
        hyps = []
        with torch.no_grad():
            for i in range(0, len(rows), 4):
                batch = rows[i:i + 4]
                enc = tok([TAG + r["en"] for r in batch], return_tensors="pt", padding=True, truncation=True,
                          max_length=a.max_len).to("cuda")
                gen = model.generate(**enc, num_beams=4, max_new_tokens=min(a.max_len, 192), use_cache=True)
                hyps += [h.strip() for h in tok.batch_decode(gen, skip_special_tokens=True)]
        model.train()
        s = chrf.corpus_score(hyps, [[r["ksw"] for r in rows]]).score
        for r, h in list(zip(rows, hyps))[:show]:
            log(f"    {r['book']} {r['chapter']}:{r['verse']}  EN  {r['en'][:90]}")
            log(f"      KAREN {r['ksw'][:90]}")
            log(f"      MODEL {h[:90]}")
        return s

    updates_per_epoch = math.ceil(len(train) / (a.batch * a.accum))
    total_updates = int(updates_per_epoch * a.epochs)
    warm = max(1, total_updates // 20)
    log(f"before training: chrF {score(dev[:a.dev_size]):.1f} on {min(a.dev_size, len(dev))} held-out verses")
    best, update, step, t0, running = -1.0, 0, 0, time.time(), []
    model.train()
    out = Path(a.out)
    done = False
    while not done:
        random.shuffle(train)
        # Batches of neighbours in length pad less; the shuffle above still mixes the epochs.
        chunks = [train[i:i + a.batch * 50] for i in range(0, len(train), a.batch * 50)]
        batches = []
        for chunk in chunks:
            chunk.sort(key=lambda r: len(r["en"]))
            batches += [chunk[i:i + a.batch] for i in range(0, len(chunk), a.batch)]
        random.shuffle(batches)
        for batch in batches:
            loss = model(**encode(batch)).loss / a.accum
            loss.backward()
            running.append(loss.item() * a.accum)
            step += 1
            if step % a.accum:
                continue
            update += 1
            for g in opt.param_groups:                       # warm up, then cosine down
                g["lr"] = lr * (update / warm if update < warm
                                else 0.5 * (1 + math.cos(math.pi * (update - warm) / max(1, total_updates - warm))))
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            if update % 50 == 0:
                rate = (time.time() - t0) / update
                log(f"update {update}/{total_updates}: loss {sum(running[-200:]) / len(running[-200:]):.3f}, "
                    f"{rate:.1f}s each, about {rate * (total_updates - update) / 60:.0f} min left")
            if update % a.eval_every == 0 or update >= total_updates:
                s = score(dev if update >= total_updates else dev[:a.dev_size])
                log(f"update {update}: chrF {s:.1f}" + (" (best so far, saved)" if s > best else ""))
                if s > best:
                    best = s
                    to_save = model.merge_and_unload() if a.lora and update >= total_updates else model
                    if a.lora and update < total_updates:
                        model.save_pretrained(out / "adapter")
                    else:
                        to_save.save_pretrained(out, safe_serialization=True)
                        tok.save_pretrained(out)
                    (out / "TRAINING.json").write_text(json.dumps(
                        {"base": a.base, "lora": a.lora, "update": update, "chrf": round(s, 2),
                         "held_out_chapters": [f"{b} {c}" for b, c in held], "pairs": len(train),
                         "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1), encoding="utf-8")
            if update >= total_updates:
                done = True
                break
    log(f"done: best chrF {best:.1f}; model in {out}")


if __name__ == "__main__":
    main()
