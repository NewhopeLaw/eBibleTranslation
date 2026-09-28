#!/usr/bin/env python3
"""The pitch of Karen read aloud, learnt from Karen readers, for the voice to be retuned to.

    python "NGAW KAREN TTS/karen_tones.py" --fit         # from reports/reader_syllable_pitch.json (calibrate_speakers.py)

A tone table - each tone mark its curve - was the first idea, from Emma
Htoo's paradigm, and it fails on connected speech. Five readers of the
Lord's Prayer (calibrate_speakers.py), each syllable's pitch in semitones
from that reader's verse median, agree with each other (a reader against
the others' mean, r = 0.63); but the tone marks alone predict that shared
pitch at r = 0.29 on the verses they were fitted on and 0.0 on verses they
were not, and Emma's table 0.0 too. In running speech the unmarked syllable
she says low comes out high. Pitch there is mostly the phrase: it falls
through each clause and lifts on the last syllable.

So the target is a small linear model of the readers' mean, over what a
syllable is and where it stands (FEATURES): its tone mark, its place in the
clause, whether it is a light prefix (a bare consonant, တ- က-) or a short
ə, its onset and its vowel. Fitted on verses 9-11 it predicts 12-13, which
it never saw, at r = 0.65 - as well as one reader predicts the others. The
weights below are fitted on all five verses. Within a syllable the curve
takes the readers' average shape for its mark (SHAPES), start, middle and
end about the syllable's level.

Among the marks the readers keep Emma's order where it counts - ၣ် high,
ာ် lowest - and a full unmarked syllable sits high where a prefix sits low,
which is what made her isolated "unmarked is low" mislead.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import karen_phonemes as kp                                        # noqa: E402

READERS = HERE / "reports" / "reader_syllable_pitch.json"
READER_LENGTHS = HERE / "reports" / "reader_syllable_length.json"
MARKS = ["", "ၤ", "ၢ်", "ၣ်", "ာ်", "း"]
VOICELESS = {"k", "t", "p", "s", "θ", "ʃ", "x", "h", "tʃ"}

# Fitted by --fit on the five readers, all of Matthew 6:9-13 (146 syllables).
WEIGHTS = {"aspirated": -0.855, "first": -0.661, "high vowel": 1.301, "last": 2.38, "last clause": 0.258, "mark none": 2.549, "mark ာ်": -1.722, "mark း": 0.652, "mark ၢ်": -0.151, "mark ၣ်": 1.237, "mark ၤ": -0.499, "position": -5.49, "prefix": -2.759, "short": -0.577, "voiceless": -0.097}
SHAPES = {"": [-0.3, -0.34], "ၤ": [0.29, -0.54], "ၢ်": [0.0, 0.02], "ၣ်": [0.2, -0.92], "ာ်": [0.5, -1.03], "း": [0.11, -0.59]}
# Syllable length, log of the syllable's length over its reader's median in
# the verse, fitted by --fit the same way (reports/reader_syllable_length.json).
LENGTHS = {"aspirated": 0.231, "first": -0.146, "high vowel": -0.07, "last": 0.155, "last clause": 0.086, "mark none": 0.138, "mark ာ်": 0.226, "mark း": -0.129, "mark ၢ်": 0.01, "mark ၣ်": -0.198, "mark ၤ": -0.005, "position": -0.157, "prefix": -0.602, "short": -0.046, "voiceless": 0.184}


def features(syllables, i, clause_last):
    """One syllable, among the syllables of its clause (kp.SYLLABLE matches)."""
    m = syllables[i]
    it = kp.syllables(m.group(0))[0][1]
    mark = m.group(4) or ""
    n = len(syllables)
    f = {"mark " + (mark or "none"): 1.0,
         "position": i / max(1, n - 1), "first": float(i == 0), "last": float(i == n - 1),
         "last clause": float(clause_last),
         "aspirated": float("ʰ" in it["onset"]), "voiceless": float(it["onset"] in VOICELESS),
         "prefix": float(it["vowel"] == "a" and not mark and m.group(3) is None),
         "short": float(it["short"]), "high vowel": float(it["vowel"] in ("i", "u", "ɨ"))}
    return f


def clauses(verse):
    return [c for c in re.split(r"[,.၊။]", verse) if c.strip()]


def targets(clause, clause_last, weights=None, shapes=None):
    """(start, middle, end) semitones for each syllable of a clause, about its
    own mean: what to retune the voice to."""
    weights, shapes = weights or WEIGHTS, shapes or SHAPES
    sy = list(kp.SYLLABLE.finditer(clause))
    levels = [sum(weights.get(k, 0.0) * v for k, v in features(sy, i, clause_last).items()) for i in range(len(sy))]
    mid = float(np.mean(levels)) if levels else 0.0
    out = []
    for m, lv in zip(sy, levels):
        s, e = shapes.get(m.group(4) or "", (0.0, 0.0))
        out.append((lv - mid + s, lv - mid, lv - mid + e))
    return out


def lengths(clause, clause_last, weights=None):
    """Each syllable's length relative to the clause's average syllable, as
    Karen readers give it: 1.0 average, 0.55 a light prefix."""
    weights = weights or LENGTHS
    sy = list(kp.SYLLABLE.finditer(clause))
    logs = np.array([sum(weights.get(k, 0.0) * v for k, v in features(sy, i, clause_last).items()) for i in range(len(sy))])
    return list(np.exp(logs - logs.mean())) if len(logs) else []


def passage_features():
    """The features of every syllable of Matthew 6:9-13, with its verse and mark."""
    from karen_speech import karen_verses
    rows, verse_of, marks = [], [], []
    for v, text in enumerate(karen_verses("Matt", 6, range(9, 14))):
        cl = clauses(text)
        for ci, c in enumerate(cl):
            sy = list(kp.SYLLABLE.finditer(c))
            for i in range(len(sy)):
                rows.append(features(sy, i, ci == len(cl) - 1))
                verse_of.append(v)
                marks.append(sy[i].group(4) or "")
    return rows, np.array(verse_of), np.array(marks)


def fit_lengths(train_verses=None):
    """Least squares on the readers' mean log length per syllable; returns
    weights and r on the verses held out (if any)."""
    d = json.loads(READER_LENGTHS.read_text(encoding="utf-8"))
    y = np.nanmean(np.array([[np.nan if r[2] is None else r[2] for r in rows] for rows in d.values()]), 0)
    rows, verse_of, _ = passage_features()
    names = sorted({k for r in rows for k in r})
    A = np.c_[np.array([[r.get(k, 0.0) for k in names] for r in rows]), np.ones(len(rows))]
    ok = ~np.isnan(y)
    train = ok & (np.isin(verse_of, train_verses) if train_verses is not None else True)
    w, *_ = np.linalg.lstsq(A[train], y[train], rcond=None)
    held = ok & ~train
    r = float(np.corrcoef((A @ w)[held], y[held])[0, 1]) if held.any() else None
    return {k: round(float(x), 3) for k, x in zip(names, w[:-1])}, r


def fit(train_verses=None):
    """Least squares on the readers' mean pitch per syllable; returns weights,
    shapes, and r on the verses held out (if any)."""
    d = json.loads(READERS.read_text(encoding="utf-8"))
    S = np.array([[[np.nan] * 3 if r[2] is None else r[2:5] for r in rows] for rows in d.values()])
    mean = np.nanmean(S, 0)                                            # syllable x (start, mid, end)
    rows, verse_of, marks = passage_features()
    assert len(rows) == len(mean), (len(rows), len(mean))
    names = sorted({k for r in rows for k in r})
    X = np.array([[r.get(k, 0.0) for k in names] for r in rows])
    y = np.nanmean(mean, 1)
    ok = ~np.isnan(y)
    train = ok & (np.isin(verse_of, train_verses) if train_verses is not None else True)
    A = np.c_[X, np.ones(len(X))]
    w, *_ = np.linalg.lstsq(A[train], y[train], rcond=None)
    weights = {k: round(float(x), 3) for k, x in zip(names, w[:-1])}
    shapes = {}
    for mk in MARKS:
        sel = train & (np.array(marks) == mk)
        c = np.nanmean(mean[sel], 0) if sel.any() else np.zeros(3)
        shapes[mk] = (round(float(c[0] - c[1]), 2), round(float(c[2] - c[1]), 2))
    held = ok & ~train
    r = float(np.corrcoef((A @ w)[held], y[held])[0, 1]) if held.any() else None
    return weights, shapes, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true", help="fit on 9-11, test on 12-13, then fit on all and write the weights here")
    a = ap.parse_args()
    if a.fit:
        _, _, r = fit(train_verses=[0, 1, 2])
        print(f"fitted on 9-11, unseen 12-13: r = {r:.2f}")
        weights, shapes, _ = fit()
        _, r = fit_lengths(train_verses=[0, 1, 2])
        print(f"length, fitted on 9-11, unseen 12-13: r = {r:.2f}")
        length, _ = fit_lengths()
        src = Path(__file__).read_text(encoding="utf-8")
        src = re.sub(r"^LENGTHS = .*$", "LENGTHS = " + json.dumps(length, ensure_ascii=False), src, count=1, flags=re.M)
        src = re.sub(r"^WEIGHTS = .*$", "WEIGHTS = " + json.dumps(weights, ensure_ascii=False), src, count=1, flags=re.M)
        src = re.sub(r"^SHAPES = .*$", "SHAPES = " + json.dumps(shapes, ensure_ascii=False), src, count=1, flags=re.M)
        Path(__file__).write_text(src, encoding="utf-8")
        print("weights:", weights)
        print("shapes:", shapes)
        print("lengths:", length)


if __name__ == "__main__":
    main()
