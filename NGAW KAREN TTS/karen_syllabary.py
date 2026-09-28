#!/usr/bin/env python3
"""Speak Karen with the speaker's own recordings wherever we have the word, and a voice elsewhere.

    python "NGAW KAREN TTS/karen_syllabary.py" --text "ပှၤ ဟဲ လၢ ဟံၣ်"          # audio/ksw/hybrid.wav
    python "NGAW KAREN TTS/karen_syllabary.py" Gen 1 1-3 --show                # which words were real, which synthetic
    python "NGAW KAREN TTS/karen_syllabary.py" --coverage Gen 1                  # how much of a chapter the cuts cover

A neural voice trained on three minutes of Karen slurs, and a Vietnamese
voice reading Karen phonemes has an accent a villager cannot see through.
But the cuts under audio/cuts are the Karen speaker himself saying the
lesson words, and nothing is clearer than that. So this voice looks every
word of the text up in the cuts by its Karen spelling and plays the
recording when it has one - a whole word as one block, as the lessons give
them - and hands only the rest to the Piper engine. On the daily-life
vocabulary of the lessons it is the speaker; on a Bible verse it is mostly
Piper, and --coverage says exactly how much of each.

Words in the text are found as the longest spelled strings the cuts know,
scanning left to right within each space-separated stretch; Karen writes
spaces between phrases, not words, so a stretch may hold several words.
Recordings are level-matched and joined with short gaps; the seam between a
recording and a synthetic word is audible and meant to be, so a listener
knows which is which.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import karen_phonemes as kp                                        # noqa: E402
from karen_speech import PiperKaren, karen_verses, write_wav        # noqa: E402
from karen_voice_test import read_wav                               # noqa: E402

HERE = Path(__file__).resolve().parent
INDEX = HERE / "audio" / "cuts" / "index.jsonl"
OUT = HERE / "audio" / "ksw"
GAP_WORD, GAP_PHRASE, GAP_STOP = 0.06, 0.18, 0.5

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def load_cuts(confirmed_only=True, speaker="vocab"):
    """{karen spelling: wav path}; the shortest recording of a word when it was cut more than once.
    `speaker` keeps one voice: the vocabulary lessons' man or Emma Htoo ("emma");
    a sentence stitched from both changes speaker mid-word. "" takes both."""
    cuts = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if confirmed_only and not r.get("confirmed"):
            continue
        if speaker and not r["lesson"].startswith(speaker):
            continue
        k = r["ksw"].strip()
        if k not in cuts or (r["end"] - r["start"]) < cuts[k][1]:
            cuts[k] = (HERE / r["wav"], r["end"] - r["start"])
    return {k: v[0] for k, v in cuts.items()}


def segment(text, cuts):
    """[(kind, piece)]: ("real", karen word), ("synth", karen text), ("gap", seconds)."""
    out = []
    keys = sorted(cuts, key=len, reverse=True)
    for stretch in re.split(r"(\s+|[,.;:!?၊။])", text):
        if not stretch:
            continue
        if stretch.isspace():
            out.append(("gap", GAP_PHRASE))
            continue
        if stretch in ",.;:!?၊။":
            out.append(("gap", GAP_STOP))
            continue
        i, pending = 0, ""
        while i < len(stretch):
            hit = next((k for k in keys if stretch.startswith(k, i)), None)
            # a hit must end at a syllable boundary, or ဟံၣ် would be found inside ဟံၣ်ဖိ's first half only when whole
            if hit and (i + len(hit) == len(stretch) or kp.SYLLABLE.match(stretch, i + len(hit))):
                if pending:
                    out.append(("synth", pending))
                    pending = ""
                out.append(("real", hit))
                i += len(hit)
            else:
                m = kp.SYLLABLE.match(stretch, i)
                step = m.end() - i if m else 1
                pending += stretch[i:i + step]
                i += step
        if pending:
            out.append(("synth", pending))
    return out


def speak(items, cuts, voice, fs):
    parts = []
    for kind, piece in items:
        if kind == "gap":
            parts.append(np.zeros(int(fs * piece)))
        elif kind == "real":
            x, f0 = read_wav(cuts[piece])
            if f0 != fs:
                x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * fs / f0)), np.arange(len(x)), x)
            parts += [x / max(1e-9, np.abs(x).max()) * 0.8, np.zeros(int(fs * GAP_WORD))]
        else:
            x = voice.say(piece)
            if voice.fs != fs:
                x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * fs / voice.fs)), np.arange(len(x)), x)
            parts += [x / max(1e-9, np.abs(x).max()) * 0.6, np.zeros(int(fs * GAP_WORD))]
    return np.concatenate(parts) if parts else np.zeros(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?")
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("verses", nargs="?")
    ap.add_argument("--text")
    ap.add_argument("--out")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--coverage", action="store_true", help="report only: share of syllables the cuts cover")
    ap.add_argument("--all-cuts", action="store_true", help="use unconfirmed spellings too")
    ap.add_argument("--speaker", default="vocab", help="vocab (the lessons' man), emma, or '' for both")
    a = ap.parse_args()
    cuts = load_cuts(confirmed_only=not a.all_cuts, speaker=a.speaker)
    if a.text:
        texts = [a.text]
    else:
        if not (a.book and a.chapter):
            ap.error("give a book and chapter, or --text")
        lo, _, hi = (a.verses or "1-200").partition("-")
        texts = karen_verses(a.book, a.chapter, range(int(lo), int(hi or lo) + 1))
    items = []
    for t in texts:
        items += segment(t, cuts) + [("gap", GAP_STOP)]
    real = sum(len(kp.syllables(p)) for k, p in items if k == "real")
    synth = sum(len(kp.syllables(p)) for k, p in items if k == "synth")
    print(f"{len(cuts)} recorded words known; this text: {real} syllables from recordings, {synth} synthetic "
          f"({100 * real / max(1, real + synth):.0f}% real)")
    if a.show:
        print(" ".join(f"[{p}]" if k == "real" else p if k == "synth" else "" for k, p in items if k != "gap"))
    if a.coverage:
        return
    voice = PiperKaren(deterministic=False)
    fs = voice.fs
    audio = speak(items, cuts, voice, fs)
    out = Path(a.out) if a.out else OUT / (("hybrid_" + re.sub(r"\W+", "_", a.text)[:30]) if a.text
                                          else f"hybrid_{a.book}_{a.chapter}_{a.verses or 'all'}") .with_suffix(".wav")
    write_wav(audio, fs, out)
    print(f"{len(audio) / fs:.0f}s -> {out}")


if __name__ == "__main__":
    main()
