#!/usr/bin/env python3
"""Teach Meta's Burmese voice to read Sgaw Karen: the fine-tune from Burmese.

    python "NGAW KAREN TTS/train_mms.py" --say "ပှၤကညီ" --base          # the Burmese voice as it stands, the yardstick
    python "NGAW KAREN TTS/train_mms.py" --train --epochs 200            # a run under models/mms/karen-runs/<name>
    python "NGAW KAREN TTS/train_mms.py" --train --from <run>/G_e0100.pth --epochs 100    # carry a run on
    python "NGAW KAREN TTS/train_mms.py" --say "ပှၤကညီ" --model <run>/G_e0200.pth

The Piper fine-tunes started from a Vietnamese voice because Vietnamese has
six tones, and fed it Karen through a phoneme layer and a fitted tone mapping.
It never came clear: two layers of guessing stood between the Karen letters
and a voice that had never seen them. Meta's MMS Burmese voice
(facebook/mms-tts-mya) reads the Myanmar script itself - one symbol per
character, no romanising, no phonemiser - and was trained on Burmese Bible
readings, the same kind of text we want read.

Karen as written was not enough: Karen gives some Burmese signs other sounds,
and six of its characters, a fifth of Mason's text, are not in the Burmese
alphabet at all. So each syllable is respelled on the way in into the sounds
Emma Htoo's course teaches, in the Burmese spelling of those sounds where
Burmese has one and in a few new symbols where it does not (respell and
KAREN_TOKENS below). Each new symbol starts from the Burmese ones nearest it,
so it begins as a sound rather than as noise.

The training itself is VITS's own, from the code MMS was trained with
(sources/vits, jaywalnut310/vits, MIT): Meta's released checkpoints load into
it as they are, generator and discriminator both, with no conversion. Two
things in that code no longer run on current libraries - the spectrogram
(torch.stft and librosa's mel filters changed their calls) and the Cython
alignment - so the spectrograms are computed here and the alignment comes
from the monotonic-alignment-search package.

The data is the lesson cuts, one speaker at a time (a single-speaker voice
trained on two averages them into neither), Emma Htoo by default: ~16 minutes
of confirmed spellings, mostly isolated syllables. Two-thirds of those are
shorter than the half second VITS trains on (the crash Piper hit at epoch 80),
so short cuts are padded with silence rather than dropped. The v1 and v2
lesson holds here too: isolated syllables are the wrong shape of data, and
connected read speech is what will make a real voice. This script takes any
`wav|karen text` list (--list) so that speech plugs straight in.

Needs: torch, librosa, scipy, monotonic-alignment-search; sources/vits
(git clone https://github.com/jaywalnut310/vits sources/vits); and Meta's
checkpoints in models/mms/mya/:
    https://dl.fbaipublicfiles.com/mms/tts/mya.tar.gz                           (G_100000.pth, config, vocab)
    https://huggingface.co/facebook/mms-tts/resolve/main/full_models/mya/D_100000.pth
The Burmese model is CC BY-NC 4.0, and so is any voice made from it.
"""
import argparse
import json
import math
import random
import sys
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VITS = ROOT / "sources" / "vits"
BASE = ROOT / "models" / "mms" / "mya"
RUNS = ROOT / "models" / "mms" / "karen-runs"
CUTS = HERE / "audio" / "cuts"
OUT = HERE / "audio" / "ksw"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "scripts"))

# How Karen reaches the voice: respelled into the sounds Emma Htoo teaches
# (phonics-emma-htoo.md), written the way the Burmese voice already says them.
# Fed letter for letter, the voice read Karen's reused vowel signs with their
# Burmese values - ိ and ီ came out as /i/, which in Karen are /o/ and /ɔ/
# (reports/reading_check_*) - and could not see the tone marks at all: Meta's
# alphabet makes the asat ် symbol 0, the same id as the blank between
# letters, so လၢ (/lə/) and တၢ် (/ta/, falling) differed by two blanks and
# ဒ် (/də/) looked like ဒ (/da/). So each syllable is parsed (karen_phonemes)
# and written out again:
#   vowel   the Burmese spelling of her sound: ံ /i/ as ီ, ိ /o/ as ို, ီ /ɔ/
#           as ော, ့ /e/ as ေ (lesson 3); ါ ာ and the bare consonant /a/ as
#           ာ, so a light prefix syllable (တ- က-) still has a vowel; ၢ and
#           a lone ် /ə/ as a symbol of their own, which Burmese lacks.
#   tone    each of the five marks one symbol of its own (lesson 4, video 11).
#   onset   as written, but ၡ /ʃ/ as Burmese ရှ, and ဃ /x/ its own symbol.
#   medial  ှ ွ as written; ၠ /j/ as Burmese ျ, which is /j/; Karen's ျ is
#           /l/ and ြ /r/ (lesson 5: ကျဲ road, ကြၢး should), which Burmese
#           says /j/, so each is a symbol of its own.
# The new symbols live in the private-use area. Each starts from the Burmese
# symbols named beside it, averaged: the vowel ə between ာ and ု, the high
# tones ၢ် ၣ် from Burmese's high း, the short tones ာ် း from its short
# creaky ့, and ၤ from the blank, a tone that starts as nothing and is
# learnt.
SCHWA, T_KEPHO, T_EU, T_HATHI, T_LOW, T_VISARGA, MED_L, MED_R, GHA = (chr(0xE000 + i) for i in range(1, 10))
KAREN_TOKENS = {SCHWA: ["ာ", "ု"], T_KEPHO: ["်"], T_EU: ["း"], T_HATHI: ["း"], T_LOW: ["့"], T_VISARGA: ["့"],
                MED_L: ["လ"], MED_R: ["ရ"], GHA: ["ခ"]}
SPELL_VOWEL = {"": "ာ", "ါ": "ါ", "ာ": "ာ", "ံ": "ီ", "ၢ": SCHWA, "်": SCHWA, "ု": "ု", "ူ": "ူ",
               "့": "ေ", "ဲ": "ဲ", "ိ": "ို", "ီ": "ော"}
SPELL_TONE = {"": "", "ၤ": T_KEPHO, "ၢ်": T_EU, "ၣ်": T_HATHI, "ာ်": T_LOW, "း": T_VISARGA}
SPELL_ONSET = {"ၡ": "ရှ", "ဃ": GHA}
SPELL_MEDIAL = {"ၠ": "ျ", "ျ": MED_L, "ြ": MED_R}


def respell(karen):
    """Karen text as (source, respelled) pieces: a syllable at a time, and
    anything that is not a syllable (a space, a stray mark) as itself."""
    import karen_phonemes as kp
    text, out, i = unicodedata.normalize("NFC", karen), [], 0
    while i < len(text):
        m = kp.SYLLABLE.match(text, i)
        if not m:
            out.append((text[i], " " if text[i].isspace() else text[i]))
            i += 1
            continue
        cons, meds, vowel, mark = m.group(1), m.group(2) or "", m.group(3) or "", m.group(4) or ""
        out.append((m.group(0), SPELL_ONSET.get(cons, cons) + "".join(SPELL_MEDIAL.get(x, x) for x in meds)
                    + SPELL_VOWEL[vowel] + SPELL_TONE[mark]))
        i = m.end()
    return out


MIN_SECONDS = 0.6      # the training window is 8192 samples, 0.51 s at 16 kHz
MAX_SECONDS = 12.0

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def maximum_path(neg_cent, mask):
    """VITS's alignment, from the monotonic-alignment-search package. The
    package is glow-tts's version of the same search and lays the matrix out
    text by frames, where VITS passes frames by text, so it goes in and comes
    out transposed."""
    from monotonic_alignment_search import maximum_path as search
    return search(neg_cent.transpose(1, 2).contiguous(), mask.transpose(1, 2).contiguous()).transpose(1, 2)


def load_vits():
    """Import VITS's model code with the alignment it expects under its old name."""
    import types
    sys.modules.setdefault("monotonic_align", types.SimpleNamespace(maximum_path=maximum_path))
    if not (VITS / "models.py").exists():
        raise SystemExit(f"no VITS source at {VITS}: git clone https://github.com/jaywalnut310/vits sources/vits")
    sys.path.insert(0, str(VITS))
    import commons
    import losses
    import models
    return commons, losses, models


def base_config():
    return json.loads((BASE / "config.json").read_text(encoding="utf-8"))


def base_symbols():
    """Meta's alphabet, one symbol per line, in id order. One of the lines is
    a space, so the file is split on newlines and not stripped."""
    lines = (BASE / "vocab.txt").read_text(encoding="utf-8").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


class Text:
    """Karen text to symbol ids, as MMS does it: each known symbol one id,
    anything else dropped, and with add_blank a blank (id 0) between every
    pair and at both ends. A voice whose alphabet has the Karen symbols is
    fed respelled Karen (respell); the first runs (emma-v1), letter for
    letter. `units`, a list, gets for each symbol said the piece of the text
    it came from, so a reading can be timed back onto its syllables."""

    def __init__(self, symbols, add_blank=True):
        self.symbols = symbols
        self.ids = {s: i for i, s in enumerate(symbols)}
        self.add_blank = add_blank
        self.karen = SCHWA in self.ids
        self.dropped = {}

    def __call__(self, karen, units=None):
        # not stripped: speak() ends a clause on a space on purpose
        pieces = respell(karen) if self.karen else [(ch, ch) for ch in unicodedata.normalize("NFC", karen)]
        out = []
        for n, (source, spelled) in enumerate(pieces):
            for ch in spelled:
                if ch in self.ids:
                    out.append(self.ids[ch])
                    if units is not None:
                        units.append((n, source))
                else:
                    self.dropped[ch] = self.dropped.get(ch, 0) + 1
        if self.add_blank:
            spaced = [0] * (len(out) * 2 + 1)
            spaced[1::2] = out
            out = spaced
        return out


class Audio:
    """VITS's spectrograms, written for the current torch and librosa: the
    linear spectrogram the posterior encoder reads, and the mel spectrogram
    the reconstruction loss compares."""

    def __init__(self, cfg, device):
        import torch
        from librosa.filters import mel
        d = cfg["data"]
        self.n_fft, self.hop, self.win = d["filter_length"], d["hop_length"], d["win_length"]
        self.fs = d["sampling_rate"]
        self.window = torch.hann_window(self.win, device=device)
        self.mel = torch.from_numpy(mel(sr=self.fs, n_fft=self.n_fft, n_mels=d["n_mel_channels"],
                                        fmin=d["mel_fmin"], fmax=d["mel_fmax"])).float().to(device)

    def spec(self, y):
        import torch
        import torch.nn.functional as F
        pad = (self.n_fft - self.hop) // 2
        y = F.pad(y.unsqueeze(1), (pad, pad), mode="reflect").squeeze(1)
        s = torch.stft(y, self.n_fft, hop_length=self.hop, win_length=self.win, window=self.window,
                       center=False, pad_mode="reflect", normalized=False, onesided=True, return_complex=True)
        return torch.sqrt(s.real ** 2 + s.imag ** 2 + 1e-6)

    def spec_to_mel(self, s):
        import torch
        return torch.log(torch.clamp(torch.matmul(self.mel, s), min=1e-5))

    def mel_of(self, y):
        return self.spec_to_mel(self.spec(y))


def read_audio(path, fs, peak=True):
    from math import gcd
    from scipy.signal import resample_poly
    from karen_voice_test import read_wav
    x, rate = read_wav(path)
    if rate != fs:
        g = gcd(int(rate), int(fs))
        x = resample_poly(x, fs // g, int(rate) // g)
    if not peak:
        return x.astype(np.float32)
    peak = np.abs(x).max()
    return (x / peak * 0.9 if peak > 0 else x).astype(np.float32)


REF = HERE / "audio" / "reference"
REACH = 0.15           # how far past a lesson cut's edge to look for the quiet
FADE = 0.01


class Recut:
    """The lesson cuts were made tight - half of Emma's end while she is still
    sounding, and most begin mid-onset - and a voice trained on them learnt to
    stop its own syllables short. So each clip is cut again from the lesson's
    full recording: each edge reaches out, up to REACH, to where the sound
    has died away, and is faded there. The old edges sat 26 dB under the
    word's peak, where a Karen tone is still fading; the room (or the music
    under the lesson) is about 40 dB down, so the edge goes to the first
    frame within 3 dB of the quietest one in reach."""

    def __init__(self, fs):
        self.fs = fs
        index = json.loads((REF / "index.json").read_text(encoding="utf-8"))
        self.by_id = {e["id"]: ROOT / e["wav"] for e in index.values()}
        self.by_key = {k: ROOT / e["wav"] for k, e in index.items()}
        self.cache = {}

    def source(self, row):
        path = self.by_id.get(row.get("source")) or self.by_key.get(row["lesson"])
        if not path or not path.exists() or "start" not in row:
            return None
        if path not in self.cache:
            self.cache = {path: read_audio(path, self.fs, peak=False)}     # one lesson at a time: rows come grouped
        return self.cache[path]

    def __call__(self, row):
        x = self.source(row)
        if x is None:
            return None
        fs, hop = self.fs, int(self.fs * 0.01)
        lo, hi = int(row["start"] * fs), int(row["end"] * fs)
        if hi - lo < hop:
            return None
        def reach(edge, step):
            steps = []
            for i in range(1, int(REACH / 0.01) + 1):
                a = edge + step * i * hop
                if a < 0 or a > len(x):
                    break
                seg = x[a - hop:a] if step > 0 else x[a:a + hop]       # the frame this step takes in
                steps.append((float(np.sqrt((seg ** 2).mean())), a))
            if not steps:
                return edge
            floor = min(level for level, _ in steps) * 10 ** (3 / 20)
            return next(a for level, a in steps if level <= floor)

        lo, hi = reach(lo, -1), reach(hi, 1)
        piece = x[lo:hi].copy()
        n = int(FADE * fs)
        ramp = np.linspace(0, 1, n, dtype=np.float32)
        piece[:n] *= ramp
        piece[-n:] *= ramp[::-1]
        peak = np.abs(piece).max()
        return piece / peak * 0.9 if peak > 0 else piece


def lesson_rows(speaker, include_unconfirmed):
    """The lesson cuts as (row, Karen text), as train_voice gathers them:
    the word cuts, plus Emma Htoo's letters and vowels, whose spellings are
    certain. Each row keeps where it lies in its lesson, for Recut."""
    rows = [json.loads(l) for l in (CUTS / "index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if not include_unconfirmed:
        rows = [r for r in rows if r.get("confirmed")]
    for name, key in (("emma01_letters.json", "letter"), ("emma03_vowels.json", "spelled")):
        f = HERE / "words" / name
        if f.exists():
            for r in json.loads(f.read_text(encoding="utf-8")):
                wav = r["wav"].replace("\\", "/")
                wav = wav[len("NGAW KAREN TTS/"):] if wav.startswith("NGAW KAREN TTS/") else wav
                rows.append({"lesson": r["lesson"], "ksw": r[key], "wav": wav, "start": r["start"], "end": r["end"]})
    rows = [r for r in rows if r["lesson"].startswith(speaker)]
    for r in rows:
        r["wav"] = HERE / r["wav"].replace("\\", "/")
    return [(r, r["ksw"]) for r in rows]


def list_rows(path):
    """A `wav|karen text` list, wav paths relative to the list."""
    path = Path(path)
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            wav, _, text = line.partition("|")
            out.append((path.parent / wav, text))
    return out


def load_data(rows, text, fs, recut=True):
    """rows: (lesson row or wav path, Karen text). A lesson row is cut again
    from its recording (Recut) unless recut is False; a plain wav is read as
    it is."""
    data, padded = [], 0
    cutter = Recut(fs) if recut else None
    for src, karen in rows:
        karen = karen.strip()
        ids = text(karen)
        if len(ids) < 3:
            continue
        x = cutter(src) if cutter and isinstance(src, dict) else None
        wav = src["wav"] if isinstance(src, dict) else src
        if x is None:
            x = read_audio(wav, fs)
        if len(x) > MAX_SECONDS * fs:
            continue
        short = int(MIN_SECONDS * fs) - len(x)
        if short > 0:
            x = np.pad(x, (short // 2, short - short // 2))
            padded += 1
        data.append({"ids": ids, "wav": x, "karen": karen, "name": Path(wav).stem})
    return data, padded


def build(cfg, n_symbols, device):
    _, _, models = load_vits()
    d, m = cfg["data"], cfg["model"]
    seg = cfg["train"]["segment_size"] // d["hop_length"]
    net_g = models.SynthesizerTrn(n_symbols, d["filter_length"] // 2 + 1, seg, n_speakers=d["n_speakers"], **m).to(device)
    net_d = models.MultiPeriodDiscriminator(m["use_spectral_norm"]).to(device)
    return net_g, net_d


def extend_embedding(state, symbols):
    """Grow the text embedding from Meta's alphabet to ours, each new row
    the average of the Burmese symbols it starts from (KAREN_TOKENS)."""
    import torch
    emb = state["enc_p.emb.weight"]
    have = emb.shape[0]
    if have == len(symbols):
        return state
    rows = [emb]
    for s in symbols[have:]:
        rows.append(emb[[symbols.index(b) for b in KAREN_TOKENS[s]]].mean(0, keepdim=True).clone())
    state["enc_p.emb.weight"] = torch.cat(rows)
    return state


def karen_symbols():
    base = base_symbols()
    return base + list(KAREN_TOKENS)


def load_generator(path, device):
    """A voice for synthesis: Meta's Burmese one with the Karen letters added
    (path None), or a checkpoint of ours."""
    import torch
    cfg = base_config()
    if path:
        ck = torch.load(str(path), map_location="cpu", weights_only=False)
        symbols, state = ck["symbols"], ck["model"]
    else:
        symbols = karen_symbols()
        state = extend_embedding(torch.load(str(BASE / "G_100000.pth"), map_location="cpu", weights_only=False)["model"], symbols)
    net_g, _ = build(cfg, len(symbols), device)
    net_g.load_state_dict(state)
    net_g.eval()
    return net_g, symbols, cfg


class MmsKaren:
    """The fine-tuned voice with the say() the other engines have, for
    karen_speech and karen_voice_test. Deterministic by default, like
    PiperKaren: a measurement needs the same word the same way twice.
    model: a checkpoint, None for the newest, or "base" for Meta's Burmese
    voice with the Karen letters added and nothing learnt."""

    def __init__(self, model=None, deterministic=True, pace=1.0, device=None, clarity=0.0, tones=0.0, lengths=0.0):
        import torch
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net, symbols, cfg = load_generator(None if model == "base" else (model or latest_checkpoint()), self.device)
        self.text = Text(symbols, cfg["data"]["add_blank"])
        self.fs = cfg["data"]["sampling_rate"]
        self.noise, self.noise_w = (0.0, 0.0) if deterministic else (0.667, 0.8)
        self.pace = pace
        self.clarity = clarity
        self.tones = tones
        self.lengths = lengths

    def say(self, karen, timings=None):
        return speak(self.net, self.text, karen, self.fs, self.device, self.noise, self.noise_w, self.pace, timings, self.clarity, self.tones,
                     self.lengths)


# Mason punctuates with the ASCII comma and full stop (and sometimes ၊ ။),
# none of which the voice has a symbol for, so they were being dropped and a
# verse came out as one breath. Each clause is said on its own instead, ending
# on a space so its last syllable is not the last thing the voice sees, with a
# pause between. karen_speech's pauses (0.28 and 0.5 s) were dead air to the
# ear, and a verse's closing pause stacked on the gap between verses to make a
# second of silence, so the pauses are shorter and none follows the last clause:
# what comes after a verse is the caller's to decide.
PAUSE = {",": 0.15, "၊": 0.15, ".": 0.3, "။": 0.3}


def enunciate(y, fs, onsets, clarity):
    """Lift the consonants. Emma Htoo speaks softly and calmly, pleasant to
    hear and soft to learn from - her onsets rise over about 90 ms where the
    Burmese Bible voice's rise over 70 - and the voice learnt her softness.
    `clarity` 1 raises the band above 2 kHz, where bursts and hisses live,
    by 4 dB, and each syllable's first 60 ms (its consonant and the release
    into the vowel) by a further 3 dB, falling away over the vowel; 0 leaves
    the voice as it is. The syllable starts are the voice's own timings."""
    if clarity <= 0 or not len(y):
        return y
    from scipy.signal import butter, sosfilt
    hi = sosfilt(butter(2, 2000, "highpass", fs=fs, output="sos"), y)
    y = y + hi * (10 ** (clarity * 4 / 20) - 1)
    gain = np.ones_like(y)
    lift, n, ramp = 10 ** (clarity * 3 / 20) - 1, int(0.06 * fs), int(0.005 * fs)
    shape = np.concatenate([np.linspace(0, 1, ramp), 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, n))])
    for t in onsets:
        a = int(t * fs) - ramp
        lo, hi_ = max(0, a), min(len(y), a + len(shape))
        if hi_ > lo:
            gain[lo:hi_] = np.maximum(gain[lo:hi_], 1 + lift * shape[lo - a:hi_ - a])
    return y * gain


def retone(y, fs, clause, clause_last, pieces, scale):
    """Give a clause the pitch Karen readers give it (karen_tones): each
    syllable, from its start to the next one's, follows its target curve in
    semitones about the voice's own median; `scale` 1 is the readers' mean,
    more exaggerates it. WORLD takes the voice apart into pitch, timbre and
    breath and puts it back with the new pitch, so the sounds and their
    timing are the voice's own. Unvoiced stretches stay unvoiced."""
    import pyworld as pw
    import karen_tones as kt
    tg = kt.targets(clause, clause_last)
    if scale <= 0 or not pieces or len(pieces) != len(tg):
        return y
    x = np.ascontiguousarray(y, dtype=np.float64)
    f0, t = pw.dio(x, fs, f0_floor=70, f0_ceil=500, frame_period=5)
    f0 = pw.stonemask(x, f0, t, fs)
    voiced = f0 > 0
    if voiced.sum() < 5:
        return y
    sp, ap = pw.cheaptrick(x, f0, t, fs), pw.d4c(x, f0, t, fs)
    track = np.full(len(f0), np.nan)
    starts = [t0 for _, t0, _ in pieces] + [pieces[-1][2]]
    for k, ((_, t0, _), (a_, m_, e_)) in enumerate(zip(pieces, tg)):
        a, b = int(t0 * 200), min(len(f0), int(max(starts[k + 1], t0 + 0.02) * 200))
        if b > a:
            pos = np.linspace(0, 1, b - a)
            track[a:b] = np.where(pos < 0.5, a_ + (m_ - a_) * pos / 0.5, m_ + (e_ - m_) * (pos - 0.5) / 0.5)
    known = np.flatnonzero(~np.isnan(track))
    track = np.interp(np.arange(len(track)), known, track[known])
    track = np.convolve(track, np.ones(6) / 6, mode="same")               # 30 ms: syllables join, not step
    f0 = np.where(voiced, np.median(f0[voiced]) * 2 ** (scale * track / 12), 0.0)
    out = pw.synthesize(f0, sp, ap, fs, frame_period=5)
    return np.pad(out, (0, max(0, len(y) - len(out))))[:len(y)]


def infer(net, ids, device, noise, noise_w, pace, adjust=None):
    """VITS's own inference (SynthesizerTrn.infer), with one step added: the
    frames the duration predictor gives each symbol pass through `adjust`
    before they are fixed, so a syllable can be held longer or shorter
    without the rest of the voice changing."""
    import torch
    commons, _, _ = load_vits()
    x = torch.LongTensor(ids).unsqueeze(0).to(device)
    x, m_p, logs_p, x_mask = net.enc_p(x, torch.LongTensor([len(ids)]).to(device))
    logw = net.dp(x, x_mask, g=None, reverse=True, noise_scale=noise_w) if net.use_sdp else net.dp(x, x_mask, g=None)
    w = torch.exp(logw) * x_mask * pace
    if adjust is not None:
        w = adjust(w)
    w_ceil = torch.ceil(w)
    y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
    y_mask = torch.unsqueeze(commons.sequence_mask(y_lengths, None), 1).to(x_mask.dtype)
    attn = commons.generate_path(w_ceil, torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1))
    m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
    logs_p = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)
    z_p = m_p + torch.randn_like(m_p) * torch.exp(logs_p) * noise
    z = net.flow(z_p, y_mask, g=None, reverse=True)
    return net.dec(z * y_mask, g=None), attn


def restretch(clause, clause_last, units, add_blank, scale):
    """An `adjust` for infer: each syllable's frames scaled towards the
    length Karen readers give it (karen_tones.lengths) - a light prefix
    about half an ordinary syllable, ာ် long, ၣ် and း short, a clause's
    last syllable drawn out - keeping the clause's total, so the rate
    stays the voice's. `scale` 1 takes the readers' proportions; 0 leaves
    the voice's own."""
    import karen_phonemes as kp
    import karen_tones as kt
    want = kt.lengths(clause, clause_last)
    step, first = (2, 1) if add_blank else (1, 0)
    starts = {}
    for i, (n, source) in enumerate(units):
        starts.setdefault((n, source), i * step + first)
    order = sorted(starts.items(), key=lambda kv: kv[1])
    spans = []
    for j, ((n, source), k) in enumerate(order):
        end = order[j + 1][1] if j + 1 < len(order) else None
        if kp.SYLLABLE.fullmatch(source):
            spans.append((k, end))

    def adjust(w):
        if scale <= 0 or len(spans) != len(want):
            return w
        w = w.clone()
        d = w[0, 0]
        cur = np.array([float(d[a:b].sum()) for a, b in spans])
        if (cur <= 0).any():
            return w
        factor = (np.array(want) / (cur / cur.mean())) ** scale
        factor *= cur.sum() / (cur * factor).sum()
        for (a, b), f in zip(spans, factor):
            d[a:b] *= float(f)
        return w
    return adjust


def speak(net, text, karen, fs, device, noise=0.667, noise_w=0.8, pace=1.0, timings=None, clarity=0.0, tones=0.0,
          lengths=0.0):
    """`timings`, a list, gets one (clause, piece, start s, end s) per piece
    of text the voice said - a syllable for a respelling voice, a character
    for the first runs: VITS decides how many frames each symbol lasts, so
    these are where each one is, not an estimate. `clarity`: enunciate;
    `tones`: retone, and `lengths`: restretch, for a voice fed respelled Karen."""
    import re
    import torch
    import karen_phonemes as kp
    parts, at, hop = [], 0, base_config()["data"]["hop_length"]
    found = [(c, m) for c, m in re.findall(r"([^,.၊။]+)([,.၊။]?)", karen) if c.strip()]
    for n_clause, (clause, mark) in enumerate(found):
        units = []
        ids = text(clause.strip() + " ", units)
        adjust = restretch(clause.strip(), n_clause == len(found) - 1, units, text.add_blank, lengths)             if lengths and text.karen else None
        with torch.no_grad():
            y, attn = infer(net, ids, device, noise, noise_w, pace, adjust)
        y = y[0, 0].float().cpu().numpy().astype(np.float64)
        frames = attn[0, 0].sum(0).cpu().numpy()                      # per symbol, blanks between
        edges = np.concatenate([[0], np.cumsum(frames)]) * hop / fs
        step, first = (2, 1) if text.add_blank else (1, 0)
        spans = {}
        for i, unit in enumerate(units):
            k = i * step + first
            spans[unit] = (spans.get(unit, (edges[k],))[0], edges[k + 1])
        pieces = [(piece, t0, t1) for (_, piece), (t0, t1) in sorted(spans.items()) if piece.strip()]
        if tones and text.karen:
            y = retone(y, fs, clause.strip(), n_clause == len(found) - 1,
                       [p for p in pieces if kp.SYLLABLE.fullmatch(p[0])], tones)
        # a syllable starts at a piece that starts with a consonant letter
        y = enunciate(y, fs, [t0 for piece, t0, _ in pieces if piece[0] in kp.CONSONANTS], clarity)
        if timings is not None:
            timings += [(clause.strip(), piece, at + t0, at + t1) for piece, t0, t1 in pieces]
        n = min(len(y) // 4, int(fs * FADE))
        if n:
            y[-n:] *= np.linspace(1, 0, n)
        parts += [y, np.zeros(int(fs * PAUSE.get(mark, 0.0)))]
        at += (len(y) + len(parts[-1])) / fs
    return np.concatenate(parts[:-1]) if parts else np.zeros(1)


def latest_checkpoint():
    ckpts = sorted(RUNS.rglob("G_e*.pth"), key=lambda p: p.stat().st_mtime)
    if not ckpts:
        raise SystemExit(f"no checkpoint under {RUNS}; train first, or use --base")
    return ckpts[-1]


def write_wav(audio, fs, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def sample_texts():
    """What each saved checkpoint reads aloud, to listen to the run as it goes:
    connected text the lessons never gave it."""
    from karen_speech import karen_verses
    out = []
    for book, ch, v in (("Gen", 1, 1), ("John", 3, 16), ("Matt", 6, 9)):
        got = karen_verses(book, ch, [v])
        if got:
            out.append((f"{book}{ch}_{v}", got[0]))
    return out


def train(a):
    import torch
    import torch.nn.functional as F
    commons, losses, _ = load_vits()
    torch.manual_seed(a.seed)
    random.seed(a.seed)
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    device = "cuda"
    cfg = base_config()
    tc, dc = cfg["train"], cfg["data"]
    hop, seg = dc["hop_length"], tc["segment_size"]

    if a.start:
        ck = torch.load(str(a.start), map_location="cpu", weights_only=False)
        symbols, g_state, epoch0 = ck["symbols"], ck["model"], ck.get("epoch", 0)
        d_path = Path(a.start).with_name("D_last.pth")
        d_state = torch.load(str(d_path), map_location="cpu", weights_only=False)["model"]
    else:
        symbols, epoch0 = karen_symbols(), 0
        g_state = extend_embedding(torch.load(str(BASE / "G_100000.pth"), map_location="cpu", weights_only=False)["model"], symbols)
        d_state = torch.load(str(BASE / "D_100000.pth"), map_location="cpu", weights_only=False)["model"]
    net_g, net_d = build(cfg, len(symbols), device)
    net_g.load_state_dict(g_state)
    net_d.load_state_dict(d_state)

    text = Text(symbols, dc["add_blank"])
    rows = list_rows(a.list) if a.list else lesson_rows(a.speaker, a.unconfirmed)
    data, padded = load_data(rows, text, dc["sampling_rate"])
    if text.dropped:
        print("characters the voice has no symbol for, dropped:", " ".join(f"{c!r}×{n}" for c, n in text.dropped.items()))
    random.shuffle(data)
    n_val = max(4, len(data) // 20)
    val, data = data[:n_val], data[n_val:]
    minutes = sum(len(d["wav"]) for d in data) / dc["sampling_rate"] / 60
    print(f"{len(data)} clips, {minutes:.1f} min ({padded} short ones padded with silence), {len(val)} held out")

    audio = Audio(cfg, device)
    for d in data + val:
        d["y"] = torch.from_numpy(d["wav"]).to(device)
        d["spec"] = audio.spec(d["y"].unsqueeze(0))[0]

    # The new letters start as borrowed Burmese sounds and have furthest to
    # go, so the text embedding learns faster than the rest of the network.
    emb = [p for n, p in net_g.named_parameters() if n == "enc_p.emb.weight"]
    rest = [p for n, p in net_g.named_parameters() if n != "enc_p.emb.weight"]
    betas, eps = tuple(tc["betas"]), tc["eps"]
    optim_g = torch.optim.AdamW([{"params": rest}, {"params": emb, "lr": a.lr * 5}], a.lr, betas=betas, eps=eps)
    optim_d = torch.optim.AdamW(net_d.parameters(), a.lr, betas=betas, eps=eps)
    sched_g = torch.optim.lr_scheduler.ExponentialLR(optim_g, tc["lr_decay"])
    sched_d = torch.optim.lr_scheduler.ExponentialLR(optim_d, tc["lr_decay"])

    def batch(items):
        xl = torch.LongTensor([len(d["ids"]) for d in items])
        sl = torch.LongTensor([d["spec"].shape[1] for d in items])
        x = torch.zeros(len(items), int(xl.max()), dtype=torch.long)
        spec = torch.zeros(len(items), items[0]["spec"].shape[0], int(sl.max()), device=device)
        y = torch.zeros(len(items), 1, int(sl.max()) * hop, device=device)
        for i, d in enumerate(items):
            x[i, :len(d["ids"])] = torch.LongTensor(d["ids"])
            spec[i, :, :d["spec"].shape[1]] = d["spec"]
            n = min(len(d["y"]), y.shape[2])
            y[i, 0, :n] = d["y"][:n]
        return x.to(device), xl.to(device), spec, sl.to(device), y

    def step(items, train_step=True):
        x, xl, spec, sl, y = batch(items)
        y_hat, l_length, _, ids_slice, _, z_mask, (_, z_p, m_p, logs_p, _, logs_q) = net_g(x, xl, spec, sl)
        y_mel = commons.slice_segments(audio.spec_to_mel(spec), ids_slice, seg // hop)
        y_hat_mel = audio.mel_of(y_hat.squeeze(1))
        y = commons.slice_segments(y, ids_slice * hop, seg)
        loss_mel = F.l1_loss(y_mel, y_hat_mel)
        if not train_step:
            return {"mel": loss_mel.item()}
        y_d_r, y_d_g, _, _ = net_d(y, y_hat.detach())
        loss_disc, _, _ = losses.discriminator_loss(y_d_r, y_d_g)
        optim_d.zero_grad()
        loss_disc.backward()
        commons.clip_grad_value_(net_d.parameters(), None)
        optim_d.step()
        _, y_d_g, fmap_r, fmap_g = net_d(y, y_hat)
        loss_dur = torch.sum(l_length.float())
        loss_kl = losses.kl_loss(z_p, logs_q, m_p, logs_p, z_mask) * tc["c_kl"]
        loss_fm = losses.feature_loss(fmap_r, fmap_g)
        loss_gen, _ = losses.generator_loss(y_d_g)
        loss = loss_gen + loss_fm + loss_mel * tc["c_mel"] + loss_dur + loss_kl
        optim_g.zero_grad()
        loss.backward()
        commons.clip_grad_value_(net_g.parameters(), None)
        optim_g.step()
        return {"mel": loss_mel.item(), "dur": loss_dur.item(), "kl": loss_kl.item(),
                "gen": loss_gen.item(), "fm": loss_fm.item(), "disc": loss_disc.item()}

    run = Path(a.start).parent if a.start else RUNS / (a.name or time.strftime("%Y%m%d-%H%M") + f"-{a.speaker or 'list'}")
    run.mkdir(parents=True, exist_ok=True)
    # A carried-on run keeps the first leg's record beside its own.
    (run / (f"run_from_e{epoch0:04d}.json" if epoch0 else "run.json")).write_text(json.dumps({**vars(a), "clips": len(data), "minutes": round(minutes, 2),
                                              "symbols": symbols}, ensure_ascii=False, indent=1), encoding="utf-8")
    samples = sample_texts()
    log = (run / "log.jsonl").open("a", encoding="utf-8")
    print("run ->", run)

    def save(epoch):
        torch.save({"model": net_g.state_dict(), "symbols": symbols, "epoch": epoch}, run / f"G_e{epoch:04d}.pth")
        torch.save({"model": net_d.state_dict(), "epoch": epoch}, run / "D_last.pth")
        net_g.eval()
        with torch.no_grad():
            for name, karen in samples + [(f"val_{d['name']}", d["karen"]) for d in val[:3]]:
                y = speak(net_g, text, karen, dc["sampling_rate"], device)
                write_wav(y / max(1e-9, np.abs(y).max()) * 0.9, dc["sampling_rate"], run / "samples" / f"e{epoch:04d}_{name}.wav")
        net_g.train()

    net_g.train()
    net_d.train()
    for epoch in range(epoch0 + 1, epoch0 + a.epochs + 1):
        t = time.time()
        random.shuffle(data)
        sums = {}
        for i in range(0, len(data), a.batch):
            for k, v in step(data[i:i + a.batch]).items():
                sums[k] = sums.get(k, 0) + v
        n = math.ceil(len(data) / a.batch)
        sched_g.step()
        sched_d.step()
        row = {"epoch": epoch, **{k: round(v / n, 4) for k, v in sums.items()}, "s": round(time.time() - t, 1)}
        if epoch % a.val_every == 0 or epoch == epoch0 + a.epochs:
            with torch.no_grad():
                net_g.eval()
                row["val_mel"] = round(float(np.mean([step(val[i:i + a.batch], False)["mel"] for i in range(0, len(val), a.batch)])), 4)
                net_g.train()
        print(json.dumps(row), flush=True)
        log.write(json.dumps(row) + "\n")
        log.flush()
        if epoch % a.save_every == 0 or epoch == epoch0 + a.epochs:
            save(epoch)
    print("done ->", run)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--say", help="Karen text to read aloud")
    ap.add_argument("--base", action="store_true", help="--say with the Burmese voice as Meta made it (Karen letters added, untrained)")
    ap.add_argument("--model", help="--say with this checkpoint (default: the newest under models/mms/karen-runs)")
    ap.add_argument("--out", help="where --say writes (default audio/ksw/mms_<model>.wav)")
    ap.add_argument("--pace", type=float, default=1.0, help="--say: above 1 is slower")
    ap.add_argument("--speaker", default="emma", help="lessons whose key starts with this: emma or vocab")
    ap.add_argument("--unconfirmed", action="store_true", help="train on unconfirmed spellings too")
    ap.add_argument("--list", help="train on a `wav|karen text` list instead of the lesson cuts")
    ap.add_argument("--from", dest="start", help="carry on from this G_e*.pth (its run's D_last.pth beside it)")
    ap.add_argument("--name", help="run folder name")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4, help="Meta trained at 2e-4; a fine-tune goes gentler")
    ap.add_argument("--val-every", type=int, default=5)
    ap.add_argument("--save-every", type=int, default=25)
    ap.add_argument("--seed", type=int, default=1234)
    a = ap.parse_args()
    if a.train:
        train(a)
    elif a.say:
        voice = MmsKaren("base" if a.base else a.model, deterministic=False, pace=a.pace)
        audio = voice.say(a.say)
        tag = "base" if a.base else Path(a.model or latest_checkpoint()).stem
        out = Path(a.out) if a.out else OUT / f"mms_{tag}.wav"
        write_wav(audio / max(1e-9, np.abs(audio).max()) * 0.9, voice.fs, out)
        if voice.text.dropped:
            print("dropped:", voice.text.dropped)
        print(f"{len(audio) / voice.fs:.1f}s -> {out}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
