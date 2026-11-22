#!/usr/bin/env python3
"""The APK's own workings, run on the PC, for the dashboard's mobile preview.

    python scripts/phone.py say John 1 1            # the phone's Taiwanese voice -> phone_say.wav
    python scripts/phone.py say John 1 1 hak        # its Hakka one
    python scripts/phone.py meaning en "the man thrown to the lions"

The dashboard's mobile switch shows the reader at a phone's size. Where the PC
and the APK differ underneath, the page cannot show the difference by its size
alone: on the PC Taiwanese and Hakka are played from the recordings, which the
APK does not carry, and the page searches by meaning with a table where the APK
asks the model itself. So the preview asks this instead, and this does what the
phone does, with the files the phone is given:

  - say: the Taiwanese or the Hakka student (scripts/taiwanese_student.py,
    scripts/hakka_student.py) from its int8 ONNX file and onnx/tokens.json, on
    the CPU, two threads, as ONNX Runtime on Android runs it - not the
    checkpoint, and not the GPU. A language whose student has not been
    exported has no phone voice.
  - meaning: the search model from site/model/ (scripts/build_encoder.py), the
    question cut into pieces by the same unigram search Meaning.java makes over
    vocab.tsv, run by ONNX Runtime and measured against vecm_<lang>.bin. This is
    Meaning.java written again in Python, line for line, so the page's side of
    the bridge can be tried here; the Java is checked on its own.

Both are slow the first time (a file is loaded) and quick after.
"""
from __future__ import annotations

import io
import json
import re
import struct
import sys
import threading
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402

STUDENTS = {"nan": ROOT / "models" / "taiwanese-student", "hak": ROOT / "models" / "hakka-student"}
MODEL = ROOT / "site" / "model"
SR = 22050
GAP_VERSE = 0.7
_lock = threading.Lock()
_cache: dict = {}


def _session(path, threads=2):
    """An ONNX Runtime session for a file, kept until the file changes."""
    import onnxruntime as ort
    key, stamp = str(path), path.stat().st_mtime
    got = _cache.get(key)
    if got and got[0] == stamp:
        return got[1]
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads              # a phone's two big cores, as Meaning.java asks for
    s = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    _cache[key] = (stamp, s)
    return s


# ------------------------------------------------------------------ the voice
def voice_state():
    """{lang: {made, run, mb}} for the phone voices there are files for."""
    out = {}
    for lang, home in STUDENTS.items():
        f, tok = home / "onnx" / "student.int8.onnx", home / "onnx" / "tokens.json"
        if f.exists() and tok.exists():
            t = json.loads(tok.read_text(encoding="utf-8"))
            out[lang] = {"made": f.stat().st_mtime, "run": t.get("run") or "", "mb": round(f.stat().st_size / 1e6, 1)}
    return out


def say(book, ch, v, lang="nan"):
    """One verse in the phone's Taiwanese or Hakka voice -> wav bytes, or raises LookupError saying why not."""
    import taiwanese_student as ts
    if lang not in STUDENTS:
        raise LookupError(f"the phone has no voice of its own for {lang!r}")
    home = STUDENTS[lang]
    which, script = ("Taiwanese", "taiwanese") if lang == "nan" else ("Hakka", "hakka")
    if lang not in voice_state():
        raise LookupError(f"the phone's {which} voice has not been exported yet ({script}_student.py export)")
    # the reader names a book as the files do (Genesis, 1_Samuel); a short key (Gen) is taken too
    name = f"{BOOKS[book]['name'].replace(' ', '_') if book in BOOKS else book}_{int(ch):02d}"
    phon = home / "phonemes" / f"{name}.json"
    if not phon.exists():
        raise LookupError(f"{name} has no spoken form worked out ({script}_phonemes.py)")
    pieces = dict(json.loads(phon.read_text(encoding="utf-8"))["verses"]).get(int(v))
    if not pieces:
        raise LookupError(f"{book} {ch}:{v} has no spoken form")
    t = json.loads((home / "onnx" / "tokens.json").read_text(encoding="utf-8"))
    vocab, ids, blank = ts.Vocab(t["tokens"]), t["ids"], t["blank"]
    if lang == "hak":                               # its own tokens, without setting the Taiwanese module for Hakka
        import hakka_student
        text = lambda p: hakka_student.text(vocab, p)   # noqa: E731
    else:
        text = vocab.text
    with _lock:
        s = _session(home / "onnx" / "student.int8.onnx")
        names = {i.name for i in s.get_inputs()}
        parts = []
        for p, gap in pieces:
            x = [blank] + [y for c in text(p) for y in (ids[c], blank)]
            feeds = {"input": np.array([x], np.int64), "input_lengths": np.array([len(x)], np.int64),
                     "scales": np.array(t["scales"], np.float32)}
            parts += [s.run(None, {k: a for k, a in feeds.items() if k in names})[0].reshape(-1),
                      np.zeros(int(SR * gap), np.float32)]
    audio = np.concatenate(parts[:-1])
    audio = audio / max(1e-9, float(np.abs(audio).max())) * 0.9
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()


# ------------------------------------------------------------------ search by meaning
QUERY, MAXLEN = "query: ", 128                     # as in Meaning.java and build_encoder.py


class _Meaning:
    def __init__(self):
        lines = (MODEL / "vocab.tsv").read_text(encoding="utf-8").split("\n")
        lines = [ln for ln in lines if ln]
        self.piece, self.score, self.max = {}, np.zeros(len(lines)), 0
        for i, ln in enumerate(lines):
            p, _, sc = ln.rpartition("\t")
            self.score[i] = float(sc)
            self.piece.setdefault(p, i)
            self.max = max(self.max, len(p))
        self.bos, self.eos, self.unk = self.piece["<s>"], self.piece["</s>"], self.piece["<unk>"]
        self.unk_score = min(0.0, self.score.min()) - 10
        b = (MODEL / "proj.bin").read_bytes()
        assert b[:4] == b"PROJ", "proj.bin is not a projection"
        din, dout = struct.unpack("<ii", b[4:12])
        self.mu = np.frombuffer(b, "<f4", din, 12)
        self.proj = np.frombuffer(b, "<f4", din * dout, 12 + 4 * din).reshape(din, dout)
        self.langs, self.stamp = {}, (MODEL / "encoder.onnx").stat().st_mtime

    def tokens(self, text):
        ids = [self.bos]
        for word in unicodedata.normalize("NFKC", QUERY + text).strip().split():
            cp = "▁" + word
            n = len(cp)
            best, frm, pc = [-np.inf] * (n + 1), [0] * (n + 1), [0] * (n + 1)
            best[0] = 0.0
            for i in range(n):
                if best[i] == -np.inf:
                    continue
                for j in range(i, min(n, i + self.max)):
                    r = self.piece.get(cp[i:j + 1])
                    if r is not None and best[i] + self.score[r] > best[j + 1]:
                        best[j + 1], frm[j + 1], pc[j + 1] = best[i] + self.score[r], i, r
                if best[i] + self.unk_score > best[i + 1]:
                    best[i + 1], frm[i + 1], pc[i + 1] = best[i] + self.unk_score, i, self.unk
            got, k = [], n
            while k > 0:
                got.insert(0, pc[k])
                k = frm[k]
            for g in got:
                if not (g == self.unk and ids and ids[-1] == self.unk):
                    ids.append(g)
        return ids[:MAXLEN - 1] + [self.eos]

    def verses(self, lang):
        if lang not in self.langs:
            b = (MODEL / f"vecm_{lang}.bin").read_bytes()
            assert b[:4] == b"VECM", f"vecm_{lang}.bin is not a verse file"
            n, d, s = struct.unpack("<iif", b[4:16])
            self.langs = {lang: (np.frombuffer(b, "<i4", n, 16),
                                 np.frombuffer(b, np.int8, n * d, 16 + 4 * n).reshape(n, d).astype(np.float32) * s)}
        return self.langs[lang]

    def nearest(self, lang, q, k):
        t = self.tokens(q)
        s = _session(MODEL / "encoder.onnx")
        e = s.run(None, {"input_ids": np.array([t], np.int64), "attention_mask": np.ones((1, len(t)), np.int64)})[0][0]
        v = (e - self.mu) @ self.proj
        v /= max(1e-6, float(np.linalg.norm(v)))
        ids, vv = self.verses(lang)
        score = vv @ v
        top = np.argsort(-score)[:k]
        return [[round(float(score[i]), 4), int(ids[i])] for i in top]


def meaning_langs():
    if not (MODEL / "encoder.onnx").exists():
        return []
    return sorted(p.stem[5:] for p in MODEL.glob("vecm_*.bin"))


def meaning(lang, q, k=12):
    """-> [[cosine, verse id], ...] for the k verses nearest the question, nearest first, as Meaning.nearest."""
    if lang not in meaning_langs():
        raise LookupError(f"no model verses for {lang} (build_encoder.py)")
    with _lock:
        m = _cache.get("meaning")
        if m is None or m.stamp != (MODEL / "encoder.onnx").stat().st_mtime:
            m = _cache["meaning"] = _Meaning()
        return m.nearest(lang, q, k)


def state():
    """What the preview has: the phone voices, and the languages the model can search."""
    return {"voice": voice_state(), "meaning": meaning_langs(),
            "loaded": "meaning" in _cache}


if __name__ == "__main__":
    if sys.argv[1:2] == ["say"]:
        t0 = time.time()
        Path("phone_say.wav").write_bytes(say(*sys.argv[2:6]))
        print(f"phone_say.wav in {time.time() - t0:.2f} s")
    elif sys.argv[1:2] == ["meaning"]:
        bynum = {m["num"]: k for k, m in BOOKS.items()}
        for sc, vid in meaning(sys.argv[2], " ".join(sys.argv[3:]), 8):
            print(f"  {sc:.3f}  {bynum.get(vid // 1000000, '?')} {vid // 1000 % 1000}:{vid % 1000}")
    else:
        print(json.dumps(state(), indent=1))
