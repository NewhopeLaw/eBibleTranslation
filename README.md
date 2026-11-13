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
- **Per language: `lang_models`** — a language can be written by another
  model than the rest. `qwen3:32b` wrote Cantonese and Mandarin when asked
  for Hakka, so `hak` goes to `qwen3.5:35b-a3b`. `translate.py --model <name>`
  overrides both for one run; `mend.py` and `build_ui.py` follow the same
  choice. The dashboard's model select changes only `model`.

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
scripts/translate.py  John 1 --lang hak --model gemma3:27b   ...with another model for this run
scripts/hakka_from_zh.py John 1         Hakka from our Mandarin: word replacement (targets/hak/replace.json
                                        + the MOE Sixian dictionary), then the model mends what is left
scripts/hakka_speech.py  John 1         read a Hakka chapter aloud (FormoSpeech voice) -> audio/hak/
scripts/taiwanese_from_zh.py John 1     Taiwanese the same way (targets/nan/replace.json + the MOE Taiwanese
                                        dictionary); both run on scripts/from_zh.py
scripts/taiwanese_speech.py  John 1     read a Taiwanese chapter aloud (ga642381's SuíSiann voice) -> audio/nan/
                                        (all four are TTS processing jobs on the dashboard; --all for the lot)
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
and in the Torah, matched by the rare lexemes they share. In the reader: take
a verse and press **Notes** for its cross-references and parallels; the
*parallels* tab lays the chapter out in columns beside the books it parallels.

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
*Text notes* in a taken verse's **Notes**. This is an apparatus of editions,
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

### Our own lexeme inventory

`scripts/build_lexemes.py` grows a dictionary-word list from the text instead of
inheriting one. Every distinct form — 61,537 Hebrew and Aramaic, 19,357 Greek —
goes to the local model in the verse where it first stands; the model gives the
dictionary form, part of speech, gloss and (for Hebrew) the root, and forms that
answer with the same dictionary form become one lexeme, numbered in order of
first appearance (`eH00001`, `eG00001`). About one second per form, so roughly a
day for the whole text, resumable throughout.

`--score` measures it against the reference tagging we already hold: on a
300-form sample spread across frequencies, 95.6% of tokens fell in a lexeme
whose members share the same reference tag (`logs/lexeme_report.md`). The
reference is a yardstick only — nothing from it enters our inventory.

### Search index

`scripts/build_index.py` maps every word of every text to the verses it stands
in: 1.69 million postings over the Hebrew, the Greek, the Septuagint and each
translation, delta-encoded and loaded per language on demand. Vowel points and
accents are folded, so a search matches what a reader types, and the languages
that do not space their words are indexed by short character runs. The reader
uses it to jump straight to the candidate verses, which takes about 10 ms
instead of scanning the whole text; a language with no index yet falls back to
scanning and says so.

The postings are built in code, not by the model — a list of occurrences has to
be exact. The model's part is the layer above: grouping the forms of a word so
that a search for one form finds the others.

### Search by meaning, on the phone

`scripts/build_vectors.py` gives every verse a vector and writes a table of
vectors for the word pieces they are built from; the head of that script says
how and why. The reader cuts what was typed into the same pieces, adds up their
vectors and shows the verses nearest it as **Verses like this**, so "the man
thrown into the den of lions" reaches Daniel 6 and a Thai reader typing "do not
worry about tomorrow" reaches Matthew 6:34, with no word in common. In a browser
it is arithmetic in the page, over a table of what each word piece means alone.
In the Android app it is the model itself: `scripts/build_encoder.py` cuts
multilingual-e5-small down to this project's vocabulary, stores it as int8 and
embeds every verse with it, and the app runs it with ONNX Runtime and hands the
page verse numbers. The model reads the question whole, which matters most in
Thai, where the table found the passage for two questions of eight and the
model for five. Either way it only ever picks verses, so what is shown is the
reader's own text, and a question nothing is near (a single common word, a
typing slip) gets no such section rather than twelve strays. Run
`build_encoder.py` before `build_apk.py`; the APK carries the model where it
was built and the table where it was not.

**Stories, not only verses.** A reader describes a story, and a verse is one
sentence of it. `build_encoder.py` also embeds the chapter themes' plain
descriptions of each run of verses ("Daniel's refusal of the royal diet",
Daniel 1:8-16), and in the app a description nearer the question than any of
its verses lifts that run as a block. In English that took the right passage
first from 37 of 100 hand-written questions to 44. The descriptions are in
English, and Thai, Spanish and Chinese questions gained nothing from them, so
`scripts/translate_stories.py` puts them into each language, and the app reads
a language's own where it has them.

**Measuring it.** `targets/search/tests.jsonl` holds 100 questions a reader
might type, in English, Thai, Spanish and Chinese, written by hand and each
answer checked against the text. `scripts/search_test.py` asks them the way the
phone does and says how often the passage came first, in the first five and in
the first ten; `--compare` sets verses alone beside verses with stories, and
`--misses` lists what was not found. `scripts/make_search_tests.py` has the
model write more, in every language, Karen too.

**Teaching the model the Bible.** No multilingual Bible search model exists to
take, so `scripts/train_search.py` teaches ours, on the PC's GPU, from pairs the
project already has: questions the model wrote about passages, each passage's
description in every language, and the same verse in two languages. Passages
the hand-written questions ask about are kept out of training, so the test
stays honest. The order on the PC:

```
python scripts/translate_stories.py                 # the descriptions in every language (hours, once)
python scripts/make_search_tests.py --train --n 3000 # questions to train on
python scripts/train_search.py                      # -> models/e5-bible/
python scripts/build_encoder.py                     # the phone's files, from the taught model
python scripts/search_test.py                       # better than before? if not, delete models/e5-bible/
```

### Search with the model behind it (the PC)

The index is what a phone can carry. On this machine the reader is served by the
dashboard (`/reader`), and its search page grows a button: **Ask qwen3:32b** (or
whatever `config.json` names). `scripts/ask.py` puts the question to the model
in three steps — the model names passages and the words such a verse would be
described with; code checks every reference against the source, adds a verse
either side (the model counts the Psalms the English way, this text the
Masoretic) and adds what those words find in the topical lines and the
translation; then the model reads those verses as they stand in the reader's
language and picks. It can only pick from the list, so nothing it remembers
wrongly reaches the page, and what is drawn is the reader's own text.

    python scripts/ask.py "the writing on the wall at a feast"
    python scripts/ask.py --lang zh "那个离开九十九只羊去找一只的牧人"

A question is two short model calls, a few seconds on an idle GPU. While a
translation or a job is running it waits its turn between their requests, and
the page says so. Answers are kept under `logs/ask/`, which is not committed.
Opened as a file, on a phone or from any other server, the reader never shows
the button.

### Themes

The whole Bible is about 944,000 tokens and the model holds 40,960, so
`scripts/build_themes.py` never asks it to read everything at once. It works
bottom up, the way a reader does: each chapter (about 2,300 tokens) is read on
its own and gives two to five themes with the verses that carry them; those
several thousand labels are then folded into one canonical list in batches,
each batch measured against the list so far; packing gathers every passage
under its theme. Nothing comes from a systematic theology or a topical Bible.

Each theme also carries the vocabulary its passages use, ranked by how much more
often a word stands there than elsewhere, and each word carries the themes it
turns up under. That is deliberate: it lets a reader see James Barr's point
rather than take it on trust. A theme is not a word. *The temptation and fall*
runs on serpent, ate, opened, cursed and a dozen more; and a single word like
*good* serves creation, evaluation and law alike. The reader says so where the
vocabulary is shown.

### The rungs above themes

`scripts/build_theology.py` adds the two layers that follow from themes, both
built only from the layer below and citing it:

- **What a book argues** (`--books`): the themes of a book's own chapters are
  aggregated into its sections, its line of thought and what it keeps returning
  to. 66 books, about 12 s each. Shown under the *themes* tab of any chapter of
  that book.
- **How a theme develops** (`--trajectories`): a theme's passages in canonical
  order become a beginning, three to six stages, a culmination, and the places
  where the passages pull against each other. About 24 s a theme. Shown on the
  theme's own page.

The tensions field is deliberate: a synthesis that cannot show where the text
disagrees with itself is not worth reading. Both layers are labelled in the
reader as readings rather than tagged facts, and no published theology,
commentary or topical Bible is consulted.

The reader's tabs run in the same order as the layers: the texts first, then
interlinear and grammar search (words), fields of meaning, themes, and last the
notes on a verse — parallels, places, chronology.

### Starting and stopping the model work from the dashboard

The work bar has a start button on every unfinished job and a stop button on
every running one, with **stop all — free the GPU** in its header. Stopping
kills the process tree, so the model call goes with it and the GPU is yours
again; the job resumes from where it stopped when you start it next.

It also finds jobs started outside the dashboard — from `start_work.cmd` or a
terminal — by looking at what the running python processes are, so those can be
stopped from the same buttons. That check is done in-process with `psutil`
(`pip install psutil`), and everything the dashboard runs is started with no
console window, so nothing flashes on screen while the bar refreshes. Each
job's output goes to `logs/job_<name>.log`.

### Long model jobs (the work queue)

The jobs that need the GPU for hours — writing the lexicon, sorting every
lexeme into fields of meaning, translating the lexicon into each target
language — are queued and run one after another:

```
start_work.cmd                  (double-click) run the queue until it is done
start_work.cmd --list           what is queued and how far along it is
start_work.cmd --hours 8        stop starting new jobs after eight hours
python scripts/work.py --only lexicon,domains
```

Every job writes as it goes and skips what is already written, so the window
can be closed or the machine rebooted and the queue simply resumes. A
translation run in the dashboard can go at the same time; they share the GPU
and both run slower. Progress is appended to `logs/work.log`.

### Rebuilding the study layers

```
python scripts/build_all.py             every layer below, then the reader page
python scripts/build_all.py --fast      skip morphology and syntax (the slow two)
```

| layer | script | source | output |
|---|---|---|---|
| word tags, lexicon, concordance | `build_morph.py` | STEPBible (CC BY 4.0) | `site/morph/<Book>.js`, `lex.js`, `conc.js` |
| cross-references, parallels | `build_refs.py` | OpenBible.info (CC BY 4.0) + our tags | `xref_*.js`, `parallels.js` |
| text notes (apparatus) | `build_apparatus.py` | STEPBible | `app_*.js` |
| clause roles, referents, domains | `build_syntax.py` | MACULA Greek (CC BY 4.0) | `syn_*.js`, `domains.js` |
| places and the map | `build_places.py` | OpenBible.info + Natural Earth | `places.js` |
| chronology | `build_chronology.py` | our English text + hand-entered anchors | `chron.js` |
| search index | `build_index.py` | every text | `idx_<lang>.js` |
| search by meaning | `build_vectors.py` | multilingual-e5-small, distilled to a table | `vec_table.js`, `vec_<lang>.js` |
| search by meaning, in the app | `build_encoder.py` | multilingual-e5-small itself, int8 | `site/model/` (not in git) |
| themes | `build_themes.py` | the model, chapter by chapter | `themes.js` |
| book arguments, theme trajectories | `build_theology.py` | the model over the themes | `theology.js` |
| our lexicon | `build_lexicon.py` | the model over the concordance | `lexx.js` |
| our lexicon, translated | `translate_lexicon.py --lang zh` | the model over our entries | `lexx_<lang>.js` |
| fields of meaning | `build_domains.py` | the model over our glosses | `domains.js` |
| our own lexeme inventory | `build_lexemes.py` | the model over every word form | `lexemes.js` |

Every file loads on demand, so the reader page itself stays the same size and
the whole set works offline and inside an Android bundle.

### Names readers already know (`scripts/build_names.py`)

`targets/<lang>/names.json` is pasted into every prompt, so it holds a few
dozen names and cannot hold more without crowding out the chapter. Every other
name was left to the model, which invents a spelling per chapter with no
memory of the last one — so Stephen came out 司提反 in one chapter and 斯提反
in the next, and a reader who knows the Bible of their language met a stranger
every few verses. Measured against a reference edition, 38 of 60 well-known
names were spelled two ways in our own Chinese.

The spellings a language's readers know are already written down, in the
translation they grew up with, so they are learned rather than listed:

```
python scripts/build_names.py --lang zh --ref <a reference Bible>.json --write
```

Our English is the pivot, because its proper names can be picked out
mechanically — a real name is never written lower-case anywhere in the Bible,
which is a better filter than any stop-list. A name turns up in the same
verses in both Bibles and almost nowhere else, so pairing is by overlap
(Dice); an ordinary word is spread across the canon and pairs with nothing.
For a language written without spaces the alphabet of transliteration
characters is bootstrapped from the names already pinned, with a frequency cap
so that no character carried by the whole language can join it. Where the
evidence cannot separate two names — Cappadocia and Pontus are named in the
same breath and nowhere else — both are dropped rather than guessed, and so is
any spelling claimed by two unrelated names.

It writes `targets/<lang>/names.map.json`, and `translate.py` injects only the
names in the chapter being translated: about ten per chapter, a hundred and
forty characters, instead of a list that would not fit. `verify.py` then flags
a chapter that ignored one. The reference text is read on this machine and
none of it is reproduced — what is kept is a list of spellings, which is a
convention, not a text. Chinese: 744 names.

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
| `ksw` | Sgaw Karen — machine-translated from our English by MADLAD-400, see below | — | — | `output/ksw/` |

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

Sgaw Karen is the exception: a language the chat model cannot write, so its
text comes from a translation model taught for it. The chat model writes
Burmese when asked for Karen, and a wrong answer in Myanmar script passes
every check the verifier has, so it is not asked. NLLB-200 turned out to know
Burmese and Shan but no Karen at all. Google's MADLAD-400 lists `ksw`, and
what it writes under that tag is Shan, with stretches of Burmese and, now and
then, a memorised line of the Karen Bible that says something else: measured
against the Karen Bible's Genesis 1 (97 of 100 words carry Karen's own tone
letters, none carry Shan's), MADLAD's chapter had Karen letters in a seventh of
its words and Shan letters by the dozen. But its tokenizer spells Karen
fluently, so it was taught: `scripts/karen_corpus.py` pairs Mason's 1853
Karen Bible (public domain, `sources/ksw-mason/`) with our English, 27,500
verses, and `scripts/train_karen.py` fine-tunes MADLAD 3B on them (chrF 33.5
on held-out chapters, 34.9 after a pass over the mined name table,
`scripts/karen_names.py`). `scripts/mt_translate.py`, the driver for any
target marked with an `mt` code (a language put through a translation model
from our *English*, never from the originals; `translate.py` leaves those
alone), then wrote all 1,189 chapters with it - fluent Karen in Mason's
register with the meaning right roughly two times in three, a draft for a
Karen reader to correct, and every chapter and the reader's footer say so.
No phone or computer ships a Sgaw Karen voice, so the reader's Listen is not
offered for it; the voice work is in `NGAW KAREN TTS/`.

Teaching a model Karen: `scripts/karen_corpus.py` reads Mason's 1853 Karen
Bible (public domain, the SWORD module in `sources/ksw-mason/`) and pairs its
verses with ours where the numbering agrees, 27,500 pairs; `scripts/train_karen.py`
fine-tunes MADLAD on them, scores every thirtieth chapter that it never saw,
and leaves the best model in `models/madlad-ksw/`, which `mt_translate.py`
then uses by default.

### Voice

No phone or computer ships a Sgaw Karen voice. `scripts/karen_speech.py`
reads Karen with Meta's offline Burmese voice by respelling each syllable
into the Burmese spelling with the nearest sounds, then, through the WORLD
vocoder, giving each syllable the pitch curve and length of its Karen tone -
six tones where Burmese has four. Its tables (consonants, vowels, six tone
curves) are the thing to correct by ear against a Karen speaker; the audio
goes to `audio/ksw/`. A voice that is actually Karen needs a Karen speaker
recorded, which the phonemizer here is the front end for.

Every chapter's JSON carries `"engine"`: the model that wrote its verses
(`qwen3:32b` for everything translated so far, the MADLAD checkpoint for
Karen). `translate.py` and `mt_translate.py` write it; `scripts/tag_engine.py`
stamped the chapters written before it existed, from the run log. The reader's
footer and the dashboard's compare rows say it per language.

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
self-contained HTML file. The file is not committed - at fifty megabytes it
passed GitHub's limit - so a fresh checkout builds it first (`--complete-only`
for a copy to hand out), and `scripts/build_index.py` for the search indexes — full-text search, a reference finder
("Genesis 2:7", "1 sam 3:10"), and a chapter reader. No server, no network:
open the file in any browser, or as its own window with `start_reader.cmd`
(the dashboard also serves it at <http://localhost:8766/reader>).

**Taking verses.** Every verse number is a button. Press it and the verse is
taken: the number sets into the page and the verse is washed the colour of a
search hit, and a bar at the foot of the screen offers to copy it, send it,
read it aloud, or - in advanced mode, one verse at a time - show its notes,
cross-references and parallels. Press more numbers and they are taken too, in
any order and with any gaps: the bar names them the way a reference is written
("Psalms 23:1-3, 5"), copies them as one quotation with the verse numbers in
it, and reads them aloud in order without reading the numbers out. Pressing a
number again lets that verse go; tapping the text of a verse takes that one
alone, and tapping it again, pressing Escape, or the phone's back button lets
everything go. From a keyboard the chapter's numbers are a single stop on the
way through the page - arrows move between them, space or enter takes one -
because a hundred and seventy-six tab stops in Psalm 119 would be no kindness.

### Android app

`android/` is a WebView around the reader (see `android/README.md`). There are
two builds of it:

**Make Android APK** in the dashboard header builds either of them, and
`python scripts/build_apk.py [--full]` does the same from the command line. The
APK lands in `dist/`:

- **reader** - the text alone, in every translated language, always in "Just
  read" mode, with the search indexes: an 11 MB APK, 26 MB on the phone.
- **+ study tools** - the same page with everything in `site/morph/` behind it:
  word tags, lexicon, concordance, syntax, cross-references, apparatus, themes,
  places, chronology. A 26 MB APK, 78 MB on the phone, and the
  layers are frozen as they stand when it is built, so a job still running
  (themes, the lexicon, the lexemes) will be partial in it.

Both carry only the languages the whole Bible has been translated into, so a
language still in progress is left out until it is finished; the build says
which it left, and with what it had (`es (14/1189)`). The reader here on the PC
still shows every language, finished or not.

The first time, the button offers to fetch the build tools (a JDK 17, Gradle
and the Android SDK, about 1 GB, into `tools/android/`), which means accepting
the Android SDK License; it asks before doing so. Without an upload key the APK
is a debug build that installs on any phone allowing apps from outside Play.
Both variants carry the same application id, so one replaces the other on a
phone, and both hold whatever chapters have been translated when they are
built.

For a Play upload the AAB still comes from `android/sync_assets.sh` and Gradle,
as `android/README.md` describes.

### The app as one folder (`scripts/package_app.py`)

`python scripts/package_app.py` builds `dist/eBible-app/`: the dashboard, the
reader, the translation driver and the APK builder, with their own Python, the
translated text and the study layers, started by `eBible.exe`. Nothing needs
installing on the machine that runs it - translating still needs Ollama and the
model, reading and building APKs do not.

- **with the toolchain** (the default, about 1.5 GB) it also carries the JDK,
  Gradle, the Android SDK and the libraries Gradle would otherwise download, so
  it builds an APK with no network at all. Google's SDK terms forbid passing
  that on, so a bundle built this way is for your own machines.
- **`--shareable`** (about 170 MB) leaves the SDK out; the first APK build on
  the other machine offers to fetch it, under the licence whoever runs it
  accepts. See LEGAL.md section 5.

## Status

- [x] Sources fetched and normalized (66 books, 31,102 verses)
- [x] Prompt, glossary, name table, driver, verifier, site builder
- [x] Genesis 1–3 translated with llama3.3:70b and verified (0 flags)
- [ ] Side-by-side comparison with the claude.ai "Claude Fable" rendering
- [ ] Narrative books
- [ ] Poetry and prophets (heavier review budget)
- [ ] Aramaic sections of Daniel/Ezra in their own run
