#!/usr/bin/env python3
"""Check a reading by the Karen voice against its text, syllable by syllable.

    python "NGAW KAREN TTS/check_reading.py" Matt 6 9-13 --model models/mms/karen-runs/emma-v1/G_e0200.pth

Getting a few phrases right first, and the rest follows: so this says, for
every syllable of a passage, where the voice said it and whether what it said
is what the spelling asks for, measured against Emma Htoo, whose course is the
authority on the sounds (phonics-emma-htoo.md):

  length  VITS decides how many frames each letter lasts, so each syllable's
          span is exact. Under 70 ms a syllable has been swallowed.
  vowel   The first two formants in the middle of the syllable, against the
          same measurement of Emma's own vowels (lesson 3, each vowel on အ).
          Karen reuses Burmese signs for other sounds - ိ is o, ီ is ɔ, ံ is i,
          ု is ɨ, ့ is e - and a voice that started Burmese can keep the
          Burmese vowel; this is where that shows.
  tone    The syllable's pitch against its clause's middle, in semitones,
          against where Karen readers put it (karen_tones: five readers of
          the Lord's Prayer, the tone mark and the syllable's place in the
          phrase). Emma's isolated paradigm is not used here: in running
          speech its unmarked syllable, low alone, comes out high.

The reading is rendered with a fixed seed and written beside the report, with
each clause as its own file too, so what is listened to is what was measured.
The measures are rough - formants from a plain LPC, pitch on short syllables -
so they point the ear at a syllable; the ear decides.
"""
import argparse
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import karen_phonemes as kp                                        # noqa: E402
from books import BOOKS                                             # noqa: E402
from karen_speech import karen_verses                               # noqa: E402
from karen_voice_test import pitch                                  # noqa: E402
import karen_tones as kt                                            # noqa: E402
import train_mms as tm                                              # noqa: E402

REPORTS = HERE / "reports"
AUDIO = HERE / "audio" / "ksw" / "check"

SWALLOWED = 0.07
# a syllable more than this many semitones from where the readers put it is
# flagged; a reader against the others' mean is off by about this much
TONE_OFF = 3.0
# Her open a and her ə gave no steady formants in lesson 3 (the notes say
# "unreliable"), so they are shown but not judged, and never offered as the
# vowel something "sounds" like.
UNSURE = {"a", "ə"}


def formants(x, fs):
    """F1 and F2 of the middle of a stretch: a plain LPC, median over 25 ms
    frames. Rough, but the same on Emma and on the voice."""
    import librosa
    from scipy.signal import resample_poly
    if len(x) < int(0.05 * fs):
        return None
    x = resample_poly(x, 10000, fs)
    mid = x[len(x) // 4: len(x) * 3 // 4]
    x = np.append(mid[0], mid[1:] - 0.97 * mid[:-1])
    got = []
    for i in range(0, len(x) - 250, 100):
        frame = x[i:i + 250] * np.hamming(250)
        if np.abs(frame).max() < 1e-4:
            continue
        a = librosa.lpc(frame, order=10)
        roots = [r for r in np.roots(a) if np.imag(r) > 0]
        fb = sorted((np.angle(r) * 10000 / (2 * np.pi), -np.log(np.abs(r)) * 10000 / np.pi) for r in roots)
        f = [hz for hz, bw in fb if 200 < hz < 4500 and bw < 500]
        if len(f) >= 2:
            got.append(f[:2])
    return np.median(np.array(got), axis=0) if got else None


def emma_vowels(fs):
    """Emma's nine vowels from her lesson 3 cuts, measured as the voice is."""
    rows = json.loads((HERE / "words" / "emma03_vowels.json").read_text(encoding="utf-8"))
    by = {}
    for r in rows:
        wav = HERE.parent / r["wav"].replace("\\", "/")
        if not wav.exists():
            continue
        f = formants(tm.read_audio(wav, fs).astype(np.float64), fs)
        if f is not None:
            by.setdefault(r["vowel"], []).append(f)
    return {v: np.median(np.array(fs_), axis=0) for v, fs_ in by.items()}


def syllable_spans(timings):
    """Group the voice's timings into Karen syllables. They come a syllable
    at a time from a respelling voice and a character at a time from the
    first runs; either way the pieces are laid end to end and cut again at
    the syllables."""
    out, i = [], 0
    while i < len(timings):
        clause = timings[i][0]
        pieces = []
        while i < len(timings) and timings[i][0] == clause:
            pieces.append(timings[i])
            i += 1
        text, owner = "", []
        for n, (_, piece, _, _) in enumerate(pieces):
            text += piece
            owner += [n] * len(piece)
        for m in kp.SYLLABLE.finditer(text):
            a, b = owner[m.start()], owner[m.end() - 1]
            out.append({"clause": clause, "syllable": m.group(0), "mark": m.group(4) or "",
                        "item": kp.syllables(m.group(0))[0][1], "t0": pieces[a][2], "t1": pieces[b][3]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("chapter", type=int)
    ap.add_argument("verses", help="e.g. 9-13")
    ap.add_argument("--model", default="base", help="base (the default) or a checkpoint")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tones", type=float, default=1.5, help="retuning strength, as karen_speech; 0 for the voice untouched")
    ap.add_argument("--lengths", type=float, default=1.0, help="syllable length strength, as karen_speech; 0 for the voice's own")
    a = ap.parse_args()

    import torch
    lo, _, hi = a.verses.partition("-")
    wanted = list(range(int(lo), int(hi or lo) + 1))
    verses = karen_verses(a.book, a.chapter, wanted)
    voice = tm.MmsKaren(a.model, deterministic=False, tones=a.tones, lengths=a.lengths)
    fs = voice.fs
    ref = emma_vowels(fs)
    name = f"{BOOKS[a.book]['name'].replace(' ', '_')}_{a.chapter:02d}_{a.verses}"
    AUDIO.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(a.seed)
    parts, rows, at = [], [], 0.0
    for v, karen in zip(wanted, verses):
        timings = []
        y = voice.say(karen, timings)
        for s in syllable_spans(timings):
            s.update(verse=v, t0=s["t0"] + at, t1=s["t1"] + at, audio=y[int(s["t0"] * fs):int(s["t1"] * fs)])
            rows.append(s)
        parts += [y, np.zeros(int(fs * 0.3))]
        at += (len(y) + int(fs * 0.3)) / fs
    audio = np.concatenate(parts)
    audio = audio / max(1e-9, np.abs(audio).max()) * 0.9
    tm.write_wav(audio, fs, AUDIO / f"{name}.wav")

    voiced = np.concatenate([pitch(r["audio"], fs) for r in rows if len(r["audio"]) > fs // 50] or [np.array([200.0])])
    middle = float(np.median(voiced))
    clauses = {}
    for r in rows:
        it = r["item"]
        r["ipa"] = it["onset"] + it["medial"] + it["vowel"]
        r["dur"] = r["t1"] - r["t0"]
        p = pitch(r["audio"], fs) if len(r["audio"]) > fs // 50 else np.array([])
        r["st"] = float(np.median(12 * np.log2(p / middle))) if len(p) >= 3 else None
        r["f"] = formants(r["audio"], fs)
        clauses.setdefault((r["verse"], r["clause"]), []).append(r)
    # tone: within each clause, is the syllable where the readers put it?
    # Both against the clause's own middle.
    for (v, clause), rs in clauses.items():
        known = [r["st"] for r in rs if r["st"] is not None]
        verse_clauses = kt.clauses(verses[wanted.index(v)])
        n = [c.strip() for c in verse_clauses].index(clause) if clause in [c.strip() for c in verse_clauses] else -1
        want = [t[1] for t in kt.targets(clause, n == len(verse_clauses) - 1)]
        if len(known) < 3 or len(want) != len(rs):
            continue
        mid = float(np.median(known))
        wmid = float(np.median([w for w, r in zip(want, rs) if r["st"] is not None]))
        for r, w in zip(rs, want):
            if r["st"] is None:
                continue
            r["tone"], r["want"] = r["st"] - mid, w - wmid
            if abs(r["tone"] - r["want"]) > TONE_OFF:
                r["tone_flag"] = f"{'high' if r['tone'] > r['want'] else 'low'} by {abs(r['tone'] - r['want']):.1f} st"

    lines = [f"# Reading check: {a.book} {a.chapter}:{a.verses}", "",
             f"Voice `{Path(a.model).name if a.model else 'newest'}`, seed {a.seed}. Listen: `{(AUDIO / (name + '.wav')).relative_to(HERE)}`; "
             f"each clause is also `{name}_<verse>_<n>.wav`.", "",
             "Length in seconds (under 0.07 = swallowed). Vowel: measured F1/F2 against Emma's (lesson 3); "
             "a and ə are shown but not judged, her own being unsteady. "
             f"Tone: semitones against the clause's middle, and in brackets where the readers put it "
             f"(karen_tones); off by more than {TONE_OFF:g} is flagged. Retuning strength {a.tones:g}.", ""]
    summary = {"syllables": len(rows), "swallowed": 0, "vowel": 0, "tone": 0}
    for (v, clause), rs in clauses.items():
        n = list(clauses).index((v, clause)) + 1
        t0, t1 = rs[0]["t0"], rs[-1]["t1"]
        tm.write_wav(audio[int(t0 * fs):int(t1 * fs) + int(0.05 * fs)], fs, AUDIO / f"{name}_{v}_{n}.wav")
        lines += [f"## {v}.{n} ({t0:.1f}-{t1:.1f} s): {clause}", "",
                  "| syllable | sounds | tone | at s | length | vowel F1/F2 (Emma) | tone st (readers) | check |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in rs:
            want = ref.get(r["item"]["vowel"])
            fcell = (f"{r['f'][0]:.0f}/{r['f'][1]:.0f}" if r["f"] is not None else "-") + \
                    (f" ({want[0]:.0f}/{want[1]:.0f})" if want is not None else "")
            flags = []
            if r["dur"] < SWALLOWED:
                flags.append("**swallowed**")
                summary["swallowed"] += 1
            if r["f"] is not None and want is not None and r["item"]["vowel"] not in UNSURE and (abs(np.log(r["f"][0] / want[0])) > 0.35 or abs(np.log(r["f"][1] / want[1])) > 0.3):
                near = min((v for v in ref if v not in UNSURE), key=lambda x: np.hypot(*np.log(r["f"] / ref[x]) * [1, 1.2]))
                if near != r["item"]["vowel"]:
                    flags.append(f"vowel sounds {near}")
                    summary["vowel"] += 1
            if r.get("tone_flag"):
                flags.append(r["tone_flag"])
                summary["tone"] += 1
            lines.append(f"| {r['syllable']} | {r['ipa']} | {kp.TONES[r['mark']]['name']} | {r['t0']:.2f} | {r['dur']:.2f} | "
                         f"{fcell} | {'-' if r.get('tone') is None else f"{r['tone']:+.1f} ({r['want']:+.1f})"} | {', '.join(flags)} |")
        lines.append("")
    lines[5:5] = [f"{summary['syllables']} syllables: {summary['swallowed']} swallowed, {summary['vowel']} with a vowel "
                  f"nearer another of Emma's, {summary['tone']} with a tone more than {TONE_OFF:g} st from the readers'.", ""]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / f"reading_check_{name}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[5])
    print("report ->", out)
    print("audio  ->", AUDIO / f"{name}.wav")
    print("Emma's vowels (F1/F2):", {v: f"{f[0]:.0f}/{f[1]:.0f}" for v, f in sorted(ref.items())})


if __name__ == "__main__":
    main()
