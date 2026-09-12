# Working on this project

Two kinds of work happen here, and they do not happen in the same place.

## The model's work stays on the PC

Translating (`scripts/translate.py`), the study jobs (`scripts/work.py` and the
`build_*.py` it runs) and the live dashboard (`scripts/live.py`, port 8766) all
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

`site/index.html` is committed prebuilt and carries the whole text through
`site/morph/*.js`, so a cloud session can serve `site/` over a static server and
open the reader as a user sees it.

**Do not run `scripts/build_site.py` in the cloud, and never commit a site built
there.** Most of the translated chapters under `output/` are not in git; a
rebuild away from the PC would quietly replace a reader holding the whole Bible
with one holding the handful of chapters the checkout has. Rebuilding is done on
the PC, which has the translations, and that rebuild is what gets committed.

Dashboard changes are the same: the page can be read and edited anywhere, but it
is only seen working with a model behind it, on the PC.

## Presenting UI work

Any screen, component or front-end change is presented together with a
self-audit against `docs/ui-checklist.md` — seven points covering assumptions,
edge states, hierarchy, reversibility, messy data, accessibility and component
choice. The audit goes in the pull request or the reply, not in the code.

## House style

Comments and commit messages explain *why*, in plain prose, the way the existing
ones do. Keep to the voice already in the file you are editing.
