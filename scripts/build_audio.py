#!/usr/bin/env python3
"""Make the recorded readings ready for the reader.

    python scripts/build_audio.py              # every language recorded in audio/
    python scripts/build_audio.py --lang nan   # only this one

The Taiwanese and Hakka voices (taiwanese_speech.py, hakka_speech.py) write a
WAV a chapter into audio/<lang>/ - 3 GB for the Taiwanese New Testament alone,
far too much to put in front of a reader. This takes each one to
site/audio/<lang>/ as Opus at about 28 kbps, around 1.5 MB a chapter (speech
loses nothing a listener hears at that rate), and writes site/audio/<lang>.json
saying where each verse is in it, by book and chapter. build_site.py builds that into the page, so
that Listen plays the verses held rather than the whole chapter. No phone or
computer has a Taiwanese or Hakka voice of its own; these recordings are the
only way either language is heard.

Where each verse is comes from the timings the voices now write beside each
chapter. Chapters recorded before they did are measured instead (place): the
voice leaves a longer pause after a verse than inside one, and verses take
time roughly in proportion to their syllables, so the verse ends are the
pauses that divide the chapter best by its text. Over the 1189 Hakka chapters
every verse end it chose is on a pause of 0.85 s or more, as a verse's own
pause is. Over the 251 Taiwanese ones, 27 have one verse end on a shorter
pause: where the Taiwanese voice stopped for two seconds inside a verse, the
verse ends either side of it can be a clause out (John 8:25-27). The rest of
those chapters are unaffected, and anything recorded from now on carries its
own timings.

A recording whose text has changed since it was made is left out: its verses
no longer say what the page says, and the voice's job records it again.
Neither the WAVs nor what is made from them are in git (audio/ is ignored).
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "audio"
OUT = ROOT / "site" / "audio"
RATE = 24000              # Opus takes 8, 12, 16, 24 or 48 kHz; the voices make 22.05
LEVEL = 0.9               # libsndfile's Opus compression level: 0.9 is ~28 kbps for this speech
HAN = re.compile(r"[㐀-鿿\U00020000-\U0003ffff]")
NUM = {b["name"].replace(" ", "_"): b["num"] for b in BOOKS.values()}   # the reader knows a book by this name


def chapters(lang):
    """(book, chapter, recording, text) for every whole-chapter recording;
    the trial readings beside them (Matthew_05_1-8_bigvgan.wav) are not chapters."""
    for wav in sorted((AUDIO / lang).glob("*.wav")):
        m = re.fullmatch(r"(.+)_(\d{2,3})", wav.stem)
        if m and m.group(1) in NUM:
            yield m.group(1), int(m.group(2)), wav, ROOT / "output" / lang / "json" / f"{wav.stem}.json"


def verses_of(text):
    """The verses the voice read, in the order it read them (as verses_of in the voices)."""
    verses = json.loads(text.read_text(encoding="utf-8"))["verses"]
    return [(int(n), t) for n, t in verses.items() if t.strip()]


def silences(a, fs):
    """Every pause of 0.15 s or more, as (start, end) in seconds, and the length.
    Quiet is 40 dB under the loudest moment: the voices' pauses are digital
    silence, softened a little where the Taiwanese has been cleaned."""
    hop = fs // 100
    n = len(a) // hop
    rms = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1))
    quiet = rms < 10 ** (-40 / 20) * max(1e-9, float(np.abs(a).max()))
    edges = np.flatnonzero(np.diff(np.r_[0, quiet.astype(np.int8), 0]))
    return [(s / 100, e / 100) for s, e in zip(edges[::2], edges[1::2]) if e - s >= 15], n / 100


def place(passage, a, fs):
    """(verse, start, end) for a recording made without timings.

    Each verse is given a share of the chapter by its syllables (and a few
    more for the pause after it), and the verse ends are chosen among the
    pauses by dynamic programming: a long pause counts for a boundary, and a
    verse far from its share counts against one."""
    sil, total = silences(a, fs)
    lead = sil[0][1] if sil and sil[0][0] == 0 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= total - 0.02 else total
    inner = [s for s in sil if s[0] > lead and s[1] < tail]
    n = len(passage)
    if n == 1:
        return [(passage[0][0], lead, tail)]
    if len(inner) < n - 1:
        return None
    w = np.array([len(HAN.findall(t)) + 4.0 for _, t in passage])
    share = w / w.sum() * (tail - lead)
    mids = np.array([(s + e) / 2 for s, e in inner])
    lens = np.minimum(np.array([e - s for s, e in inner]), 1.6)
    fit = lambda d, x: -((d - x) / (0.15 * x + 1.0)) ** 2     # noqa: E731
    best = np.full((n - 1, len(inner)), -1e18)
    back = np.zeros((n - 1, len(inner)), dtype=int)
    best[0] = fit(mids - lead, share[0]) + 6 * lens
    for k in range(1, n - 1):
        for j in range(k, len(inner)):
            sc = best[k - 1, :j] + fit(mids[j] - mids[:j], share[k])
            i = int(np.argmax(sc))
            best[k, j], back[k, j] = sc[i] + 6 * lens[j], i
    j = int(np.argmax(best[n - 2] + fit(tail - mids, share[n - 1])))
    ends = [j]
    for k in range(n - 2, 0, -1):
        j = back[k, j]
        ends.append(j)
    ends.reverse()
    starts = [lead] + [inner[j][1] for j in ends]
    stops = [inner[j][0] for j in ends] + [tail]
    return [(v, s, e) for (v, _), s, e in zip(passage, starts, stops)]


def make(job):
    """One chapter: its Opus, if the WAV is newer, and its verse timings."""
    lang, book, ch, wav, text = job
    if not text.exists() or text.stat().st_mtime > wav.stat().st_mtime:
        return book, ch, None, "stale"
    try:
        a, fs = sf.read(str(wav), dtype="float32")
    except (RuntimeError, sf.LibsndfileError):              # still being written by the voice's job
        return book, ch, None, "unreadable"
    passage = verses_of(text)
    side, how = wav.with_suffix(".json"), "timed"
    times = None
    if side.exists() and side.stat().st_mtime >= wav.stat().st_mtime - 5:
        times = json.loads(side.read_text(encoding="utf-8"))["verses"]
    if not times:
        times, how = place(passage, a, fs), "measured"
    if not times:
        return book, ch, None, "unplaced"
    ogg = OUT / lang / f"{wav.stem}.ogg"
    if not ogg.exists() or ogg.stat().st_mtime < wav.stat().st_mtime:
        ogg.parent.mkdir(parents=True, exist_ok=True)
        g = gcd(RATE, fs)
        sf.write(str(ogg), resample_poly(a, RATE // g, fs // g).astype(np.float32), RATE,
                 format="OGG", subtype="OPUS", compression_level=LEVEL)
    return book, ch, [[int(v), round(float(s), 2), round(float(e), 2)] for v, s, e in times], how


def build(lang, workers):
    t0 = time.time()
    jobs = [(lang, *c) for c in chapters(lang)]
    made, counts = {}, {}
    with ProcessPoolExecutor(workers) as pool:
        for book, ch, times, how in pool.map(make, jobs, chunksize=4):
            counts[how] = counts.get(how, 0) + 1
            if times:
                made[(book, ch)] = times
    write_manifest(lang, made)
    size = sum(f.stat().st_size for f in (OUT / lang).glob("*.ogg")) if (OUT / lang).exists() else 0
    said = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    print(f"{lang}: {len(made)} chapters ready ({said}), {size >> 20} MB, in {time.time() - t0:.0f}s")


def write_manifest(lang, made):
    """{"John|1": [[verse, start, end], ...]}: the recording is site/audio/<lang>/John_01.ogg.
    Written whole and then moved into place: the reader fetches it while the
    voice's job is adding to it, and half a file would hide every chapter."""
    made = {f"{b}|{c}": made[b, c] for b, c in sorted(made, key=lambda k: (NUM[k[0]], k[1]))}
    OUT.mkdir(parents=True, exist_ok=True)
    part = OUT / f"{lang}.json.part"
    part.write_text(json.dumps(made, separators=(",", ":")), encoding="utf-8")
    part.replace(OUT / f"{lang}.json")


def add(lang, wav):
    """One chapter just recorded, made ready for the reader at once. The voices
    call this after each chapter, so a job that takes days is heard as it goes
    rather than when someone next remembers to run this script; the reader
    picks the chapter up on its next load, without being rebuilt."""
    m = re.fullmatch(r"(.+)_(\d{2,3})", wav.stem)
    if not (m and m.group(1) in NUM):
        return None
    book, ch = m.group(1), int(m.group(2))
    _, _, times, how = make((lang, book, ch, wav, ROOT / "output" / lang / "json" / f"{wav.stem}.json"))
    side = OUT / f"{lang}.json"
    made = {}
    if side.exists():
        for k, v in json.loads(side.read_text(encoding="utf-8")).items():
            b, c = k.split("|")
            made[(b, int(c))] = v
    if times:
        made[(book, ch)] = times
    else:
        made.pop((book, ch), None)
    write_manifest(lang, made)
    return how


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", action="append", help="only this language (may be given more than once)")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    langs = a.lang or sorted(d.name for d in AUDIO.iterdir() if d.is_dir() and (ROOT / "output" / d.name / "json").is_dir())
    for lang in langs:
        build(lang, a.workers)


if __name__ == "__main__":
    main()
