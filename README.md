# eBible Translation

A fresh English translation of the Bible from the original Hebrew, Aramaic, and
Greek, produced by a locally hosted open-weight language model. No English
translations are consulted at any stage.

## Source texts

| Text | Source | License |
|---|---|---|
| Hebrew/Aramaic OT | Westminster Leningrad Codex via [openscriptures/morphhb](https://github.com/openscriptures/morphhb) | Base text public domain; morphology CC BY 4.0 |
| Greek NT (primary) | [SBLGNT](https://github.com/LogosBible/SBLGNT) critical text | CC BY 4.0 |
| Greek NT (consulted) | [Robinson–Pierpont Byzantine](https://github.com/byztxt/byzantine-majority-text) | Public domain |
| Greek OT (reference only) | Septuagint, Swete's edition (1901–1909) via [First1KGreek](https://github.com/OpenGreekAndLatin/First1KGreek/tree/master/data/tlg0527) | CC BY-SA 4.0 |

License texts, copyright and public-domain notices for each source, with the
upstream snapshots they were verified against, are recorded in [LEGAL.md](LEGAL.md).

**The Septuagint is a reference, not a source.** Wherever the Hebrew or
Aramaic exists it is the only text being translated. `scripts/add_lxx.py
--fetch` downloads Swete's Greek Old Testament (37 books; Ecclesiastes is not
in the corpus) and writes each verse's Greek into the normalized JSON as
`lxx` beside the Hebrew, aligned by chapter and verse with the standard block
mappings where the Greek numbering diverges (Psalms, Jeremiah, Ezra–Nehemiah
as 2 Esdras, Daniel in Theodotion's version); about 96 % of Old Testament
verses align. The prompt appends it after the source text in a block marked
*reference only, not source text*: the model may consult it at a genuinely
ambiguous, rare or damaged Hebrew reading and must say so in the notes if it
follows the Greek; it must not translate from it or let its wording shape a
clear Hebrew verse. The reader and dashboard show it as a **Septuagint** tab
and as an **LXX** row in Compare, for the reader's comparison. `consult_lxx:
false` in `config.json` drops it from prompts (and `num_ctx` can go back to
16384). Swete's text comes from corrected page scans and still carries
occasional artefacts; treat it as a witness, not an edition. It would become
source material only for books that have no Hebrew, which this project does
not yet include.

The Greek base text is **SBLGNT**, with the Byzantine text available for
consultation at divergences. The OT keeps Masoretic chapter/verse divisions
(so e.g. Joel has 4 chapters and some Psalm numbers shift by one against
English convention).

## Model

Runs against any Ollama endpoint; configured in `config.json`.

- **Primary: `qwen3:32b`** (~20 GB) — fits alongside the avatar's vLLM and,
  in the Genesis 1 head-to-head (`site/compare.html`), tracked the Hebrew more
  closely with fewer familiar-English echoes, at 3× the speed.
- **Available: `llama3.3:70b`** (Q4_K_M, ~43 GB) — smoother literary cadence
  but echoes the ESV/KJV; needs the avatar's vLLM stopped
  (`docker stop nemoclaw-vllm` / `docker start nemoclaw-vllm`). Candidate for
  poetry/prophets spot passes.

**Running it on the 5090 PC:** see [PORT.md](PORT.md) — setup checklist and
the Tailscale shared-folder options (~5× faster there).

## Pipeline

```
scripts/normalize.py  [books...]        sources -> sources/normalized/*.json
scripts/translate.py  Gen 1-3           translate chapters into English (resumes; --force to redo)
scripts/translate.py  Gen 1-3 --lang zh ... into Chinese (es, ja, th; a comma list; or all)
scripts/translate.py  --all [--lang all] the whole Bible, canonical order
scripts/translate.py  --all --lang all --keep-going   ...and never stop on an error:
                                        wait, retry, resume — until done or Ctrl-C
scripts/add_lxx.py    [--fetch]         attach the Septuagint to the normalized OT
scripts/verify.py     [--lang zh] [Gen [1-3]]  flag missing/dup verses, untranslated
                                        text, truncation, name inconsistencies
scripts/build_site.py                   rebuild site/index.html reader
scripts/live.py                         live dashboard on :8766 — same driver,
                                        tokens stream to the browser as they arrive
```

`start_dashboard.cmd` (double-click, or the "eBible dashboard" Desktop shortcut)
runs `scripts/app.py`: the dashboard as a desktop app in its own window, no
browser, console, Claude Code or IDE needed. It serves `live.py` in-process
(or attaches to a dashboard already on :8766, e.g. one started with
`python scripts\live.py`) and shows it with pywebview (`pip install pywebview`,
uses the system WebView2; without it Edge's app mode is used). Closing the
window stops the server it started — it asks first if a translation is
running. Output from a windowless start goes to `logs/app.log`.
The **read / translate** toggle in the header turns the window into the
reader, rebuilding `site/index.html` first whenever translations are newer
than it, and back. In translate mode the side panel (translations, session,
books) can be moved to either side or hidden with the tab at its edge to
give the text the whole width. `start_reader.cmd` (or `pythonw scriptspp.py
--reader`) opens just the reader — no server, it is one offline file.

### Word study in the reader (morphology)

`scripts/build_morph.py` reads the STEPBible data (CC BY 4.0, cloned with
`git clone --depth 1 https://github.com/STEPBible/STEPBible-Data sources/STEPBible-Data`)
and aligns every Hebrew, Aramaic and Greek word of the source text with its
lemma tag, morphology, gloss and a brief lexicon entry, writing `site/morph/`
(one file per book, loaded on demand; `logs/morph_report.md` shows the
alignment, 99.9% of 442,835 words). In the reader: click any original-language
word for its parsing and lexicon entry; *interlinear* puts gloss and code under
every word; *all occurrences* is a concordance of that lexeme; *grammar
search* finds words by form (e.g. every Piel participle, every aorist passive
in a book).

### Cross-references and parallels

`scripts/build_refs.py` writes two more layers into `site/morph/`: the
OpenBible.info cross-reference set (CC BY 4.0, ~341,000 voted links from the
public-domain *Treasury of Scripture Knowledge*; download
`https://a.openbible.info/data/cross-references.zip` into `sources/openbible/`),
and parallel passages computed from the word tags themselves — verses in the
Gospels, in Samuel–Kings–Chronicles with Isaiah, Jeremiah, Psalms and Micah,
and in the Torah, matched by the rare lexemes they share. In the reader: click
a verse number for its cross-references and parallels; the *parallels* tab
lays the chapter out in columns beside the books it parallels.

### Our own lexicon

`scripts/build_lexicon.py` writes a lexicon of its own: for each lexeme the
concordance supplies a sample of occurrences spread across the canon, with the
form and parsing in each, and the model writes the entry — senses with anchor
verses, how the usage shifts, idioms, near-synonyms, what is uncertain. No
published dictionary is supplied to it. Entries append to
`targets/lexicon/entries.jsonl` (resumable; `--limit`, `--tag`, `--min-count`)
and `--pack` writes `site/morph/lexx.js`, shown in the reader's word popup
under *This project's entry*. Roughly 7 s per lexeme: about 8 GPU hours for the
3,861 lexemes occurring ten times or more, 33 hours for all 16,967.

### Places and maps

`scripts/build_places.py` writes `site/morph/places.js` from the OpenBible.info
geocoding data (CC BY 4.0; the 2007 release — the newer one mixes in
OpenStreetMap geometry under a share-alike licence) and a base map clipped from
Natural Earth (public domain). The reader's *places* tab shows the places a
chapter mentions on a vector map that is drawn offline — no tiles, no map
service — with zoom, pan and a list of the places with their verses; place
names also appear in the verse panel. 1,111 located places over 4,812 verses.

### Text notes (apparatus)

`scripts/build_apparatus.py` writes `site/morph/app_*.js` from the same
STEPBible data: for Greek, which of the eight printed editions carry each
reading and where they differ in spelling; for Hebrew, the scribal Qere against
the written Ketiv and the meaning and spelling variants. They appear under
*Text notes* when a verse number is clicked. This is an apparatus of editions,
not of manuscripts — no manuscript sigla are asserted, because no openly
licensed manuscript apparatus is available.

### Clause roles, participants and semantic domains (Greek)

`scripts/build_syntax.py` reads the MACULA Greek dataset for the SBLGNT (CC BY
4.0, `sources/macula/greek.tsv`) and writes `site/morph/syn_*.js` and
`domains.js`: for all 137,741 Greek words, the role in the clause, the word
class, the semantic-domain number, and for pronouns the word they refer back
to. The word popup then says what a word is doing in its clause, links a
pronoun to its antecedent (which is highlighted when you jump to it), and lists
the other words sharing its semantic domain. Domain titles are not used: they
are copyrighted, so the grouping is shown by its members instead.

### Chronology

`scripts/build_chronology.py` writes `site/morph/chron.js`: every explicit
chronological statement in the text (ages, reign lengths, "in the Nth year
of X", spans), extracted by pattern from our own English translation and shown
with its verse, plus a hand-entered table of 17 events dated from Assyrian,
Babylonian, Persian and Roman records. The reader's *chronology* tab shows the
chapter's statements, the rest of the book's, and the anchors. Nothing is summed
into a date: no chronological system is asserted, and no copyrighted chronology
is used.

### Target languages

The pipeline translates into several languages from the same sources; each
target is fully independent (its own run, outputs, verifier report) and is
described once in `TARGETS` in `scripts/books.py`:

| code | language | prompt rules | glossary + names | output |
|---|---|---|---|---|
| `en` | English | `prompts/targets/en.txt` | `targets/en/` | `output/en/` |
| `zh` | Chinese (Simplified) | `prompts/targets/zh.txt` | `targets/zh/` | `output/zh/` |
| `es` | Spanish | `prompts/targets/es.txt` | `targets/es/` | `output/es/` |
| `ja` | Japanese | `prompts/targets/ja.txt` | `targets/ja/` | `output/ja/` |
| `th` | Thai | `prompts/targets/th.txt` | `targets/th/` | `output/th/` |
| `yue` | Cantonese, written colloquial (Traditional characters) | `prompts/targets/yue.txt` | `targets/yue/` | `output/yue/` |
| `nan` | Taiwanese Hokkien, Han-character prose (MOE characters) | `prompts/targets/nan.txt` | `targets/nan/` | `output/nan/` |
| `hak` | Hakka, Han-character prose (Sixian, MOE characters) | `prompts/targets/hak.txt` | `targets/hak/` | `output/hak/` |
| `vi` | Vietnamese | `prompts/targets/vi.txt` | `targets/vi/` | `output/vi/` |
| `ko` | Korean | `prompts/targets/ko.txt` | `targets/ko/` | `output/ko/` |
| `fa` | Persian (right-to-left) | `prompts/targets/fa.txt` | `targets/fa/` | `output/fa/` |
| `tr` | Turkish | `prompts/targets/tr.txt` | `targets/tr/` | `output/tr/` |
| `id` | Indonesian | `prompts/targets/id.txt` | `targets/id/` | `output/id/` |
| `ms` | Malay | `prompts/targets/ms.txt` | `targets/ms/` | `output/ms/` |
| `ja-easy` | やさしい日本語 (Easy Japanese: short sentences, furigana on all but the most basic kanji) | `prompts/targets/ja-easy.txt` | `targets/ja-easy/` | `output/ja-easy/` |

Easy Japanese writes furigana as `{漢字|かんじ}`; the reader and dashboard
render it as ruby text, the markdown output as 漢字（かんじ）. Persian is
right-to-left: `"dir": "rtl"` in `TARGETS` sets the direction of its columns.

`prompts/system_prompt.txt` is the language-neutral core (the absolute rules,
the notes format, the output shape); the per-target file supplies STYLE and
TERMINOLOGY in that language (how YHWH, Elohim, Kyrios, Christos are rendered,
register, punctuation). Glossaries and name tables are seeded with the divine
names and the most frequent people and places and grow as each translation
proceeds. To add a language: one line in `TARGETS`, one rules file, one
glossary, one name table.

### Original languages

One table, `LANGS` in `scripts/books.py`, describes the three source languages
(code, name, writing direction, script, source edition) and two helpers,
`verse_lang` / `chapter_lang`, classify normalized verses: `hbo`, `arc`, `grc`,
or `mixed` for chapters that switch (Daniel 2, Ezra 4, 6, 7, Jeremiah 10). Everything that
labels or renders original text goes through it:

- `translate.py` names the source language in each prompt from it;
- `build_site.py` embeds the original text of all 1,189 chapters (about 7 MB,
  still one offline file), so every book and chapter is navigable before it is
  translated; each chapter gets a tab row — **Hebrew / Aramaic / Greek**, one
  tab per translation that exists (English, 中文, Español, 日本語, ไทย),
  **Side by side** (original next to the selected translation) and
  **Compare** (every translation under each verse) — with right-to-left
  layout for Hebrew script and a per-verse tag wherever a chapter mixes Hebrew
  and Aramaic. A header menu picks the translation language for reading,
  search and progress counts. Untranslated chapters show the original;
- `live.py` shows the same tabs while a chapter is being translated, so each
  verse appears next to its source as the model writes it. While idle it is a
  browser too: pick a book in the sidebar or the Run box, step through
  chapters with ◀ ▶ (or arrow keys) or the chapter strip, and read the
  original alongside any translation that already exists.

**Keep going until Stop.** In the dashboard choose *All books* and a target
(or *All languages*) and press Start: the run works book by book through the
whole Bible — with *All languages*, the whole Bible in English first, then
Chinese, Spanish, Japanese, Thai — skipping chapters that exist, and treats
any failure (Ollama restarted,
a bad response) as a pause: it reports, waits with backoff, and retries the
same book until it goes through. Only Stop, or the end of the Bible, ends it.
The same behaviour from the terminal is `translate.py --all --lang all
--keep-going`.

**Loop guard.** A model can fall into repeating itself and never stop —
2 Samuel 17:28, whose Hebrew lists roasted grain twice, produced "and barley,
and meal, and roasted grain, and barley, and meal, and roasted grain, …" until
the context filled. The driver now watches the output as it streams: the moment
the tail is one stretch of text repeated back to back four or more times (at
least 150 characters, so refrains like "holy, holy, holy" pass), it drops the
connection, which makes Ollama stop, and retranslates the chapter with a note
about where it looped and stronger anti-repeat sampling
(`loop_retry_options` in `config.json`; default `repeat_penalty` 1.15,
`presence_penalty` 1.0). Up to `max_attempts` (default 3) tries cover loops and
missing/extra verses alike; the best attempt is kept, a still-looping verse is
cut back to its first pass and marked `[…]`, and the chapter is logged with
`"loop"` and a WARN status so `verify.py` (which flags `LOOP` on any such verse)
and the dashboard show it. `num_predict` (default 8192 tokens, about three
times the longest chapter) caps a runaway that nothing else stops. Optional
`repeat_penalty`, `repeat_last_n`, `presence_penalty`, `frequency_penalty` and
`seed` in `config.json` are passed through to every call.

Chapter memory: each prompt includes the previous chapter's translation for
continuity. Logs in `logs/translate.jsonl` (timing + token counts per chapter,
with the target language); verifier reports in `logs/verify_<lang>.md`.

## Reader / search (site/index.html)

`scripts/build_site.py` embeds every translated chapter into a single
self-contained HTML file — full-text search, a reference finder
("Genesis 2:7", "1 sam 3:10"), and a chapter reader. No server, no network:
open the file in any browser, or as its own window with `start_reader.cmd`
(the dashboard also serves it at <http://localhost:8766/reader>).

### Android app (planned)

The reader is deliberately one offline HTML file so it can be wrapped as an
APK with no code changes:

1. **Capacitor** (recommended): `npx cap init && npx cap add android`, copy
   `site/index.html` into the webDir, build in Android Studio or with Gradle.
2. Minimal hand-rolled WebView project loading the file from `assets/` —
   smallest APK, no framework.

Building either requires the Android SDK; not installed on the Spark yet.

## Status

- [x] Sources fetched and normalized (66 books, 31,102 verses)
- [x] Prompt, glossary, name table, driver, verifier, site builder
- [x] Genesis 1–3 translated with llama3.3:70b and verified (0 flags)
- [ ] Side-by-side comparison with the claude.ai "Claude Fable" rendering
- [ ] Narrative books
- [ ] Poetry and prophets (heavier review budget)
- [ ] Aramaic sections of Daniel/Ezra in their own run
