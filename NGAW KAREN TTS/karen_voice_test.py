#!/usr/bin/env python3
"""Test the Karen voice against a Karen speaker: word by word, by ear and by pitch.

    python "NGAW KAREN TTS/karen_voice_test.py" "NGAW KAREN TTS/audio/reference/vocab1.wav" --words "NGAW KAREN TTS/words/vocab1.json"
    python "NGAW KAREN TTS/karen_voice_test.py" "NGAW KAREN TTS/audio/reference/vocab1.wav" --words "NGAW KAREN TTS/words/vocab1.json" --pick 2 --per-word 2

Nobody on this side can hear whether the retuned Burmese voice (karen_speech.py)
passes for Karen, so the judge is a recording of a Karen speaker saying words
on their own - a vocabulary lesson - and the test is made twice over:

  by ear    one file, the speaker's word and then ours, for every word in
            turn, so a listener hears them side by side (audio/reference/*_ab.wav)
  by pitch  for each word, the speaker's pitch curve and length against ours,
            through the WORLD vocoder; and since each word's tone mark is
            known, the speaker's curves are averaged per tone - the measured
            table that should replace the guessed one in karen_speech.TONES

The recording is cut into words at its silences. The word list gives, in the
order spoken, the English and the Karen spelling, and says whether the
Karen Bible corpus confirmed that spelling (scripts/karen_names.py's method,
run on the lesson's words), since a curve measured on a wrong spelling would
teach a wrong tone. --per-word says how many times each word is spoken in the
recording and --pick which saying to use, because a lesson often says the
English first or the Karen twice.
"""
import argparse
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))   # books.py and friends
from karen_speech import SYLLABLE, TONES, PiperKaren, Voice, render, syllables, write_wav   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent          # the project
HERE = Path(__file__).resolve().parent                 # NGAW KAREN TTS
REPORT = HERE / "reports" / "karen_voice_test.md"          # _piper.md for the other engine

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def read_wav(path):
    with wave.open(str(path), "rb") as w:
        fs, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype={1: np.int8, 2: np.int16, 4: np.int32}[sw]).astype(np.float64)
    data /= float(2 ** (8 * sw - 1))
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, fs


def segments(wav, fs, min_len=0.12, gap=0.25, floor_db=-38):
    """(start, end) in samples of each stretch of speech, split at silences."""
    hop = int(fs * 0.01)
    frames = np.array([np.sqrt(np.mean(wav[i:i + hop] ** 2)) + 1e-9 for i in range(0, len(wav) - hop, hop)])
    db = 20 * np.log10(frames / max(frames.max(), 1e-9))
    loud = db > floor_db
    out, start = [], None
    for i, on in enumerate(list(loud) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            out.append([start, i])
            start = None
    merged = []
    for s, e in out:                                  # bridge short gaps inside a word
        if merged and s - merged[-1][1] < gap / 0.01:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s * hop, e * hop) for s, e in merged if (e - s) * 0.01 >= min_len]


def pitch(wav, fs):
    """Voiced pitch track in Hz (unvoiced frames dropped), 5 ms frames."""
    import pyworld as pw
    f0, _ = pw.harvest(np.ascontiguousarray(wav), fs, f0_floor=70, f0_ceil=400)
    return f0[f0 > 0]


def contour(wav, fs, base, points=20):
    """Voiced pitch in semitones from `base` - the speaker's middle over all
    their words, not this word's own, so a high tone and a low tone differ in
    height and not only in shape - resampled to `points`; plus the voiced length."""
    v = pitch(wav, fs)
    if len(v) < 3:
        return None, None, 0.0
    st = 12 * np.log2(v / base)
    idx = np.linspace(0, len(st) - 1, points)
    return np.interp(idx, np.arange(len(st)), st), float(np.median(v)), len(v) * 0.005


def last_tone(karen):
    marks = [m.group(4) or "" for m in SYLLABLE.finditer(karen)]
    return marks[-1] if marks else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", help="wav of the speaker, words separated by silence")
    ap.add_argument("--words", required=True, help="json: [{en, ksw, confirmed}] in the order spoken")
    ap.add_argument("--per-word", type=int, default=1, help="sayings per word in the recording")
    ap.add_argument("--pick", type=int, default=1, help="which saying to use, 1-based")
    ap.add_argument("--floor", type=float, default=-38, help="silence threshold, dB below the loudest frame")
    ap.add_argument("--engine", choices=["burmese", "piper", "mms"], default="burmese", help="which of our voices to test")
    ap.add_argument("--model", help="mms: the checkpoint to test (default: the newest run; \"base\" for the untrained Burmese voice)")
    a = ap.parse_args()

    wav, fs = read_wav(a.recording)
    words = json.loads(Path(a.words).read_text(encoding="utf-8"))
    segs = segments(wav, fs, floor_db=a.floor)
    print(f"{len(segs)} stretches of speech found; {len(words)} words x {a.per_word} sayings expected "
          f"({len(words) * a.per_word})")
    if all("after" in w and "before" in w for w in words):
        # The list says when each Karen word is spoken ("after" the English,
        # "before" the next item), taken from the video's own captions: a
        # lesson with music under it never falls silent, so counting stretches
        # in order would drift. The word is every stretch inside its window.
        chosen = []
        for w in words:
            # Cut inside the window alone, with the threshold relative to the
            # loudest thing in it - the Karen word - so a quiet word is not
            # lost to a loud one elsewhere, and a stretch that spills over the
            # window's edge is clipped rather than thrown away.
            lo, hi = int(w["after"] * fs), int(w["before"] * fs)
            inside = segments(wav[lo:hi], fs, floor_db=a.floor)
            if not inside:
                chosen.append(None)
                continue
            # The word is the loudest stretch in the window and whatever
            # touches it: a syllable can straddle a tiny dip, but a breath or
            # the music under the lesson does not.
            sub = wav[lo:hi]
            loudest = max(range(len(inside)), key=lambda i: float(np.abs(sub[inside[i][0]:inside[i][1]]).max()))
            start, end = inside[loudest]
            for s2, e2 in inside[loudest + 1:]:
                if s2 - end > 0.12 * fs:
                    break
                end = e2
            for s2, e2 in reversed(inside[:loudest]):
                if start - e2 > 0.12 * fs:
                    break
                start = s2
            chosen.append((lo + start, lo + end))
        missing = [w["en"] for w, c in zip(words, chosen) if c is None]
        if missing:
            print(f"no speech found in the window of: {', '.join(missing)} (raise --floor)")
        words, chosen = zip(*[(w, c) for w, c in zip(words, chosen) if c]) if any(chosen) else ([], [])
    else:
        if len(segs) < len(words) * a.per_word:
            print("fewer stretches than words: lower --floor, or check --per-word; matching the first ones in order")
        chosen = [segs[i * a.per_word + (a.pick - 1)] for i in range(min(len(words), len(segs) // a.per_word))]

    if a.engine == "mms":
        from train_mms import MmsKaren
        voice = MmsKaren(a.model)
    else:
        voice = PiperKaren() if a.engine == "piper" else Voice()
    # Each speaker's middle pitch over every word, the zero of the semitone scale below
    def middle(tracks):
        allv = np.concatenate(tracks) if tracks else np.array([])
        return float(np.median(allv)) if len(allv) else 180.0
    human_base = middle([pitch(wav[s:e], fs) for s, e in chosen])
    renders = [render(syllables(w["ksw"]), voice) if a.engine == "burmese" else voice.say(w["ksw"]) for w in words]
    ours_base = middle([pitch(r, voice.fs) for r in renders])
    print(f"speaker's middle pitch {human_base:.0f} Hz, our voice's {ours_base:.0f} Hz")
    rows, ab = [], []
    per_tone = {}
    for w, (s, e), ours in zip(words, chosen, renders):
        human = wav[s:e]
        if fs != voice.fs:                                 # bring the speaker to the voice's rate for the montage
            idx = np.linspace(0, len(human) - 1, int(len(human) * voice.fs / fs))
            human_rs = np.interp(idx, np.arange(len(human)), human)
        else:
            human_rs = human
        human_rs = human_rs / max(1e-9, np.abs(human_rs).max()) * 0.9
        ab += [human_rs, np.zeros(int(voice.fs * 0.4)), ours, np.zeros(int(voice.fs * 0.9))]
        hc, hmed, hdur = contour(human, fs, human_base)
        oc, omed, odur = contour(ours, voice.fs, ours_base)
        corr = float(np.corrcoef(hc, oc)[0, 1]) if hc is not None and oc is not None else float("nan")
        rows.append((w, hdur, odur, corr, hc))
        if w.get("confirmed") and hc is not None:
            per_tone.setdefault(last_tone(w["ksw"]), []).append((hc, hdur))

    out = Path(a.recording).with_name(Path(a.recording).stem + ("_ab.wav" if a.engine == "burmese" else f"_ab_{a.engine}.wav"))
    write_wav(np.concatenate(ab), voice.fs, out)

    lines = [f"# Karen voice against a speaker: {Path(a.recording).name}", "",
             f"{len(chosen)} words compared. Side by side: `{out}` (speaker, then our voice, per word).", "",
             "Pitch correlation is between the two words' pitch curves, each in semitones from its own middle; "
             "1.0 is the same shape, 0 no relation, negative the opposite movement. Length in seconds.", "",
             "| # | English | Karen | tone | speaker s | ours s | pitch corr | spelling |", "|---|---|---|---|---|---|---|---|"]
    for i, (w, hd, od, corr, _) in enumerate(rows, 1):
        lines.append(f"| {i} | {w['en']} | {w['ksw']} | {TONES[last_tone(w['ksw'])]['name']} | {hd:.2f} | {od:.2f} | "
                     f"{corr:.2f} | {'confirmed' if w.get('confirmed') else 'unverified'} |")
    lines += ["", "## The speaker's tones, measured", "",
              "Average pitch at the start, middle and end of the word's last syllable's tone, in semitones from the "
              "speaker's own middle, over the confirmed words with that tone; and the average length. Against the guessed "
              "table in karen_speech.TONES.", "",
              "| tone | words | measured start, mid, end | length s | guessed |", "|---|---|---|---|---|"]
    for mark, spec in TONES.items():
        got = per_tone.get(mark, [])
        if got:
            mean = np.mean([c for c, _ in got], axis=0)
            meas = f"{mean[0]:+.1f}, {mean[len(mean) // 2]:+.1f}, {mean[-1]:+.1f}"
            length = np.mean([d for _, d in got])
            lines.append(f"| {mark or '(none)'} {spec['name']} | {len(got)} | {meas} | {length:.2f} | {spec['pitch']} |")
        else:
            lines.append(f"| {mark or '(none)'} {spec['name']} | 0 | - | - | {spec['pitch']} |")
    report = REPORT if a.engine == "burmese" else REPORT.with_name(f"karen_voice_test_{a.engine}.md")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"side by side -> {out}\nreport -> {report}")
    for line in lines[6:6 + len(rows) + 2]:
        print(line)


if __name__ == "__main__":
    main()
