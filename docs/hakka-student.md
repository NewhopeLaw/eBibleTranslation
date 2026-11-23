# A Hakka voice for the phone

The PC and dashboard readers play Hakka from chapter recordings made ahead of
time (`scripts/hakka_speech.py`): FormoSpeech's YourTTS
(`formospeech/yourtts-htia-240704`), speaker XF, a Miaoli woman reading
Sixian, all 1,189 chapters in `audio/hak/`, 14 GB as WAV. They stay as they
are. The APK carries no recordings, so the phone has no Hakka voice at all.
The decision of 2026-11-03 holds for Hakka as for Taiwanese: the full
recordings for the PC, a voice model for the phone. This is that model, made
the way the Taiwanese one is (`docs/taiwanese-student.md`, which says why
VITS, why this size, and how it is shipped), and only what differs is written
down here. Nothing here is in the APK yet.

## Where it stands

A smoke run only, on 2026-11-22, to prove the pipeline, sharing the GPU
with the Taiwanese student's night run: three minutes from the command line,
which saved, read its sample and exported itself on reaching its target, then
two more started from the dashboard's card, a Make sample asked of it while
it ran, and its Stop, which saved `checkpoint_334.pth` at 5 minutes. It reads
nothing yet worth hearing. The export came to 62.3 MB as float32 and **16.4 MB
with 8-bit weights**, 12× real time on one thread of this PC's CPU and 28× on
two, and the phone preview plays it. The night run is the dashboard's
**hakka-student** job, under TTS processing, which carries that run on to 360
minutes at full speed, with Make sample, its chart and a gentle Stop, like the
Taiwanese student's.

<!-- RESULT -->

## Why not a voice that already exists

- **Meta's `facebook/mms-tts-hak`** (36 M weights, CC BY-NC 4.0) reads only
  romanised Hakka, not the characters the reader holds, and its dialect is
  not stated. It would need a romaniser in front of it on the phone and would
  still not be the voice the PC plays.
- **The teacher itself** is a multi-speaker YourTTS with a speaker encoder and
  language embeddings, too large and too slow for a mid-range phone, and
  formog2p's lexicons and jieba would have to ship with it.

A student of one speaker at Piper's "medium" size is 15.4 M weights at
reading time, about 16 MB as 8-bit weights, and reads what the PC's
recordings say, in the same voice.

## May a student of this voice ship?

**The teacher.** `formospeech/yourtts-htia-240704` is **CC BY-NC 4.0** (its
model card; part of VoxHakka, arXiv:2409.01548), trained on more than
nineteen Taiwanese Hakka speakers in five dialects. Its card says it is not
for commercial use.

**What follows for a student.** As with SuíSiann, the safe reading is the
strict one: a voice taught from the teacher's output is adapted from it, so
the student's weights are **CC BY-NC 4.0** too, with the credit. NonCommercial
is the condition that matters: the APK that carries the student may be given
away but not sold, and nothing in it may be put behind a payment. That is the
terms the recordings already have on the PC (`hakka_speech.py`), now carried
to the phone. Taiwanese's CC BY-SA reaches only the voice file; NC is best
taken as reaching the whole APK that carries it, since an app sold with the
voice inside it is a commercial use of the voice whatever licence the rest has.

**The front end.** formog2p is MIT. Its lexicons ship inside the package with
no other source or terms stated. They stay on the PC: what ships is the
reading of each verse, worked out here, as for Taiwanese.

**What it needs.** Nothing in `LEGAL.md`, the reader or the app credits
FormoSpeech yet. The APK that carries the student needs a line such as:

> Hakka voice: taught from FormoSpeech's yourtts-htia-240704 (VoxHakka),
> speaker XF, CC BY-NC 4.0; pronunciation by formog2p (MIT).

## What it reads

`scripts/hakka_phonemes.py` runs the teacher's own front end over every
chapter, in the Hakka voice's environment: each verse cut at its sentence
ends (`hakka_speech.sentences`), each sentence through formog2p into Sixian
IPA, the string the teacher was given, with ` .` added at its end.

- Each syllable comes out as initial, final and tone, `s-oŋ_55` (上), so the
  student's tokens are the Taiwanese student's three per syllable:
  `I:s F:oŋ T:55`. A word's syllables are joined by `-`, words by a space,
  and the comma is the only other mark the teacher knows. 93 tokens in all.
- The ` .` is not the teacher's. A lesson of a whole verse would run its
  sentences together, and the student should see where the 0.8 s it hears
  between them comes from. (Every lesson so far is one sentence, so it is
  there for the ones that may not be.)
- A word formog2p cannot read reaches the teacher as characters, and the
  teacher says nothing for them. It is left out of the spoken form and listed
  under `unread`: 35 words in 18 chapters.
- All 1,189 chapters come to **8.6 MB of JSON, 2.1 MB gzipped**.

## The lessons

`scripts/hakka_student.py cut` uses the Taiwanese cutter
(`taiwanese_student.cut`) with Hakka's pauses. Here the teacher is easier to
cut than SuíSiann. Its pauses are digital silence put in by
`hakka_speech.py` (0.35 s between sentences, 0.7 s between verses), with
about 0.22 s of YourTTS's own quiet either side and nothing cleaned after.
In every chapter looked at, a sentence ends 0.80–0.85 s before the next and a
verse 1.15–1.21 s, with nothing between, so the cuts sit at 0.6 s and 1.0 s.
In 40 New Testament chapters every verse had a pause for every sentence. XF
reads at 3.3 syllables a second, 98 sentences in 100 between 2.8 and 3.8.

From the New Testament, John 1 held out:

| | |
|---|---|
| lessons | 9,233 sentences (no whole verses needed), 18.7 h |
| held out | John 1, 65 sentences |
| left out | 12 for their pace; 13 verses and their neighbours where the pauses disagreed with `build_audio.place` |
| longer than 16 s | 104 sentences, 0.5 h, which the trainer passes over |

The student, its training, Make sample, the gentle stop and the export are
the Taiwanese one's code, unchanged. `hakka_student.py` sets the language,
the model folder, the tokens and the pauses, and calls it. The ear test is
the same pair: John 1:1, never trained on, and John 3:16, trained on.

## The trial

<!-- TRIAL -->
