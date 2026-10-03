# S'gaw Karen TTS: Data Plan

As of 2026-09-27. Companion to the [S'gaw Karen Text-to-Speech Engine: Design Document](https://claude.ai/code/artifact/6d606add-133e-4fae-8640-03c4c9d87119).

## Summary

No open, transcribed, single-speaker [S'gaw Karen](https://en.wikipedia.org/wiki/S%27gaw_Karen_language) (`ksw`) speech corpus exists, so the core of the dataset must be our own studio recordings. Open data still helps: a large public-domain Burmese corpus for pretraining, untranscribed Karen news audio for adaptation, and possibly aligned Karen talking books.

Training uses three stages, from largest and least matched to smallest and best matched:

1. **Pretrain** a Burmese-script VITS model on transcribed Burmese speech.
2. **Adapt** it to the sound of Karen using Karen audio (untranscribed or lightly transcribed).
3. **Fine-tune** on 5–10 hours of clean studio recordings from one native Karen speaker.

## What has been tried (2026-09-27)

Before this plan, a shortcut was tried: borrow a voice that already speaks
a six-tone language and teach it Karen. It did not work well enough.

- **Vietnamese adaptation did not work.** A Piper voice trained on
  Vietnamese read Karen from our phonetic notation, with Karen's six tones
  mapped onto Vietnamese ones and the mapping fitted to recorded Karen
  speakers. Every word is audible, but to a listener it is Karen with a
  heavy Vietnamese accent, and the judgement was that native speakers
  would not follow it. Fine-tuning that voice on Karen lesson recordings
  made it worse, not better: 0.8 minutes of one speaker gave slurred
  speech, and 8.5 minutes of two speakers (a teacher's isolated syllables
  and a vocabulary list read over music) dropped the pitch-shape match with
  the speaker from 0.55 to 0.08-0.15. Isolated syllables and words over
  music are the wrong shape of data for a neural voice, however many.
- **A retuned Burmese voice** (Meta's `mms-tts-mya`, Karen respelled into
  Burmese and each syllable's pitch reshaped to its Karen tone) was tried
  first and scored lower than the Vietnamese one, but it was never trained
  on Karen at all. Burmese shares the script and most consonants, which is
  why this plan starts from Burmese; the next attempt adapts Burmese rather
  than Vietnamese.
- **What does work:** the hybrid voice that plays real Karen recordings for
  every word it has and synthesises only the rest (`karen_syllabary.py`);
  and the measurements, which are reusable for any engine: the full
  spelling-to-sound table (`karen_phonemes.py`) confirmed against Emma
  Htoo's course, and the six tones measured on one speaker
  (`phonics-emma-htoo.md`).
- **Open question answered:** there is no `facebook/mms-tts-ksw`
  checkpoint (checked on Hugging Face; the MMS-TTS collection has no Karen
  language of any kind).

## Available open data

| Dataset | Language | Size | Transcripts | License | Use in this project |
| --- | --- | --- | --- | --- | --- |
| [Sagaw Karen ASR](https://huggingface.co/datasets/freococo/sagaw_karen_asr) | S'gaw Karen | 8.8+ h, 2–15 s clips | No | CC0 (uploader's claim; see risks) | Stage 2 adaptation; source of anchor clips to hand-transcribe |
| [Bloom Library talking books](https://bloomlibrary.org/language:ksw) | S'gaw Karen | Unknown; check in browser | Yes, sentence-aligned | Varies per book | Possible clean aligned Karen hours for stage 2 or 3 |
| [VOA Myanmar Voices](https://huggingface.co/datasets/freococo/voa_myanmar_voices) | Burmese | ~8,200 h, 20 s FLAC clips | Yes | Public domain (U.S. government work) | Stage 1 pretraining |
| [Myanmar Written Corpus](https://huggingface.co/datasets/freococo/myanmar-written-corpus) | Burmese | ~10M sentences | Text only | CC0 | Testing the Unicode normalizer |

Not found: a S'gaw Karen dataset on [Mozilla Common Voice](https://commonvoice.mozilla.org), or any existing open Karen TTS model.

## Our own recordings (primary dataset)

| Item | Target |
| --- | --- |
| Speakers | 1 native speaker, dialect agreed with the community |
| Amount | 5–10 h, about 3,000–6,000 clips |
| Clip length | 2–10 s |
| Recording format | 44.1 or 48 kHz, 24-bit WAV; resampled to 22.05 kHz for training |
| Held-out test set | 200 sentences, never used in training |
| Consent | Written consent and a clear usage license from the speaker |

### Recording script

- Build 3,000–6,000 sentences from Karen news, church material and the S'gaw Karen test Wikipedia on Wikimedia Incubator.
- Select sentences to cover every consonant, vowel and tone mark.
- Include numbers, dates, times, common abbreviations and loanwords.
- Have a native speaker proofread every sentence before recording.

### Recording protocol

- Quiet, treated room; one USB condenser mic at a fixed distance.
- Sessions of at most 2 hours; same time of day where possible.
- Neutral, natural reading style (not a sermon or news-reading style).
- Re-record any line with a misread, stumble or background noise.

## Processing pipeline

1. **Convert and normalize text.** Convert any legacy-font text to Unicode, apply NFC, and run the project text normalizer.
2. **Clean audio.** Trim silence, normalize loudness, and remove clips with music, noise or overlapping speakers.
3. **Segment and align.** Split long audio into 2–10 s clips and align text to audio with the [MMS](https://huggingface.co/docs/transformers/model_doc/mms) forced aligner.
4. **Filter.** Drop clips whose alignment score or duration-to-text ratio falls outside normal ranges.
5. **Package.** Store clips with a `metadata.csv` of `file_id|normalized_text`, versioned per release.

### Extra steps for the [Sagaw Karen ASR](https://huggingface.co/datasets/freococo/sagaw_karen_asr) audio

- Run voice activity detection to remove music-only and jingle clips.
- Cluster by speaker embedding to find the largest consistent single voice (for example a regular news anchor).
- Hand-transcribe 30–60 minutes of that voice with a native speaker as optional extra fine-tuning data.

## Training data by stage

| Stage | Data | Goal |
| --- | --- | --- |
| 1. Pretrain | [VOA Myanmar Voices](https://huggingface.co/datasets/freococo/voa_myanmar_voices) (subset of a few hundred hours is likely enough) | Learn Burmese-script text-to-sound mapping |
| 2. Adapt | [Sagaw Karen ASR](https://huggingface.co/datasets/freococo/sagaw_karen_asr) audio, any [Bloom talking books](https://bloomlibrary.org/talking-books), hand-transcribed anchor clips | Learn Karen sounds and tones |
| 3. Fine-tune | 5–10 h studio recordings | Produce one clean, natural Karen voice |

If an [MMS-TTS](https://huggingface.co/facebook/mms-tts) `ksw` checkpoint turns out to exist, it replaces stages 1 and 2 as the starting point.

## Risks

| Risk | Mitigation |
| --- | --- |
| Rights to rebroadcast news audio are unclear despite the CC0 label | Confirm with PVTV before any commercial use; keep it out of the final fine-tune if in doubt |
| Burmese pretraining teaches Burmese pronunciation of shared letters | Keep stage 1 short; rely on stages 2–3 to override it |
| Bloom book licenses differ | Use only books with licenses that allow derivative works |
| No confirmed voice speaker | Recruit early through Karen community groups, churches and diaspora organizations |

## Open questions

- [ ] How many [S'gaw Karen Bloom books](https://bloomlibrary.org/language:ksw) have audio, and under which licenses?
- [x] Does a `facebook/mms-tts-ksw` checkpoint exist? No (checked 2026-09-27).
- [ ] Which dialect will the voice represent?
- [ ] Budget for recording time, transcription and GPU hours.

## Sources

- Design document: https://claude.ai/code/artifact/6d606add-133e-4fae-8640-03c4c9d87119
- Sagaw Karen ASR dataset: https://huggingface.co/datasets/freococo/sagaw_karen_asr
- VOA Myanmar Voices dataset: https://huggingface.co/datasets/freococo/voa_myanmar_voices
- Myanmar Written Corpus: https://huggingface.co/datasets/freococo/myanmar-written-corpus
- Bloom Library, S'gaw Karen books: https://bloomlibrary.org/language:ksw
- Bloom Library talking books: https://bloomlibrary.org/talking-books
- MMS-TTS models: https://huggingface.co/facebook/mms-tts
- MMS documentation (includes forced alignment): https://huggingface.co/docs/transformers/model_doc/mms
- Mozilla Common Voice: https://commonvoice.mozilla.org
- S'gaw Karen language (Wikipedia): https://en.wikipedia.org/wiki/S%27gaw_Karen_language
