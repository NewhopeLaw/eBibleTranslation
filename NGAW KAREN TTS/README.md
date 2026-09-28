# NGAW KAREN TTS

Teaching a speech engine to pronounce Sgaw Karen (ကညီကျိာ်, "K'nyaw"). No
phone, computer or public model ships a Karen voice, so this folder builds one
in layers, each layer testable against a Karen speaker:

| step | what | file |
|---|---|---|
| 1 | Karen letters → sounds and tones (a lookup: the spelling is a sound table) | `karen_phonemes.py` |
| 2 | A borrowed voice reads those sounds: Meta's Burmese voice respelled and retuned, or a Piper neural voice trained on Vietnamese fed the phonemes | `karen_speech.py` |
| 3 | Test any voice against a Karen speaker, word by word, by ear and by pitch | `karen_voice_test.py` |
| 4 | Cut lesson recordings into words with known spellings: the syllabary and the training data | `karen_lessons.py` |
| 5 | Fine-tune Meta's Burmese voice on the Karen cuts: it reads the Myanmar script as written, so no phoneme layer | `train_mms.py` |
| 5a | (retired) Fit the tone table and fine-tune the Piper Vietnamese voice | `fit_tones.py`, `train_voice.py` |
| 6 | Emma Htoo's course, read for her pronunciation and phonics; the check at the end | `phonics-emma-htoo.md` |

The audio under `audio/` is not in git: `audio/reference/` holds recordings of
Karen speakers from YouTube (the "Learning Sgaw Karen" vocabulary lessons by
Stuff of Life, Emma Htoo's "Learn the Karen Language" course, a reading of the
Lord's Prayer), used to measure and to teach, not to ship; `audio/ksw/` holds
what our voices produce. `words/` holds the word lists with their Karen
spellings, `reports/` the measurements.

What this session tried, with every YouTube source and what it gave, and
suggestions for the next attempt, is in `experiment-log.md`. It ends by
pointing at a channel with the whole Karen Bible read aloud (102 hours),
not yet used.

The plan for a real voice is in `data-plan.md`: pretrain on Burmese, adapt
on Karen audio, fine-tune on studio recordings of one Karen speaker. The
Vietnamese adaptation below did not work well and is kept as a record and a
fallback; the next attempt adapts Burmese.

## Where things stand (2026-09-27)

- The Vietnamese route is retired: two layers of guessing (phonemes, then a
  tone mapping) between the Karen letters and a voice that never saw them,
  and neither fine-tune came clear. The voice is now fine-tuned from Meta's
  MMS Burmese one (`train_mms.py`), which takes Karen text as written; the
  six Karen characters it lacks (ၤ ၢ ၣ ဃ ၡ ၠ, a fifth of Mason's text) are
  added, each starting from its nearest Burmese symbol. Trained with VITS's
  own code on Meta's released generator and discriminator. The Burmese model
  is CC BY-NC 4.0, and so is what is made from it. Yardstick on the
  vocabulary test (`karen_voice_test.py --engine`, mean pitch correlation over
  39 words): the Piper Vietnamese voice 0.31, the untrained Burmese voice
  -0.02. First run, `emma-v1`: Emma's confirmed cuts, 21.7 minutes with the
  short ones padded with silence, 200 epochs; held-out mel loss fell all the
  way (0.444 at epoch 5 to 0.397 at 200). On the vocabulary test it scores
  0.04 to 0.15 by checkpoint (best at epoch 100), under Piper's 0.31; on
  Emma's 102 held-out cuts every voice, Piper included, sits near 0.1, so
  her isolated syllables cannot rank voices by pitch. The ear decides.
- To the ear `emma-v1` cut its enunciation off, for two reasons. The lesson
  cuts ended 26 dB under the word's peak, while the tone was still fading
  (the room is about 40 dB down), so the voice learnt to stop syllables
  short; `train_mms.py` now cuts each clip again from the full lesson out to
  the quiet, 91 ms longer at the median. And Mason's punctuation (ASCII
  `,` `.`) is not in the voice's alphabet and was dropped, so a verse came
  out in one breath; the voice now says each clause separately, with a pause
  between. `emma-v2-recut` retrains from the Burmese voice on the re-cut clips.

- The phonetic layer is complete and regular, and Emma Htoo's lessons confirm
  it: every consonant (lesson 1), the nine vowels including the three signs
  Karen reads differently from Burmese (lesson 3), and the five tone marks
  measured from her voice (lesson 4), which move differently from Wade's
  1861 descriptions - ၤ falls, ၣ် rises, း rises steeply. `phonics-emma-htoo.md`.
- Lessons digested one at a time so far: Emma 1, 3, 4; vocabulary 1, 4, 5, 6
  (86 word cuts, 45 with corpus-confirmed spellings), plus 172 single-syllable
  cuts of Emma's letters and vowels. Captions for vocabulary 2 and Emma 5 are
  fetched when YouTube's rate limit lets them through.
- The Piper Vietnamese voice with the tone mapping refitted on all the cuts
  scores 0.53 mean pitch correlation with the speakers (reports/tones.md);
  the fit is still order-sensitive at this size.
- Emma's syllable tables gave the tone data: 42 syllables under ၢ် ၣ် ၤ
  (video 8, 276 cuts, by tracking her on-screen highlight), 30 under the
  vowel i (video 10, 439 cuts, by screen change), and the whole six-tone
  paradigm on eighteen consonants (video 11, 236 cuts, by tracking her mouse
  pointer). On one vowel and one speaker the six tones sit in a clear order
  within three semitones - ၣ် highest, ၢ် high, ၤ and း mid, unmarked low,
  ာ် lowest - and differ in length as much as pitch; the table follows that.
  2,391 cuts in all with her course complete (all sixteen lessons), her
  lesson 6 phrases and lesson 2, 7 and 8 words the first connected speech. The lessons are
  digested by tracking whatever marks her place on screen: a cyan box, a
  pink cursor, an accumulating yellow highlight, a mouse pointer, a
  selection box - each lesson its own detector.
- Fine-tunes so far: v1, single speaker, 0.8 minutes, 300 epochs
  (`karen-v1.onnx`), slurred to the user's ear; v2, the vocabulary man and
  Emma as two voices of one model, 8.5 minutes, 150 epochs (`karen-v2.onnx`),
  pitch correlation with the speaker 0.08 and 0.15 against the base voice's
  0.55. Lesson cuts are isolated syllables and words over background music,
  the wrong shape of data for a neural voice however many there are; the
  lesson from both runs is that the next training data must be connected
  read speech from one speaker, 30-60 minutes, which only a recording made
  for the purpose gives. Until then the base voice with the fitted tone
  mapping, a tenth slower, is the synthetic voice, and the hybrid the
  intelligible one.
- The Vietnamese tone mapping is fitted on the vocabulary speaker's whole
  words alone (`fit_tones.py --speaker vocab`, 0.49 to 0.55 correlation);
  fitted on Emma's flat isolated syllables it is underdetermined (0.26).
- Fine-tune v1 (`models/piper/karen-v1.onnx`): the Vietnamese voice trained
  300 epochs on the vocabulary speaker's 53 cuts (0.8 min). It sits at his
  pitch (129 Hz) with tone shapes near the base voice's (0.45 against 0.52
  correlation) but, to the user's ear, slurs: under three minutes of Karen
  cannot teach a neural voice clarity. Listening copies play a tenth slower
  (`--pace`), which helped.
- `karen_syllabary.py` is the hybrid: the speaker's own recording for every
  word or syllable the cuts know, Piper for the rest. Intelligible by
  construction on the lesson vocabulary; with all 2,391 cuts, 24% of
  Genesis 1's syllables come from recordings (confirmed spellings, both
  speakers) and 48% of John 3's (all cuts). One speaker at a time by
  default (`--speaker vocab` or `emma`), since a sentence should not change
  voice mid-word.
- What would make a real voice: 30-60 minutes of one Karen speaker reading
  transcribed text (a reader recorded on the trip, or the Sgaw Karen audio
  Bible aligned to Mason's text with its owners' permission). The pipeline
  is ready for it: `karen_lessons.py` cuts, `fit_tones.py` fits,
  `train_voice.py` trains and exports.

## Running

    python "NGAW KAREN TTS/karen_phonemes.py" Gen 1 1-3                 # notation
    python "NGAW KAREN TTS/karen_speech.py" Matt 6 9-13 --engine piper    # audio/ksw/*.wav
    python "NGAW KAREN TTS/karen_voice_test.py" "NGAW KAREN TTS/audio/reference/vocab1.wav" --words "NGAW KAREN TTS/words/vocab1.json" --floor -18 --engine piper
    python "NGAW KAREN TTS/train_mms.py" --train --epochs 200 --name emma-v1          # models/mms/karen-runs/emma-v1
    python "NGAW KAREN TTS/karen_speech.py" Gen 1 1-5 --engine mms                     # the newest checkpoint
    python "NGAW KAREN TTS/karen_voice_test.py" "NGAW KAREN TTS/audio/reference/vocab1.wav" --words "NGAW KAREN TTS/words/vocab1.json" --floor -18 --engine mms --model <run>/G_e0200.pth

Needs: torch, transformers, pyworld, piper-tts, numpy, scipy, yt-dlp,
imageio-ffmpeg, librosa, monotonic-alignment-search; the Piper voices under
`models/piper/` (rhasspy/piper-voices); for `train_mms.py`, VITS
(`git clone https://github.com/jaywalnut310/vits sources/vits`) and Meta's
Burmese checkpoints in `models/mms/mya/` (mya.tar.gz from
dl.fbaipublicfiles.com/mms/tts/, and D_100000.pth from facebook/mms-tts's
full_models/mya on Hugging Face).
