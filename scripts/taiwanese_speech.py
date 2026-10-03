#!/usr/bin/env python3
"""Read the Taiwanese Bible aloud with a Taiwanese voice.

    python scripts/taiwanese_speech.py John 1 1-5          # writes audio/nan/John_01_1-5.wav
    python scripts/taiwanese_speech.py --text "太初有道，道佮上帝同在，道就是上帝。"
    python scripts/taiwanese_speech.py John 1 1 --show     # also print each piece's Tâi-lô and what the voice is given
    python scripts/taiwanese_speech.py --all               # every chapter not yet recorded (the dashboard job)

The voice is ga642381's Taiwanese Speech Synthesis (github.com/ga642381/
Taiwanese-Speech-Synthesis, MIT): a Tacotron2 and a WaveRNN trained on the
SuíSiann recordings of one Taiwanese speaker (public domain), with the
weights from the author's Google Drive. It does not read Chinese characters.
It reads a phonetic spelling of Taiwanese as it is spoken - tone sandhi
already applied, the way 意傳's 臺灣言語工具 writes it ('tai7-ʔuan7 si3
tsit10-ʔe7 ...'). So each verse goes three steps:

  1. characters -> Tâi-lô. The MOE dictionary of Taiwan Southern Min gives
     the reading of every headword; a verse is cut by the longest headword
     that fits, and a character left over takes the reading it most often
     has in the dictionary's own example sentences (which give each one in
     characters and in Tâi-lô), or its own headword's, or failing both the
     literary reading in Campbell's 1913 character dictionary. Our Taiwanese is
     written in the MOE characters (scripts/taiwanese_from_zh.py), so most
     of it is found.
  2. Tâi-lô -> spoken form: 臺灣言語工具's 台灣話口語講法 applies the sandhi.
  3. spoken form -> sound: Tacotron2 makes the spectrogram, the voice's own
     WaveRNN the wave, and DeepFilterNet takes out the hiss WaveRNN leaves
     (see Voice and Cleaner).

The voice stops at 1,000 spectrogram frames (~12 s), so a verse is read a
clause at a time, clauses joined while they stay short. A character with no
reading anywhere is left out and named, verse by verse, as the Hakka reader
does. What to listen for: names (read a character at a time, in the
dictionary's everyday readings, where a Taiwanese Bible may use literary
ones), and characters with two readings the longest-match got wrong.

The voice's code wants its own environment (Python 3.10, numpy 1.x); this
script moves into it by itself. To set it up once:

    git clone https://github.com/ga642381/Taiwanese-Speech-Synthesis sources/taiwanese-tts/code
    python -m gdown --folder https://drive.google.com/drive/folders/1XuQ2Q4CAU4By_E45JW-G-4CiGM8e8HV8 -O sources/taiwanese-tts/weights
    uv venv --python 3.10 sources/taiwanese-tts/.venv
    uv pip install --python sources/taiwanese-tts/.venv/Scripts/python.exe "torch==2.8.*" --index-url https://download.pytorch.org/whl/cu128
    uv pip install --python sources/taiwanese-tts/.venv/Scripts/python.exe "numpy<2" scipy librosa soundfile unidecode inflect matplotlib psutil tai5-uan5_gian5-gi2_kang1-ku7 huggingface_hub deepfilternet praat-parselmouth
    uv pip install --python sources/taiwanese-tts/.venv/Scripts/python.exe "torchaudio==2.8.*" --index-url https://download.pytorch.org/whl/cu128
    git clone --depth 1 https://github.com/NVIDIA/BigVGAN sources/taiwanese-tts/bigvgan       # only for --vocoder bigvgan
"""
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import wave
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = ROOT / "sources" / "taiwanese-tts"
VENV = HOME / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

# Run in the voice's own environment, in UTF-8 mode (as hakka_speech.py does).
if Path(sys.prefix).resolve() != VENV.resolve() or not sys.flags.utf8_mode:
    if not VENV_PY.exists():
        raise SystemExit(f"the Taiwanese voice's environment is not set up; see the top of {Path(__file__).name}")
    raise SystemExit(subprocess.call([str(VENV_PY), __file__, *sys.argv[1:]], env={**os.environ, "PYTHONUTF8": "1"}))

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402

CODE = HOME / "code"
WEIGHTS = HOME / "weights"
DICT = ROOT / "sources" / "taigi-dict" / "dict-twblg.json"
DICT_URL = "https://raw.githubusercontent.com/g0v/moedict-data-twblg/master/dict-twblg.json"
LEXICON = ROOT / "sources" / "taigi-dict" / "lexicon.json"
KAM = ROOT / "sources" / "taigi-dict" / "kam.csv"
KAM_URL = ("https://raw.githubusercontent.com/ChhoeTaigi/ChhoeTaigiDatabase/master/ChhoeTaigiDatabase/"
           "ChhoeTaigi_KamJitian.csv")
VERSES = ROOT / "output" / "nan" / "json"
AUDIO = ROOT / "audio" / "nan"
LONGEST = 8              # the longest headword looked for
PIECE = 22               # syllables a piece may grow to before it is read on its own
TARGET, OVERLAP = 4400, 440   # WaveRNN folds (--vocoder wavernn): smaller folds, more at once - twice the repo's speed
PITCH = 3.0            # semitones up: ~205 Hz -> ~245 Hz, easier to follow (raise_pitch)
BIGVGAN_CODE = HOME / "bigvgan"
BIGVGAN_MODEL = "nvidia/bigvgan_v2_22khz_80band_256x"
BIGVGAN_HOP = 256
GAP = {"clause": 0.25, "sentence": 0.45, "verse": 0.7}
HAN = re.compile(r"[㐀-鿿\U00020000-\U0003ffff]")
PUNCT = "，、；：。！？,;:.!?"


# ------------------------------------------------------------------ characters -> Tâi-lô
def syllables(tailo):
    """The syllables of a Tâi-lô string, lower case, marks kept."""
    t = unicodedata.normalize("NFC", tailo.lower())
    t = re.sub(r"[，。、；：？！,.;:?!「」『』“”\"'()（）…—]", " ", t)
    return [s for s in re.split(r"[\s\-]+", t) if s]


def build_lexicon():
    """{word: Tâi-lô} for every headword, and {character: Tâi-lô} for every
    character, from the MOE dictionary. A character's reading is the one its
    example sentences and the headwords it is part of give it most often
    (both are written in characters and in Tâi-lô, and where the counts
    match, character by character), else its own headword's."""
    if not DICT.exists():
        import urllib.request
        DICT.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DICT_URL, DICT)
    entries = json.loads(DICT.read_text(encoding="utf-8"))
    words, heads = {}, {}
    seen = defaultdict(Counter)
    for e in entries:
        title = e.get("title", "")
        for h in e.get("heteronyms", [])[:1]:
            trs = (h.get("trs") or "").split("/")[0].strip()
            if not trs or not title or not all(HAN.match(c) for c in title):
                continue
            if len(syllables(trs)) == len(title):
                words.setdefault(title, unicodedata.normalize("NFC", trs.lower()))
                if len(title) == 1:
                    heads[title] = words[title]
                else:                              # a character found only inside a word (藉 in 藉口) still has a reading
                    for c, s in zip(title, syllables(trs)):
                        seen[c][s] += 1
        for h in e.get("heteronyms", []):
            for d in h.get("definitions", []):
                for ex in d.get("example", []):
                    m = re.match(r"￹(.*?)￺(.*?)￻", ex, re.S)
                    if not m:
                        continue
                    chars = [c for c in m.group(1) if HAN.match(c)]
                    syl = syllables(m.group(2))
                    if len(chars) == len(syl):
                        for c, s in zip(chars, syl):
                            seen[c][s] += 1
    chars = {c: n.most_common(1)[0][0] for c, n in seen.items()}
    for c, t in heads.items():
        chars.setdefault(c, t)
    # What the MOE dictionary lacks is mostly the characters of names (約翰's
    # 翰, 摩西's 摩) and bookish words (榮耀's 耀): Campbell's 1913 character
    # dictionary (甘字典, as ChhoeTaigi keeps it, CC BY-NC-SA 3.0 TW) has them,
    # in Tâi-lô, with the literary reading a name is read in.
    if not KAM.exists():
        import urllib.request
        urllib.request.urlretrieve(KAM_URL, KAM)
    import csv
    with KAM.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            c = r.get("HanLoTaibunPoj", "")
            reading = (r.get("HanbunImKipUnicode") or r.get("KipUnicode") or "").split("/")[0].split(",")[0].strip()
            if len(c) == 1 and HAN.match(c) and c not in chars and reading and len(syllables(reading)) == 1:
                chars[c] = syllables(reading)[0]
    LEXICON.write_text(json.dumps({"words": words, "chars": chars}, ensure_ascii=False), encoding="utf-8")
    return words, chars


def lexicon():
    if LEXICON.exists() and LEXICON.stat().st_mtime >= DICT.stat().st_mtime:
        d = json.loads(LEXICON.read_text(encoding="utf-8"))
        return d["words"], d["chars"]
    return build_lexicon()


def to_tailo(text, words, chars):
    """Taiwanese in characters -> Tâi-lô words (space between, hyphens
    within), punctuation kept as , . ? - and the characters with no reading."""
    out, unknown, i = [], [], 0
    while i < len(text):
        c = text[i]
        if not HAN.match(c):
            if c in "。！":
                out.append(".")
            elif c in "？?":
                out.append("?")
            elif c in PUNCT:
                out.append(",")
            i += 1
            continue
        for n in range(min(LONGEST, len(text) - i), 0, -1):
            w = text[i:i + n]
            if n > 1 and w in words:
                out.append(words[w])
                i += n
                break
        else:
            if c in chars:
                out.append(chars[c])
            else:
                unknown.append(c)
            i += 1
    s = " ".join(out)
    s = re.sub(r"\s+([,.?])", r"\1", s)
    s = re.sub(r"([,.?])(?:[,.?])+", r"\1", s).strip(" ,")
    return s, unknown


def pieces(text):
    """A verse cut at its punctuation into pieces short enough for the voice:
    (piece, the pause after it)."""
    parts = [p for p in re.split(r"(?<=[，、；：。！？,;:.!?])", text) if p.strip()]
    out, cur = [], ""
    for p in parts:
        n = len(HAN.findall(p))
        if cur and len(HAN.findall(cur)) + n > PIECE:
            out.append(cur)
            cur = p
        else:
            cur += p
    if cur.strip():
        out.append(cur)
    return [(p, GAP["sentence"] if p.rstrip()[-1:] in "。！？.!?" else GAP["clause"]) for p in out]


# ------------------------------------------------------------------ the voice
def load_bigvgan(dev):
    """NVIDIA's BigVGAN v2, 22 kHz / 80 bands, from its own code (a clone in
    sources/taiwanese-tts/bigvgan) and weights (Hugging Face). Its loader
    does not agree with the huggingface_hub installed here, so the two files
    are fetched and loaded by hand. Its code has a utils.py, and the voice's
    code a utils package already loaded under that name: the voice's is set
    aside while BigVGAN's modules are imported, then put back."""
    import torch
    from huggingface_hub import snapshot_download
    theirs = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "utils" or k.startswith("utils.")}
    sys.path.insert(0, str(BIGVGAN_CODE))
    try:
        import bigvgan
        from env import AttrDict
    finally:
        sys.path.remove(str(BIGVGAN_CODE))
        for k in [k for k in sys.modules if k == "utils" or k.startswith("utils.")]:
            sys.modules.pop(k)
        sys.modules.update(theirs)
    snap = Path(snapshot_download(BIGVGAN_MODEL, allow_patterns=["config.json", "bigvgan_generator.pt"]))
    h = AttrDict(json.loads((snap / "config.json").read_text(encoding="utf-8")))
    net = bigvgan.BigVGAN(h, use_cuda_kernel=False)
    net.load_state_dict(torch.load(snap / "bigvgan_generator.pt", map_location="cpu")["generator"])
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        net.remove_weight_norm()
    return net.eval().to(dev)


class Voice:
    """Tacotron2 for the spectrogram, then a vocoder for the wave.

    The voice came with a WaveRNN vocoder, and read by it the speech is
    scratchy: WaveRNN here samples 9-bit mu-law values, and the quantising
    is heard as a hiss over every word - the same with the repo's own fold
    sizes as with the smaller, faster ones used here, so it is the vocoder
    and not how it was run. So the hiss is taken out afterwards (Cleaner).

    NVIDIA's BigVGAN (v2, 22 kHz, 80 bands, MIT) was tried in its place: a
    vocoder trained on many voices for spectrograms of this very shape
    (22,050 Hz, 1024-point FFT, 80 mel bands, no upper cut), which reads
    Tacotron2's output once three things are undone (to_bigvgan): the
    spectrogram's decibel scale, its 40 Hz floor, and its 275-sample hop.
    It was three times faster and measured cleaner, but to the ear it buzzes
    where WaveRNN does not - a vocoder trained on real recordings, given the
    smoother spectrograms a TTS model makes, and WaveRNN was trained on this
    Tacotron2's own. --vocoder bigvgan keeps it to hand."""

    def __init__(self, vocoder="wavernn"):
        import torch
        sys.path.insert(0, str(CODE))
        from utils import hparams as hp
        with contextlib.redirect_stdout(io.StringIO()):
            hp.configure(CODE / "hparams.py")
        from tacotron2 import Tacotron2
        from utils.text import text_to_sequence
        from 臺灣言語工具.解析整理.拆文分析器 import 拆文分析器
        from 臺灣言語工具.語音合成 import 台灣話口語講法
        self.torch, self.hp, self.seq = torch, hp, text_to_sequence
        self.align, self.spoken = 拆文分析器.對齊句物件, 台灣話口語講法
        dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tts = Tacotron2().to(dev)
        with contextlib.redirect_stdout(io.StringIO()):
            self.tts.load(WEIGHTS / "tacotron2.pyt")
        self.tts.eval()
        self.dev, self.fs, self.vocoder = dev, hp.sample_rate, vocoder
        if vocoder == "wavernn":
            from wavernn import WaveRNN
            self.voc = WaveRNN(rnn_dims=hp.voc_rnn_dims, fc_dims=hp.voc_fc_dims, bits=hp.bits, pad=hp.voc_pad,
                               upsample_factors=hp.voc_upsample_factors, feat_dims=hp.num_mels,
                               compute_dims=hp.voc_compute_dims, res_out_dims=hp.voc_res_out_dims,
                               res_blocks=hp.voc_res_blocks, hop_length=hp.hop_length,
                               sample_rate=hp.sample_rate, mode=hp.voc_mode).to(dev)
            with contextlib.redirect_stdout(io.StringIO()):
                self.voc.load(WEIGHTS / "wavernn.pyt")
        else:
            self.big = load_bigvgan(dev)
            import librosa
            top = hp.sample_rate / 2
            self.src_centres = librosa.mel_frequencies(n_mels=hp.num_mels + 2, fmin=hp.fmin, fmax=top)[1:-1]
            self.big_centres = librosa.mel_frequencies(n_mels=hp.num_mels + 2, fmin=0, fmax=top)[1:-1]
        self.words, self.chars = lexicon()

    def to_bigvgan(self, mel):
        """Tacotron2's spectrogram (dB scaled to 0..1, bands from 40 Hz, a
        frame every 275 samples) as BigVGAN reads one (natural log of the
        magnitude, bands from 0 Hz, a frame every 256).

        The first way of doing it put a 'bug zapper' behind the voice: its
        high frequencies pulsed at the two frame rates, 86 and 80 times a
        second (5-6 dB above their surroundings on Matthew 5:1-8). Two things
        made it: rebuilding a full spectrum from the 80 bands and banding it
        again (a guess that jitters from frame to frame), and stretching the
        frames with straight lines, which leaves a kink at every old frame.
        Now each new band is read off the old ones at its centre frequency,
        in the log domain, and the frames are stretched with band-limited
        resampling (resample_poly): the pulse falls to 2.3 dB."""
        import numpy as np
        import scipy.signal as ss
        hp = self.hp
        floor = np.log(1e-5)
        ln = (np.clip(mel, 0, 1) * -hp.min_level_db + hp.min_level_db) / 20 * np.log(10)
        banded = np.stack([np.interp(self.big_centres, self.src_centres, ln[:, t]) for t in range(ln.shape[1])],
                          axis=1)
        stretched = ss.resample_poly(np.maximum(banded, floor), hp.hop_length, BIGVGAN_HOP, axis=1, padtype="line")
        return np.maximum(stretched, floor)

    def phonetic(self, tailo):
        """Tâi-lô -> the spoken form the voice was trained on (sandhi applied)."""
        return self.spoken(self.align(tailo, tailo)).strip() + ("" if tailo.rstrip()[-1:] in ".?" else " .")

    def sound(self, phon):
        """The wave for one piece, or None if the voice ran past its limit."""
        import numpy as np
        x = self.torch.tensor([self.seq(phon, ["basic_cleaners"])], dtype=self.torch.long, device=self.dev)
        with self.torch.no_grad(), contextlib.redirect_stdout(io.StringIO()):
            _, mel, _, _ = self.tts.inference(x)
            if mel.shape[2] >= self.hp.max_decoder_steps - 1:
                return None
            if self.vocoder == "wavernn":
                wav = self.voc.generate(mel, True, TARGET, OVERLAP, self.hp.mu_law)
            else:
                m = self.torch.tensor(self.to_bigvgan(mel[0].cpu().numpy()), dtype=self.torch.float32,
                                      device=self.dev)[None]
                wav = self.big(m)[0, 0].cpu().numpy()
        return np.asarray(wav, dtype=np.float32)

    def say(self, text, show=False):
        """One piece of Taiwanese: its wave (or None) and the characters with no reading."""
        tailo, unknown = to_tailo(text, self.words, self.chars)
        if not syllables(tailo):
            return None, unknown
        try:
            phon = self.phonetic(tailo)
        except Exception as e:                     # noqa: BLE001 - the toolkit refuses a spelling it does not know
            print(f"    could not apply sandhi to {tailo!r}: {e}", file=sys.stderr)
            return None, unknown
        if show:
            print(f"  {text}\n    {tailo}\n    {phon}")
        wav = self.sound(phon)
        if wav is None and "," in tailo:           # too long for one breath: read it in two
            half = len(text) // 2
            cut = max((m.end() for m in re.finditer(r"[，、；：]", text) if m.end() <= half + 6), default=half)
            a, ua = self.say(text[:cut], show)
            b, ub = self.say(text[cut:], show)
            import numpy as np
            parts = [p for p in (a, b) if p is not None]
            return (np.concatenate(parts) if parts else None), ua + ub
        return wav, unknown


# ------------------------------------------------------------------ passages and chapters
def verses_of(book, chapter, wanted):
    path = VERSES / f"{BOOKS[book]['name'].replace(' ', '_')}_{chapter:02d}.json"
    if not path.exists():
        raise SystemExit(f"{path.relative_to(ROOT)} is not there: the chapter has not been made in Taiwanese yet")
    verses = json.loads(path.read_text(encoding="utf-8"))["verses"]
    return [(int(n), t) for n, t in verses.items() if int(n) in wanted and t.strip()]


class Cleaner:
    """The hiss taken out of a reading: a 60 Hz high-pass for the rumble
    WaveRNN also leaves (5% of its energy was below 60 Hz), then DeepFilterNet
    (v3, MIT/Apache), a small network for taking noise out of speech, which
    works at 48 kHz. On John 1:1-5 it brought the pauses down 15 dB and left
    the speech as loud as it was, the s and sh sounds included; spectral
    gating (noisereduce), tried beside it, quietened the pauses further but
    ate 4 dB of the speech with them."""

    def __init__(self):
        from df.enhance import enhance, init_df
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.model, self.state, _ = init_df()
        self.enhance = enhance

    def __call__(self, audio, fs):
        import librosa
        import numpy as np
        import scipy.signal as ss
        import torch
        audio = ss.sosfiltfilt(ss.butter(4, 60, "highpass", fs=fs, output="sos"), audio).astype(np.float32)
        x = librosa.resample(audio, orig_sr=fs, target_sr=self.state.sr())
        with torch.no_grad():
            y = self.enhance(self.model, self.state, torch.from_numpy(x)[None])
        return librosa.resample(y[0].numpy(), orig_sr=self.state.sr(), target_sr=fs).astype(np.float32)


def raise_pitch(audio, fs, semitones):
    """The reading made higher by so many semitones, its timing and vowels
    kept: Praat's PSOLA ('Change gender', formants left where they are), so
    it is the same speaker a little higher rather than a sped-up tape. The
    SuíSiann voice reads around 205 Hz; a listener found it easier to
    follow higher (PITCH)."""
    import numpy as np
    import parselmouth
    from parselmouth.praat import call
    if not semitones:
        return audio
    snd = parselmouth.Sound(audio.astype(np.float64), fs)
    f0 = snd.to_pitch(pitch_floor=60, pitch_ceiling=500).selected_array["frequency"]
    f0 = f0[f0 > 0]
    if not len(f0):
        return audio
    out = call(snd, "Change gender", 60, 500, 1.0, float(np.median(f0)) * 2 ** (semitones / 12), 1.0, 1.0)
    return out.values[0].astype(np.float32)


def read(voice, passage, show=False, clean=None, pitch=0.0):
    import numpy as np
    parts, unread = [], []
    for n, text in passage:
        text = re.sub(r"[「」『』（）()“”‘’]", "", text.replace("\n", "，"))
        for piece, gap in pieces(text):
            wav, unknown = voice.say(piece, show)
            unread += [(n, c) for c in unknown]
            if wav is not None:
                parts += [wav, np.zeros(int(voice.fs * gap), dtype=np.float32)]
        parts.append(np.zeros(int(voice.fs * GAP["verse"]), dtype=np.float32))
    audio = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    if clean is not None and len(audio) > voice.fs:
        audio = clean(audio, voice.fs)
    if len(audio) > voice.fs:
        audio = raise_pitch(audio, voice.fs, pitch)
    return audio / max(1e-9, float(np.abs(audio).max())) * 0.9, unread


def write_wav(audio, fs, path):
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def translating():
    """Whether the Taiwanese text is still being made (scripts/taiwanese_from_zh.py)."""
    try:
        import psutil
        return any("taiwanese_from_zh.py" in " ".join(p.info["cmdline"] or ())
                   for p in psutil.process_iter(["cmdline"]))
    except Exception:                          # noqa: BLE001
        return False


def stale_chapters():
    """(book, chapter) of every Taiwanese chapter with no recording, or with
    text newer than its recording - New Testament first, as the text is made."""
    order = sorted(BOOKS, key=lambda c: (BOOKS[c]["testament"] != "NT", BOOKS[c]["num"]))
    out = []
    for code in order:
        name = BOOKS[code]["name"].replace(" ", "_")
        for f in sorted(VERSES.glob(f"{name}_*.json")):
            if f.stem.rsplit("_", 1)[0] != name:
                continue
            ch = int(f.stem.rsplit("_", 1)[1])
            wav = AUDIO / f"{name}_{ch:02d}.wav"
            if not wav.exists() or wav.stat().st_mtime < f.stat().st_mtime:
                out.append((code, ch))
    return out


def read_all(vocoder="wavernn", clean=True, pitch=None):
    """Every Taiwanese chapter not yet recorded, with the voice loaded once;
    it waits for more while the text is still being made. The dashboard's
    taiwanese-voice job, stoppable at any point: a chapter is written whole."""
    voice = cleaner = None
    while True:
        todo = stale_chapters()
        if not todo:
            if translating():
                time.sleep(60)
                continue
            print("every Taiwanese chapter is recorded")
            return
        if voice is None:
            voice, cleaner = Voice(vocoder), (Cleaner() if clean else None)
        for code, ch in todo:
            passage = verses_of(code, ch, range(1, 200))
            if not passage:
                continue
            t0 = time.time()
            audio, unread = read(voice, passage, clean=cleaner, pitch=PITCH if pitch is None else pitch)
            write_wav(audio, voice.fs, AUDIO / f"{BOOKS[code]['name'].replace(' ', '_')}_{ch:02d}.wav")
            print(f"{BOOKS[code]['name']} {ch}: {len(passage)} verses, {len(audio) / voice.fs:.0f}s of audio in "
                  f"{time.time() - t0:.0f}s" + (f", no reading for {' '.join(sorted({c for _, c in unread}))}"
                                                if unread else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS code, e.g. John")
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("verses", nargs="?", help="e.g. 1-5 (default: the whole chapter)")
    ap.add_argument("--all", action="store_true", help="record every Taiwanese chapter not yet recorded (or changed since)")
    ap.add_argument("--text", help="Taiwanese (in characters) to read instead of a passage")
    ap.add_argument("--out", help="where to write the .wav")
    ap.add_argument("--show", action="store_true", help="print each piece's Tâi-lô and the spoken form the voice is given")
    ap.add_argument("--vocoder", choices=["wavernn", "bigvgan"], default="wavernn",
                    help="wavernn (default, the voice's own) or bigvgan (faster, but buzzes)")
    ap.add_argument("--pitch", type=float, default=PITCH,
                    help=f"semitones higher than the voice reads (default {PITCH:g}; 0 for its own pitch)")
    ap.add_argument("--clean", choices=["dfn", "none"], default="dfn",
                    help="dfn (default): take the hiss out with DeepFilterNet; none: leave the vocoder's output as it is")
    ap.add_argument("--rebuild-lexicon", action="store_true", help="rebuild the reading lexicon from the dictionary")
    a = ap.parse_args()
    if a.rebuild_lexicon:
        w, c = build_lexicon()
        print(f"lexicon: {len(w)} words, {len(c)} characters")
        if not (a.book or a.text or a.all):
            return
    if a.all:
        read_all(a.vocoder, a.clean == "dfn", a.pitch)
        return
    if a.text:
        passage, stem = [(None, a.text)], "text"
    else:
        if not (a.book and a.chapter):
            ap.error("give a book and chapter, or --text, or --all")
        if a.book not in BOOKS:
            ap.error(f"no book {a.book!r}; use the OSIS code, e.g. Gen, John, 1Cor")
        lo, _, hi = (a.verses or "1-200").partition("-")
        passage = verses_of(a.book, a.chapter, range(int(lo), int(hi or lo) + 1))
        stem = f"{BOOKS[a.book]['name'].replace(' ', '_')}_{a.chapter:02d}{'_' + a.verses if a.verses else ''}"
    t0 = time.time()
    voice = Voice(a.vocoder)
    audio, unread = read(voice, passage, a.show, Cleaner() if a.clean == "dfn" else None, a.pitch)
    out = Path(a.out) if a.out else AUDIO / f"{stem}.wav"
    write_wav(audio, voice.fs, out)
    print(f"{len(passage)} verse(s), {len(audio) / voice.fs:.0f}s of audio in {time.time() - t0:.0f}s -> {out}")
    if unread:
        print("no reading, left out:", file=sys.stderr)
        for n, c in unread:
            print(f"  {'v' + str(n) + ' ' if n else ''}{c}", file=sys.stderr)


if __name__ == "__main__":
    main()
