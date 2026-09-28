#!/usr/bin/env python3
"""Read Sgaw Karen aloud with a Burmese voice, respelled for its mouth and retuned for Karen's tones.

    python "NGAW KAREN TTS/karen_speech.py" Matt 6 9-13              # writes audio/ksw/Matthew_06_9-13.wav
    python "NGAW KAREN TTS/karen_speech.py" Gen 1 1-5 --show          # also print each syllable's respelling and tone
    python "NGAW KAREN TTS/karen_speech.py" --text "ဒီးယွၤစံးဝဲဒၣ်" --out try.wav
    python "NGAW KAREN TTS/karen_speech.py" Gen 1 1-5 --plain         # the Burmese voice's own tones, no retuning

No phone or computer ships a Sgaw Karen voice, and the only offline voice for
the Myanmar script on hand is Meta's Burmese one (facebook/mms-tts-mya). Fed
Karen as written, it reads nonsense: Karen borrowed the Burmese letters but
not their sounds - ိ is /o/ in Karen and /i/ in Burmese, ံ is /i/ and not a
nasal, ့ is the vowel /e/ and not a tone - and Karen's own six tone letters
(ၢ် ာ် း ၣ် ၤ and none) are not in the voice's alphabet at all, so it drops
them, and tone is what tells Karen words apart.

Two things are done about that, and they are kept apart:

  respelling  Each Karen syllable (consonant, optional medial, vowel sign,
              tone mark - the table is regular and public, Wade 1861) is
              rewritten as the Burmese spelling with the nearest consonant and
              vowel, in Burmese's plain low tone. The Burmese voice supplies
              the mouth: the consonants, the vowels, the timbre.
  retuning    Burmese has four tones and Karen six, so the voice cannot say
              Karen's tones however it is spelled. Instead each syllable is
              synthesised on its own, taken apart with the WORLD vocoder into
              pitch, timbre and breath, given the pitch curve and the length
              of its Karen tone, and put back together - the way a Vocaloid
              editor drags a note's pitch and length on a piano roll. The
              curves are in TONES below, six lines, and are the first thing a
              Karen listener should correct.

What is still lost: the vowels /ɨ/ and /ə/, which Burmese lacks (said as /u/
and a short /a/), and the medial /ɣ/, which becomes a short syllable of its
own. It is an accent, then, not Karen - a first thing to play to a Karen
listener, who alone can say whether it can be followed. A Karen voice of our
own needs a Karen speaker recorded. Needs: pip install torch transformers
pyworld scipy.
"""
import argparse
import json
import re
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))   # books.py and friends
from books import BOOKS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent          # the project
HERE = Path(__file__).resolve().parent                 # NGAW KAREN TTS
VERSES = ROOT / "sources" / "ksw-mason" / "verses.jsonl"
AUDIO = HERE / "audio" / "ksw"
VOICE = "facebook/mms-tts-mya"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# Karen consonant -> Burmese letter with the nearest sound. Karen ဂ is /ɣ/ and
# ဃ is /x/, for which Burmese has ဂ /g/ and ခ /kʰ/; ၡ /ʃ/ is Burmese ရှ; ဧ /ɦ/
# is a breathy h. Everything else keeps its sound across the two languages.
CONSONANTS = {"က": "က", "ခ": "ခ", "ဂ": "ဂ", "ဃ": "ခ", "င": "င", "စ": "စ", "ဆ": "ဆ", "ၡ": "ရှ", "ည": "ည",
              "တ": "တ", "ထ": "ထ", "ဒ": "ဒ", "န": "န", "ပ": "ပ", "ဖ": "ဖ", "ဘ": "ဘ", "မ": "မ",
              "ယ": "ယ", "ရ": "ရ", "လ": "လ", "ဝ": "ဝ", "သ": "သ", "ဟ": "ဟ", "အ": "အ", "ဧ": "ဟ"}
# Karen medials: ှ is /ɣ/ (no Burmese equivalent: it becomes its own short
# syllable), ၠ is /j/, ျ is /l/ in the old reading and /j/ in the modern one
# (Burmese ျ, /j/, serves both), ြ is /r/, ွ is /w/.
MEDIALS = {"ၠ": "ျ", "ျ": "ျ", "ြ": "ြ", "ွ": "ွ"}
# Karen vowel sign -> the vowel it stands for. No sign is the inherent /a/.
VOWELS = {"": "a", "ါ": "a", "ာ": "a", "ံ": "i", "ၢ": "ə", "်": "ə", "ု": "ɨ", "ူ": "u", "့": "e", "ဲ": "ɛ", "ိ": "o", "ီ": "ɔ"}
# Burmese spelling of each vowel in Burmese's plain low tone, after the
# consonant; the Karen tone is put on afterwards by retuning. /ɨ/ and /ə/ do
# not exist in Burmese: /ɨ/ is said as /u/ (northern-Thai Karen say [ɯ], which
# is nearer that than anything else), /ə/ as the bare consonant's short /a/.
PLAIN = {"a": "ာ", "i": "ီ", "u": "ူ", "e": "ေ", "ɛ": "ယ်", "o": "ို", "ɔ": "ော်", "ɨ": "ူ", "ə": ""}
# The same, in the Burmese tone nearest each Karen tone, for --plain.
SPELL = {  # vowel: (high, low, creaky, checked)
    "a": ("ား", "ာ", "", "တ်"), "i": ("ီး", "ီ", "ိ", "စ်"), "u": ("ူး", "ူ", "ု", "ုတ်"),
    "e": ("ေး", "ေ", "ေ့", "ိတ်"), "ɛ": ("ဲ", "ယ်", "ဲ့", "က်"), "o": ("ိုး", "ို", "ို့", "ုတ်"),
    "ɔ": ("ော", "ော်", "ော့", "ော့"), "ɨ": ("ူး", "ူ", "ု", "ုတ်"), "ə": ("", "", "", ""),
}
BURMESE_TONE = {"": 0, "ၤ": 1, "ၢ်": 2, "ၣ်": 2, "ာ်": 3, "း": 3}

# Karen's six tones as pitch curves and lengths, after Wade's descriptions of
# 1861 ("a heavy falling inflection", "abruptly, at a low pitch", ...). Pitch
# is in semitones from the voice's own middle, given at the start, middle and
# end of the syllable; length is relative to what the Burmese voice said; an
# abrupt tone is cut short with a glottal stop. Six lines to correct by ear.
TONES = {
    "":   {"name": "rising",           "pitch": (-2, 0, 3),   "length": 1.0, "cut": False},
    "ၤ":  {"name": "level, prolonged", "pitch": (0, 0, 0),    "length": 1.35, "cut": False},
    "ၢ်": {"name": "heavy falling",    "pitch": (4, 0, -5),   "length": 1.1, "cut": False},
    "ၣ်": {"name": "circumflex",       "pitch": (1, 4, -2),   "length": 1.0, "cut": False},
    "ာ်": {"name": "abrupt, low",      "pitch": (-4, -4, -5), "length": 0.55, "cut": True},
    "း":  {"name": "abrupt, mid",      "pitch": (0, 0, -1),   "length": 0.55, "cut": True},
}
# A consonant with the killer alone (ဒ်, မ်) is a short /ə/ syllable, as in ဒ် "like".
SYLLABLE = re.compile(r"([က-အဧၡ])([ှၠျြွ]*)([ါာံၢုူ့ဲိီ](?!်)|်)?(ၢ်|ာ်|ၣ်|း|ၤ)?")
GAP = {"syllable": 0.02, "space": 0.14, "၊": 0.28, "။": 0.5}


def syllables(text):
    """Karen text -> [(kind, payload)]: ("syl", (burmese_plain, tone_mark, burmese_toned)),
    ("gap", seconds) at a space or a stop, anything else dropped with a note."""
    out, i = [], 0
    text = text.replace(".", "။").replace(",", "၊")
    while i < len(text):
        ch = text[i]
        if ch in " \n":
            out.append(("gap", GAP["space"]))
            i += 1
            continue
        if ch in "၊။":
            out.append(("gap", GAP[ch]))
            i += 1
            continue
        m = SYLLABLE.match(text, i)
        if not m:
            i += 1                                     # a stray mark: nothing to say for it
            continue
        cons, medials, vowel, tone = m.group(1), m.group(2) or "", m.group(3) or "", m.group(4) or ""
        onset, lead = CONSONANTS[cons], ""
        for med in medials:
            if med == "ှ":                    # /ɣ/: a short syllable of its own before the vowel
                lead, onset = onset, "ဂ"
            else:
                onset += MEDIALS[med]
        v = VOWELS[vowel]
        if lead:
            out.append(("syl", (lead, "း", lead + SPELL["a"][3])))          # the released consonant, short
        out.append(("syl", (onset + PLAIN[v], tone, onset + SPELL[v][BURMESE_TONE[tone]])))
        i = m.end()
    return out


def karen_verses(book, chapter, verses):
    name = BOOKS[book]["name"]
    want = set(verses)
    rows = [json.loads(l) for l in VERSES.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r["ksw"] for r in rows if r["book"] == name and r["chapter"] == chapter and r["verse"] in want]


class Voice:
    def __init__(self):
        import torch
        from transformers import AutoTokenizer, VitsModel
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(VOICE)
        self.model = VitsModel.from_pretrained(VOICE).eval()   # small enough for the CPU; the GPU may be busy
        self.fs = self.model.config.sampling_rate
        self.cache = {}

    def say(self, burmese):
        import numpy as np
        if burmese not in self.cache:
            with self.torch.no_grad():
                wav = self.model(**self.tok(burmese, return_tensors="pt")).waveform[0].numpy().astype(np.float64)
            self.cache[burmese] = trim(wav, self.fs)
        return self.cache[burmese]


def trim(wav, fs, floor=0.02):
    """Cut the silence the voice puts round a lone syllable, keeping 10 ms each side."""
    import numpy as np
    loud = np.abs(wav) > floor * max(1e-9, np.abs(wav).max())
    if not loud.any():
        return wav
    a, b = np.argmax(loud), len(loud) - np.argmax(loud[::-1])
    pad = int(fs * 0.01)
    return wav[max(0, a - pad):min(len(wav), b + pad)]


def retune(wav, fs, tone, base_f0):
    """One syllable, given its Karen tone: pitch curve, length, and the cut of an
    abrupt tone, through the WORLD vocoder (analysis - edit - resynthesis)."""
    import numpy as np
    import pyworld as pw
    spec = TONES[tone]
    f0, t = pw.harvest(wav, fs, f0_floor=70, f0_ceil=400)
    sp = pw.cheaptrick(wav, f0, t, fs)
    ap = pw.d4c(wav, f0, t, fs)
    n = len(f0)
    # length: resample the frame tracks
    m = max(4, int(round(n * spec["length"])))
    src = np.linspace(0, n - 1, m)
    idx = np.clip(np.round(src).astype(int), 0, n - 1)
    f0, sp, ap = f0[idx], sp[idx], ap[idx]
    # pitch: the tone's curve over the voiced part, in semitones from the voice's middle
    voiced = f0 > 0
    if voiced.any():
        pos = np.linspace(0, 1, m)
        a, b, c = spec["pitch"]
        st = np.where(pos < 0.5, a + (b - a) * pos / 0.5, b + (c - b) * (pos - 0.5) / 0.5)
        target = base_f0 * 2 ** (st / 12)
        f0 = np.where(voiced, target, 0.0)
    out = pw.synthesize(f0, sp, ap, fs)
    if spec["cut"]:                                     # a glottal stop: a fast fade, not a click
        k = min(len(out), int(fs * 0.03))
        out[-k:] *= np.linspace(1, 0, k)
    return out


def render(items, voice, tuned=True, show=False):
    """The syllables and gaps of a passage as one waveform."""
    import numpy as np
    parts = []
    if tuned:
        # The voice's middle pitch, so every syllable's tone is relative to the same speaker
        import pyworld as pw
        med = []
        for kind, p in items:
            if kind == "syl":
                f0, _ = pw.harvest(voice.say(p[0]), voice.fs, f0_floor=70, f0_ceil=400)
                med += list(f0[f0 > 0])
        base_f0 = float(np.median(med)) if med else 180.0
    for kind, p in items:
        if kind == "gap":
            parts.append(np.zeros(int(voice.fs * p)))
            continue
        plain, tone, toned = p
        if show:
            print(f"   {plain:8} tone {tone or '(none)':4} {TONES[tone]['name']}")
        wav = retune(voice.say(plain), voice.fs, tone, base_f0) if tuned else voice.say(toned)
        parts += [wav, np.zeros(int(voice.fs * GAP["syllable"]))]
    audio = np.concatenate(parts) if parts else np.zeros(1)
    return audio / max(1e-9, np.abs(audio).max()) * 0.9


class PiperKaren:
    """A Piper voice trained on Vietnamese, fed Karen as phonemes (karen_phonemes.piper).

    Vietnamese has six tones and a neural voice for them exists; Karen's six
    ride on the nearest of those, one line per tone in karen_phonemes.TONES.
    Unlike the Burmese route there is no respelling and no retuning: the
    phonemes say the sounds and the tone symbols say the pitch, and the voice
    does the rest. Needs models/piper/vi_VN-vais1000-medium.onnx (rhasspy/piper-voices).
    """
    MODEL = ROOT / "models" / "piper" / "vi_VN-vais1000-medium.onnx"

    PACE = 1.1        # a tenth slower than the voice's own pace: a Karen listener followed it better that way

    def __init__(self, model=None, speaker=None, deterministic=True, pace=None):
        from piper import PiperVoice, SynthesisConfig
        import karen_phonemes
        self.kp = karen_phonemes
        self.voice = PiperVoice.load(str(model or self.MODEL))
        self.fs = self.voice.config.sample_rate
        # Piper adds a little noise to each rendering for liveliness; a
        # measurement or a fit needs the same word to come out the same way
        # twice, so by default the noise is off. deterministic=False for
        # listening copies.
        self.syn = SynthesisConfig(speaker_id=speaker, noise_scale=0.0 if deterministic else None,
                                   noise_w_scale=0.0 if deterministic else None,
                                   length_scale=self.PACE if pace is None else pace)

    def say(self, karen):
        import numpy as np
        phonemes = [p for p in self.kp.piper(self.kp.syllables(karen)) if p]
        ids = self.voice.phonemes_to_ids(phonemes)
        audio = self.voice.phoneme_ids_to_audio(ids, self.syn) if self.syn else self.voice.phoneme_ids_to_audio(ids)
        audio = np.asarray(audio, dtype=np.float64)
        if audio.dtype != np.float64 or np.abs(audio).max() > 1.5:      # int16 came back
            audio = audio / 32768.0
        return audio


def write_wav(audio, fs, path):
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS code, e.g. Matt")
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("verses", nargs="?", help="e.g. 9-13 (default: the whole chapter)")
    ap.add_argument("--text", help="Karen text to read instead of a passage")
    ap.add_argument("--out", help="where to write the .wav")
    ap.add_argument("--plain", action="store_true", help="no retuning: the Burmese voice's nearest tones")
    ap.add_argument("--pace", type=float, default=None, help="piper: 1.0 is the voice's own speed, 1.1 a tenth slower (the default)")
    ap.add_argument("--engine", choices=["burmese", "piper", "mms"], default="burmese",
                    help="burmese: Meta's Burmese voice respelled and retuned; piper: a Vietnamese neural voice fed Karen phonemes; "
                         "mms: the Burmese voice fine-tuned on Karen (train_mms.py)")
    ap.add_argument("--model", help="mms: the checkpoint to read with (default: the newest run)")
    ap.add_argument("--show", action="store_true", help="print each syllable's respelling and tone")
    a = ap.parse_args()
    if a.text:
        karen = [a.text]
        out = Path(a.out or AUDIO / "text.wav")
    else:
        if not (a.book and a.chapter):
            ap.error("give a book and chapter, or --text")
        if a.verses:
            lo, _, hi = a.verses.partition("-")
            wanted = list(range(int(lo), int(hi or lo) + 1))
        else:
            wanted = list(range(1, 200))
        karen = karen_verses(a.book, a.chapter, wanted)
        if not karen:
            raise SystemExit("no such verses in the Karen Bible")
        out = Path(a.out or AUDIO / f"{BOOKS[a.book]['name'].replace(' ', '_')}_{a.chapter:02d}"
                   f"{'_' + a.verses if a.verses else ''}{'_plain' if a.plain else ''}.wav")
    if a.engine in ("piper", "mms"):
        import numpy as np
        if a.engine == "mms":
            from train_mms import MmsKaren
            voice = MmsKaren(a.model, deterministic=False, pace=a.pace or 1.0)
        else:
            voice = PiperKaren(deterministic=False, pace=a.pace)
        parts = []
        for k in karen:
            if a.show:
                print("KAREN", k)
                if a.engine == "piper":
                    print("  " + "".join(voice.kp.piper(voice.kp.syllables(k))))
            parts += [voice.say(k), np.zeros(int(voice.fs * 0.5))]
        audio = np.concatenate(parts)
        audio = audio / max(1e-9, np.abs(audio).max()) * 0.9
        items = [("syl", None) for k in karen for it in syllables(k) if it[0] == "syl"]
        if not a.out:
            out = out.with_name(out.stem + "_" + a.engine + out.suffix)
        write_wav(audio, voice.fs, out)
        print(f"{len(karen)} verse(s), {len(items)} syllables, {len(audio) / voice.fs:.0f}s of audio -> {out}")
        return
    voice = Voice()
    items = []
    for k in karen:
        if a.show:
            print("KAREN", k)
        items += syllables(k) + [("gap", GAP["။"])]
    audio = render(items, voice, tuned=not a.plain, show=a.show)
    write_wav(audio, voice.fs, out)
    print(f"{len(karen)} verse(s), {sum(1 for k, _ in items if k == 'syl')} syllables, "
          f"{len(audio) / voice.fs:.0f}s of audio -> {out}")


if __name__ == "__main__":
    main()
