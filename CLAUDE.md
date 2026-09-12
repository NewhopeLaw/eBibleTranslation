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
`site/morph/*.js`, so any checkout can serve `site/` over a static server and
open the reader as a user sees it. The translations under `output/` are in git
too, so `python scripts/build_site.py` rebuilds the full reader anywhere — but
check the build line reports every translated chapter (1189 in English at the
time of writing) before committing the result; a checkout that is behind on
`output/` would shrink the reader. Prefer to commit the generator change and let
the PC, which always has the latest chapters, commit the rebuild.

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
