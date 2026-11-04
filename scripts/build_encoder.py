#!/usr/bin/env python3
"""Search by meaning with the model itself on the phone: the encoder, and the verse vectors it is measured against.

    python scripts/build_encoder.py                      # every finished language -> site/model/
    python scripts/build_encoder.py --langs en,th
    python scripts/build_encoder.py --probe "the man thrown to the lions" --lang en

build_vectors.py made search by meaning possible on a phone by giving up the
model: a table holds what each word piece means on its own, and a question is
the weighted sum of its pieces. That is arithmetic and runs anywhere, and for
English it does well. For Thai it does badly, and the reason is in the method -
Thai is written without spaces and cut into short pieces that mean little alone,
so a table of pieces knows little about a Thai sentence. Measured on the same
questions, the table found the passage within the first five for two of eight
Thai questions; the model itself found five. English went from nine of fifteen
to twelve.

So this builds what lets the phone run the model. The Android app carries ONNX
Runtime, which runs it in under a second on an ordinary phone, offline; the
page asks the app through the AndroidApp bridge and is answered with verse
numbers. The reader in a browser has no such runtime, and keeps the table.

The encoder is multilingual-e5-small, made fit to carry:

  - its vocabulary cut to the pieces this project's text uses, with the common
    run every language shares, so a reader's own words are still understood.
    Below COMMON the ids are unchanged, which keeps <s>, <pad>, </s> and <unk>
    where the model expects them;
  - mean pooling and normalisation built into the graph, so the phone's whole
    job is one call;
  - its weights stored as int8, which is a quarter of the size and, measured
    against the full model, changes almost nothing.

The verse vectors are made by the same int8 model the phone runs, so a question
and a verse are measured with the same instrument. They are reduced from 384 to
192 dimensions by one projection fitted to every language at once (the phone
applies the same projection to the question): measured, 192 keeps nearly all
of what 384 finds, at half the size.

Written to site/model/ (gitignored: a model is made from its source, not kept
in git, and these files are rebuilt whenever the text changes):

    encoder.onnx      the model, int8
    vocab.tsv         the pruned vocabulary in id order: piece TAB unigram score
    proj.bin          the projection: "PROJ", in dims, out dims, mean, matrix (float32)
    vecm_<lang>.bin   the verses: "VECM", count, dims, scale, ids int32[], vectors int8[]

scripts/build_apk.py carries these when they are there. It wants torch,
transformers, onnx and onnxruntime; a GPU makes the verses a few minutes'
work, and a CPU makes them about five minutes a language.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                                  # noqa: E402
from books import BOOKS, TARGETS                                 # noqa: E402
from build_vectors import verses                                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "model"
TEACHER = "intfloat/multilingual-e5-small"
COMMON = 32000        # as in build_vectors.py: the low ids are every language's common subwords
DIMS = 192
MAXLEN = 128          # a verse with its topical line rarely passes this; a question never does
QUERY, PASSAGE = "query: ", "passage: "     # the prefixes e5 was trained with, on each side


def need(what):
    print(f"build_encoder.py needs {what} (pip install torch transformers onnx onnxruntime).", file=sys.stderr)
    raise SystemExit(2)


def export(tok, keep, path):
    """The model with its vocabulary cut to `keep`, pooling inside, as ONNX at float32."""
    import torch
    from transformers import AutoModel
    model = AutoModel.from_pretrained(TEACHER, attn_implementation="eager").eval()
    emb = model.embeddings.word_embeddings
    cut = torch.nn.Embedding(len(keep), emb.weight.shape[1], padding_idx=emb.padding_idx)
    cut.weight.data = emb.weight.data[torch.tensor(keep)].clone()
    model.embeddings.word_embeddings = cut
    model.config.vocab_size = len(keep)

    class Encoder(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            h = self.m(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            mask = attention_mask.unsqueeze(-1).to(h.dtype)
            pooled = (h * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return torch.nn.functional.normalize(pooled, dim=-1)

    sample = tok([QUERY + "the shepherd who leaves the ninety-nine"], return_tensors="pt")
    remap = {t: i for i, t in enumerate(keep)}
    ids = torch.tensor([[remap.get(int(t), remap[tok.unk_token_id]) for t in sample["input_ids"][0]]])
    torch.onnx.export(Encoder(model), (ids, sample["attention_mask"]), str(path), dynamo=False,
                      input_names=["input_ids", "attention_mask"], output_names=["embedding"],
                      dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                    "embedding": {0: "batch"}},
                      opset_version=17)


def quantize(src, dst):
    from onnxruntime.quantization import QuantType, quantize_dynamic
    quantize_dynamic(str(src), str(dst), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul", "Gather"])


class Runner:
    """The int8 encoder through onnxruntime, as the phone will run it."""

    def __init__(self, path, tok, keep):
        import onnxruntime as ort
        self.s = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.tok, self.remap = tok, {t: i for i, t in enumerate(keep)}

    def __call__(self, texts, batch=64):
        import numpy as np
        out = np.zeros((len(texts), 384), dtype=np.float32)
        # Shortest first, so a batch is padded only to the length of its own longest.
        enc = [self.tok(t, truncation=True, max_length=MAXLEN)["input_ids"] for t in texts]
        order = sorted(range(len(texts)), key=lambda i: len(enc[i]))
        unk = self.remap[self.tok.unk_token_id]
        t0 = time.time()
        for b in range(0, len(order), batch):
            idx = order[b:b + batch]
            n = max(len(enc[i]) for i in idx)
            ids = np.full((len(idx), n), self.remap[self.tok.pad_token_id], dtype=np.int64)
            mask = np.zeros((len(idx), n), dtype=np.int64)
            for r, i in enumerate(idx):
                ids[r, :len(enc[i])] = [self.remap.get(t, unk) for t in enc[i]]
                mask[r, :len(enc[i])] = 1
            out[idx] = self.s.run(None, {"input_ids": ids, "attention_mask": mask})[0]
            if len(texts) > 1000:
                print(f"    {min(b + batch, len(order))}/{len(order)} [{time.time() - t0:.0f}s]", end="\r", flush=True)
        if len(texts) > 1000:
            print()
        return out


def write_proj(mu, proj):
    import numpy as np
    with open(OUT / "proj.bin", "wb") as f:
        f.write(b"PROJ" + struct.pack("<ii", proj.shape[0], proj.shape[1]))
        f.write(mu.astype("<f4").tobytes() + np.ascontiguousarray(proj, dtype="<f4").tobytes())


def write_lang(code, ids, unit):
    import numpy as np
    scale = float(np.abs(unit).max()) or 1.0
    q = np.clip(np.rint(unit / scale * 127), -127, 127).astype(np.int8)
    p = OUT / f"vecm_{code}.bin"
    with open(p, "wb") as f:
        f.write(b"VECM" + struct.pack("<iif", len(ids), unit.shape[1], scale / 127))
        f.write(np.asarray(ids, dtype="<i4").tobytes() + q.tobytes())
    print(f"  {code}: {len(ids)} verses, {p.stat().st_size / 1e6:.1f} MB -> {p.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--langs", default="", help="which translations, comma separated (default: every complete one)")
    ap.add_argument("--dims", type=int, default=DIMS, help=f"dimensions kept per verse (default {DIMS})")
    ap.add_argument("--probe", default="", help="ask what was built a question, as the phone would")
    ap.add_argument("--lang", default="en", help="the language --probe searches")
    a = ap.parse_args()
    try:
        import numpy as np
        import onnxruntime  # noqa: F401
        from transformers import AutoTokenizer
    except ImportError:
        need("numpy, transformers and onnxruntime")
    tok = AutoTokenizer.from_pretrained(TEACHER)
    if a.probe:
        return probe(a.probe, a.lang, tok, np)
    try:
        import onnx  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        need("torch and onnx")

    whole = len(list((ROOT / "output" / "en" / "json").glob("*.json")))
    langs = [c.strip() for c in a.langs.split(",") if c.strip()] or [
        c for c in TARGETS if len(list((ROOT / "output" / c / "json").glob("*.json"))) >= whole]
    if not langs:
        raise SystemExit("no translation is complete — name one with --langs to build it anyway")
    corpus = {c: verses(c) for c in langs}
    print(f"languages: {', '.join(langs)}; verses: " + ", ".join(f"{c} {len(v)}" for c, v in corpus.items()))

    # ---- the vocabulary: every piece the passages use, the common run, and the prefixes
    used = set()
    for rows in corpus.values():
        for ids in tok([PASSAGE + t for _, t in rows], truncation=True, max_length=MAXLEN)["input_ids"]:
            used.update(ids)
    used.update(tok(QUERY)["input_ids"])
    keep = sorted(used | set(range(COMMON)))
    print(f"vocabulary: {len(keep)} pieces carried of {tok.vocab_size}")

    OUT.mkdir(parents=True, exist_ok=True)
    full = json.loads(tok.backend_tokenizer.to_str())["model"]["vocab"]
    with open(OUT / "vocab.tsv", "w", encoding="utf-8", newline="\n") as f:
        for i in keep:
            piece, score = full[i]
            f.write(f"{piece}\t{score:.6g}\n")

    # ---- the model
    raw = OUT / "encoder.fp32.onnx"
    export(tok, keep, raw)
    quantize(raw, OUT / "encoder.onnx")
    for p in OUT.glob("encoder.fp32.onnx*"):
        p.unlink()
    print(f"  encoder: {(OUT / 'encoder.onnx').stat().st_size / 1e6:.1f} MB, int8")
    run = Runner(OUT / "encoder.onnx", tok, keep)

    # ---- the verses, then one projection for all of them
    wide = {}
    for c, rows in corpus.items():
        print(f"  embedding {c}")
        wide[c] = run([PASSAGE + t for _, t in rows])
    allv = np.concatenate(list(wide.values()))
    mu = allv.mean(0)
    _, _, vt = np.linalg.svd(allv - mu, full_matrices=False)
    proj = vt[:a.dims].T.astype(np.float32)
    write_proj(mu, proj)
    for c, rows in corpus.items():
        v = (wide[c] - mu) @ proj
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        write_lang(c, [vid for vid, _ in rows], v)

    manifest.record("encoder", sum(len(r) for r in corpus.values()), "verse vectors",
                    f"search by meaning with the model on the phone ({', '.join(langs)})", "build_encoder.py")


def read_lang(code, np):
    b = (OUT / f"vecm_{code}.bin").read_bytes()
    assert b[:4] == b"VECM"
    n, d, s = struct.unpack("<iif", b[4:16])
    ids = np.frombuffer(b, "<i4", n, 16)
    return ids, np.frombuffer(b, np.int8, n * d, 16 + 4 * n).reshape(n, d).astype(np.float32) * s


def probe(query, lang, tok, np):
    """A question against the built files, the way the phone asks it."""
    if not (OUT / "encoder.onnx").exists():
        raise SystemExit("nothing built yet — run scripts/build_encoder.py first")
    pieces = [ln.split("\t")[0] for ln in (OUT / "vocab.tsv").read_text(encoding="utf-8").splitlines()]
    full = json.loads(tok.backend_tokenizer.to_str())["model"]["vocab"]
    at = {p: i for i, p in enumerate(pieces)}
    keep = [None] * len(pieces)
    for i, (p, _) in enumerate(full):
        if p in at:
            keep[at[p]] = i
    run = Runner(OUT / "encoder.onnx", tok, keep)
    b = (OUT / "proj.bin").read_bytes()
    din, dout = struct.unpack("<ii", b[4:12])
    mu = np.frombuffer(b, "<f4", din, 12)
    proj = np.frombuffer(b, "<f4", din * dout, 12 + 4 * din).reshape(din, dout)
    q = (run([QUERY + query])[0] - mu) @ proj
    q /= np.linalg.norm(q)
    ids, vv = read_lang(lang, np)
    score = vv @ q
    bynum = {m["num"]: m["name"] for m in BOOKS.values()}
    print(f"{lang}: “{query}”")
    for i in np.argsort(-score)[:8]:
        vid = int(ids[i])
        print(f"  {score[i]:.3f}  {bynum.get(vid // 1000000, '?')} {vid // 1000 % 1000}:{vid % 1000}")


if __name__ == "__main__":
    main()
