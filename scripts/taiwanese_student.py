#!/usr/bin/env python3
"""A Taiwanese voice small enough for a phone, taught by the big one.

    python scripts/taiwanese_student.py cut      # the recordings cut into the pieces the teacher read -> data/
    python scripts/taiwanese_student.py train --resume newest [--minutes 360] [--duty 0.5]   (the dashboard's job)
    python scripts/taiwanese_student.py say John 1 1-5     # the student reads -> samples/
    python scripts/taiwanese_student.py sample   # the dashboard's sample verses from the newest checkpoint
    python scripts/taiwanese_student.py check [--only John_01]   # every verse against its recording, worst first
    python scripts/taiwanese_student.py export   # ONNX, as a phone would run it, and its speed on this CPU

The teacher (scripts/taiwanese_speech.py) is SuíSiann's Tacotron2 and WaveRNN,
then DeepFilterNet and a Praat pitch change: about 1.3 times real time on the
5090, far too heavy for a phone. Its finished chapters are the student's
lessons: the student learns the cleaned, raised voice directly, so a phone
would need neither the cleaner nor Praat.

The student is VITS (Kim et al. 2021, Coqui's implementation) cut to the size
of Piper's "medium" voices, the ones Piper and sherpa-onnx run on a Raspberry
Pi and on Android: a text encoder, explicit durations from a duration
predictor (the stochastic one is left out - a Bible verse should be read the
same way twice), a flow and a small HiFi-GAN, about 15 M weights at reading
time. It is not autoregressive, so it cannot run on past its end or stall the
way Tacotron2 can, and needs no 1,000-frame limit.

What it reads is the teacher's own input: the spoken form, sandhi applied,
that scripts/taiwanese_phonemes.py works out per chapter ahead of time. Each
syllable goes in as three tokens - its initial, its final and its tone - so
'sioŋ3-te2' is I:s F:ioŋ T:3 - F:e T:2 (the hyphen kept: sandhi groups read
together).

Everything here lives under models/taiwanese-student/ (gitignored, like the
other models): phonemes/ from taiwanese_phonemes.py, data/ from cut, run/
from train, samples/ from say, onnx/ from export. --root points at the
checkout whose recordings to learn from.
"""
import argparse
import json
import os
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS   # noqa: E402

SR = 22050
GAP = {"clause": 0.25, "sentence": 0.45, "verse": 0.7}   # as the teacher leaves them (taiwanese_speech.GAP)
QUIET = -60.0          # dB below the chapter's loudest 10 ms: the teacher's pauses, after cleaning, sit below this
VERSE_GAP = 0.9        # seconds: a verse gap is 0.7 s plus the 0.25-0.45 s after the verse's last piece
PIECE_GAP = 0.2        # seconds: the shortest pause the teacher leaves between pieces is 0.25 s
PAD = 0.05             # seconds of the pause kept either side of a cut piece
LONGEST = 15.0         # seconds: a verse that cannot be cut into its pieces is kept whole up to this long
TRIAL_MINUTES = 360    # a night at full speed: about 70,000 steps, where VITS on one clean voice reads well
RATE = (2.3, 5.5)     # syllables a second a lesson must fall within (see cut)
HELD_OUT = {("John", 1)}   # a trial never trains on John 1, the usual ear test (cut --all keeps it in)
# What the dashboard plays as the run goes, as VoiceLab does: a verse it never trains on and one it does, read by
# the voice as it stands every SAMPLE_EVERY minutes of training, beside the teacher's own reading of them.
SAMPLE_VERSES = [("John", 1, 1), ("John", 3, 16)]
SAMPLE_EVERY = 15
INITIALS = ["tsʰ", "kʰ", "pʰ", "tʰ", "ts", "dz", "p", "b", "m", "t", "n", "l", "k", "g", "ŋ", "h", "s", "ʔ"]
SYLLABLE = re.compile(r"^(" + "|".join(INITIALS) + r")?(.*?)(\d+)$")
MARKS = {",": ",", ".": ".", "?": "?", "-": "-", " ": " "}


def home(root):
    return Path(root) / "models" / "taiwanese-student"


# ------------------------------------------------------------------ tokens
def tokens(phon):
    """A spoken form ('kʰi1 tsʰo7 ʔu3 tə7 , tə3 ka2 sioŋ3-te2') -> tokens: per syllable its initial, final and tone,
    with the word gaps, hyphens and punctuation between."""
    out = []
    for part in re.split(r"(\s+|-|[,.?])", phon.strip()):
        if not part:
            continue
        if part.isspace():
            if out and out[-1] != " ":
                out.append(" ")
            continue
        if part in MARKS:
            if out and out[-1] == " ":
                out.pop()
            out.append(part)
            continue
        m = SYLLABLE.match(part)
        if not m:
            raise ValueError(f"not a syllable: {part!r} in {phon!r}")
        out += ["I:" + (m.group(1) or "∅"), "F:" + (m.group(2) or "∅"), "T:" + m.group(3)]
    return out


class Vocab:
    """Tokens <-> the single characters Coqui's tokenizer wants: each token gets one from the Private Use Area,
    the marks stay themselves."""

    def __init__(self, toks):
        self.toks = sorted(t for t in toks if t not in MARKS)
        self.char = {t: chr(0xE000 + i) for i, t in enumerate(self.toks)}
        self.char.update(MARKS)

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))["tokens"])

    def save(self, path):
        Path(path).write_text(json.dumps({"tokens": self.toks}, ensure_ascii=False, indent=0), encoding="utf-8")

    def text(self, phon):
        return "".join(self.char[t] for t in tokens(phon))

    def letters(self):
        return "".join(self.char[t] for t in self.toks)


def chapter_name(book, ch):
    return f"{BOOKS[book]['name'].replace(' ', '_')}_{ch:02d}"


# ------------------------------------------------------------------ cutting the recordings
def read_wav(path):
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getsampwidth() == 2 and w.getnchannels() == 1, path
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


def write_wav(path, audio):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def pauses(audio, shortest):
    """(start, end) in samples of every stretch quieter than QUIET for at least `shortest` seconds."""
    hop = SR // 100
    n = len(audio) // hop
    rms = np.sqrt((audio[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12)
    quiet = np.r_[0, (20 * np.log10(rms / rms.max()) < QUIET).astype(np.int8), 0]
    e = np.flatnonzero(np.diff(quiet))
    return [(s * hop, t * hop) for s, t in zip(e[::2], e[1::2]) if (t - s) / 100 >= shortest]


def sounds(audio, lo, hi, shortest):
    """The stretches of sound between lo and hi, split at pauses of at least `shortest` seconds."""
    out, at = [], lo
    for s, e in pauses(audio[lo:hi], shortest):
        s, e = s + lo, e + lo
        if s > at:
            out.append((at, s))
        at = e
    if hi > at:
        out.append((at, hi))
    # a few ms of sound at the very edges (a click from the cleaner) is not a piece
    return [(s, e) for s, e in out if e - s > SR * 0.08]


def cut(root, hold_out=True):
    """Every recorded chapter whose recording is newer than its text, cut into the pieces the teacher read (or, where
    a verse's pauses do not match its pieces, whole verses), each with its spoken form. A trial holds John 1 back to
    hear how the student reads what it has not heard; the voice that ships learns every verse, since the Bible is
    the only text it will ever read (hold_out=False)."""
    import importlib
    sys.path.insert(0, str(Path(root) / "scripts"))
    build_audio = importlib.import_module("build_audio")
    place = build_audio.place
    h = home(root)
    audio_dir, text_dir, phon_dir = Path(root) / "audio" / "nan", Path(root) / "output" / "nan" / "json", h / "phonemes"
    data = h / "data"
    (data / "wavs").mkdir(parents=True, exist_ok=True)
    every = set()
    for f in phon_dir.glob("*.json"):
        for _, ps in json.loads(f.read_text(encoding="utf-8"))["verses"]:
            for p, _ in ps:
                every.update(tokens(p))
    vocab = Vocab(every)
    vocab.save(data / "vocab.json")
    rows, held, report = [], [], {"pieces": 0, "verses": 0, "skipped": []}
    seconds = 0.0
    nt = [c for c in BOOKS if BOOKS[c]["testament"] == "NT"]
    for code in nt:
        for wav in sorted(audio_dir.glob(chapter_name(code, 1)[:-2] + "[0-9][0-9].wav")):
            ch = int(wav.stem.rsplit("_", 1)[1])
            name = wav.stem
            text, phon = text_dir / f"{name}.json", phon_dir / f"{name}.json"
            if not phon.exists() or wav.stat().st_mtime < text.stat().st_mtime:
                report["skipped"].append(f"{name}: text newer than its recording")
                continue
            verses = [(n, ps) for n, ps in json.loads(phon.read_text(encoding="utf-8"))["verses"] if ps]
            audio = read_wav(wav)
            spans = sounds(audio, 0, len(audio), VERSE_GAP)
            if len(spans) != len(verses):
                report["skipped"].append(f"{name}: {len(spans)} stretches of sound for {len(verses)} verses")
                continue
            # A second opinion on where each verse is: the timings the teacher now writes beside a chapter, or for
            # older chapters build_audio.place, which divides the chapter by its text. A chapter whose long pauses
            # number its verses can still be wrong if a long pause inside one verse and a short pause after another
            # cancel out; the verse that disagrees with the second opinion, and the verses either side, are left out.
            side = wav.with_suffix(".json")
            if side.exists():
                ref = json.loads(side.read_text(encoding="utf-8"))["verses"]
            else:
                ref = place([(n, t) for n, t in build_audio.verses_of(text)], audio, SR) or []
            ref = {int(n): (s, e) for n, s, e in ref}
            # (place hears quiet at 40 dB down where this cuts at 60, so a soft verse end can differ by a few tenths
            # of a second; a verse put in the wrong place is a clause out, seconds)
            off = {n for n, (s, e) in zip([n for n, _ in verses], spans)
                   if n not in ref or abs(s / SR - ref[n][0]) > 1.5 or abs(e / SR - ref[n][1]) > 1.5}
            doubt = off | {n + 1 for n in off} | {n - 1 for n in off}
            report["doubtful"] = report.get("doubtful", 0) + len(off)
            out = held if hold_out and (code, ch) in HELD_OUT else rows
            for (n, ps), (vs, ve) in zip(verses, spans):
                if n in doubt:
                    continue
                parts = sounds(audio, vs, ve, PIECE_GAP)
                if len(parts) == len(ps):
                    chunks = [((s, e), p) for (s, e), (p, _) in zip(parts, ps)]
                    report["pieces"] += len(ps)
                elif (ve - vs) / SR <= LONGEST:
                    chunks = [((vs, ve), " ".join(p for p, _ in ps))]
                    report["verses"] += 1
                else:
                    continue
                for i, ((s, e), p) in enumerate(chunks):
                    # The teacher reads about 3.3 syllables a second, and nearly always between 2.5 and 4.8; a
                    # piece far outside that is a cut in the wrong place, or Tacotron2 stalling, not a lesson.
                    rate = len(re.findall(r"\d+", p)) / ((e - s) / SR)
                    if not RATE[0] <= rate <= RATE[1]:
                        report["odd"] = report.get("odd", 0) + 1
                        continue
                    pad = int(PAD * SR)
                    clip = audio[max(0, s - pad):e + pad]
                    key = f"{name}_{n:03d}_{i}"
                    write_wav(data / "wavs" / f"{key}.wav", clip)
                    out.append((key, p))
                    seconds += len(clip) / SR
    for path, items in (("metadata.csv", rows), ("held_out.csv", held)):
        with open(data / path, "w", encoding="utf-8") as f:
            for key, p in items:
                f.write(f"{key}|{p}\n")
    json.dump(report, open(data / "report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(rows)} lessons ({report['pieces']} pieces, {report['verses']} whole verses), "
          f"{len(held)} held out, {seconds / 3600:.1f} h in all, {report.get('odd', 0)} left out for their pace, "
          f"{report.get('doubtful', 0)} verses (and their neighbours) for disagreeing with the verse timings; "
          f"{len(vocab.toks)} tokens; "
          f"{len(report['skipped'])} chapters skipped -> {data}")
    for s in report["skipped"][:20]:
        print("  skipped", s)


# ------------------------------------------------------------------ the student
def plain_wav_reading():
    """Coqui reads audio through torchaudio, which since torch 2.9 goes through torchcodec and FFmpeg, and that
    will not load on this PC. The lessons are plain 16-bit WAVs, which need neither. Done at import, so the data
    loader's worker processes (started afresh on Windows) do it too."""
    try:
        import torch
        import TTS.tts.datasets.dataset as dataset
        import TTS.tts.models.vits as vits
    except ImportError:
        return

    def size(path):
        with wave.open(str(path), "rb") as w:
            return w.getnframes()

    def load(path):
        return torch.from_numpy(read_wav(path))[None], SR
    dataset.get_audio_size = size
    vits.load_audio = load


if sys.argv[1:2] == ["train"]:
    plain_wav_reading()


def config(root, run_name="run"):
    from TTS.config.shared_configs import BaseAudioConfig, BaseDatasetConfig
    from TTS.tts.configs.shared_configs import CharactersConfig
    from TTS.tts.configs.vits_config import VitsConfig
    from TTS.tts.models.vits import VitsArgs
    h = home(root)
    vocab = Vocab.load(h / "data" / "vocab.json")
    john = json.loads((h / "phonemes" / "John_01.json").read_text(encoding="utf-8"))["verses"]
    return VitsConfig(
        run_name=run_name,
        output_path=str(h),
        # Piper's "medium" size: the same text encoder, flow and posterior encoder as VITS, the small HiFi-GAN
        model_args=VitsArgs(use_sdp=False, resblock_type_decoder="2", resblock_kernel_sizes_decoder=[3, 5, 7],
                            resblock_dilation_sizes_decoder=[[1, 2], [2, 6], [3, 12]],
                            upsample_rates_decoder=[8, 8, 4], upsample_initial_channel_decoder=256,
                            upsample_kernel_sizes_decoder=[16, 16, 8]),
        audio=BaseAudioConfig(sample_rate=SR, win_length=1024, hop_length=256, fft_size=1024, num_mels=80,
                              mel_fmin=0, mel_fmax=None),
        characters=CharactersConfig(characters_class="TTS.tts.utils.text.characters.Graphemes", pad="<PAD>",
                                    eos="<EOS>", bos="<BOS>", blank="<BLNK>", characters=vocab.letters(),
                                    punctuations="".join(MARKS), is_unique=True, is_sorted=True),
        use_phonemes=False, text_cleaner=None, add_blank=True, enable_eos_bos_chars=False,
        datasets=[BaseDatasetConfig(formatter="ljspeech", meta_file_train="metadata.csv", path=str(h / "data"))],
        batch_size=32, eval_batch_size=8, num_loader_workers=4, num_eval_loader_workers=2,
        min_audio_len=int(0.5 * SR), max_audio_len=int(LONGEST * SR) + SR, max_text_len=600,
        # a checkpoint every 1,000 steps, about five minutes at full speed: what a kill can cost
        mixed_precision=True, epochs=100000, print_step=100, plot_step=500, save_step=1000, save_n_checkpoints=3,
        save_best_after=2000, run_eval=True, test_delay_epochs=-1, print_eval=False,
        test_sentences=[[vocab.text(ps[0][0])] for _, ps in john[:2]],
    )


def formatter(vocab):
    """Coqui's dataset rows from metadata.csv, the spoken forms turned into the vocabulary's characters."""
    def read(root_path, meta_file, **_):
        rows = []
        for line in open(os.path.join(root_path, meta_file), encoding="utf-8"):
            key, phon = line.rstrip("\n").split("|", 1)
            rows.append({"text": vocab.text(phon), "audio_file": os.path.join(root_path, "wavs", key + ".wav"),
                         "speaker_name": "suisiann", "root_path": root_path, "audio_unique_name": key})
        return rows
    return read


class Progress:
    """progress.json in the run folder, for the dashboard, in VoiceLab's shape: state, heartbeat, minutes trained
    over every run, the target, the training mel loss (points) and the checking set's (scores), lower better.

    The dashboard stops a run by killing it, so the minutes that count are those the newest checkpoint holds:
    each time a new checkpoint appears its minutes are noted, and a run that starts again starts from them, with
    the points after them dropped."""
    EVERY = 120        # seconds between writes
    KEEP = 300         # points kept; beyond that every other one is dropped

    def __init__(self, run, target):
        self.path = Path(run) / "progress.json"
        try:
            old = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        base = old.get("checkpoint_minutes", 0.0)
        self.p = {"state": "training", "heartbeat": time.time(), "minutes": base, "target_minutes": target,
                  "points": [x for x in old.get("points", []) if x[0] <= base],
                  "scores": [x for x in old.get("scores", []) if x[0] <= base],
                  "best": None, "checkpoint_minutes": base, "checkpoint": old.get("checkpoint"),
                  "sampled": min(old.get("sampled", base), base)}
        scores = [s for _, s in self.p["scores"]]
        self.p["best"] = min(scores) if scores else None
        self.base, self.t0, self.last = base, time.time(), 0.0

    def minutes(self):
        return self.base + (time.time() - self.t0) / 60

    def note_checkpoint(self):
        ck = newest_checkpoint(self.path.parent)
        if ck and ck.name != self.p.get("checkpoint") and ck.stat().st_mtime >= self.t0:
            at = self.base + (ck.stat().st_mtime - self.t0) / 60      # its minutes when it was written
            self.p["checkpoint"], self.p["checkpoint_minutes"] = ck.name, round(at, 2)

    def point(self, key, value):
        rows = self.p[key]
        rows.append([round(self.minutes(), 2), round(float(value), 4)])
        if len(rows) > self.KEEP:
            rows[:] = rows[:1] + rows[1:-1:2] + rows[-1:]
        if key == "scores":
            self.p["best"] = min(s for _, s in rows)

    def write(self, state="training", force=False):
        if not force and time.time() - self.last < self.EVERY:
            return
        self.note_checkpoint()
        self.p.update(state=state, heartbeat=time.time(), minutes=round(self.minutes(), 2))
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.p), encoding="utf-8")
        for _ in range(20):            # Windows refuses the swap while the dashboard has the file open
            try:
                os.replace(tmp, self.path)
                break
            except PermissionError:
                time.sleep(0.1)
        self.last = time.time()


def newest_checkpoint(run):
    return max(Path(run).glob("checkpoint_*.pth"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]), default=None)


def sound_checkpoint(run):
    """The run's newest checkpoint, if it loads. One cut short by a kill while it was being written is set aside
    (renamed .broken) and the one before it tried, so a run killed at any moment can carry on."""
    import torch
    while (ck := newest_checkpoint(run)) is not None:
        try:
            torch.load(ck, map_location="cpu", weights_only=False)
            return ck
        except Exception as e:                     # noqa: BLE001
            print(f"{ck.name} does not load ({type(e).__name__}); set aside")
            ck.rename(ck.with_suffix(".pth.broken"))
    return None


def student_class(duty, progress, stop_file, sample=None, ask_file=None, finish=None):
    """Coqui's VITS with what the dashboard needs. It rests between steps when it shares the GPU (`duty` is the
    share of the time it computes, 1 = never rests: the recording job runs Tacotron2 and WaveRNN a step at a time,
    and a run at full tilt would hold the GPU in front of it); it writes progress.json; it reads the sample verses
    (sample(model)) every SAMPLE_EVERY minutes, when ask_file appears (the dashboard's Make sample) and as it
    leaves; and it stops, saving a checkpoint first, once the run's minutes reach the target or stop_file appears.
    A run that reaches its target also calls finish() (the export to ONNX the phone preview reads) before it goes.

    Coqui's trainer answers Ctrl+C by exiting with 130 whatever happens, so a run that has done what it was asked
    leaves by os._exit(0) instead, once its checkpoint and progress are written: the dashboard restarts a job that
    exits with anything else."""
    from TTS.tts.models.vits import Vits

    class Student(Vits):
        def read_sample(self):
            # a sample that fails is reported and training goes on: it is something to listen to, not the run
            if ask_file:
                ask_file.unlink(missing_ok=True)
            try:
                sample(self)
            except Exception as e:                 # noqa: BLE001
                print(f"no sample: {type(e).__name__}: {e}", flush=True)

        def on_train_step_start(self, trainer):
            done = progress.minutes() >= progress.p["target_minutes"]
            if done or stop_file.exists():
                stop_file.unlink(missing_ok=True)
                trainer.save_checkpoint()
                if sample and progress.minutes() - progress.p["sampled"] >= 1:
                    self.read_sample()             # how it sounds where it stopped
                if done and finish:
                    try:
                        finish()
                    except Exception as e:         # noqa: BLE001
                        print(f"not exported: {type(e).__name__}: {e}", flush=True)
                progress.write("finished" if done else "stopped", force=True)
                print(f"{'finished' if done else 'stopped'} at {progress.minutes():.0f} min", flush=True)
                # the data loader's workers would outlive an os._exit, waiting for a parent that is gone
                import multiprocessing
                for child in multiprocessing.active_children():
                    child.kill()
                os._exit(0)
            if sample and (progress.minutes() - progress.p["sampled"] >= SAMPLE_EVERY
                           or (ask_file and ask_file.exists())):
                self.read_sample()
            now = time.time()
            last = getattr(self, "_rest_mark", None)
            if last is not None and duty < 1:
                time.sleep(min(2.0, (now - last) * (1 - duty) / duty))
            self._rest_mark = time.time()
            parent = getattr(super(), "on_train_step_start", None)
            if parent:
                parent(trainer)

        def on_train_step_end(self, trainer):
            # the epoch's running mean of the mel loss, which the trainer has just brought up to date
            avg = trainer.keep_avg_train.avg_values if trainer.keep_avg_train else {}
            if "avg_loss_mel" in avg and time.time() - progress.last >= progress.EVERY:
                progress.point("points", avg["avg_loss_mel"])
            progress.write()
            parent = getattr(super(), "on_train_step_end", None)
            if parent:
                parent(trainer)

        def on_epoch_end(self, trainer):
            avg = trainer.keep_avg_eval.avg_values if trainer.keep_avg_eval else {}
            if "avg_loss_mel" in avg:
                progress.point("scores", avg["avg_loss_mel"])
                progress.write(force=True)
            parent = getattr(super(), "on_epoch_end", None)
            if parent:
                parent(trainer)
    return Student


def train(root, minutes, duty, resume=None):
    """Train until the run has `minutes` in all. resume: a run folder to carry on, or "newest" for the newest run
    folder with a checkpoint that loads (a first run if there is none) - the command the dashboard runs again
    after a crash or a kill. A run already at its target exits at once."""
    import torch
    from trainer import Trainer, TrainerArgs
    from TTS.tts.datasets import load_tts_samples
    from TTS.utils.audio import AudioProcessor
    from TTS.tts.utils.text.tokenizer import TTSTokenizer
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    h = home(root)
    if resume == "newest":
        runs = sorted(h.glob("run-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        resume = next((r for r in runs if sound_checkpoint(r)), None)
    elif resume:
        resume = Path(resume) if sound_checkpoint(resume) else None
    if resume:
        progress = Progress(resume, minutes)
        if progress.minutes() >= minutes:
            progress.write("finished", force=True)
            print(f"{resume.name} has trained {progress.minutes():.0f} of {minutes:g} min: nothing to do")
            return
    cfg = config(root)
    # on the CPU, mixed precision means bfloat16, which Coqui's plots cannot draw (a test run only)
    cfg.mixed_precision = torch.cuda.is_available()
    vocab = Vocab.load(h / "data" / "vocab.json")
    rows, _ = load_tts_samples(cfg.datasets, eval_split=False, formatter=formatter(vocab))
    # the same lessons to check against every time the run is started again (Coqui's split is drawn afresh)
    train_rows, eval_rows = [r for i, r in enumerate(rows) if i % 200], rows[::200]
    ap = AudioProcessor.init_from_config(cfg)
    tok, cfg = TTSTokenizer.init_from_config(cfg)
    stop = h / "STOP"
    if not resume:
        progress = Progress(h / "pending", minutes)       # given its folder once the trainer has made it

    def sample(m):
        made = progress_sample(m, vocab, root, progress.path.parent, progress.minutes(), progress.p["scores"])
        progress.p["sampled"] = progress.minutes()
        progress.write(force=True)
        print(f"sample -> {made}", flush=True)
    model = student_class(duty, progress, stop, sample, h / "SAMPLE",
                          lambda: export(root, Path(trainer.output_path)))(cfg, ap, tok, speaker_manager=None)
    weights = sum(p.numel() for n, p in model.named_parameters() if not n.startswith(("posterior_encoder", "disc")))
    print(f"student: {weights / 1e6:.2f} M weights at reading time ({weights * 2 / 1e6:.0f} MB as half floats); "
          f"{len(train_rows)} lessons, {len(eval_rows)} to check against")
    trainer = Trainer(TrainerArgs(continue_path=str(resume) if resume else ""), cfg, str(h), model=model,
                      train_samples=train_rows, eval_samples=eval_rows)
    # a checkpoint saved before the first check (a run stopped in its first epoch) holds no best loss, and Coqui,
    # resuming from it, would compare the next one with None (it reads the best loss as fit begins)
    restore = trainer._restore_best_loss

    def restore_best_loss():
        restore()
        if isinstance(trainer.best_loss, dict):
            trainer.best_loss = {k: float("inf") if v is None else v for k, v in trainer.best_loss.items()}
    trainer._restore_best_loss = restore_best_loss
    progress.path = Path(trainer.output_path) / "progress.json"
    progress.t0 = time.time()                         # the minutes count training, not loading
    progress.write(force=True)
    print(f"{Path(trainer.output_path).name}: from {progress.base:.0f} to {minutes:g} min; stops early when {stop} "
          f"appears", flush=True)
    trainer.fit()


# ------------------------------------------------------------------ reading
def load_student(run):
    """The newest checkpoint of a run folder -> (model on the GPU if there is one, vocab)."""
    import torch
    from TTS.tts.configs.vits_config import VitsConfig
    from TTS.tts.models.vits import Vits
    run = Path(run)
    cfg = VitsConfig()
    cfg.load_json(str(run / "config.json"))
    model = Vits.init_from_config(cfg)
    ck = max(run.glob("checkpoint_*.pth"), key=lambda p: int(re.findall(r"\d+", p.stem)[-1]), default=None)
    best = run / "best_model.pth"
    path = ck or best
    model.load_checkpoint(cfg, str(path), eval=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    return model.to(dev), Vocab.load(Path(cfg.datasets[0]["path"]) / "vocab.json"), path


def latest_run(root):
    runs = sorted((home(root)).glob("run-*"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("no trained student yet: train first")
    return runs[-1]


def read_verse(model, vocab, pieces):
    """One verse in the student's voice: its pieces, each followed by the teacher's pause, the last one's trimmed."""
    import torch
    dev = next(model.parameters()).device
    parts = []
    for p, gap in pieces:
        ids = torch.tensor([model.tokenizer.text_to_ids(vocab.text(p))], device=dev)
        with torch.no_grad():
            parts += [model.inference(ids)["model_outputs"][0, 0].float().cpu().numpy(),
                      np.zeros(int(SR * gap), np.float32)]
    return np.concatenate(parts[:-1])


def mel_db(audio):
    import librosa
    m = librosa.feature.melspectrogram(y=audio, sr=SR, n_fft=1024, hop_length=256, n_mels=80)
    return 10 * np.log10(m + 1e-6)


def distance(a, b):
    """How differently two readings of the same verse sound: the mean gap in dB between their mel spectra, frame
    against frame once dynamic time warping has lined them up (the two need not keep the same pace), over the frames
    where the recording has sound. 0 is the same reading."""
    import librosa
    ma, mb = mel_db(a), mel_db(b)
    top = max(ma.max(), mb.max())
    ma, mb = np.maximum(ma, top - 60), np.maximum(mb, top - 60)    # what is 60 dB down is silence either way
    _, path = librosa.sequence.dtw(X=ma, Y=mb, metric="euclidean", backtrack=True)
    i, j = path[:, 0], path[:, 1]
    loud = ma[:, i].max(0) > top - 40
    return float(np.abs(ma[:, i] - mb[:, j]).mean(0)[loud].mean())


def check(root, which, run=None):
    """Every verse of the chapters asked for (default: all recorded ones) read by the student and set against the
    teacher's recording of it, worst first, into check.tsv - the verses at its head are the ones to hear. As with a
    translation, a voice is finished when each verse has been found to say what its recording says."""
    model, vocab, path = load_student(run or latest_run(root))
    h = home(root)
    held = {chapter_name(b, c) for b, c in HELD_OUT}
    rows, t0 = [], time.time()
    wavs = sorted((Path(root) / "audio" / "nan").glob("*.wav"))
    for wav in wavs:
        if not re.fullmatch(r".+_\d{2,3}", wav.stem) or (which and not any(wav.stem.startswith(w) for w in which)):
            continue
        phon = h / "phonemes" / f"{wav.stem}.json"
        if not phon.exists():
            continue
        verses = [(n, ps) for n, ps in json.loads(phon.read_text(encoding="utf-8"))["verses"] if ps]
        teacher = read_wav(wav)
        spans = sounds(teacher, 0, len(teacher), VERSE_GAP)
        if len(spans) != len(verses):
            rows.append((wav.stem, "-", float("nan"), "verse pauses do not match: not checked"))
            continue
        for (n, ps), (s, e) in zip(verses, spans):
            d = distance(teacher[s:e], read_verse(model, vocab, ps))
            rows.append((wav.stem, n, d, "held out" if wav.stem in held else "trained on"))
    rows.sort(key=lambda r: -r[2] if r[2] == r[2] else 1e9)
    with open(h / "check.tsv", "w", encoding="utf-8") as f:
        f.write("chapter\tverse\tdB apart\t\n")
        for r in rows:
            f.write(f"{r[0]}\t{r[1]}\t{r[2]:.2f}\t{r[3]}\n")
    for kind in ("held out", "trained on"):
        d = np.array([r[2] for r in rows if r[3] == kind])
        if len(d):
            print(f"{kind}: {len(d)} verses, median {np.median(d):.2f} dB apart, worst tenth from "
                  f"{np.percentile(d, 90):.2f} dB, worst {d.max():.2f} dB")
    print(f"{len(rows)} verses in {time.time() - t0:.0f}s ({path.parent.name}/{path.name}) -> {h / 'check.tsv'}")


def say(root, book, chapter, verses, run=None, out=None):
    """The student reads a passage, with the teacher's pauses between pieces and verses, and the teacher's own
    reading of it is cut from the chapter recording beside it."""
    import torch
    model, vocab, path = load_student(run or latest_run(root))
    h = home(root)
    lo, _, hi = verses.partition("-")
    wanted = range(int(lo), int(hi or lo) + 1)
    name = chapter_name(book, chapter)
    chapter_phon = json.loads((h / "phonemes" / f"{name}.json").read_text(encoding="utf-8"))["verses"]
    parts, t_model = [], 0.0
    for n, ps in chapter_phon:
        if n not in wanted:
            continue
        t0 = time.time()
        parts += [read_verse(model, vocab, ps), np.zeros(int(SR * GAP["verse"]), np.float32)]
        t_model += time.time() - t0
    audio = np.concatenate(parts)
    audio = audio / max(1e-9, float(np.abs(audio).max())) * 0.9
    out = Path(out) if out else h / "samples"
    stem = f"{name}_{verses}"
    write_wav(out / f"{stem}_student.wav", audio)
    teacher = read_wav(Path(root) / "audio" / "nan" / f"{name}.wav")
    spans = sounds(teacher, 0, len(teacher), VERSE_GAP)
    first, last = wanted.start - 1, min(wanted.stop - 1, len(spans)) - 1
    write_wav(out / f"{stem}_teacher.wav", teacher[max(0, spans[first][0] - SR // 10):spans[last][1] + SR // 2])
    print(f"{stem}: {len(audio) / SR:.1f} s, {t_model:.2f} s of model time on {next(model.parameters()).device} "
          f"({path.parent.name}/{path.name}) -> {out}")


def teacher_sample(root, wavdir):
    """The teacher's reading of the sample verses, cut from its chapter recordings once per run folder, for the
    dashboard to play above the student's."""
    out = wavdir / "teacher.wav"
    if out.exists():
        return
    parts = []
    for book, ch, v in SAMPLE_VERSES:
        teacher = read_wav(Path(root) / "audio" / "nan" / f"{chapter_name(book, ch)}.wav")
        s, e = sounds(teacher, 0, len(teacher), VERSE_GAP)[v - 1]
        parts += [teacher[max(0, s - SR // 10):e + SR // 10], np.zeros(int(SR * GAP["verse"]), np.float32)]
    write_wav(out, np.concatenate(parts[:-1]))


def progress_sample(model, vocab, root, run, minutes, scores):
    """The sample verses in the voice as it is now, into the run's samples/, named by the minutes it has trained,
    with a .json beside it (minutes, the newest steady score, when it was made). model may be the one in training:
    it is put in eval mode for the reading and back after."""
    h, wavdir = home(root), Path(run) / "samples"
    wavdir.mkdir(parents=True, exist_ok=True)
    teacher_sample(root, wavdir)
    was = model.training
    model.eval()
    try:
        parts = []
        for book, ch, v in SAMPLE_VERSES:
            verses = dict(json.loads((h / "phonemes" / f"{chapter_name(book, ch)}.json")
                                     .read_text(encoding="utf-8"))["verses"])
            parts += [read_verse(model, vocab, verses[v]), np.zeros(int(SR * GAP["verse"]), np.float32)]
    finally:
        model.train(was)
    audio = np.concatenate(parts[:-1])
    name = f"{int(minutes):04d}min"
    write_wav(wavdir / f"{name}.wav", audio / max(1e-9, float(np.abs(audio).max())) * 0.9)
    (wavdir / f"{name}.json").write_text(json.dumps(
        {"minutes": round(minutes, 1), "score": scores[-1][1] if scores else None, "made": time.time(),
         "verses": [f"{b} {c}:{v}" + (" (never trained on)" if (b, c) in HELD_OUT else " (trained on)")
                    for b, c, v in SAMPLE_VERSES]}), encoding="utf-8")
    return wavdir / f"{name}.wav"


def sample_now(root, run=None):
    """The dashboard's Make sample when nothing is training: the sample verses from the run's newest checkpoint,
    at the minutes that checkpoint holds."""
    run = Path(run) if run else latest_run(root)
    model, vocab, path = load_student(run)
    try:
        p = json.loads((run / "progress.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        p = {}
    print(f"sample -> {progress_sample(model, vocab, root, run, p.get('checkpoint_minutes') or 0, p.get('scores'))} "
          f"({path.name})")


# ------------------------------------------------------------------ on a phone
def weights_in_8_bits(src, dst):
    """The ONNX file with every large weight kept as 8-bit integers and a scale per output channel, widened back to
    floats by a DequantizeLinear in front of it. ONNX Runtime folds those away when it loads the file, so the voice
    runs as fast as in float32 from a file a third the size. (Its own dynamic quantization keeps the arithmetic in 8
    bits too, which for these convolutions was seven times slower on this CPU.)"""
    import onnx
    from onnx import helper, numpy_helper
    m = onnx.load(str(src))
    g = m.graph
    used = {}
    for node in g.node:
        for name in node.input:
            used.setdefault(name, set()).add(node.op_type)
    keep, add, nodes = [], [], []
    for init in g.initializer:
        w = numpy_helper.to_array(init)
        if w.dtype != np.float32 or w.size < 4096 or not used.get(init.name, set()) & {"Conv", "ConvTranspose", "MatMul", "Gemm"}:
            keep.append(init)
            continue
        axis = 1 if used[init.name] == {"ConvTranspose"} else 0
        moved = np.moveaxis(w, axis, 0).reshape(w.shape[axis], -1)
        scale = np.maximum(np.abs(moved).max(1), 1e-12) / 127
        shape = [1] * w.ndim
        shape[axis] = -1
        q = np.clip(np.round(w / scale.reshape(shape)), -127, 127).astype(np.int8)
        add += [numpy_helper.from_array(q, init.name + "_q8"),
                numpy_helper.from_array(scale.astype(np.float32), init.name + "_scale")]
        nodes.append(helper.make_node("DequantizeLinear", [init.name + "_q8", init.name + "_scale"], [init.name],
                                      axis=axis))
    del g.initializer[:]
    g.initializer.extend(keep + add)
    for n in reversed(nodes):
        g.node.insert(0, n)
    onnx.save(m, str(dst))


def export(root, run=None):
    """The student as an ONNX file, as ONNX Runtime on Android would load it, in float32 and with its weights in
    8 bits, and how fast each reads John 1:1 on this PC's CPU with one and two threads (a phone's big core is
    roughly a third to a half of one of these)."""
    import onnxruntime as ort
    import torch
    model, vocab, path = load_student(run or latest_run(root))
    model = model.cpu().float()
    h = home(root)
    out = h / "onnx"
    out.mkdir(exist_ok=True)
    f32 = out / "student.onnx"
    # Coqui's export was written for the TorchScript exporter; torch 2.9 on defaults to the dynamo one, which
    # cannot follow VITS's lengths (the flow's mask has a size known only once the durations are)
    plain, torch.onnx.export = torch.onnx.export, lambda *a, **k: plain(*a, **k, dynamo=False)
    try:
        model.export_onnx(str(f32), verbose=False)
    finally:
        torch.onnx.export = plain
    q8 = out / "student.int8.onnx"
    weights_in_8_bits(f32, q8)
    john = json.loads((h / "phonemes" / "John_01.json").read_text(encoding="utf-8"))["verses"]
    ids = np.array([model.tokenizer.text_to_ids(vocab.text(john[0][1][0][0]))], dtype=np.int64)
    feeds = {"input": ids, "input_lengths": np.array([ids.shape[1]], dtype=np.int64),
             "scales": np.array([0.667, 1.0, 0.8], dtype=np.float32)}
    # how far the 8-bit weights move the sound, with the noise turned off so both read the same way
    still = {**feeds, "scales": np.array([0.0, 1.0, 0.0], dtype=np.float32)}
    a, b = (ort.InferenceSession(str(f), providers=["CPUExecutionProvider"]).run(None, still)[0].reshape(-1)
            for f in (f32, q8))
    n = min(len(a), len(b))
    # by the spectrum, not the wave: a vocoder can shift a phase the ear never hears
    import librosa
    mel = lambda x: 10 * np.log10(librosa.feature.melspectrogram(y=x[:n], sr=SR, n_fft=1024, hop_length=256) + 1e-6)
    ma, mb = mel(a), mel(b)
    loud = ma > ma.max() - 50
    print(f"8-bit weights against float32: the spectra differ by {np.abs(ma - mb)[loud].mean():.2f} dB on average "
          f"where there is sound; {len(a)} and {len(b)} samples")
    for f in (f32, q8):
        for threads in (1, 2, 4):
            so = ort.SessionOptions()
            so.intra_op_num_threads = threads
            s = ort.InferenceSession(str(f), so, providers=["CPUExecutionProvider"])
            names = {i.name for i in s.get_inputs()}
            fd = {k: v for k, v in feeds.items() if k in names}
            s.run(None, fd)
            t0 = time.time()
            for _ in range(3):
                wav = s.run(None, fd)[0]
            dt = (time.time() - t0) / 3
            secs = wav.size / SR
            print(f"{f.name}: {f.stat().st_size / 1e6:.1f} MB, {threads} thread(s): {secs:.1f} s of speech in "
                  f"{dt:.2f} s ({secs / dt:.0f}x real time)")
        if f is q8:
            write_wav(h / "samples" / "John_01_1_student_int8.wav", wav.reshape(-1) / max(1e-9, np.abs(wav).max()) * 0.9)
    phone_tokens(root, model.tokenizer, vocab, path.parent.name)


def phone_tokens(root, tokenizer=None, vocab=None, run=""):
    """onnx/tokens.json: the id of every character the student reads and of the blank set between them, so a phone
    (or scripts/phone.py, the dashboard's stand-in for one) can turn a spoken form into the model's input without
    Coqui. Checked against Coqui's own text_to_ids on John 1 before it is written."""
    h = home(root)
    if tokenizer is None:
        from TTS.tts.utils.text.tokenizer import TTSTokenizer
        tokenizer, _ = TTSTokenizer.init_from_config(config(root))
    vocab = vocab or Vocab.load(h / "data" / "vocab.json")
    chars = tokenizer.characters
    ids = {c: chars.char_to_id(c) for c in vocab.letters() + "".join(MARKS)}
    blank = chars.char_to_id(chars.blank)
    john = json.loads((h / "phonemes" / "John_01.json").read_text(encoding="utf-8"))["verses"]
    for _, ps in john[:5]:
        for p, _ in ps:
            text = vocab.text(p)
            mine = [blank] + [x for c in text for x in (ids[c], blank)]
            assert mine == tokenizer.text_to_ids(text), f"the token ids differ from Coqui's for {p!r}"
    (h / "onnx").mkdir(exist_ok=True)
    (h / "onnx" / "tokens.json").write_text(json.dumps(
        {"ids": ids, "blank": blank, "tokens": vocab.toks, "scales": [0.667, 1.0, 0.8], "run": run,
         "made": time.time()}, ensure_ascii=False), encoding="utf-8")
    print(f"tokens.json: {len(ids)} characters, blank {blank}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["cut", "train", "say", "sample", "check", "export"])
    ap.add_argument("book", nargs="?", default="John")
    ap.add_argument("chapter", nargs="?", type=int, default=1)
    ap.add_argument("verses", nargs="?", default="1-5")
    ap.add_argument("--root", default=str(ROOT), help="the checkout whose recordings and phonemes to use")
    ap.add_argument("--all", action="store_true", help="cut: hold nothing back (the voice that ships)")
    ap.add_argument("--minutes", type=float, default=TRIAL_MINUTES,
                    help=f"train: minutes the run should have in all, over every restart (default {TRIAL_MINUTES})")
    ap.add_argument("--duty", type=float, default=1.0,
                    help="train: share of the time spent computing (0.5 leaves the GPU idle half the time)")
    ap.add_argument("--resume", help="train: a run folder to carry on, or 'newest' (a first run if there is none)")
    ap.add_argument("--run", help="say/check/export: a run folder (default: the newest)")
    ap.add_argument("--only", help="check: chapters whose names start so, comma-separated (John_01,Mark_)")
    a = ap.parse_args()
    if a.cmd == "cut":
        cut(a.root, not a.all)
    elif a.cmd == "train":
        train(a.root, a.minutes, a.duty, a.resume)
    elif a.cmd == "say":
        say(a.root, a.book, a.chapter, a.verses, a.run)
    elif a.cmd == "sample":
        sample_now(a.root, a.run)
    elif a.cmd == "check":
        check(a.root, a.only.split(",") if a.only else None, a.run)
    else:
        export(a.root, a.run)


if __name__ == "__main__":
    main()
