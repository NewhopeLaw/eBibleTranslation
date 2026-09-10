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
whole Bible — with *All languages*, every language for a book before the next
book — skipping chapters that exist, and treats any failure (Ollama restarted,
a bad response) as a pause: it reports, waits with backoff, and retries the
same book until it goes through. Only Stop, or the end of the Bible, ends it.
The same behaviour from the terminal is `translate.py --all --lang all
--keep-going`.

Chapter memory: each prompt includes the previous chapter's translation for
continuity. Logs in `logs/translate.jsonl` (timing + token counts per chapter,
with the target language); verifier reports in `logs/verify_<lang>.md`.

## Reader / search (site/index.html)

`scripts/build_site.py` embeds every translated chapter into a single
self-contained HTML file — full-text search, a reference finder
("Genesis 2:7", "1 sam 3:10"), and a chapter reader. No server, no network:
open the file in any browser.

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
