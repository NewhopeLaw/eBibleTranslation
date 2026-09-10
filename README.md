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
scripts/normalize.py  [books...]     sources -> sources/normalized/*.json
scripts/translate.py  Gen 1-3        translate chapters (resumes; --force to redo)
scripts/translate.py  --all          the whole Bible, canonical order
scripts/verify.py     [Gen [1-3]]    flag missing/dup verses, untranslated text,
                                     truncation, name inconsistencies
scripts/build_site.py                rebuild site/index.html reader
```

Conventions live in `prompts/system_prompt.txt`; fixed renderings in
`glossary.json`; proper-name spellings in `names.json`. Chapter memory: each
prompt includes the previous chapter's English for continuity. Logs in
`logs/translate.jsonl` (timing + token counts per chapter).

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
