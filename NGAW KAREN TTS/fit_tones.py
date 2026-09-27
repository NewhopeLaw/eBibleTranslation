#!/usr/bin/env python3
"""Measure the Karen tones from every word cut so far, and refit the Piper mapping to them.

    python "NGAW KAREN TTS/fit_tones.py"              # report only
    python "NGAW KAREN TTS/fit_tones.py" --apply      # also write the best Vietnamese mapping into karen_phonemes.TONES

Two things come out, both into reports/tones.md:

  measured   for each tone mark, the speaker's pitch at the start, middle and
             end of the word's final syllable, in semitones from that
             speaker's own middle, averaged over the cuts whose spelling the
             corpus confirmed; and the length. This is the table Wade guessed
             at in 1861 and Emma Htoo's lesson gave a first reading of.
  fitted     the Vietnamese tone symbol and vowel length for each Karen tone
             that makes the Piper Vietnamese voice's pitch curves correlate
             best with the speaker's, all six adjusted together (coordinate
             descent on whole-word correlation). --apply writes it.

Only the final syllable's tone is attributed to a word's curve, so
monosyllables weigh most; a multi-syllable word still scores the fit, since
the fit is on the whole curve.
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
from karen_voice_test import contour, pitch, read_wav               # noqa: E402

HERE = Path(__file__).resolve().parent
INDEX = HERE / "audio" / "cuts" / "index.jsonl"
REPORT = HERE / "reports" / "tones.md"
OPTIONS = [(vi, long) for vi in ["", "ɜ", "2", "4", "5", "6"] for long in (False, True)]
VI_NAMES = {"": "ngang (level)", "ɜ": "sắc (high rising)", "2": "huyền (low falling)", "4": "hỏi (dipping)",
            "5": "ngã (rising, broken)", "6": "nặng (low, cut)"}

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def last_mark(karen):
    marks = [m.group(4) or "" for m in kp.SYLLABLE.finditer(karen)]
    return marks[-1] if marks else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", action="store_true", help="use unconfirmed spellings too")
    ap.add_argument("--speaker", default="", help="fit on one speaker's lessons only, e.g. vocab: whole words said "
                    "in a natural voice fit better than a teacher's flat isolated syllables")
    a = ap.parse_args()
    rows = [json.loads(l) for l in INDEX.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("confirmed") or a.all]
    if a.speaker:
        rows = [r for r in rows if r["lesson"].startswith(a.speaker)]
    # one middle pitch per lesson (each lesson may be a different speaker or recording)
    by_lesson = {}
    for r in rows:
        by_lesson.setdefault(r["lesson"], []).append(r)
    human = []
    for lesson, rs in by_lesson.items():
        wavs = [(r, read_wav(HERE / r["wav"])) for r in rs]
        tracks = [pitch(w, fs) for _, (w, fs) in wavs]
        base = float(np.median(np.concatenate([t for t in tracks if len(t)]))) if any(len(t) for t in tracks) else 180.0
        for (r, (w, fs)), t in zip(wavs, tracks):
            c, _, dur = contour(w, fs, base)
            if c is not None:
                human.append((r, c, dur))
    print(f"{len(human)} cuts with pitch from {len(by_lesson)} lessons")

    lines = ["# Karen tones, measured and fitted", "",
             f"{len(human)} word cuts with a pitch track, from lessons: {', '.join(sorted(by_lesson))}.", "",
             "## Measured", "",
             "Pitch at the start, middle and end of the word (semitones from the speaker's middle), averaged over the "
             "words whose final syllable carries the mark; and the average word length.", "",
             "| mark | Wade's name | words | start, mid, end | length s |", "|---|---|---|---|---|"]
    measured = {}
    for mark, spec in kp.TONES.items():
        got = [(c, d) for r, c, d in human if last_mark(r["ksw"]) == mark]
        if got:
            m = np.mean([c for c, _ in got], axis=0)
            measured[mark] = (len(got), m[0], m[len(m) // 2], m[-1], float(np.mean([d for _, d in got])))
            lines.append(f"| {mark or '(none)'} | {spec['name']} | {len(got)} | {m[0]:+.1f}, {m[len(m)//2]:+.1f}, {m[-1]:+.1f} | {np.mean([d for _, d in got]):.2f} |")
        else:
            lines.append(f"| {mark or '(none)'} | {spec['name']} | 0 | - | - |")

    # the fit
    from karen_speech import PiperKaren
    voice = PiperKaren()

    # A word's rendering depends only on the settings of the marks it contains,
    # so renders are cached by (word, those settings): most of a fitting round
    # changes one mark, and only the words carrying it are rendered again.
    cache = {}
    marks_of = {r["ksw"]: tuple(sorted({m.group(4) or "" for m in kp.SYLLABLE.finditer(r["ksw"])})) for r, _, _ in human}

    def render(word):
        key = (word, tuple((kp.TONES[m]["vi"], kp.TONES[m]["vi_long"]) for m in marks_of[word]))
        if key not in cache:
            x = voice.say(word)
            cache[key] = (x, pitch(x, voice.fs))
        return cache[key]

    def score():
        rends = [render(r["ksw"]) for r, _, _ in human]
        base = float(np.median(np.concatenate([t for _, t in rends if len(t)])))
        cs = []
        for (r, hc, _), (x, _) in zip(human, rends):
            oc = contour(x, voice.fs, base)[0]
            if oc is not None:
                cs.append(float(np.corrcoef(hc, oc)[0, 1]))
        return float(np.mean(cs))

    original = {m: (v["vi"], v["vi_long"]) for m, v in kp.TONES.items()}
    best = score()
    lines += ["", "## Fitted", "", f"Starting mapping scores {best:.2f} mean pitch correlation with the speakers.", ""]
    current = dict(original)
    for rnd in range(3):
        moved = False
        for mark in kp.TONES:
            keep = current[mark]
            for opt in OPTIONS:
                kp.TONES[mark]["vi"], kp.TONES[mark]["vi_long"] = opt
                s = score()
                if s > best + 0.005:
                    best, keep, moved = s, opt, True
            current[mark] = keep
            kp.TONES[mark]["vi"], kp.TONES[mark]["vi_long"] = keep
        lines.append(f"round {rnd + 1}: {best:.2f}")
        print(f"round {rnd + 1}: {best:.2f}  " + ", ".join(f"{m or '(none)'}={v or 'ngang'}{'L' if l else ''}" for m, (v, l) in current.items()), flush=True)
        if not moved:
            break
    lines += ["", "| mark | Wade's name | rides on | vowel | was |", "|---|---|---|---|---|"]
    for mark, (vi, long) in current.items():
        o = original[mark]
        lines.append(f"| {mark or '(none)'} | {kp.TONES[mark]['name']} | {VI_NAMES[vi]} | {'long' if long else 'short'} | "
                     f"{VI_NAMES[o[0]]}, {'long' if o[1] else 'short'} |")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    if a.apply:
        p = HERE / "karen_phonemes.py"
        s = p.read_text(encoding="utf-8")
        for mark, (vi, long) in current.items():
            pat = re.compile(r'(    "' + re.escape(mark) + r'":\s*\{[^\n]*?"vi": ")[^"]*(", "vi_long": )(True|False)')
            s, n = pat.subn(lambda m: m.group(1) + vi + m.group(2) + ("True" if long else "False"), s, count=1)
            if n != 1:
                print(f"could not write the mapping for {mark or '(none)'} into karen_phonemes.py")
        p.write_text(s, encoding="utf-8")
        print("mapping written into karen_phonemes.TONES")
    else:
        for mark in kp.TONES:
            kp.TONES[mark]["vi"], kp.TONES[mark]["vi_long"] = original[mark]


if __name__ == "__main__":
    main()
