# A Taiwanese voice for the phone

The PC and dashboard readers play Taiwanese from chapter recordings made
ahead of time (`scripts/taiwanese_speech.py`): SuíSiann's Tacotron 2 and
WaveRNN, then DeepFilterNet and a Praat pitch change, at about 1.3 times real
time on the 5090. They stay as they are. The phone has no Taiwanese voice at
all: the whole Bible in Opus comes to about 1.5 GB, far too much for the APK.
The decision is to keep the full recordings for the PC and give the phone a
voice model. This is the question of whether the recorded voice can be taught
to a model small enough for a mid-range Android phone, and a trial of it.
Nothing here is in the APK yet.

## Where it stands

<!-- RESULT -->

## May a student of this voice ship?

**The recordings the voice learnt from.** The SuíSiann dataset
(suisiann-dataset.ithuan.tw, version 0.2.1, recorded 2018–2019 by
Ông Siù-iông 王秀容 at Muscene Studio for 意傳科技) is **CC BY-SA 4.0**, not
public domain as the docstring of `taiwanese_speech.py` says. Its terms, from
the site and the licence form behind it: the audio may be used for speech
synthesis, academic or commercial, with the source credited; the Han text of
the transcripts may not be altered, and the transcripts may be used only for
speech synthesis.

**The teacher.** ga642381's Taiwanese-Speech-Synthesis is MIT (© 2021
Kai-Wei Chang). The Tacotron 2 and WaveRNN weights come from a Google Drive
folder linked from that README; nothing gives them a licence of their own, so
they are best taken as the MIT repository's, trained on CC BY-SA audio.

**What follows for a student.** Whether a model trained on CC BY-SA audio is
"adapted material" of it is unsettled. A student trained on the teacher's
output is one step further from the recordings, but nothing in the terms
rests on that distance, so the safe reading is the strict one: treat the
student's weights as adapted from SuíSiann, and ship that one file under CC
BY-SA 4.0 with the credit. That puts no condition on the app. ShareAlike
reaches only the voice file, which may sit in an APK beside code under any
licence, the way the reader already carries CC BY-SA study layers.

**What it needs.** The APK carries no recordings today (`build_apk.py`
stages the page without `audio/`, so the phone says it has no Taiwanese
voice), and the recordings stay on the PC. The student would be the first
thing from SuíSiann to leave this machine. Nothing in `LEGAL.md`, the reader
or the app credits SuíSiann yet, so the APK that carries the student needs a
line such as:

> Taiwanese voice: trained on the SuíSiann Dataset (台灣媠聲), read by
> 王秀容, © 意傳科技, CC BY-SA 4.0 (suisiann-dataset.ithuan.tw); via
> ga642381's Taiwanese-Speech-Synthesis (MIT).

The pronunciation dictionaries are a separate matter (see below): the MOE
臺灣閩南語常用詞辭典 is CC BY-ND 3.0 TW and Campbell's 甘字典 as ChhoeTaigi
keeps it is CC BY-NC-SA 3.0 TW. Neither should go into the APK as a file.

## The student

**VITS, cut to Piper's "medium" size** (`scripts/taiwanese_student.py`,
Coqui's implementation): a 6-layer text encoder, a deterministic duration
predictor (VITS's stochastic one is left out, so a verse reads the same way
twice), the flow, and a small HiFi-GAN (type-2 resblocks, 256 channels).
About **15.4 M weights at reading time**. The posterior encoder and the
discriminators are used only in training and are not exported.

Why this and not the alternatives:

- It is not autoregressive. Tacotron 2's attention can stall or run on, and
  it is why the teacher reads at most 1,000 frames a piece. VITS has
  explicit durations and cannot do either.
- It needs no aligner. VITS finds its own alignment while it trains
  (monotonic alignment search), so the teacher's chapters need only cutting
  at their pauses, which the teacher leaves exactly where its pieces end.
- It is the proven phone size. Piper's medium voices are this network and
  run on a Raspberry Pi and under sherpa-onnx on Android. The float32 ONNX file
  comes to 62.3 MB, the same as Piper's.
- VoiceLab's design (`ShrineGirl/VoiceLab/scripts/train.py`, 2.8 M weights)
  is only a decoder. Open JTalk gives it its timing and pitch, and Taiwanese
  has nothing to do that. A durations-and-pitch-from-the-teacher variant is
  possible (the Bible text is fixed, so even timing and melody could be
  worked out on the PC and shipped), but it needs a phone-level alignment of
  every recording first. It is kept as the fallback if VITS's own prosody
  falls short.

**Size and speed, measured.** These are from `taiwanese_student.py export`,
reading John 1:1 (4.4 s of speech), ONNX Runtime 1.26 on this PC's CPU:

| file | size | 1 thread | 2 threads | 4 threads |
|---|---|---|---|---|
| float32 | 62.3 MB | 18× real time | 29× | 38× |
| 8-bit weights, float arithmetic | **16.4 MB** | 17× | 27× | 40× |
| ONNX Runtime's dynamic int8 | 18.6 MB | 2× | 3× | 4× |

The middle row is the one to ship. It stores each large weight as 8-bit
integers with a scale per channel, and ONNX Runtime widens them back to
floats when it loads the file. It is as fast as float32 from a quarter of the
size. ONNX Runtime's own dynamic quantization keeps the arithmetic in 8 bits
too, which for these convolutions was seven times slower. A mid-range
phone's big core does roughly a third to a half of the work of one of these
desktop cores, which puts the student at about 6–9× real time on one core,
comfortably ahead of the voice. Inside the reader's WebView, onnxruntime-web
(WASM) would be slower again and cost about 10 MB of runtime. A small Java
bridge to ONNX Runtime for Android (arm64 only, about 8 MB) is the better
road. A phone measurement is still to be made.

## Where the pronunciation is worked out

On the PC, at build time, and shipped beside the text. The idea holds.

The teacher never reads characters. Each verse is cut into pieces at its
punctuation, turned into Tâi-lô by longest match in the MOE dictionary (with
甘字典 for what it lacks), and the Tâi-lô into the spoken form with the tone
sandhi applied by 臺灣言語工具. Every step depends only on the text, and the
text is fixed once a chapter is made. `scripts/taiwanese_phonemes.py` runs
the teacher's own frontend over every chapter and writes the very strings
the teacher was given. The cutter's agreement with the recordings is the
check that they are the same. In 240 of the 260 New Testament chapters there
is a pause for every verse, and in all but 121 of those verses a pause for
every piece. Each of those 121 had a pause too few or too many.

- All 1,189 chapters come to **6.1 MB of JSON, 1.9 MB gzipped**. As one byte
  per token it would be nearer 1 MB.
- The phone needs no dictionary, no sandhi rules and no Python. The
  dictionaries' ND and NC-SA licences stay on the PC. What ships is a
  reading of each verse, which is what the recordings carry already.
- A wrong reading becomes cheap to mend. Today a misread name means
  re-recording a chapter. With a student it means correcting that verse's
  phonemes, at build time, in milliseconds.
- What the phone cannot then do is read text it was not given: a search
  result or a note typed on the phone. For a Bible reader that is the right
  trade. When the text of a chapter changes (`mend.py`), its phonemes are
  remade with it, as its recording is now.

## The trial

<!-- TRIAL -->
