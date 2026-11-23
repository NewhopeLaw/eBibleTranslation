#!/usr/bin/env python3
"""A Hakka voice small enough for a phone, taught by the big one.

    python scripts/hakka_phonemes.py             # first, in the voice's environment: every chapter's spoken form
    python scripts/hakka_student.py cut          # the recordings cut into the sentences the teacher read -> data/
    python scripts/hakka_student.py train --resume newest [--minutes 360] [--duty 0.5]   (the dashboard's job)
    python scripts/hakka_student.py say John 1 1-5     # the student reads -> samples/
    python scripts/hakka_student.py sample       # the dashboard's sample verses from the newest checkpoint
    python scripts/hakka_student.py check [--only John_01]   # every verse against its recording, worst first
    python scripts/hakka_student.py export       # ONNX, as a phone would run it, and its speed on this CPU

The PC reads Hakka from chapter recordings (scripts/hakka_speech.py:
FormoSpeech's YourTTS, speaker XF, Sixian), which the APK cannot carry. This
is the same student as the Taiwanese one, and the same code: VITS at Piper's
"medium" size, about 15 M weights, taught from the teacher's own recordings
cut at the teacher's pauses (scripts/taiwanese_student.py, which says why;
docs/hakka-student.md for what is particular to Hakka). Only what the student
is given to read, and how the teacher spaces it, differ, and they are set
here before anything of the Taiwanese module runs.

What it reads is what the teacher was given: formog2p's Sixian IPA for each
sentence, worked out per chapter by scripts/hakka_phonemes.py. Each syllable
goes in as three tokens, its initial, final and tone, as for Taiwanese, so
's-oŋ_55|t-i_55' (上帝) is I:s F:oŋ T:55 - I:t F:i T:55, the hyphen joining
the syllables of one word.

Everything lives under models/hakka-student/ (gitignored). The voice it learns
from is CC BY-NC 4.0, and so is a voice taught from it (docs/hakka-student.md).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import taiwanese_student as ts   # noqa: E402

LANG, NAME = "hak", "hakka-student"
# The recordings' pauses are digital silence the teacher put in (hakka_speech.SENTENCE_GAP and VERSE_GAP) with
# about 0.22 s of YourTTS's own quiet either side, and nothing is cleaned after, so they are exact: 0.80-0.85 s
# between the sentences of a verse and 1.15-1.21 s between verses, in every chapter looked at, with nothing in
# between. The cuts sit in the middle of each gap.
VERSE_GAP = 1.0
PIECE_GAP = 0.6
# Between verses, as the student reads them out: the 1.15 s heard, less the 0.05 s its lessons keep either side.
VERSE_PAUSE = 1.05
# Syllables a second a lesson must fall within. XF reads at 3.3 a second, and 98 sentences in 100 between 2.8
# and 3.8 (40 New Testament chapters, 2026-11-22), far steadier than SuíSiann; one well outside is a cut in the
# wrong place.
RATE = (2.2, 4.6)
SYLLABLE = re.compile(r"^(?:([^-_\s]+)-)?([^-_\s]+)_(\d+)$")


def tokens(phon):
    """A spoken form ('tʰ-au_55 ， s-oŋ_55|t-i_55 .') -> tokens: per syllable its initial, final and tone, with the
    word gaps, the joins inside a word ('-'), the comma and the sentence end between, in the marks the Taiwanese
    student uses."""
    out = []
    for part in re.split(r"(\s+|\||，|,|\.)", phon.strip()):
        if not part:
            continue
        if part.isspace():
            if out and out[-1] != " ":
                out.append(" ")
            continue
        if part in ("|", "，", ",", "."):
            if out and out[-1] == " ":
                out.pop()
            out.append({"|": "-", "，": ","}.get(part, part))
            continue
        m = SYLLABLE.match(part)
        if not m:
            raise ValueError(f"not a syllable: {part!r} in {phon!r}")
        out += ["I:" + (m.group(1) or "∅"), "F:" + m.group(2), "T:" + m.group(3)]
    return out


def text(vocab, phon):
    """A spoken form as the characters the student's tokenizer reads (Vocab.text with Hakka's tokens), for
    scripts/phone.py, which reads both languages in one process and so cannot use() either."""
    return "".join(vocab.char[t] for t in tokens(phon))


def use():
    """Set the Taiwanese module for Hakka. Called before anything of it runs, in this script and in the data
    loader's workers (which Windows starts afresh by importing this file as __mp_main__), and not on a plain
    import, so a process that reads both languages (phone.py) keeps the Taiwanese one as it is."""
    ts.LANG, ts.NAME = LANG, NAME
    ts.tokens = tokens
    ts.GAP = {**ts.GAP, "verse": VERSE_PAUSE}
    ts.VERSE_GAP, ts.PIECE_GAP, ts.RATE = VERSE_GAP, PIECE_GAP, RATE


if __name__ in ("__main__", "__mp_main__"):
    use()

if __name__ == "__main__":
    ts.main()
