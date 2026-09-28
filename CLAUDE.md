# Working on this project

Two kinds of work happen here, and they do not happen in the same place.

## The model's work stays on the PC

Translating (`scripts/translate.py`), the study jobs (`scripts/work.py` and the
`build_*.py` it runs), the live dashboard (`scripts/live.py`, port 8766) and the
search that asks the model (`scripts/ask.py`, behind the dashboard's `/ask`) all
talk to Ollama on this machine's GPU — the model named in `config.json`. None of
that can run anywhere else: a cloud session has no GPU, no Ollama and no
`sources/morphhb` and friends (those clones are gitignored; see README.md).

A cloud session must not try to start a job, a translation run or the dashboard,
and must not report on how far a job has got — the counts in the repo are
whatever was last pushed from the PC.

## The reader and dashboard UI can be worked on anywhere

The pages themselves are ordinary front-end work:

- `scripts/build_site.py` generates `site/index.html` — the offline reader. Edit
  the generator, never the built file.
- `scripts/live.py` holds the dashboard page (HTML, CSS and JS in one string
  near the bottom) as well as the server.

### Looking at a change

`site/index.html` is not in git — it passed GitHub's 50 MB file limit — and
neither are the search indexes (`site/morph/idx_*.js`); both are built from
what is committed. The translations under `output/` are in git, so
`python scripts/build_site.py --complete-only` and `python scripts/build_index.py`
make the full reader on any checkout, and `site/` can then be served over a
static server and opened as a user sees it. Check the build line reports every
translated chapter (1189 in English at the time of writing): a checkout that is
behind on `output/` would build a smaller reader. The rest of `site/morph/` is
the study layers the model wrote, and those stay committed.

Dashboard changes are the same: the page can be read and edited anywhere, but it
is only seen working with a model behind it, on the PC.

## Where the work is going

`docs/from-the-text.md` records the plan for the word layers: everything from
forms to meaning is being rebuilt from the text by the model, bottom up, with
the STEPBible-based layers kept only as a yardstick and each step compared
against them before the next is built. Read it before touching `build_morph.py`,
`build_lexemes.py`, `build_lexicon.py` or `build_domains.py`, and keep its
"Where things stand" section current when a step lands.

## Presenting UI work

Any screen, component or front-end change is presented together with a
self-audit against `docs/ui-checklist.md` — seven points covering assumptions,
edge states, hierarchy, reversibility, messy data, accessibility and component
choice. The audit goes in the pull request or the reply, not in the code.

## Finished means verified

A chapter is translated when its verses are in it. A run that fails — the
model answers in the wrong language, or echoes the prompt back — still leaves
a file behind, and counting files let a Chinese Bible with no Psalm 119 in it
call itself complete and ship in an APK. `build_site.py --complete-only` now
counts verses against the source, and says which chapters are hollow.

## House style

Comments and commit messages explain *why*, in plain prose, the way the existing
ones do. Keep to the voice already in the file you are editing.
