#!/usr/bin/env python3
"""The phone-sized Taiwanese and Hakka voices, put beside the reader for a browser to run.

    python scripts/build_voices.py            # -> site/voice/
    python scripts/build_voices.py --ort PATH  # the onnxruntime-web dist folder to take the runtime from

No phone or computer has a voice for Taiwanese or Hakka, and the recordings the
PC plays (audio/, about 1.5 GB for Taiwanese alone) are too big for GitHub
Pages and for the APK. The students (scripts/taiwanese_student.py,
scripts/hakka_student.py) were taught from those recordings to be small enough
for a phone - 16 MB each as int8 ONNX - and ONNX Runtime's web build runs them
in a browser: John 1:1 was read in under a second in Chrome, on one thread. So
the website reads a verse aloud the way the phone will, by making it there.

What the page needs is the model and, for every verse, the numbers the model
reads. Those are worked out here, from the same spoken forms the voice was
taught on, so the page needs no tokenizer and no knowledge of Hokkien or Hakka
sound: one file a book, fetched when a verse of that book is first heard.

Written to site/voice/ (committed: GitHub Pages publishes site/ as it stands):

    voices.json            what there is, for build_site.py to tell the page
    <lang>/student.onnx    the int8 model
    <lang>/<Book>.js       VOICEIDS["<lang>|<Book>"] = {ch: [[verse, [[ids, pause], ...]], ...]}
                           ids base64, one byte each, without the blanks between
                           them (the page puts those back), pause in seconds
    ort/                   onnxruntime-web's wasm build (MIT), pinned to ORT_VERSION

The voices are taught from SuíSiann (Taiwanese, CC BY-NC-SA) and FormoSpeech
(Hakka, CC BY-NC 4.0) and keep those terms; the page credits both.
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402
import taiwanese_student as ts   # noqa: E402

OUT = ROOT / "site" / "voice"
ORT_VERSION = "1.31.1"
ORT_FILES = ("ort.wasm.min.js", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm")
VOICES = {
    "nan": {"home": ROOT / "models" / "taiwanese-student", "text": None,
            "credit": "Taiwanese voice taught from recordings made with SuíSiann (CC BY-NC-SA)"},
    "hak": {"home": ROOT / "models" / "hakka-student", "text": "hakka",
            "credit": "Hakka voice taught from recordings made with FormoSpeech's YourTTS (CC BY-NC 4.0)"},
}


def text_of(lang, vocab):
    if VOICES[lang]["text"] == "hakka":
        import hakka_student
        return lambda p: hakka_student.text(vocab, p)
    return vocab.text


def build_lang(lang):
    v = VOICES[lang]
    model, tok = v["home"] / "onnx" / "student.int8.onnx", v["home"] / "onnx" / "tokens.json"
    if not (model.exists() and tok.exists()):
        print(f"{lang}: no exported student ({model}); left out")
        return None
    t = json.loads(tok.read_text(encoding="utf-8"))
    vocab, ids, blank = ts.Vocab(t["tokens"]), t["ids"], t["blank"]
    assert max(ids.values()) < 256, "the ids no longer fit a byte each"
    text = text_of(lang, vocab)
    out = OUT / lang
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy2(model, out / "student.onnx")
    books, verses, size = [], 0, 0
    for b in BOOKS.values():
        chapters = {}
        key = stem = b["name"].replace(" ", "_")          # as the reader names a book: Genesis, 1_Samuel
        for f in sorted(v["home"].glob(f"phonemes/{stem}_*.json"), key=lambda p: int(p.stem.rsplit("_", 1)[1])):
            ch = int(f.stem.rsplit("_", 1)[1])
            rows = []
            for n, pieces in json.loads(f.read_text(encoding="utf-8"))["verses"]:
                if pieces:
                    rows.append([n, [[base64.b64encode(bytes(ids[c] for c in text(p))).decode(), round(g, 2)]
                                     for p, g in pieces]])
            if rows:
                chapters[str(ch)] = rows
                verses += len(rows)
        if chapters:
            js = f"VOICEIDS[{json.dumps(lang + '|' + key)}]={json.dumps(chapters, separators=(',', ':'))};\n"
            (out / f"{key}.js").write_text(js, encoding="utf-8")
            books.append(key)
            size += len(js)
    print(f"{lang}: {verses} verses in {len(books)} books, {size // 1024} KB of ids, "
          f"model {model.stat().st_size / 1e6:.1f} MB (exported {time.strftime('%Y-%m-%d %H:%M', time.localtime(model.stat().st_mtime))})")
    return {"blank": blank, "scales": t["scales"], "sr": ts.SR, "books": books, "made": int(model.stat().st_mtime),
            "credit": v["credit"]}


def copy_ort(dist):
    dist = Path(dist)
    (OUT / "ort").mkdir(parents=True, exist_ok=True)
    for name in ORT_FILES:
        shutil.copy2(dist / name, OUT / "ort" / name)
    (OUT / "ort" / "VERSION").write_text(f"onnxruntime-web {ORT_VERSION} (MIT)\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ort", help=f"onnxruntime-web {ORT_VERSION}'s dist folder (npm pack onnxruntime-web@{ORT_VERSION}); "
                                  "needed the first time, kept after")
    a = ap.parse_args()
    if a.ort:
        copy_ort(a.ort)
    if not all((OUT / "ort" / n).exists() for n in ORT_FILES):
        raise SystemExit(f"site/voice/ort/ is missing the runtime: run with --ort, after npm pack onnxruntime-web@{ORT_VERSION}")
    made = {lang: got for lang in VOICES if (got := build_lang(lang))}
    (OUT / "voices.json").write_text(json.dumps(made, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"site/voice/voices.json: {', '.join(made) or 'no voices'}")


if __name__ == "__main__":
    main()
