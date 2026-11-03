#!/usr/bin/env python3
"""What the Taiwanese voice is given to read, worked out ahead of time.

    python scripts/taiwanese_phonemes.py                 # every Taiwanese chapter -> models/taiwanese-student/phonemes/
    python scripts/taiwanese_phonemes.py John 1          # one chapter, printed
    python scripts/taiwanese_phonemes.py --root "D:/Home/4. AI/eBibleTranslation"   # another checkout's text and dictionary

The voice (scripts/taiwanese_speech.py) never reads characters: each verse
is cut into pieces, the pieces turned into Tâi-lô from the MOE dictionary,
and the Tâi-lô into the spoken form with the tone sandhi applied. All of that
depends only on the text, and the Bible text does not change once it is made,
so it can be done once, on the PC, and the result carried beside the text -
a phone that reads it then needs neither the dictionaries nor the sandhi
toolkit (scripts/taiwanese_student.py is the small voice that would read it).

This writes, per chapter, the very strings the teacher voice was given:
{"verses": [[n, [[piece's spoken form, pause after it], ...]], ...]}. It
runs in the voice's own environment, which has the sandhi toolkit, and takes
the frontend from the checkout named by --root, so the pieces match the
recordings that checkout made.
"""
import argparse
import gzip
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def venv_python(root):
    return root / "sources" / "taiwanese-tts" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS code, e.g. John (default: every chapter)")
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("--root", default=str(ROOT), help="the checkout whose text, dictionary and frontend to use")
    ap.add_argument("--out", help="where the chapters go (default: <root>/models/taiwanese-student/phonemes)")
    a = ap.parse_args()
    root = Path(a.root).resolve()

    # Into the voice's environment, as taiwanese_speech.py does: it alone has 臺灣言語工具.
    if Path(sys.prefix).resolve() != venv_python(root).parent.parent.resolve() or not sys.flags.utf8_mode:
        if not venv_python(root).exists():
            raise SystemExit(f"the Taiwanese voice's environment is not set up under {root}; see scripts/taiwanese_speech.py")
        raise SystemExit(subprocess.call([str(venv_python(root)), __file__, *sys.argv[1:]],
                                         env={**os.environ, "PYTHONUTF8": "1"}, stdout=sys.stdout, stderr=sys.stderr))
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    sys.path.insert(0, str(root / "scripts"))
    ts = importlib.import_module("taiwanese_speech")
    from books import BOOKS
    from 臺灣言語工具.解析整理.拆文分析器 import 拆文分析器
    from 臺灣言語工具.語音合成 import 台灣話口語講法
    words, chars = ts.lexicon()

    def spoken(text):
        """A verse as the teacher reads it: its pieces' spoken forms and the pause after each (taiwanese_speech.read)."""
        text = re.sub(r"[「」『』（）()“”‘’]", "", text.replace("\n", "，"))
        out = []
        for piece, gap in ts.pieces(text):
            tailo, _ = ts.to_tailo(piece, words, chars)
            if not ts.syllables(tailo):
                continue
            try:
                phon = 台灣話口語講法(拆文分析器.對齊句物件(tailo, tailo)).strip()
            except Exception:                      # noqa: BLE001 - the teacher skips these too
                continue
            out.append([phon + ("" if tailo.rstrip()[-1:] in ".?" else " ."), gap])
        return out

    out = Path(a.out) if a.out else root / "models" / "taiwanese-student" / "phonemes"
    out.mkdir(parents=True, exist_ok=True)
    src = root / "output" / "nan" / "json"
    if a.book:
        name = BOOKS[a.book]["name"].replace(" ", "_")
        files = [src / f"{name}_{a.chapter:02d}.json"] if a.chapter else sorted(src.glob(f"{name}_*.json"))
    else:
        files = sorted(src.glob("*.json"))
    raw = packed = 0
    for f in files:
        verses = json.loads(f.read_text(encoding="utf-8"))["verses"]
        chapter = {"verses": [[int(n), spoken(t)] for n, t in verses.items() if t.strip()]}
        body = json.dumps(chapter, ensure_ascii=False, separators=(",", ":"))
        (out / f.name).write_text(body, encoding="utf-8")
        raw += len(body.encode("utf-8"))
        packed += len(gzip.compress(body.encode("utf-8"), 9))
        if a.book and a.chapter:
            for n, ps in chapter["verses"]:
                for p, g in ps:
                    print(n, g, p)
    print(f"{len(files)} chapters -> {out}: {raw / 1e6:.1f} MB as JSON, {packed / 1e6:.1f} MB gzipped chapter by chapter")


if __name__ == "__main__":
    main()
