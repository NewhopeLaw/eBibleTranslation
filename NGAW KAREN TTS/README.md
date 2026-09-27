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
| 5 | Fit the tone table to the speaker, then fine-tune a Piper voice on the Karen cuts | `tune_tones` reports, `train_voice.py` |
| 6 | Emma Htoo's course, read for her pronunciation and phonics; the check at the end | `phonics-emma-htoo.md` |

The audio under `audio/` is not in git: `audio/reference/` holds recordings of
Karen speakers from YouTube (the "Learning Sgaw Karen" vocabulary lessons by
Stuff of Life, Emma Htoo's "Learn the Karen Language" course, a reading of the
Lord's Prayer), used to measure and to teach, not to ship; `audio/ksw/` holds
what our voices produce. `words/` holds the word lists with their Karen
spellings, `reports/` the measurements.

The plan for a real voice is in `data-plan.md`: pretrain on Burmese, adapt
on Karen audio, fine-tune on studio recordings of one Karen speaker. The
Vietnamese adaptation below did not work well and is kept as a record and a
fallback; the next attempt adapts Burmese.

## Where things stand (2026-09-27)

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

Needs: torch, transformers, pyworld, piper-tts, numpy, scipy, yt-dlp,
imageio-ffmpeg; the Piper voices under `models/piper/` (rhasspy/piper-voices).
