#!/usr/bin/env python3
"""What the Hakka voice is given to read, worked out ahead of time.

    python scripts/hakka_phonemes.py                 # every Hakka chapter -> models/hakka-student/phonemes/
    python scripts/hakka_phonemes.py John 1          # one chapter, printed

The Hakka voice (scripts/hakka_speech.py) never reads characters either: each
verse is cut at its sentence ends, and formog2p turns each sentence into
Sixian IPA, one syllable at a time - 'tʰ-ai_55', initial, final and tone.
That depends only on the text, so as for Taiwanese (taiwanese_phonemes.py) it
is done once, here, and the phone that reads it needs neither formog2p nor its
lexicons. scripts/hakka_student.py is the small voice that would read it.

This writes, per chapter, the very string the teacher voice was given for each
sentence, ' .' at its end, with the pause the recordings leave after it:
{"verses": [[n, [[sentence's spoken form, pause after it], ...]], ...]}. A
word formog2p cannot read reaches the teacher as its characters, and the
teacher says nothing for them; it is left out of the spoken form too, and
listed under "unread", so what the student learns to say is what was said.

It runs in the Hakka voice's environment, the one that has formog2p.
"""
import argparse
import gzip
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / "sources" / "hakka-tts" / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
# Into the voice's environment first, in UTF-8 mode, as hakka_speech.py goes itself: importing it from outside
# would start hakka_speech.py in there with this script's arguments.
if Path(sys.prefix).resolve() != VENV.resolve() or not sys.flags.utf8_mode:
    if not VENV_PY.exists():
        raise SystemExit("the Hakka voice's environment is not set up; see the top of scripts/hakka_speech.py")
    raise SystemExit(subprocess.call([str(VENV_PY), __file__, *sys.argv[1:]], env={**os.environ, "PYTHONUTF8": "1"},
                                     stdout=sys.stdout, stderr=sys.stderr))

sys.path.insert(0, str(Path(__file__).parent))
import hakka_speech as hs   # noqa: E402
from books import BOOKS     # noqa: E402
SYLLABLE = re.compile(r"^(?:[^-_\s]+-)?[^-_\s]+_\d+$")
# The pause after a sentence, as heard: the teacher puts 0.35 s of silence between the sentences of a verse and
# 0.7 s after it, and YourTTS leaves about 0.22 s more of its own either side of what it says, so in the
# recordings a sentence ends 0.80-0.85 s before the next begins and a verse 1.15-1.21 s. What is stored is that,
# less the 0.05 s the student's lessons keep either side (hakka_student.PAD).
SENTENCE_PAUSE = 0.7


def spoken(text):
    """A verse as the teacher reads it: each sentence's spoken form and the pause after it, and the words left
    unread. The spoken form is the teacher's own string - formog2p's words with their syllables joined by '|',
    a space between words, '，' where the voice pauses."""
    from formog2p.hakka import g2p
    out, unread = [], []
    for s in hs.sentences(text):
        r = g2p(s, hs.DIALECT[0], "ipa")
        words = []
        for p in r.pronunciations:
            syl = p.split()
            if p == "，":
                if words and words[-1] != "，":
                    words.append("，")
            elif syl and all(SYLLABLE.match(x) for x in syl):
                words.append("|".join(syl))
            else:
                unread.append(p)
        while words and words[-1] == "，":
            words.pop()
        while words and words[0] == "，":
            words.pop(0)
        if words:
            # ' .' where the voice ends a sentence, as taiwanese_phonemes.py ends each piece: the teacher was not
            # given it (it knows only the comma), but a lesson of a whole verse runs its sentences together, and
            # the student should see where the pause it hears between them comes from
            out.append([" ".join(words) + " .", SENTENCE_PAUSE])
    return out, unread


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS code, e.g. John (default: every chapter)")
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("--out", help="where the chapters go (default: models/hakka-student/phonemes)")
    a = ap.parse_args()
    out = Path(a.out) if a.out else ROOT / "models" / "hakka-student" / "phonemes"
    out.mkdir(parents=True, exist_ok=True)
    src = ROOT / "output" / "hak" / "json"
    if a.book:
        name = BOOKS[a.book]["name"].replace(" ", "_")
        files = [src / f"{name}_{a.chapter:02d}.json"] if a.chapter else sorted(src.glob(f"{name}_*.json"))
    else:
        files = sorted(src.glob("*.json"))
    raw = packed = 0
    unread_all = {}
    for f in files:
        verses = json.loads(f.read_text(encoding="utf-8"))["verses"]
        chapter, unread = {"verses": []}, []
        for n, t in verses.items():
            if not t.strip():
                continue
            ps, un = spoken(t)
            chapter["verses"].append([int(n), ps])
            unread += [[int(n), w] for w in un]
        if unread:
            chapter["unread"] = unread
            unread_all[f.stem] = len(unread)
        body = json.dumps(chapter, ensure_ascii=False, separators=(",", ":"))
        (out / f.name).write_text(body, encoding="utf-8")
        raw += len(body.encode("utf-8"))
        packed += len(gzip.compress(body.encode("utf-8"), 9))
        if a.book and a.chapter:
            for n, ps in chapter["verses"]:
                for p, g in ps:
                    print(n, g, p)
            for n, w in unread:
                print(f"  unread v{n}: {w}")
    print(f"{len(files)} chapters -> {out}: {raw / 1e6:.1f} MB as JSON, {packed / 1e6:.1f} MB gzipped chapter by "
          f"chapter; {sum(unread_all.values())} words unread in {len(unread_all)} chapters")


if __name__ == "__main__":
    main()
