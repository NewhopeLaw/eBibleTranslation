# Experiment log: teaching a borrowed voice to speak Sgaw Karen

Session of 2026-09-26 to 2026-09-27, on the PC (RTX 5090). Written for the
next session, and in particular for the branch that is adapting a Burmese
voice: what was tried here, what each attempt produced, what was measured,
which sources were used and how, and which to try next.

**Short version.** A Vietnamese neural voice was taught to read Karen through
our own phonetic notation. It reads every word audibly, but as Karen with a
heavy Vietnamese accent, and the judgement by ear was that native speakers
would not follow it. Fine-tuning it on Karen recordings made it worse,
because the only recordings were language lessons: isolated syllables and
words, often over music, from two different people. What survives and is
worth reusing: the spelling-to-sound table, six tones measured on a real
speaker, 2,391 labelled cuts of Karen speech, a test harness that scores any
voice against a Karen speaker, and a hybrid voice that plays real recordings
where it has them. The most promising source for a real voice was found at
the very end and not yet used: a YouTube channel with the whole Bible read
aloud in Karen, one video per chapter, 102 hours.

## 1. The goal

A missions trip to Karen villages in the hills near Chiang Mai needs a Sgaw
Karen Bible that can be read aloud to people who may not read. The text was
solved in the same session (a MADLAD-400 model taught from Mason's 1853
Karen Bible; all 1,189 chapters, in the reader and the APK). The voice was
not. No phone, computer or public model speaks Sgaw Karen, and there is no
`facebook/mms-tts-ksw` (checked on Hugging Face).

## 2. What was tried, in order

### 2.1 Burmese voice with Karen respelled (first attempt)

`karen_speech.py --engine burmese`. Meta's offline Burmese voice
(`facebook/mms-tts-mya`) was fed Karen respelled into the Burmese spelling
with the nearest sounds: Karen ိ /o/ written as Burmese ို, ံ /i/ as ီ, and so
on. Karen's six tones were squeezed into Burmese's four.

- **Why it could not work as is.** The voice's alphabet has 58 symbols and
  none of the twelve letters Karen adds to the script (U+1061 to U+106D),
  which are Karen's tone marks and extra vowels. Fed Karen directly, it
  drops them.
- **Then retuned per syllable, "Vocaloid style".** Each syllable was
  synthesised on its own, pulled apart with the WORLD vocoder (pitch,
  spectral envelope, aperiodicity), given its Karen tone's pitch curve and
  length, and resynthesised (`render(... tuned=True)`).
- **Result.** Pitch-shape correlation with a Karen speaker averaged 0.01
  over 39 words, which is no relation. It sounded choppy, one syllable at a
  time.
- **Note for the Burmese branch.** This was a zero-shot respelling, not a
  trained adaptation. It says nothing against training a Burmese model on
  Karen audio. The script and most consonants are shared, and the vowel and
  tone tables below say exactly where Karen and Burmese part.

### 2.2 Vietnamese neural voice fed Karen phonemes

`karen_phonemes.py` turns Karen text into IPA with tones, then into the
phoneme symbols a Piper voice trained by espeak-ng on Vietnamese understands
(`vi_VN-vais1000-medium`, rhasspy/piper-voices). Vietnamese was chosen
because it also has six tones, so each Karen tone could ride on a
Vietnamese one without pitch surgery. This is `karen_speech.py --engine
piper`.

- **Tone mapping.** First guessed by nearest contour. It was then fitted by
  trying every Vietnamese tone symbol and vowel length for each Karen tone,
  all six adjusted together by coordinate descent, and scoring whole-word
  pitch curves against the speaker (`fit_tones.py`).
- **Result.** 0.20 correlation guessed, 0.42 to 0.55 fitted on the
  vocabulary speaker's words. This is the best any synthetic voice reached.
- **The user's verdict.** "Sounds like Karen in a Vietnamese accent, what we
  see in a language exchange meetup." Then: "the Vietnamese is accented so
  much, I don't think native speakers can understand."
- **One thing that helped.** Slowing output by a tenth (`length_scale` 1.1,
  now the default `--pace`).
- **Only one Vietnamese voice is usable.** Of Piper's three Vietnamese
  voices, only vais1000 was trained with tone symbols. The other two ignore
  them.

### 2.3 Fine-tuning the Vietnamese voice on Karen recordings

`train_voice.py`. The voice's checkpoint was warm-started and trained on
Karen word cuts, with transcripts as phoneme ids from our notation.

| run | data | epochs | pitch corr. with speaker | by ear |
|---|---|---|---|---|
| base, not fine-tuned | none | none | 0.55 | accented, clear |
| v1 | 0.8 min, the vocabulary speaker alone, 53 cuts | 300 | 0.45 | slurred, not enough clarity |
| v2 | 8.5 min, the vocabulary speaker and Emma Htoo as two speakers, 692 cuts | 150 | 0.08 (his voice), 0.15 (hers) | worse; his voice dropped to 88 Hz from his real 130 |

**Why it failed.** The data had the wrong shape, not too little of it:
isolated syllables and single words, a teacher's deliberately flat
isolated-syllable voice, background music in the vocabulary videos, and two
speakers. A neural voice learns how speech runs together, and none of this
runs together.

### 2.4 Hybrid voice: real recordings where we have them

`karen_syllabary.py`. For each word or syllable of the text, it looks the
spelling up in the cuts. If a recording exists, it plays the Karen
speaker's own recording as one block; otherwise it synthesises with the
Piper voice.

- **Coverage.** With all cuts it covers 24% of Genesis 1's syllables
  (confirmed spellings only), 48% of John 3 and 36% of the Lord's Prayer.
- **Result.** This is the only intelligible voice built so far. It is
  intelligible by construction on the lesson vocabulary, and patchy
  elsewhere.
- **Default.** It uses one speaker at a time (`--speaker vocab` or `emma`),
  so a sentence does not change voice mid-word.

## 3. The sources, and exactly what each gave

All audio went into `NGAW KAREN TTS/audio/reference/` and is gitignored,
since it is other people's recordings, used to measure and to teach, not to
ship. Cuts are in `audio/cuts/<lesson>/` with one row each in
`audio/cuts/index.jsonl` (lesson, Karen spelling, IPA, phonemes, time,
whether the spelling is confirmed). Transcripts from YouTube's automatic
English captions are in `transcripts/`, and word lists in `words/`.

### 3.1 Emma Htoo, "Learn the Karen Language" (16 lessons, 3 h 14 min)

Playlist: https://www.youtube.com/playlist?list=PL4LG0veTz85MpKDP5uI6TSY_pfFjawDgn

A Karen teacher abroad, teaching Karen children to read. She says every
sound many times and shows it on screen. The best phonics source found, and
digested one lesson at a time (the user's instruction: download one, digest
it completely, then the next). Each lesson needed its own way of finding
which item she was saying at each moment, listed in the right-hand column.

| # | video | length | content | how her place was tracked | cuts (confirmed) |
|---|---|---|---|---|---|
| 1 | [o8u-xNHviDg](https://www.youtube.com/watch?v=o8u-xNHviDg) | 12:41 | the 25 consonants | contact sheets of the letter screens, by hand | 114 letter sounds |
| 2 | [xpS4YW50cCw](https://www.youtube.com/watch?v=xpS4YW50cCw) | 7:20 | the alphabet again, faster | scene changes | 150 (0: no captions to filter her English) |
| 3 | [a_0j53ep4VY](https://www.youtube.com/watch?v=a_0j53ep4VY) | 5:33 | the 9 vowels on အ | contact sheets | 58 vowels |
| 4 | [dQGvZ3G7K4U](https://www.youtube.com/watch?v=dQGvZ3G7K4U) | 3:20 | the 5 tone marks, alone | contact sheets | 27 tone samples |
| 5 | [aeKedX1LUPc](https://www.youtube.com/watch?v=aeKedX1LUPc) | 5:23 | the 5 medials (ှ ၠ ြ ျ ွ) | read only; captions refused | 0 |
| 6 | [JQo2_YcUFXY](https://www.youtube.com/watch?v=JQo2_YcUFXY) | 11:48 | every consonant with း and with ါ | text-cursor I-beam, by difference from the page | 223 (223) |
| 7 | [4xE8uZMfyyc](https://www.youtube.com/watch?v=4xE8uZMfyyc) | 8:47 | 12 words with the light first syllable | blue selection box | 74 (74) |
| 8 | [QxDGlLCV0zs](https://www.youtube.com/watch?v=QxDGlLCV0zs) | 11:27 | 14 consonants with ၢ် ၣ် ၤ (42 syllables) | cyan highlight box | 276 (276) |
| 9 | [-JwdOGfb0rE](https://www.youtube.com/watch?v=-JwdOGfb0rE) | 7:26 | 8 two-syllable words | pink cursor | 15 (15) |
| 10 | [3ugSu3RcZ8M](https://www.youtube.com/watch?v=3ugSu3RcZ8M) | 26:41 | consonants with ံ, and with း and ၢ် | screen changes in the top of the frame | 439 (439) |
| 11 | [JoGf8QF0o0g](https://www.youtube.com/watch?v=JoGf8QF0o0g) | 29:38 | **the whole six-tone paradigm** on 18 consonants, plus 5 phrases | mouse pointer, by difference from each screen's median | 236 + 10 phrases (236 + 6) |
| 12 | [AsQdO1ExyPg](https://www.youtube.com/watch?v=AsQdO1ExyPg) | 14:39 | 17 words and short phrases | the newest yellow highlight (earlier ones stay yellow) | 102 (87) |
| 13 | [ElD0-18-zxM](https://www.youtube.com/watch?v=ElD0-18-zxM) | 16:32 | 18 words, mostly with ံ | the newest yellow highlight | 246 (144) |
| 14 | [4JTFL3YZOYk](https://www.youtube.com/watch?v=4JTFL3YZOYk) | 8:54 | 10 consonants with ၢ in three tones | the newest yellow highlight | 239 (239) |
| 15 | [hKNvy6vM5RE](https://www.youtube.com/watch?v=hKNvy6vM5RE) | 11:09 | 14 words with ၢ; vegetables | the newest yellow highlight | 204 (52: ၢ and ၢၢ် unreadable at 360p) |
| 16 | [4TKOpmwpr-Q](https://www.youtube.com/watch?v=4TKOpmwpr-Q) | 12:54 | 11 consonants with ာ် ၣ် ၤ | blue selection box | 91 (91) |

**Note on numbering.** Her "Lesson 1" to "Lesson 11" are videos 6 to 16.
Videos 1 to 5 are the alphabet and vowel series.

**What she established** (full notes in `phonics-emma-htoo.md`):

- **Consonants.** The table agrees with hers for every letter. YouTube's
  English recogniser, mishearing her Karen, confirms the aspiration
  contrasts for free: က as "gah", ခ as "cut"; တ as "does", ထ as "ha"; ပ as
  "but", ဖ as "pat".
- **Vowels.** Three signs Karen reads differently from Burmese are exactly
  as the table has them: ိ is /o/, ီ is /ɔ/, ံ is /i/. And ့ is a vowel, /e/,
  not a tone. Her cuts' formants confirm it: ံ at F1 331 Hz and F2 2900 Hz,
  ိ at F1 484 Hz and F2 1161 Hz.
- **Medials.** ှ, ၠ, ြ, ျ and ွ are made from ဂ, ယ, ရ, လ and ဝ.
- **Tones.** Measured on her, one vowel, eighteen consonants (video 11,
  her middle pitch 203 Hz), in semitones from her middle:

  | form | mark | start, mid, end | length | Wade 1861 said |
  |---|---|---|---|---|
  | ကၣ် | ၣ် | +0.1, +1.2, +0.7 | 0.34 s | "falling circumflex" |
  | ကၢ် | ၢ် | +0.5, +0.6, +0.2 | 0.36 s | "heavy falling" |
  | ကၤ | ၤ | 0.0, -0.6, -1.0 | 0.41 s | "prolonged, even" |
  | ကး | း | +0.4, -0.6, -1.3 | 0.35 s | "abrupt, ordinary pitch" |
  | ကါ | none | -1.4, -1.0, -0.7 | 0.43 s | "rising" |
  | ကာ် | ာ် | -1.0, -1.3, -1.6 | 0.42 s | "abrupt, low" |

  In isolation the whole range is under three semitones, and length tells
  the tones apart as much as pitch. Video 6 adds, across all 25 consonants:
  ကါ lasts 0.53 s and ကး 0.33 s at nearly the same pitch, so "abrupt" is
  about length. These are an isolated-syllable teacher's tones; in running
  speech the movements are larger (the vocabulary speaker's words moved
  2 to 5 semitones).

### 3.2 "Learning Sgaw Karen", Stuff of Life - War & Life Project (29 short videos, 33 min)

Playlist: https://www.youtube.com/playlist?list=PLaaRoEXki_vm5rnbRl_1a5BCfJ7CmExzj

A man says an English prompt, then the Karen word, over light background
music. The Karen spelling is not always on screen. The method
(`karen_lessons.py`) matches each English prompt in the automatic captions,
takes the window after it, and cuts the loudest stretch of speech in that
window. Spellings come from the on-screen list where shown, and are checked
against the Karen Bible corpus (20 or more occurrences counts as
"confirmed").

| # | video | content | status |
|---|---|---|---|
| 1 | [CykVWgkqcBk](https://www.youtube.com/watch?v=CykVWgkqcBk) | 39 basic words and verbs | cut: 38 (17 confirmed); used for every tone fit |
| 2 | [xgYqAD_EPs8](https://www.youtube.com/watch?v=xgYqAD_EPs8) | house, eat, drink, river... (list read from the video) | audio + list; captions refused |
| 3 | [ePtaaTaHOzo](https://www.youtube.com/watch?v=ePtaaTaHOzo) | vocabulary 3 | audio only |
| 4 | [k8a1OU6daTw](https://www.youtube.com/watch?v=k8a1OU6daTw) | give, use, find, tell, ask... | cut: 13 (9) |
| 5 | [AaNO2dtulPs](https://www.youtube.com/watch?v=AaNO2dtulPs) | cry, laugh, today, month, fish, sun... | cut: 17 (8) |
| 6 | [lzH_nt___F0](https://www.youtube.com/watch?v=lzH_nt___F0) | love, flower, tree, hand, head... | cut: 18 (11) |
| 7 | [CgydSZ_WDIQ](https://www.youtube.com/watch?v=CgydSZ_WDIQ) | days and months | audio only |
| 8 | [z7EWbNnZgs4](https://www.youtube.com/watch?v=z7EWbNnZgs4) | vocabulary 8 | audio only |
| 9 | [F8_08g4d1x4](https://www.youtube.com/watch?v=F8_08g4d1x4) | numbers | not downloaded |
| 10 to 11 | [TImf7wWJwZQ](https://www.youtube.com/watch?v=TImf7wWJwZQ), [8ICKKyRDraw](https://www.youtube.com/watch?v=8ICKKyRDraw) | vocabulary | audio only |
| 12 to 13 | [HVtyr6iOTM8](https://www.youtube.com/watch?v=HVtyr6iOTM8), [h00sPQg7DoM](https://www.youtube.com/watch?v=h00sPQg7DoM) | **conversations 1 and 2** | 12 audio only; 13 not downloaded |
| 14 to 17 | [cYCu9pP0Xns](https://www.youtube.com/watch?v=cYCu9pP0Xns), [ujPIEXCtI7M](https://www.youtube.com/watch?v=ujPIEXCtI7M), [QoJk-A4dk0E](https://www.youtube.com/watch?v=QoJk-A4dk0E), [BcurqMg3Jtw](https://www.youtube.com/watch?v=BcurqMg3Jtw) | vocabulary 12 to 15 | 15 and 16 audio only |
| 18 | [EH3o7671bH4](https://www.youtube.com/watch?v=EH3o7671bH4) | **Christian phrases** | not downloaded |
| 19 to 23 | [b-8LGEzA-y0](https://www.youtube.com/watch?v=b-8LGEzA-y0), [35Av3ys_BIY](https://www.youtube.com/watch?v=35Av3ys_BIY), [hXk0roVqSwo](https://www.youtube.com/watch?v=hXk0roVqSwo), [Gq3DJPOI518](https://www.youtube.com/watch?v=Gq3DJPOI518), [I4RD4-spfa4](https://www.youtube.com/watch?v=I4RD4-spfa4) | vocabulary 16 to 20 (22 is phrases: "Where are you going?", "I am hungry", "Can you help me?") | 20 and 21 audio only; 22 audio + captions |
| 24 to 29 | [yDeQELdfogY](https://www.youtube.com/watch?v=yDeQELdfogY), [TVPqnQZ_3zI](https://www.youtube.com/watch?v=TVPqnQZ_3zI), [ovOUEAz2JHs](https://www.youtube.com/watch?v=ovOUEAz2JHs), [eMqHUAydGUE](https://www.youtube.com/watch?v=eMqHUAydGUE), [eD5XriMcAOk](https://www.youtube.com/watch?v=eD5XriMcAOk), [0C8_ZCQuF5k](https://www.youtube.com/watch?v=0C8_ZCQuF5k) | head, rooms, school, verbs in the 1st person, daily activities, daily routines (picture posters, no Karen on screen) | 24, 25, 27 audio + captions; spellings still needed |

The same channel has the two Scripture readings the session started from:

- The Lord's Prayer in Karen, [uZecdbDTPac](https://www.youtube.com/watch?v=uZecdbDTPac) (3:00; downloaded as `lords_prayer.wav`, not yet cut).
- A shorter reading, [R5gY33TkUy0](https://www.youtube.com/watch?v=R5gY33TkUy0) (1:00).
- Matthew 6 in Karen and English, [sZ3RXZL2_tw](https://www.youtube.com/watch?v=sZ3RXZL2_tw).

### 3.3 Found at the end, not yet used

- **"Reading KAREN Bible"**,
  https://www.youtube.com/channel/UCFvX8VtEM-czN-2mwP5TAPA: 1,190 videos, 102
  hours, one per chapter, Genesis to Revelation (for example Genesis 1,
  [ofrVQ5IKk6I](https://www.youtube.com/watch?v=ofrVQ5IKk6I), 6:51). This is
  **connected read speech of a known text**, the one thing every failed
  fine-tune lacked. See the first suggestion below.
- **Pah Karen channel**: English, Burmese and Karen side by side, about 30
  minutes each: [7Kj-CUdK8DI](https://www.youtube.com/watch?v=7Kj-CUdK8DI),
  [dxoR179Xv8o](https://www.youtube.com/watch?v=dxoR179Xv8o),
  [2Pe5yLVzQLw](https://www.youtube.com/watch?v=2Pe5yLVzQLw). Also
  English-to-Karen conversation:
  [23kTdKERBTE](https://www.youtube.com/watch?v=23kTdKERBTE),
  [UDNowE99Tto](https://www.youtube.com/watch?v=UDNowE99Tto),
  [KO_2XmHPu9o](https://www.youtube.com/watch?v=KO_2XmHPu9o). **Burmese and
  Karen said by the same speaker**, which is useful to a Burmese-to-Karen
  adaptation as paired data.
- **Resources in the Karen language**: Karen Alphabet
  [NFHM3JuKWVE](https://www.youtube.com/watch?v=NFHM3JuKWVE), Karen Vowels
  [gG3AyM0VZ9s](https://www.youtube.com/watch?v=gG3AyM0VZ9s). A second
  teacher's alphabet and vowels, to check Emma's against.
- **In `data-plan.md`**: the Sagaw Karen ASR dataset (8.8 hours of
  untranscribed news audio), Bloom Library Karen talking books, and VOA
  Myanmar Voices (8,200 hours of Burmese).

## 4. Suggestions for the next session (the Burmese adaptation)

In order of expected value:

1. **Check the "Reading KAREN Bible" channel first.**
   - **Is it Mason's text?** Download one chapter only, Genesis 1
     ([ofrVQ5IKk6I](https://www.youtube.com/watch?v=ofrVQ5IKk6I)), and
     force-align it against Mason's Genesis 1 from `sources/ksw-mason/`
     (run `scripts/karen_corpus.py` to rebuild `verses.jsonl`). The MMS
     aligner in data-plan.md takes romanized text, and `karen_phonemes.py`
     gives an ASCII spelling. If Mason's Genesis 1 aligns well, the channel
     is 102 hours of transcribed Karen. If not, find which Karen Bible it
     reads (the 1954 revision, the KBC Bible); Mason's text may be close
     enough to align anyway.
   - **Is it one reader?** Cluster a few chapters by speaker embedding.
   - **Who owns it?** Ask the channel before training anything that ships.
     Use it for research until then.

   If all three answers are good, this replaces the studio recordings in
   stage 3 of data-plan.md, or at least stage 2.
2. **Use the measurements, not just the audio.** The tone table and the
   vowel table say where Karen differs from Burmese. That tells a Burmese
   model what it must unlearn: the vowels ိ ီ ံ ့ are read differently from
   Burmese, and there are twelve letters Burmese lacks. `karen_phonemes.py`
   is the normalized, regular transcription for training; one symbol set
   for both languages would let the model share what is shared.
3. **Use `karen_voice_test.py` as the scorecard.** It scores any engine
   against a Karen speaker, word by word, with pitch correlation and
   length, and writes an A/B file for listening. The base Vietnamese voice
   scored 0.55 on the vocabulary speaker. Beating that number is the first
   bar for a Burmese-derived voice, and the user's ear is the second.
4. **Emma's lessons are syllable-level ground truth, not training speech.**
   Her six-tone paradigm (video 11) and her 42-syllable table (video 8) are
   ideal for testing whether a voice gets the tones in the right order and
   length. Do not train a voice on them. That is what failed here.
5. **Pah Karen's Burmese and Karen from the same speaker** is paired data
   that suits a Burmese-to-Karen adaptation.
6. **Finish the loose ends if useful.** Captions for vocabulary 2, Emma 2
   and Emma 5 were refused (HTTP 429); retry them one at a time, with pauses.
   Vocabulary 24 to 29 need their Karen spellings typed in from a Karen
   speaker. The Lord's Prayer recording is downloaded but not cut.

## 5. Practical notes for this machine

- **YouTube rate-limits the caption endpoint.** Audio and video downloads
  kept working; automatic captions returned HTTP 429 after a handful of
  requests and stayed refused for hours. Fetch one lesson at a time. The
  user asked for that anyway.
- **Piper training on Windows needs fixes.** The pip wheel (piper-tts 1.4.2)
  ships without its training package. It was dropped in from the
  piper1-gpl source with these changes:
  - The Cython monotonic-alignment extension is rewritten in numba, since
    MSVC here has no Windows SDK headers.
  - The legacy ONNX exporter is used (`dynamo=False`); torch.export fails
    on the spline transform.
  - The published Vietnamese checkpoint is re-saved without its pickled
    PosixPath objects and old hyperparameters (`*.clean.ckpt`).
  - Fine-tuning uses `--model.warmstart_ckpt`, not `--ckpt_path`.
  - `num_workers` is 4 (at 0 the GPU idled at a quarter).
  - Cuts must be at least 0.5 s (shorter ones crashed the feature loss at
    epoch 80).
- **Windows CUDA memory spills into system RAM.** Long GPU jobs slowed
  fivefold when that happened. Release the cache between items.
- **Everything is under `NGAW KAREN TTS/`.** `README.md` is the map,
  `data-plan.md` the plan, `phonics-emma-htoo.md` the lesson notes, and
  `reports/` the measurements. The models are in `models/piper/`
  (gitignored): `karen-v1.onnx`, `karen-v2.onnx` and the Vietnamese base
  voices.
