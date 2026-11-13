#!/usr/bin/env python3
"""Teach the search model the Bible: multilingual-e5-small, trained on this project's own text.

    python scripts/train_search.py                  # train -> models/e5-bible/, on the PC's GPU
    python scripts/train_search.py --epochs 2
    python scripts/train_search.py --tiny           # a few steps on any machine: does it run at all
    python scripts/build_encoder.py                 # then the phone's files from it, as usual
    python scripts/search_test.py                   # and the score, against the one before

There is no multilingual Bible search model to take. The ones that exist read
English alone (TheoBERT, EmbeddingGemma and BGE fine-tunes), so they cannot
serve a Thai or Karen reader. So the multilingual model the app already
carries is taught here instead, the way those were made and the way Quran
search was made multilingual (Pavlova & Makhlouf 2025, arXiv:2509.15380): pairs of a
question and the passage that answers it, each pulled toward the other and
away from every other passage in the batch (InfoNCE, in-batch negatives).
Nothing about the phone changes - the same model, the same size, the same
files - only what its numbers know.

The pairs come from what the project already has:

  - questions the model wrote about passages (make_search_tests.py --train,
    targets/search/train.jsonl), each paired with a verse of its passage;
  - each chapter theme's description of a run of verses, in every language it
    has been translated into (translate_stories.py), paired with a verse of
    the run in the same language: the way a reader describes a story;
  - the same verse in two languages: what lets a Thai question reach an
    English description, and Karen, which no model writes well, learn from
    the translation it already has.

Any pair touching a passage the hand-written test questions ask about
(targets/search/tests.jsonl, "by": "hand") is left out, so search_test.py
still measures passages the model was never shown.

Written to models/e5-bible/ (gitignored) in the form transformers reads.
build_encoder.py uses it when it is there, and says so; delete the folder and
the next build is the untaught model again.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_encoder as E                                        # noqa: E402
from books import TARGETS                                        # noqa: E402
from build_vectors import verses                                 # noqa: E402
from search_test import TESTS, ranges                            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / "targets" / "search" / "train.jsonl"
OUT = ROOT / "models" / "e5-bible"


def held_out():
    """Verse-id ranges the hand-written test questions answer with."""
    out = []
    for ln in TESTS.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r.get("by") == "hand":
                out += ranges(r["refs"])
    return out


def pairs(langs, rng, cross):
    """-> [(question, passage, group)] with group the passage's first verse id,
    so two pairs about one passage are never each other's negatives."""
    text = {c: dict(verses(c)) for c in langs}
    hold = held_out()
    blocked = lambda lo, hi: any(lo <= b and a <= hi for a, b in hold)
    out = []

    def verse_in(lang, lo, hi):
        got = [v for v in range(lo, hi + 1) if v in text[lang]]
        return rng.choice(got) if got else None

    # Questions written by the model about a passage.
    n = 0
    if TRAIN.exists():
        for ln in TRAIN.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r["lang"] not in text:
                continue
            for lo, hi in ranges(r["refs"]):
                if blocked(lo, hi):
                    continue
                v = verse_in(r["lang"], lo, hi)
                if v:
                    out.append((r["q"], text[r["lang"]][v], lo))
                    n += 1
    print(f"  {n} model-written questions")

    # A passage's description, in each language it exists in, to a verse of it.
    rows = E.story_rows()
    for c in langs:
        tr = {} if c == "en" else E.story_translations(c)
        if c != "en" and not tr:
            continue
        m = 0
        for lo, hi, t in rows:
            if blocked(lo, hi):
                continue
            desc = t if c == "en" else tr.get(t)
            v = verse_in(c, lo, hi) if desc else None
            if v:
                out.append((desc, text[c][v], lo))
                m += 1
        print(f"  {m} passage descriptions in {c}")

    # The same verse in two languages.
    ids = [v for v in text[langs[0]] if not blocked(v, v)]
    m = 0
    for v in rng.sample(ids, min(cross, len(ids))):
        a, b = rng.sample(langs, 2) if len(langs) > 1 else (langs[0], langs[0])
        if v in text[a] and v in text[b] and a != b:
            out.append((text[a][v], text[b][v], v))
            m += 1
    print(f"  {m} verses paired across languages")
    rng.shuffle(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", default="", help="comma list (default: every finished translation)")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--cross", type=int, default=40000, help="verse pairs across languages (default 40000)")
    ap.add_argument("--temp", type=float, default=0.05, help="InfoNCE temperature")
    ap.add_argument("--tiny", action="store_true", help="20 small steps, written to a scratch folder: a check")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    import torch
    from transformers import AutoModel, AutoTokenizer

    whole = len(list((ROOT / "output" / "en" / "json").glob("*.json")))
    langs = [c.strip() for c in a.langs.split(",") if c.strip()] or [
        c for c in TARGETS if len(list((ROOT / "output" / c / "json").glob("*.json"))) >= whole]
    rng = random.Random(11)
    print(f"languages: {', '.join(langs)}")
    data = pairs(langs, rng, 400 if a.tiny else a.cross)
    if a.tiny:
        data = data[:20 * 8]
        a.batch, out = 8, Path("/tmp/e5-bible-tiny")
    else:
        out = Path(a.out)
    print(f"{len(data)} pairs")

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(E.TEACHER)
    model = AutoModel.from_pretrained(E.TEACHER).to(dev).train()
    steps = max(1, int(math.ceil(len(data) / a.batch) * a.epochs))
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    warm = max(1, steps // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min((s + 1) / warm, max(0.0, (steps - s) / (steps - warm + 1))))
    amp = dev == "cuda"

    def embed(texts):
        enc = tok(texts, padding=True, truncation=True, max_length=E.MAXLEN, return_tensors="pt").to(dev)
        h = model(**enc).last_hidden_state
        m = enc["attention_mask"].unsqueeze(-1).to(h.dtype)
        return torch.nn.functional.normalize((h * m).sum(1) / m.sum(1).clamp(min=1e-9), dim=-1)

    t0, step, seen = time.time(), 0, 0
    while step < steps:
        for b in range(0, len(data), a.batch):
            if step >= steps:
                break
            part = data[b:b + a.batch]
            if len(part) < 2:
                continue
            with torch.autocast(dev, dtype=torch.bfloat16, enabled=amp):
                q = embed([E.QUERY + x for x, _, _ in part])
                p = embed([E.PASSAGE + y for _, y, _ in part])
                sim = (q @ p.T).float() / a.temp
                # Two pairs about the same passage are not each other's wrong answers.
                g = torch.tensor([k for _, _, k in part], device=dev)
                same = (g[:, None] == g[None, :]) & ~torch.eye(len(part), dtype=torch.bool, device=dev)
                sim = sim.masked_fill(same, -1e4)
                gold = torch.arange(len(part), device=dev)
                loss = (torch.nn.functional.cross_entropy(sim, gold) + torch.nn.functional.cross_entropy(sim.T, gold)) / 2
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            step += 1
            seen += len(part)
            if step % 50 == 0 or step == steps or a.tiny:
                print(f"  step {step}/{steps}  loss {loss.item():.3f}  [{time.time() - t0:.0f}s]", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    (out / "trained.json").write_text(json.dumps({
        "from": E.TEACHER, "pairs": len(data), "epochs": a.epochs, "steps": steps, "batch": a.batch,
        "lr": a.lr, "temp": a.temp, "langs": langs, "finished": time.strftime("%Y-%m-%d %H:%M")}, indent=1),
        encoding="utf-8")
    print(f"written to {out} - now scripts/build_encoder.py, then scripts/search_test.py")


if __name__ == "__main__":
    main()
