#!/usr/bin/env python3
"""Semantic search: a vector for every verse, and a table small enough to carry.

    python scripts/build_vectors.py                      # -> site/morph/vec_*.js
    python scripts/build_vectors.py --langs en --dims 128
    python scripts/build_vectors.py --probe "the shepherd who leaves ninety-nine sheep"

The search we have finds letters. Type "anxiety" and it finds the verses with
those eight letters in them, which is a concordance — useful when you know the
wording, useless when you only know what you are looking for. This builds the
other half: a vector for every verse, so a reader who half-remembers a passage
can describe it and be taken there.

The constraint that decides the whole design is that the reader is offline on a
phone. Whatever embeds the verses has to embed the reader's query too, in the
same space, in a WebView, with no model and no runtime — so the embedder cannot
be a transformer. It is a static table instead: a vector per token, looked up
and averaged. That is a sentence embedding as it was done before transformers
took the job over, and it is chosen here for exactly the reason it was dropped
then and is worth having back now — it is arithmetic, and arithmetic runs
anywhere.

The table is distilled from a real model on the GPU, once. Every token of the
vocabulary is passed through the teacher on its own and the outputs are reduced
to a few dozen dimensions; what survives is what the teacher knows about a word
with no sentence around it. Tokens are then weighted the way Arora's SIF
baseline weights them, by how rare they are in this corpus, so that "shepherd"
counts for more than "the". Measured against the full teacher on the same
queries, the table loses very little, and on narrative recall it sometimes wins.

What it is good at, and what it is not
--------------------------------------
Verse vectors answer "find the passage I am thinking of" well: "the shepherd
who leaves ninety-nine sheep" reaches Matthew 18:12 and Luke 15:4, neither of
which shares a word with the query. They answer "what does the Bible say about
X" poorly, and the reason is not the table but the text. A verse is short and
holds no vocabulary but its own: "Do not be anxious" never says stress, or
burnout, or depression, so nothing in the sentence can be matched against a
reader who uses those words. The cure is to give each verse a plain-language
line saying what it concerns, written by the model on the PC, and to embed the
verse together with that line. When targets/search/topics.jsonl exists it is
folded in here; until then this builds from the verses alone, which is already
the half of the problem that needs no GPU time to solve.

Only the vocabulary this project actually uses is carried. Across English,
Chinese and Spanish the whole Bible touches 21,667 of the teacher's 250,002
tokens, so the table is pruned to those plus a slice of common vocabulary for
the words a reader types that the text never uses.

Written to site/morph/:

    vec_table.js   VECTAB = {d, s, v, w, p, g}   the tokens: pieces, scores, vectors, weights
    vec_<lang>.js  VEC["en"] = {n, d, s, i, v}   the verses: ids and vectors

This one runs on the PC only: it wants torch, transformers and the GPU, none of
which a checkout elsewhere has. The files it writes are committed, so the reader
can be built anywhere.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                                  # noqa: E402
from books import BOOKS, TARGETS                                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "morph"
TOPICS = ROOT / "targets" / "search" / "topics.jsonl"

TEACHER = "intfloat/multilingual-e5-small"
COMMON = 32000        # the teacher's vocabulary is roughly frequency-ordered, so the low ids
                      # are the common subwords of every language: kept whether or not the
                      # Bible happens to use them, because the reader's words are not the text's
FURI = re.compile(r"\{([^{}|\]]+)\|[^{}\]]+[}\]]")               # furigana notation, as build_index.py strips it
SIF_A = 1e-3          # Arora et al., "A Simple but Tough-to-Beat Baseline for Sentence Embeddings"


def need(what):
    """Say plainly which machine this script wants, rather than an import traceback."""
    print(f"build_vectors.py needs {what}. It runs on the PC with the GPU, where the model\n"
          f"work happens; the vec_*.js it writes are committed, so the reader builds anywhere.",
          file=sys.stderr)
    raise SystemExit(2)


# ---------------------------------------------------------------- the corpus

def verses(lang):
    """-> [(verse id, text)] for one translation, in canonical order."""
    d = ROOT / "output" / lang / "json"
    if not d.exists():
        return []
    bynum = {m["name"]: m["num"] for m in BOOKS.values()}
    topics = chapter_topics()
    out = []
    for f in sorted(d.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        num = bynum.get(rec["book"])
        if not num:
            continue
        ch = int(rec["chapter"])
        extra = topics.get((rec["book"], ch), {})
        for v, text in rec["verses"].items():
            vid = num * 1000000 + ch * 1000 + int(v)
            said = FURI.sub(r"\1", text)
            note = extra.get(str(v))
            out.append((vid, f"{said} {note}" if note else said))
    out.sort()
    return out


def chapter_topics():
    """What the model said each verse is about, when that job has run.

    Written a chapter at a time by the topical pass, as {"book", "chapter",
    "topics": {verse: "a line of plain words"}}. Embedding the verse together
    with this line is what lets a reader's vocabulary reach a text that does not
    use it. Absent, everything below simply works from the verses.
    """
    if not TOPICS.exists():
        return {}
    got = {}
    for line in TOPICS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        got[(r["book"], int(r["chapter"]))] = {str(k): v for k, v in (r.get("topics") or {}).items()}
    return got


# ------------------------------------------------------------- the table

def distil(tok, model, keep, dev, batch=2048):
    """Every kept token through the teacher on its own -> one vector each.

    A token with no sentence around it is the only thing a lookup table can
    hold, and it is what the teacher is being asked for here: not how this word
    behaves in this verse, but what it means before any verse has been read.
    """
    import numpy as np
    import torch
    wide = np.zeros((len(keep), model.config.hidden_size), dtype=np.float32)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, len(keep), batch):
            chunk = keep[i:i + batch]
            ids = torch.tensor(chunk, device=dev).unsqueeze(1)
            out = model(input_ids=ids, attention_mask=torch.ones_like(ids))
            wide[i:i + batch] = out.last_hidden_state[:, 0].float().cpu().numpy()
            print(f"  distilled {min(i + batch, len(keep))}/{len(keep)}"
                  f" [{time.time() - t0:.0f}s]", end="\r", flush=True)
    print()
    return wide


def reduce_dims(wide, dims):
    """Down to `dims`, whitened.

    The teacher's 384 dimensions are more than a phone should carry and more
    than the signal needs: the variance is concentrated in the first few dozen
    directions. Whitening matters as much as the reduction — without it a
    handful of directions of enormous variance dominate every comparison, which
    is the familiar complaint that every sentence looks alike.
    """
    import numpy as np
    mu = wide.mean(0)
    x = wide - mu
    _, s, vt = np.linalg.svd(x, full_matrices=False)
    proj = vt[:dims].T / (s[:dims] / np.sqrt(len(x)))
    return (x @ proj).astype(np.float32)


def sif_weights(table, freq, keep):
    """How much each token counts: rare words carry the sense, common ones do not.

    Arora's weight, a/(a+p), over this corpus rather than a general one — the
    Bible's own commonplaces are not English's, and "LORD" should not count for
    what its frequency elsewhere would suggest. A token kept for the reader's
    sake and never used in the text gets the full weight, which is right: a word
    the Bible never says is as informative as a word can be.

    The magnitude of the vector is folded in here so the stored vectors can all
    be unit length, where int8 has its accuracy to spend.
    """
    import numpy as np
    total = max(sum(freq.values()), 1)
    sif = np.array([SIF_A / (SIF_A + freq.get(t, 0) / total) for t in keep], dtype=np.float32)
    norm = np.linalg.norm(table, axis=1)
    norm[norm == 0] = 1e-6
    return sif * norm, table / norm[:, None]


# ------------------------------------------------------------- writing

def b64(arr):
    return base64.b64encode(arr.tobytes()).decode("ascii")


def quantize(unit):
    """Unit vectors to int8, with the one scale that makes the most of the range."""
    import numpy as np
    scale = float(np.abs(unit).max()) or 1.0
    return np.clip(np.rint(unit / scale * 127), -127, 127).astype(np.int8), scale / 127


def write_table(pieces, scores, vecs, weights, dims):
    import numpy as np
    q, scale = quantize(vecs)
    body = ("VECTAB={"
            f'"d":{dims},"s":{scale:.10g},'
            f'"p":{json.dumps(pieces, ensure_ascii=False, separators=(",", ":"))},'
            f'"g":"{b64(np.asarray(scores, dtype=np.float16))}",'
            f'"v":"{b64(q)}",'
            f'"w":"{b64(weights.astype(np.float16))}"'
            "};\n")
    p = OUT / "vec_table.js"
    p.write_text(body, encoding="utf-8")
    print(f"  table: {len(pieces)} tokens, {dims} dims, {p.stat().st_size / 1e6:.1f} MB -> {p.name}")
    return len(pieces)


def write_lang(code, ids, vecs, dims, note):
    import numpy as np
    q, scale = quantize(vecs)
    body = (f'VEC[{json.dumps(code)}]={{"n":{len(ids)},"d":{dims},"s":{scale:.10g},'
            f'"i":"{b64(np.asarray(ids, dtype=np.int32))}",'
            f'"v":"{b64(q)}"}};\n')
    p = OUT / f"vec_{code}.js"
    p.write_text("VEC=typeof VEC==='undefined'?{}:VEC;\n" + body, encoding="utf-8")
    print(f"  {code}: {len(ids)} verses, {p.stat().st_size / 1e6:.1f} MB{note} -> {p.name}")


# ------------------------------------------------------------- the run

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--langs", default="", help="which translations, comma separated (default: every complete one)")
    ap.add_argument("--dims", type=int, default=128, help="dimensions kept per vector (default 128)")
    ap.add_argument("--teacher", default=TEACHER, help=f"the model distilled from (default {TEACHER})")
    ap.add_argument("--common", type=int, default=COMMON, help="how much general vocabulary to keep beside the text's")
    ap.add_argument("--probe", default="", help="run a query against what was built and print the verses")
    a = ap.parse_args()

    try:
        import numpy as np
    except ImportError:
        need("numpy")
    if a.probe:
        return probe(a.probe, np)

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        need("torch and transformers")

    OUT.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"teacher {a.teacher} on {dev}")
    tok = AutoTokenizer.from_pretrained(a.teacher)
    model = AutoModel.from_pretrained(a.teacher).to(dev).eval()
    if dev == "cuda":
        model = model.half()

    # Which languages: every one whose translation is finished, unless told otherwise.
    # A half-translated text would answer a search with whichever books happen to
    # be done, which reads as though the rest had nothing to say.
    whole = len(list((ROOT / "output" / "en" / "json").glob("*.json")))
    langs = [c.strip() for c in a.langs.split(",") if c.strip()] or [
        c for c in TARGETS if len(list((ROOT / "output" / c / "json").glob("*.json"))) >= whole]
    print(f"languages: {', '.join(langs) or 'none complete'}")
    if not langs:
        raise SystemExit("no translation is complete — name one with --langs to build it anyway")

    corpus = {c: verses(c) for c in langs}
    topical = TOPICS.exists()
    print(f"verses: " + ", ".join(f"{c} {len(v)}" for c, v in corpus.items())
          + (" (with the topical lines folded in)" if topical else " (verse text alone)"))

    # ---- the vocabulary actually needed
    freq = Counter()
    tokens = {}
    for c, rows in corpus.items():
        ids = tok([t for _, t in rows], add_special_tokens=False)["input_ids"]
        tokens[c] = ids
        for one in ids:
            freq.update(one)
    keep = sorted(set(freq) | set(range(a.common)))
    print(f"vocabulary: {len(freq)} tokens used by the text, {len(keep)} carried")

    # ---- the table
    table = reduce_dims(distil(tok, model, keep, dev), a.dims)
    weights, table = sif_weights(table, freq, keep)
    full = json.loads(tok.backend_tokenizer.to_str())["model"]["vocab"]
    write_table([full[i][0] for i in keep], [full[i][1] for i in keep], table, weights, a.dims)

    # ---- the verses
    rows = {t: i for i, t in enumerate(keep)}
    total = 0
    for c, verse_rows in corpus.items():
        vecs = np.zeros((len(verse_rows), a.dims), dtype=np.float32)
        for n, ids in enumerate(tokens[c]):
            r = [rows[i] for i in ids if i in rows]
            if r:
                w = weights[r][:, None]
                vecs[n] = (table[r] * w).sum(0)
        norm = np.linalg.norm(vecs, axis=1, keepdims=True)
        norm[norm == 0] = 1
        write_lang(c, [vid for vid, _ in verse_rows], vecs / norm, a.dims,
                   f", {TARGETS[c]['name']}")
        total += len(verse_rows)

    manifest.record("vectors", total, "verse vectors",
                    "semantic search" + (", with the topical lines" if topical else ", verse text alone"),
                    "build_vectors.py")
    if not topical:
        print("\nThe topical lines have not been written yet, so this answers 'find the passage\n"
              "I half-remember' well and 'what does the text say about X' poorly. See the head of\n"
              "this file for why, and targets/search/topics.jsonl for what fixes it.")


def probe(query, np):
    """Ask the built files a question here, the way the phone will ask them.

    Everything below is deliberately the arithmetic the reader does — the point
    of a probe is to see what the phone would see, not what the teacher would.
    """
    tab = OUT / "vec_table.js"
    if not tab.exists():
        raise SystemExit("nothing built yet — run scripts/build_vectors.py first")
    raw = json.loads(tab.read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    dims = raw["d"]
    vecs = np.frombuffer(base64.b64decode(raw["v"]), dtype=np.int8).reshape(-1, dims).astype(np.float32) * raw["s"]
    weights = np.frombuffer(base64.b64decode(raw["w"]), dtype=np.float16).astype(np.float32)
    pieces = {p: i for i, p in enumerate(raw["p"])}

    # The phone will do this with a Viterbi walk over the unigram scores; here,
    # where the tokenizer is installed, use it and keep the probe honest about
    # the table rather than about the tokenizer.
    try:
        from transformers import AutoTokenizer
    except ImportError:
        need("transformers (for --probe)")
    tok = AutoTokenizer.from_pretrained(TEACHER)
    full = json.loads(tok.backend_tokenizer.to_str())["model"]["vocab"]
    rows = [pieces[full[i][0]] for i in tok(query, add_special_tokens=False)["input_ids"]
            if full[i][0] in pieces]
    if not rows:
        raise SystemExit("no word of that query is in the table")
    q = (vecs[rows] * weights[rows][:, None]).sum(0)
    q /= np.linalg.norm(q) or 1

    bynum = {m["num"]: m["name"] for m in BOOKS.values()}
    for f in sorted(OUT.glob("vec_*.js")):
        if f.name == "vec_table.js":
            continue
        line = f.read_text(encoding="utf-8").splitlines()[1]        # after the VEC guard
        one = json.loads(line[line.index("=") + 1:].rstrip().rstrip(";"))
        ids = np.frombuffer(base64.b64decode(one["i"]), dtype=np.int32)
        vv = np.frombuffer(base64.b64decode(one["v"]), dtype=np.int8).reshape(-1, one["d"]).astype(np.float32)
        score = (vv @ q) * one["s"]
        print(f"\n{f.stem[4:]}: “{query}”")
        for i in np.argsort(-score)[:8]:
            vid = int(ids[i])
            print(f"  {score[i]:.3f}  {bynum.get(vid // 1000000, '?')} "
                  f"{vid // 1000 % 1000}:{vid % 1000}")


if __name__ == "__main__":
    main()
