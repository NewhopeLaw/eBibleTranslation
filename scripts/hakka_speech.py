#!/usr/bin/env python3
"""Read the Hakka Bible aloud with a Taiwanese Hakka voice.

    python scripts/hakka_speech.py John 1 1-5                # writes audio/hak/John_01_1-5.wav
    python scripts/hakka_speech.py Gen 1 --speaker 羅盛滿      # another reader
    python scripts/hakka_speech.py --text "太初有道，道同上帝共下，道就係上帝。" --speaker all
    python scripts/hakka_speech.py John 1 1 --show           # also print each word's reading
    python scripts/hakka_speech.py --all                      # every chapter not yet recorded (the dashboard job)

No phone or computer ships a Hakka voice; the reader falls back to Taiwan
Mandarin, which reads the characters as Mandarin and is not Hakka at all.
Hakka is better off than Sgaw Karen, though: a real voice exists. FormoSpeech
(formospeech/yourtts-htia-240704) trained a YourTTS voice on twenty Taiwanese
Hakka speakers in five dialects, and their formog2p package reads Hakka
written in the Ministry of Education's recommended characters - which is how
our Hakka target is written - into Sixian pronunciation. So nothing is
respelled or retuned here, as it has to be for Karen: the characters go to
formog2p, its readings go to the voice, and the voice speaks Sixian.

Two things the pipeline does not do for itself:

  punctuation  The voice knows only the comma and the space. A verse is cut
               at its sentence ends and read a sentence at a time, with a
               pause put in between, and the rest of the marks (、；：「」 and
               so on) become commas or go.
  unknown      A word formog2p cannot read is passed through as written, and
               the voice drops characters it has no sound for - silently. So
               every such word is printed, verse by verse, to be mended in the
               text or taught to formog2p; a listener would otherwise hear a
               gap and not know why.

Bible names are the obvious worry and mostly are not one: 伯利恆, 雅各 and the
like are in formog2p's lexicon, and a name that is not is read a character
at a time, which is how a transliterated name is read anyway. Tone sandhi is
formog2p's business, not ours. The voice and its data are CC-BY-NC 4.0, so
the audio can be given away but not sold.

The voice's library (Coqui TTS) does not run on this PC's Python 3.12, so it
lives in its own environment, and this script moves into it by itself. To
set it up once (about 3 GB; the voice, another 1 GB, downloads on first use):

    uv venv --python 3.10 sources/hakka-tts/.venv
    uv pip install --python sources/hakka-tts/.venv/Scripts/python.exe "torch==2.8.*" "torchaudio==2.8.*" --index-url https://download.pytorch.org/whl/cu128
    uv pip install --python sources/hakka-tts/.venv/Scripts/python.exe "coqui-tts>=0.24,<0.28" "transformers>=4.57,<5" formog2p huggingface_hub soundfile

(torch 2.8, not the newest: from 2.9 Coqui wants torchcodec for its audio,
which needs FFmpeg's libraries installed on Windows; and the old TTS 0.22
the FormoSpeech demo pins has no Windows build and will not compile.)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / "sources" / "hakka-tts" / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

# Run in the voice's own environment, and in UTF-8 mode: formog2p opens its
# lexicons without naming an encoding, which on Windows means cp1252 and a
# crash on the first Hakka character. The check is on sys.prefix rather than
# on whether TTS imports, so a half-built environment fails loudly in there
# instead of this script quietly re-running itself.
if Path(sys.prefix).resolve() != VENV.resolve() or not sys.flags.utf8_mode:
    if not VENV_PY.exists():
        raise SystemExit(f"the Hakka voice's environment is not set up; see the top of {Path(__file__).name}")
    raise SystemExit(subprocess.call([str(VENV_PY), __file__, *sys.argv[1:]], env={**os.environ, "PYTHONUTF8": "1"}))

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")   # Windows without developer mode copies instead; that is fine

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402

VERSES = ROOT / "output" / "hak" / "json"
AUDIO = ROOT / "audio" / "hak"
VOICE = "formospeech/yourtts-htia-240704"
DIALECT = ("hak_sx", "sixian")      # formog2p's name for Sixian, and the voice's
SPEAKER = "XF"                      # a Miaoli woman, in Sixian's home county; --speaker all to hear the rest
SENTENCE_GAP = 0.35                 # seconds of silence between the sentences of a verse
VERSE_GAP = 0.7                     # and between verses

SENTENCE_END = re.compile(r"(?<=[。！？!?])")
TO_COMMA = re.compile(r"[、；;：:,，—…]+")
DROP = re.compile(r"[「」『』《》〈〉（）()\[\]【】“”‘’\"'·．.]")


def verses_of(book, chapter, wanted):
    path = VERSES / f"{BOOKS[book]['name'].replace(' ', '_')}_{chapter:02d}.json"
    if not path.exists():
        raise SystemExit(f"{path.relative_to(ROOT)} is not there: the chapter has not been translated into Hakka yet")
    verses = json.loads(path.read_text(encoding="utf-8"))["verses"]
    return [(int(n), t) for n, t in verses.items() if int(n) in wanted and t.strip()]


def sentences(text):
    """A verse cut at its sentence ends, each with only the marks the voice knows."""
    out = []
    for s in SENTENCE_END.split(text):
        s = DROP.sub("", s)
        s = re.sub(r"[。！？!?]", "", TO_COMMA.sub("，", s))
        s = re.sub(r"，{2,}", "，", s).strip("， \n")
        if s:
            out.append(s)
    return out


def phones(ipa):
    """formog2p's IPA as the token list the voice was trained on: the word and
    syllable joins go, each tone number stays one token, the rest is spelt a
    character at a time. (As the FormoSpeech demo does it.)"""
    out = []
    for piece in re.split(r"(?<![\d])(?=[\d])|(?<=[\d])(?![\d])", ipa):
        if piece.isdigit():
            out.append(piece)
        else:
            out.extend(re.sub(r"[+\-|_]", "", piece).replace("，", " ， "))
    return out


class Voice:
    def __init__(self):
        from dataclasses import dataclass
        from typing import Dict, List

        import TTS.tts.configs.vits_config as vits_config
        from coqpit import Coqpit
        from huggingface_hub import snapshot_download

        # The voice's config lists its characters as a list, tone numbers
        # such as "55" among them; Coqui's own config wants one string of
        # single characters. The FormoSpeech demo swaps in this looser type.
        @dataclass
        class CharactersConfig(Coqpit):
            characters_class: str = None
            vocab_dict: Dict = None
            pad: str = None
            eos: str = None
            bos: str = None
            blank: str = None
            characters: List[str] = None
            punctuations: str = None
            phonemes: str = None
            is_unique: bool = True
            is_sorted: bool = True

        @dataclass
        class LooseVitsConfig(vits_config.VitsConfig):
            characters: CharactersConfig = None

        vits_config.VitsConfig = LooseVitsConfig
        import torch
        from TTS.utils.synthesizer import Synthesizer

        model = Path(snapshot_download(VOICE))
        config = (model / "config.json").read_text(encoding="utf-8")
        for name in ("speakers.pth", "language_ids.json", "speaker_embs.pth"):
            config = config.replace(name, (model / name).as_posix())
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(config)
        try:
            self.syn = Synthesizer(tts_checkpoint=str(model / "model.pth"), tts_config_path=f.name,
                                   use_cuda=torch.cuda.is_available())
        finally:
            os.unlink(f.name)
        self.fs = self.syn.tts_model.config.audio.sample_rate
        self.speakers = self.syn.tts_model.speaker_manager.speaker_names

    def say(self, text, speaker, pace=1.0, show=False):
        """One sentence: its audio, and the words formog2p could not read."""
        import numpy as np
        from formog2p.hakka import g2p

        r = g2p(text, DIALECT[0], "ipa")
        if show:
            print("  " + " ".join(f"{d['word']}[{p}]" for d, p in zip(r.details, r.pronunciations)))
        tokens = phones(" ".join(p.replace(" ", "|") for p in r.pronunciations))
        self.syn.tts_model.length_scale = pace
        wav = self.syn.tts(tokens, speaker_name=speaker, language_name=DIALECT[1], split_sentences=False)
        return np.asarray(wav, dtype=np.float32), [w for w in r.unknown_words if w != "，"]


def write_wav(audio, fs, path):
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())


def read(voice, passage, speaker, pace, show):
    """The passage as one track, and every unread word with its verse."""
    import numpy as np
    parts, unread = [], []
    for n, text in passage:
        if show:
            print(f"{n or ''} {text}".strip())
        for i, s in enumerate(sentences(text)):
            if i:
                parts.append(np.zeros(int(voice.fs * SENTENCE_GAP), dtype=np.float32))
            wav, unknown = voice.say(s, speaker, pace, show)
            parts.append(wav)
            unread += [(n, w) for w in unknown]
        parts.append(np.zeros(int(voice.fs * VERSE_GAP), dtype=np.float32))
    audio = np.concatenate(parts)
    return audio / max(1e-9, float(np.abs(audio).max())) * 0.9, unread


def translating():
    """Whether the Hakka text is still being made (scripts/hakka_from_zh.py)."""
    try:
        import psutil
        return any("hakka_from_zh.py" in " ".join(p.info["cmdline"] or ())
                   for p in psutil.process_iter(["cmdline"]))
    except Exception:                          # noqa: BLE001 - no psutil, or a process gone mid-look
        return False


def stale_chapters():
    """(book, chapter) of every Hakka chapter with no recording, or with text
    newer than its recording - New Testament first, as the text is made."""
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


def read_all(pace):
    """Every Hakka chapter not yet recorded, one after another, with the voice
    loaded once; run again, it picks up what has been translated since. It
    is the dashboard's 'hakka-voice' job, so it can be stopped at any point:
    a chapter is written only when it is whole."""
    voice = None
    while True:
        todo = stale_chapters()
        if not todo:
            # Caught up with the translation while it is still going: wait for
            # its next chapter rather than stop, so one start covers the run.
            if translating():
                time.sleep(60)
                continue
            print("every Hakka chapter is recorded")
            return
        voice = voice or Voice()
        for code, ch in todo:
            passage = verses_of(code, ch, range(1, 200))
            if not passage:
                continue
            audio, unread = read(voice, passage, SPEAKER, pace, False)
            out = AUDIO / f"{BOOKS[code]['name'].replace(' ', '_')}_{ch:02d}.wav"
            write_wav(audio, voice.fs, out)
            print(f"{BOOKS[code]['name']} {ch}: {len(passage)} verses, {len(audio) / voice.fs:.0f}s"
                  + (f", skipped {' '.join(w for _, w in unread)}" if unread else ""), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS code, e.g. John")
    ap.add_argument("--all", action="store_true", help="record every Hakka chapter not yet recorded (or changed since)")
    ap.add_argument("chapter", nargs="?", type=int)
    ap.add_argument("verses", nargs="?", help="e.g. 1-5 (default: the whole chapter)")
    ap.add_argument("--text", help="Hakka text to read instead of a passage")
    ap.add_argument("--out", help="where to write the .wav")
    ap.add_argument("--speaker", default=SPEAKER, help=f"one of the voice's twenty readers (default {SPEAKER}); 'all' writes one file each")
    ap.add_argument("--pace", type=float, default=1.0, help="1.0 is the voice's own speed, 1.15 a little slower")
    ap.add_argument("--show", action="store_true", help="print each word with formog2p's reading")
    a = ap.parse_args()

    if a.all:
        read_all(a.pace)
        return
    if a.text:
        passage = [(None, a.text)]
        stem = "text"
    else:
        if not (a.book and a.chapter):
            ap.error("give a book and chapter, or --text")
        if a.book not in BOOKS:
            ap.error(f"no book {a.book!r}; use the OSIS code, e.g. Gen, John, 1Cor")
        lo, _, hi = (a.verses or "1-200").partition("-")
        passage = verses_of(a.book, a.chapter, range(int(lo), int(hi or lo) + 1))
        if not passage:
            raise SystemExit("no such verses in the Hakka chapter")
        stem = f"{BOOKS[a.book]['name'].replace(' ', '_')}_{a.chapter:02d}{'_' + a.verses if a.verses else ''}"

    voice = Voice()
    speakers = voice.speakers if a.speaker == "all" else [a.speaker]
    for sp in speakers:
        if sp not in voice.speakers:
            raise SystemExit(f"no reader {sp!r}; the voice has: {', '.join(voice.speakers)}")
    for sp in speakers:
        audio, unread = read(voice, passage, sp, a.pace, a.show and sp == speakers[0])
        if a.out and len(speakers) == 1:
            out = Path(a.out)
        else:
            out = AUDIO / f"{stem}{'' if sp == SPEAKER and len(speakers) == 1 else '_' + sp}.wav"
        write_wav(audio, voice.fs, out)
        print(f"{sp}: {len(passage)} verse(s), {len(audio) / voice.fs:.0f}s of audio -> {out}")
    if unread:
        print("not read (the voice skipped these):", file=sys.stderr)
        for n, w in unread:
            print(f"  {'v' + str(n) + ' ' if n else ''}{w}", file=sys.stderr)


if __name__ == "__main__":
    main()
