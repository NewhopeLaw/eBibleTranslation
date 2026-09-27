#!/usr/bin/env python3
"""Cut a vocabulary lesson into Karen words: the syllabary's raw material and the voice's lessons.

    python "NGAW KAREN TTS/karen_lessons.py" vocab/01            # one lesson, by its key in audio/reference/index.json
    python "NGAW KAREN TTS/karen_lessons.py" --all                # every lesson that has a word list
    python "NGAW KAREN TTS/karen_lessons.py" vocab/01 --show      # print the windows it found

A lesson video says an English prompt and then the Karen word, once each,
over background music that never falls silent. Its automatic captions catch
the English prompts with times, and turn the Karen into gibberish; so the
prompts are matched, in order, against the lesson's word list
(words/<key>.json: en, ksw, confirmed), each match anchors a window that runs
from the end of the prompt to the start of the next, and the Karen word is
the loudest stretch of speech inside the window (karen_voice_test's method).

Each cut goes to audio/cuts/<lesson>/<n>.wav at 22050 Hz with a row in
audio/cuts/index.jsonl: the English, the Karen spelling, its phonemes, the
lesson, the time, whether the corpus confirmed the spelling. Those rows are
what karen_voice_test.py scores, what the tone fit averages, and what
train_voice.py feeds Piper: a word said by a Karen speaker beside the sounds
our notation says it is made of, which is how a new engine learns to say it.
"""
import argparse
import difflib
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import karen_phonemes as kp                                        # noqa: E402
from karen_voice_test import read_wav, segments, write_wav          # noqa: E402

HERE = Path(__file__).resolve().parent
REF = HERE / "audio" / "reference"
CUTS = HERE / "audio" / "cuts"
WORDS = HERE / "words"
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
STOP = {"to", "the", "a", "an", "i", "you", "we", "they", "he", "she", "it", "is", "are", "my", "your"}

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def caption_words(json3_path):
    """[(seconds, word)] from YouTube's automatic captions."""
    d = json.loads(Path(json3_path).read_text(encoding="utf-8"))
    out = []
    for ev in d.get("events", []):
        t0 = ev.get("tStartMs", 0)
        for s in ev.get("segs", []) or []:
            w = s.get("utf8", "").strip()
            if w and w != "\n":
                out.append(((t0 + s.get("tOffsetMs", 0)) / 1000, w.lower()))
    return out


def anchor(words, caps, show=False):
    """Give each word its window (after, before) by finding its English prompt in
    the captions, in order. A prompt is found when its content words appear in
    sequence within a short span after the previous anchor; the automatic
    captions mishear now and then, so a fuzzy match on each word is allowed."""
    pos = 0
    anchors = []
    last_t = 0.0

    # How the recogniser tends to hear the short prompts
    ALIAS = {"no": {"know"}, "ok": {"okay", "ok"}, "i": {"i", "hi", "eye"}, "we": {"we", "we're"}, "you": {"you", "you're"}}

    def same(heard, want):
        # a short word must match exactly ("no" is not "not"); a longer one may be misheard a little
        if heard in ALIAS.get(want, ()):
            return True
        return heard == want if len(want) <= 3 else difflib.SequenceMatcher(None, heard, want).ratio() >= 0.75

    # The list on screen runs in two columns and the speaker may read it row by
    # row, so each prompt is looked for anywhere, earliest unused occurrence
    # first, and the words are then put in the order they were spoken.
    used = set()
    for w in words:
        en = re.sub(r"\(.*?\)", "", w["en"]).lower()          # "(male)" is a gloss on screen, not something she says
        prompt = [t for t in WORD.findall(en) if t not in STOP] or WORD.findall(en)
        found = None
        for i in range(len(caps)):
            if i in used:
                continue
            j, k, first, hit = i, 0, None, []
            while k < len(prompt) and j < len(caps) and j < i + len(prompt) + 2:
                if j not in used and same(caps[j][1], prompt[k]):
                    if first is None:
                        first = j                     # the prompt starts at its first matched word, not where the scan began
                    hit.append(j)
                    k += 1
                j += 1
            if k == len(prompt):
                found = (caps[first][0], caps[j - 1][0])
                used.update(hit)
                break
        anchors.append(found)
    order = sorted(range(len(words)), key=lambda i: anchors[i][0] if anchors[i] else float("inf"))
    words[:] = [words[i] for i in order]
    anchors = [anchors[i] for i in order]
    windows = []
    for i, (w, a) in enumerate(zip(words, anchors)):
        nxt = next((b[0] for b in anchors[i + 1:] if b), None)
        if a is None:
            windows.append(None)
            continue
        after = a[1] + 0.55
        before = (nxt - 0.05) if nxt else after + 3.0
        windows.append((after, before))
        if show:
            print(f"  {w['en']:28} prompt at {a[0]:6.1f}-{a[1]:6.1f}  karen window {after:6.2f}-{before:6.2f}")
    return windows


def cut_word(wav, fs, after, before, floor=-18):
    lo, hi = int(after * fs), int(min(before, len(wav) / fs) * fs)
    if hi - lo < fs * 0.15:
        return None
    sub = wav[lo:hi]
    inside = segments(sub, fs, floor_db=floor)
    if not inside:
        return None
    k = max(range(len(inside)), key=lambda i: float(np.abs(sub[inside[i][0]:inside[i][1]]).max()))
    s, e = inside[k]
    for s2, e2 in inside[k + 1:]:
        if s2 - e > 0.12 * fs:
            break
        e = e2
    for s2, e2 in reversed(inside[:k]):
        if s - e2 > 0.12 * fs:
            break
        s = s2
    pad = int(fs * 0.02)
    return max(0, lo + s - pad), min(len(wav), lo + e + pad)


def process(key, index, show=False):
    entry = index[key]
    wav_path = Path(entry["wav"])
    if not wav_path.is_absolute():
        wav_path = HERE.parent / wav_path
    json3 = next(wav_path.parent.glob(wav_path.stem + "*.json3"), None)
    words_path = WORDS / (key.replace("/", "") + ".json")
    if not json3 or not words_path.exists():
        print(f"{key}: {'no captions' if not json3 else 'no word list ' + words_path.name}; skipped")
        return []
    words = json.loads(words_path.read_text(encoding="utf-8"))
    wav, fs = read_wav(wav_path)
    caps = caption_words(json3)
    windows = anchor(words, caps, show)
    out_dir = CUTS / key.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, missed = [], []
    for n, (w, win) in enumerate(zip(words, windows), 1):
        span = cut_word(wav, fs, *win) if win else None
        if not span:
            missed.append(w["en"])
            continue
        piece = wav[span[0]:span[1]]
        piece = piece / max(1e-9, np.abs(piece).max()) * 0.9
        path = out_dir / f"{n:02d}.wav"
        write_wav(piece, fs, path)
        items = kp.syllables(w["ksw"])
        rows.append({"lesson": key, "n": n, "en": w["en"], "ksw": w["ksw"], "confirmed": bool(w.get("confirmed")),
                     "ipa": kp.ipa(items), "piper": "".join(kp.piper(items)).strip(),
                     "syllables": sum(1 for k, _ in items if k == "syl"),
                     "wav": str(path.relative_to(HERE)), "start": round(span[0] / fs, 2), "end": round(span[1] / fs, 2),
                     "source": entry["id"]})
    print(f"{key}: {len(rows)} of {len(words)} words cut" + (f"; not found: {', '.join(missed)}" if missed else ""))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", help="lesson keys from audio/reference/index.json, e.g. vocab/01")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    index = json.loads((REF / "index.json").read_text(encoding="utf-8"))
    keys = [k for k in index if (WORDS / (k.replace("/", "") + ".json")).exists()] if a.all else a.keys
    rows = []
    for key in keys:
        rows += process(key, index, a.show)
    if rows:
        CUTS.mkdir(parents=True, exist_ok=True)
        old = []
        idx = CUTS / "index.jsonl"
        if idx.exists():
            done = {k for k in keys}
            old = [json.loads(l) for l in idx.read_text(encoding="utf-8").splitlines() if l.strip()]
            old = [r for r in old if r["lesson"] not in done]
        idx.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in old + rows), encoding="utf-8")
        print(f"{len(old) + len(rows)} word cuts in {idx}")


if __name__ == "__main__":
    main()
