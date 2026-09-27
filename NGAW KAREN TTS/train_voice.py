#!/usr/bin/env python3
"""Teach a Piper voice Karen from the word cuts: the accent training.

    python "NGAW KAREN TTS/train_voice.py" --prepare          # build the dataset from audio/cuts
    python "NGAW KAREN TTS/train_voice.py" --train --epochs 300
    python "NGAW KAREN TTS/train_voice.py" --export            # the last checkpoint -> models/piper/karen.onnx

The Piper Vietnamese voice knows how to be a voice; what it does not know is
Karen. Every cut under audio/cuts is a Karen speaker saying a word whose
spelling we know, and karen_phonemes turns that spelling into the phoneme
symbols the voice was trained on (IPA plus espeak's Vietnamese tone marks),
so each cut is a lesson: these sounds, said like this. Fine-tuning the voice
on them from its Vietnamese checkpoint moves it towards the speaker, which is
the accent coming off. Whole words are the unit, as the lessons give them;
a multi-syllable word is one block.

Piper's trainer takes a dataset of `id|text|phoneme ids` rows beside the wavs
(dataset_type phoneme_ids), so the ids are computed here with the voice's own
map and nothing depends on espeak at training time. The voice's config is
copied so the result keeps its phoneme map and sample rate (22050 Hz; the
cuts are resampled to it).

Needs the training extras (pip install "piper-tts[train]") with the training
package present - on this machine it was dropped in from the piper1-gpl
source with the alignment step in numba - and models/piper/vi_VN-vais1000-
medium.ckpt from rhasspy/piper-checkpoints.
"""
import argparse
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import karen_phonemes as kp                                        # noqa: E402
from karen_voice_test import read_wav                               # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CUTS = HERE / "audio" / "cuts"
DATA = HERE / "audio" / "train"
MODELS = ROOT / "models" / "piper"
BASE_ONNX = MODELS / "vi_VN-vais1000-medium.onnx"
# The checkpoint as published pickles Linux path objects that PyTorch on
# Windows will not unpickle; the .clean copy is the same weights re-saved as
# plain tensors, with the optimiser state and loop counters dropped so the
# fine-tune starts its own schedule.
BASE_CKPT = MODELS / "vi_VN-vais1000-medium.clean.ckpt"
RUNS = MODELS / "karen-runs"
SAMPLE_RATE = 22050

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def resample(x, fs, to):
    if fs == to:
        return x
    idx = np.linspace(0, len(x) - 1, int(round(len(x) * to / fs)))
    return np.interp(idx, np.arange(len(x)), x)


SPEAKERS = {"vocab": 0, "emma": 1}      # the lessons' man and Emma Htoo, when trained as two voices of one model


def prepare(include_unconfirmed, speaker="", min_len=0.5, max_len=3.0, two_speakers=False):
    """`speaker` keeps only lessons whose key starts with it ("vocab" or "emma"):
    a single-speaker voice trained on two speakers at once averages them into
    neither, and the vocabulary speaker and Emma Htoo are a man and a woman.
    `min_len` is half a second because the vocoder trains on 8192-sample
    segments (0.37 s at 22050 Hz) and a cut shorter than that crashed the
    feature loss at epoch 80 with mismatched tensor sizes."""
    from piper import PiperVoice
    voice = PiperVoice.load(str(BASE_ONNX))
    rows = [json.loads(l) for l in (CUTS / "index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if not include_unconfirmed:
        rows = [r for r in rows if r.get("confirmed")]
    # Emma Htoo's letter sounds (consonant + a) and her nine vowels on အ: single
    # syllables with a spelling that is certain, the cleanest lessons of all.
    for name, key in (("emma01_letters.json", "letter"), ("emma03_vowels.json", "spelled")):
        f = HERE / "words" / name
        if f.exists():
            for n, r in enumerate(json.loads(f.read_text(encoding="utf-8")), 1):
                rows.append({"lesson": r["lesson"], "n": n, "ksw": r[key], "wav": str(Path(r["wav"]).relative_to("NGAW KAREN TTS"))
                             if r["wav"].startswith("NGAW KAREN TTS") else r["wav"], "confirmed": True})
    if speaker:
        rows = [r for r in rows if r["lesson"].startswith(speaker)]
    if two_speakers:                       # both voices, each row saying whose it is
        rows = [r for r in rows if r["lesson"].split("/")[0] in SPEAKERS]
    DATA.mkdir(parents=True, exist_ok=True)
    wav_dir = DATA / "wav"
    wav_dir.mkdir(exist_ok=True)
    lines, kept, seconds = [], 0, 0.0
    for r in rows:
        x, fs = read_wav(HERE / r["wav"])
        if not (min_len <= len(x) / fs <= max_len):
            continue
        x = resample(x, fs, SAMPLE_RATE)
        utt = f"{r['lesson'].replace('/', '_')}_{r['n']:02d}"
        with wave.open(str(wav_dir / f"{utt}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        phonemes = [p for p in kp.piper(kp.syllables(r["ksw"])) if p and p != " "]
        ids = voice.phonemes_to_ids(phonemes)
        who = f"{SPEAKERS[r['lesson'].split('/')[0]]}|" if two_speakers else ""
        lines.append(f"wav/{utt}.wav|{who}{''.join(phonemes)}|{' '.join(map(str, ids))}")
        kept += 1
        seconds += len(x) / SAMPLE_RATE
    (DATA / "metadata.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cfg = json.loads((BASE_ONNX.with_suffix(".onnx.json")).read_text(encoding="utf-8"))
    (DATA / "phonemes.json").write_text(json.dumps(cfg["phoneme_id_map"], ensure_ascii=False), encoding="utf-8")
    (DATA / "speakers.json").write_text(json.dumps({"two_speakers": two_speakers, "map": SPEAKERS}), encoding="utf-8")
    shutil.copy(BASE_ONNX.with_suffix(".onnx.json"), DATA / "base_config.json")
    print(f"{kept} utterances, {seconds / 60:.1f} min of Karen -> {DATA / 'metadata.csv'}")


def train(epochs, batch, start=None):
    """`start`: a checkpoint to warm-start from instead of the Vietnamese one -
    an earlier Karen run, to continue it with a changed dataset."""
    RUNS.mkdir(parents=True, exist_ok=True)
    two = json.loads((DATA / "speakers.json").read_text(encoding="utf-8")).get("two_speakers") if (DATA / "speakers.json").exists() else False
    cmd = [sys.executable, "-m", "piper.train", "fit",
           "--data.csv_path", str(DATA / "metadata.csv"),
           "--data.audio_dir", str(DATA),
           "--data.cache_dir", str(DATA / "cache"),
           "--data.config_path", str(DATA / "base_config.json"),
           "--data.voice_name", "karen",
           "--data.espeak_voice", "vi",
           "--data.dataset_type", "phoneme_ids",
           "--data.phonemes_path", str(DATA / "phonemes.json"),
           "--data.batch_size", str(batch),
           "--data.validation_split", "0.05",
           "--data.num_workers", "4",          # at 0 the GPU idled at a quarter: the loader was the bottleneck
           "--model.sample_rate", str(SAMPLE_RATE),
           *(["--model.num_speakers", "2"] if two else []),
           "--trainer.accelerator", "gpu", "--trainer.devices", "1",
           "--trainer.max_epochs", str(epochs),
           "--trainer.check_val_every_n_epoch", "10",
           "--trainer.log_every_n_steps", "5",
           "--trainer.default_root_dir", str(RUNS),
           # weights only, a fresh optimiser: fine-tuning, not resuming
           "--model.warmstart_ckpt", str(start or BASE_CKPT)]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def export():
    ckpts = sorted(RUNS.rglob("*.ckpt"), key=lambda p: p.stat().st_mtime)
    if not ckpts:
        raise SystemExit("no checkpoint under " + str(RUNS))
    last = ckpts[-1]
    out = MODELS / "karen.onnx"
    cmd = [sys.executable, "-m", "piper.train.export_onnx", "--checkpoint", str(last), "--output-file", str(out)]
    print(" ".join(cmd))
    code = subprocess.call(cmd, cwd=str(ROOT))
    if code == 0:
        shutil.copy(DATA / "base_config.json", out.with_suffix(".onnx.json"))
        print("voice ->", out)
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--unconfirmed", action="store_true", help="train on unconfirmed spellings too")
    ap.add_argument("--speaker", default="", help="only lessons whose key starts with this: vocab, or emma")
    ap.add_argument("--from", dest="start", default=None, help="warm-start from this checkpoint instead of the Vietnamese one")
    ap.add_argument("--two-speakers", action="store_true", help="train the lessons' man and Emma Htoo as two voices of one model")
    a = ap.parse_args()
    if a.prepare:
        prepare(a.unconfirmed, a.speaker, two_speakers=a.two_speakers)
    if a.train:
        sys.exit(train(a.epochs, a.batch, a.start))
    if a.export:
        sys.exit(export())


if __name__ == "__main__":
    main()
