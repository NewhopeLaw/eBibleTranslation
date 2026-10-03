#!/usr/bin/env python3
"""Measure how several Karen speakers say the same passage, and where our voice sits among them.

    python "NGAW KAREN TTS/calibrate_speakers.py" --model models/mms/karen-runs/emma-v1/G_e0200.pth

Emma Htoo speaks softly, calmly and slowly: good to listen to, soft to learn
enunciation from, and a voice trained on her takes that on. How much to lift
it should not be guessed from one speaker, so this takes several people
reading the same words - the Lord's Prayer, Matthew 6:9-13 in Mason's text,
recorded by Karen readers on YouTube (audio/reference/prayer/, not in git) -
and measures each the same way. Their mean is the target, and our voice is
measured at several clarity settings (train_mms.enunciate) to find the one
that lands on it.

Where the passage is in each recording comes from Meta's MMS forced aligner
(torchaudio MMS_FA), which aligns romanised text in any language to speech.
The Karen is romanised from karen_phonemes, each syllable a "word", so every
speaker is timed syllable by syllable; a wildcard between verses takes up
whatever else a recording holds (English, an introduction, the rest of the
chapter). Our own voice is put through the same aligner, so all are measured
alike.

What is measured, over the 146 syllables of 9-13:
  rate     syllables per second of speaking, pauses over 0.3 s left out
  depth    how far the sound drops between syllables, in dB: the dip at each
           syllable's start against the syllable's peak - the audible edge
           of a syllable, which a soft speaker blurs
  rise     how quickly a syllable reaches its peak from that dip, ms
  pitch    the spread of the voice's pitch in semitones: how much it moves
  bright   the share of energy above 2 kHz, dB; this depends on the
           microphone and the upload as much as the speaker, so it is shown
           and not used for the target
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import karen_phonemes as kp                                        # noqa: E402
from karen_speech import karen_verses                               # noqa: E402
from karen_voice_test import pitch, read_wav                        # noqa: E402

PRAYER = HERE / "audio" / "reference" / "prayer"
REPORT = HERE / "reports" / "calibration.md"
FS = 16000

# The recordings: who reads, and whether they count towards the mean. A
# congregation saying it together is many voices at once, measured for
# interest and left out of the target.
SPEAKERS = {
    "uZecdbDTPac": ("Htoo Aye (Stuff of Life, with English)", True),
    "R5gY33TkUy0": ("Stuff of Life reader (with English, music under)", True),
    "-z-4AYQmvj0": ("Thaw Eh Paw, narrator", True),
    "URHGpkapKDk": ("Karen Young Dreamers, Matthew 6 read whole", True),
    "UX0z_huwmFo": ("Karen Spiritual Growth Channel", True),
    "BlIGh-AVUUw": ("congregation, Messiah St. Paul", False),
    "ErqA6PnIAV0": ("congregation, Messiah St. Paul", False),
}

ROMAN = [("tʃʰ", "ch"), ("tʃ", "ch"), ("kʰ", "kh"), ("sʰ", "s"), ("tʰ", "th"), ("pʰ", "ph"), ("ɣ", "g"), ("ŋ", "ng"),
         ("ʃ", "sh"), ("ɲ", "ny"), ("θ", "th"), ("ʔ", ""), ("ɦ", "h"), ("j", "y"), ("ə", "e"), ("ɨ", "u"), ("ɛ", "e"),
         ("ɔ", "o")]


def roman(item):
    s = item["onset"] + item["medial"] + item["vowel"]
    for a, b in ROMAN:
        s = s.replace(a, b)
    return "".join(c for c in s if c.isalpha()) or "a"


def passage():
    """Matthew 6:9-13 as verses of syllables: (Karen, romanised)."""
    out = []
    for karen in karen_verses("Matt", 6, range(9, 14)):
        out.append([(m.group(0), roman(kp.syllables(m.group(0))[0][1])) for m in kp.SYLLABLE.finditer(karen)])
    return out


class Aligner:
    def __init__(self):
        import torch
        import torchaudio
        self.torch = torch
        self.bundle = torchaudio.pipelines.MMS_FA
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.bundle.get_model(with_star=True).to(self.device).eval()
        self.tokenizer = self.bundle.get_tokenizer()
        self.aligner = self.bundle.get_aligner()

    def emission(self, x, chunk=30.0):
        """The model's letter probabilities, 30 s at a time: a whole chapter at
        once does not fit its attention."""
        torch = self.torch
        n, parts = int(chunk * FS), []
        with torch.inference_mode():
            for i in range(0, len(x), n):
                seg = torch.from_numpy(x[i:i + n].astype(np.float32)).unsqueeze(0).to(self.device)
                if seg.shape[1] < FS // 10:
                    break
                parts.append(self.model(seg)[0][0])
        return torch.cat(parts)

    def align(self, x, verses):
        """Syllable start/end times for every syllable of the passage."""
        words = ["*"]
        for v in verses:
            words += [r for _, r in v] + ["*"]
        em = self.emission(x)
        spans = self.aligner(em, self.tokenizer(words))
        sec = len(x) / FS / em.shape[0]
        out, i = [], 0
        for v in verses:
            i += 1                                                  # the wildcard before the verse
            row = []
            for syl, _ in v:
                s = spans[i]
                row.append({"syl": syl, "t0": s[0].start * sec, "t1": s[-1].end * sec,
                            "score": float(np.mean([t.score for t in s]))})
                i += 1
            out.append(row)
        return out


def rms_track(x, hop=160):
    n = len(x) // hop
    fr = x[:n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-7)


def measure(x, timed):
    """The five measures over the aligned syllables."""
    from scipy.signal import stft
    env = rms_track(x)
    frames = lambda t: int(t * 100)                                  # noqa: E731
    sylls = [s for v in timed for s in v]
    # A syllable runs from its start to the next one's start in the verse; the
    # aligner's own spans are the narrow spikes a CTC model fires, not lengths.
    durs, depth, rise = [], [], []
    for v in timed:
        for k, s in enumerate(v):
            end = v[k + 1]["t0"] if k + 1 < len(v) else s["t1"] + 0.15
            d = end - s["t0"]
            if d <= 0.3:
                durs.append(d)
            a, b = frames(s["t0"]), frames(min(end, s["t0"] + 0.4))
            if b - a < 3 or b >= len(env):
                continue
            dip = env[max(0, a - 3):a + 3].min()
            seg = env[a:b]
            peak = seg.max()
            depth.append(peak - dip)
            lin = 10 ** (seg / 20)
            lo, hi = 10 ** (dip / 20), 10 ** (peak / 20)
            t10 = np.argmax(lin >= lo + 0.1 * (hi - lo))
            t90 = np.argmax(lin >= lo + 0.9 * (hi - lo))
            rise.append(max(0, t90 - t10) * 10)
    span = x[int(sylls[0]["t0"] * FS):int((sylls[-1]["t1"] + 0.2) * FS)]
    p = pitch(span.astype(np.float64), FS)
    st = 12 * np.log2(p / np.median(p)) if len(p) > 10 else np.array([0.0])
    f, _, Z = stft(span, FS, nperseg=512)
    P = np.abs(Z) ** 2
    return {"rate": len(durs) / max(1e-6, sum(durs)), "depth": float(np.median(depth)), "rise": float(np.median(rise)),
            "pitch": float(np.std(st)), "bright": float(10 * np.log10(P[f >= 2000].sum() / P.sum())),
            "score": float(np.mean([s["score"] for s in sylls])), "start": sylls[0]["t0"], "end": sylls[-1]["t1"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="our voice's checkpoint (default: the newest run)")
    ap.add_argument("--clarity", default="0,0.5,1,1.5,2,3", help="our voice's clarity settings to try")
    a = ap.parse_args()
    import torch
    import train_mms as tm

    verses = passage()
    al = Aligner()
    rows = []
    for key, (who, counts) in SPEAKERS.items():
        f = PRAYER / f"{key}.wav"
        if not f.exists():
            continue
        x, fs = read_wav(f)
        assert fs == FS, f
        m = measure(x, al.align(x, verses))
        rows.append({"who": who, "key": key, "counts": counts, **m})
        print(f"{who:48s} {m['start']:6.1f}-{m['end']:6.1f}s  rate {m['rate']:.2f}  depth {m['depth']:.1f}  "
              f"rise {m['rise']:.0f}  pitch {m['pitch']:.2f}  bright {m['bright']:.1f}  fit {m['score']:.2f}")

    voice = tm.MmsKaren(a.model, deterministic=False)
    karen = karen_verses("Matt", 6, range(9, 14))
    ours = []
    for c in [float(v) for v in a.clarity.split(",")]:
        voice.clarity = c
        torch.manual_seed(0)
        y = np.concatenate([np.concatenate([voice.say(k), np.zeros(int(FS * 0.3))]) for k in karen])
        y = y / np.abs(y).max() * 0.9
        m = measure(y, al.align(y, verses))
        ours.append({"who": f"our voice, clarity {c:g}", "clarity": c, **m})
        print(f"{'our voice, clarity ' + format(c, 'g'):48s} rate {m['rate']:.2f}  depth {m['depth']:.1f}  "
              f"rise {m['rise']:.0f}  pitch {m['pitch']:.2f}  bright {m['bright']:.1f}")

    people = [r for r in rows if r["counts"]]
    keys = ["rate", "depth", "rise", "pitch"]
    mean = {k: float(np.mean([r[k] for r in people])) for k in keys}
    sd = {k: float(np.std([r[k] for r in people])) or 1.0 for k in keys}
    # the clarity setting nearest the mean on the two measures clarity moves
    best = min(ours, key=lambda o: abs(o["depth"] - mean["depth"]) / sd["depth"] + abs(o["rise"] - mean["rise"]) / sd["rise"])
    pace = best["rate"] / mean["rate"]

    lines = ["# Calibration: several speakers, one passage", "",
             f"Matthew 6:9-13, 146 syllables, aligned in each recording by MMS_FA. Our voice: "
             f"`{a.model or 'newest'}`.", "",
             "| speaker | where (s) | rate syl/s | depth dB | rise ms | pitch st | bright dB | fit | in mean |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['who']} | {r['start']:.1f}-{r['end']:.1f} | {r['rate']:.2f} | {r['depth']:.1f} | {r['rise']:.0f} | "
                     f"{r['pitch']:.2f} | {r['bright']:.1f} | {r['score']:.2f} | {'yes' if r['counts'] else 'no'} |")
    lines.append(f"| **mean of {len(people)} readers** | | **{mean['rate']:.2f}** | **{mean['depth']:.1f}** | "
                 f"**{mean['rise']:.0f}** | **{mean['pitch']:.2f}** | | | |")
    for o in ours:
        lines.append(f"| {o['who']} | | {o['rate']:.2f} | {o['depth']:.1f} | {o['rise']:.0f} | {o['pitch']:.2f} | "
                     f"{o['bright']:.1f} | {o['score']:.2f} | |")
    lines += ["", f"Nearest the readers' mean on depth and rise: clarity {best['clarity']:g}. "
              f"To speak at their rate the voice's pace would be {pace:.2f} (above 1 is slower).", "",
              "Fit is the aligner's mean confidence per syllable; a low one means the passage may not have been "
              "found, and that reader's numbers should not be trusted."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORT.with_suffix(".json")).write_text(json.dumps({"readers": rows, "ours": ours, "mean": mean,
                                                          "clarity": best["clarity"], "pace": pace}, indent=1), encoding="utf-8")
    print(f"\nmean of readers: {mean}\nclarity {best['clarity']:g}, pace {pace:.2f} -> {REPORT}")


if __name__ == "__main__":
    main()
