# Legal notes: sources, licenses, copyright and public-domain notices

Audit record for every third-party text this project reads, quoted from the
upstream repositories on GitHub as they stood on **2026-09-11**. Re-verify
with the commands at the end; if an upstream file has changed since, this
file records what was relied on at the time.

The source repositories themselves are not committed here (see
`.gitignore`); `sources/normalized/*.json` and `site/index.html` are derived
from them and carry the obligations below.

## Summary

| Text | Repository | Snapshot (default branch HEAD) | License of the text | Used for |
|---|---|---|---|---|
| Hebrew / Aramaic Old Testament, Westminster Leningrad Codex (WLC) | [openscriptures/morphhb](https://github.com/openscriptures/morphhb) | `master` @ `3d15126fb1` (2024-08-27) | Text: **public domain** (Public Domain Mark 1.0). Lemma and morphology data: **CC BY 4.0** | Source text that is translated (`scripts/normalize.py` reads `sources/morphhb/wlc/`) |
| Greek New Testament, SBL Greek New Testament (SBLGNT) | [LogosBible/SBLGNT](https://github.com/LogosBible/SBLGNT) | `master` @ `c4d241a9c1` (2025-01-19) | **CC BY 4.0**; © 2010 Society of Biblical Literature and Logos Bible Software | Source text that is translated (`scripts/normalize.py` reads `sources/SBLGNT/data/sblgnt/text/`) |
| Greek New Testament, Robinson–Pierpont Byzantine Majority Text (2018 edition) | [byztxt/byzantine-majority-text](https://github.com/byztxt/byzantine-majority-text) | `master` @ `27a45ff1b7` (2024-12-31) | **Public domain** (The Unlicense, `LICENSE.txt`) | Listed in README as available for consultation; no pipeline script reads it |
| Greek Old Testament, Septuagint, H. B. Swete's edition | [OpenGreekAndLatin/First1KGreek](https://github.com/OpenGreekAndLatin/First1KGreek), `data/tlg0527` | `master` @ `7881c56343` (2026-08-20); 37 TEI files fetched by `scripts/add_lxx.py` into `sources/lxx/` | Swete's printed edition (1887–1909): **public domain**. The TEI digital encoding: **CC BY-SA 4.0** (University of Leipzig / Open Greek and Latin) | Reference only: shown beside the Hebrew in the reader and dashboard, passed to the model as a clearly marked reference. Never translated |

| Word-level tags for both testaments: lemma / Extended Strong's number, morphology, gloss; brief Hebrew and Greek lexicons; morphology-code expansions | [STEPBible/STEPBible-Data](https://github.com/STEPBible/STEPBible-Data) (Tyndale House, Cambridge) | `master`, cloned 2026-09-11 into `sources/STEPBible-Data` | **CC BY 4.0**, stated in the README and at the head of every data file | `scripts/build_morph.py` aligns the tags to our text and writes `site/morph/*.js` for the reader's word popups, interlinear view, concordance and grammar search |

| Cross-references between verses (~341,000 with positive votes) | [OpenBible.info cross-reference dataset](https://www.openbible.info/labs/cross-references/) — the *Treasury of Scripture Knowledge* (1830s, public domain) extended and ranked by reader votes | `cross-references.zip` downloaded 2026-09-11 into `sources/openbible/` (data stamped 2026-09-07) | **CC BY 4.0**, stated on the page and in the file header line `#www.openbible.info CC-BY` | `scripts/build_refs.py` writes `site/morph/xref_*.js`; the reader shows them when a verse number is clicked |

| Place identifications and coordinates (1,111 located places, 4,812 verses) | [OpenBible.info Bible geocoding data](https://www.openbible.info/geo/), 2007 tab-delimited release (`geo/data/merged.txt`, `places.txt`) | downloaded 2026-09-11 into `sources/openbible/` | **CC BY 4.0** ("The dataset as a whole is licensed under the Creative Commons Attribution license") | `scripts/build_places.py` -> `site/morph/places.js`; the reader's *places* tab and the verse panel |
| Coastlines, lakes and rivers for the base map | [Natural Earth](https://www.naturalearthdata.com/) 50m coastline, 50m lakes, 50m rivers, via [nvkelso/natural-earth-vector](https://github.com/nvkelso/natural-earth-vector) | downloaded 2026-09-11 into `sources/openbible/` | **Public domain** ("Everything here is public domain… Crediting the authors is unnecessary.") | clipped, simplified and written as SVG paths, so the map draws offline with no tiles or map service |

GitHub's own license detection (`gh api repos/<owner>/<repo> --jq .license`)
reports: morphhb `NOASSERTION` (custom LICENSE.md, quoted below), SBLGNT
`CC-BY-4.0`, byzantine-majority-text `Unlicense`, First1KGreek `CC-BY-SA-4.0`.

## 1. Westminster Leningrad Codex via the Open Scriptures Hebrew Bible

**Repository:** https://github.com/openscriptures/morphhb (files under `wlc/`, OSIS XML)

**Status.** The WLC text is in the public domain. The Open Scriptures
project's added lemma and morphology tags are CC BY 4.0. This project uses
the verse text only; `scripts/normalize.py` writes plain verse text to
`sources/normalized/`, without the `lemma` and `morph` attributes.

**`LICENSE.md`, quoted in full (master @ 3d15126fb1):**

> # Open Scriptures Hebrew Bible
>
> This work is based on *The Westminster Leningrad Codex*, which is in the public domain.
>
> # License
>
> ## Creative Commons Attribution 4.0 International (CC BY 4.0)
>
> This is a human-readable summary of (and not a substitute for) the [license](http://creativecommons.org/licenses/by/4.0/).
>
> ### You are free to:
>
> * **Share** — copy and redistribute the material in any medium or format
> * **Adapt** — remix, transform, and build upon the material
> for any purpose, even commercially.
>
> The licensor cannot revoke these freedoms as long as you follow the license terms.
>
> ### Under the following terms:
>
> * **Attribution** — You must attribute the work as follows: "Original work of the Open Scriptures Hebrew Bible available at https://github.com/openscriptures/morphhb". You may do so in any reasonable manner, but not in any way that suggests the licensor endorses you or your use.
>
> **No additional restrictions** — You may not apply legal terms or technological measures that legally restrict others from doing anything the license permits.
>
> ### Notices:
>
> You do not have to comply with the license for elements of the material in the public domain or where your use is permitted by an applicable exception or limitation.
>
> No warranties are given. The license may not give you all of the permissions necessary for your intended use. For example, other rights such as publicity, privacy, or moral rights may limit how you use the material.

**`README.md` (license paragraph), quoted:**

> Lemma and morphology data are licensed under a
> [Creative Commons Attribution 4.0 International](http://creativecommons.org/licenses/by/4.0/)
> license. For attribution purposes, credit the Open Scriptures Hebrew Bible
> Project. The text of the WLC remains in the
> [Public Domain](http://creativecommons.org/publicdomain/mark/1.0/). See the [LICENSE](LICENSE.md) file for more information.

**Obligation.** None for the verse text (public domain). If lemma or
morphology data is ever used, attribute exactly as the license states:
"Original work of the Open Scriptures Hebrew Bible available at
https://github.com/openscriptures/morphhb". The attribution is given anyway
in the notice block below, as a courtesy and to be safe.

## 2. SBL Greek New Testament

**Repository:** https://github.com/LogosBible/SBLGNT (plain text under `data/sblgnt/text/`)

**Status.** Copyright 2010 Society of Biblical Literature and Logos Bible
Software, licensed CC BY 4.0. The repository's `LICENSE` file is the full
Creative Commons Attribution 4.0 International legal code (18,650 bytes,
beginning "Attribution 4.0 International"). Per the README version history
the public GitHub version and license date from v1.1 (2022-12-19); earlier
SBLGNT releases were under a separate end-user license, which does not
apply to the text fetched from this repository.

**`README.md` (license section), quoted:**

> ## License
>
> The SBLGNT is licensed under a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
>
> Copyright 2010 by the [Society of Biblical Literature](https://sbl-site.org/) and [Logos Bible Software](https://www.logos.com/).

**Version history from the README:** v1.0 2010-10-01 initial release;
v1.1 2022-12-19 "Update public version and license on github";
v1.2 2023-07-10 "Add Jn 7:53-8:11 (Pericope Adulturae)".

**Obligations under CC BY 4.0** (section 3(a) of the legal code): keep the
copyright notice and the license reference, credit the licensor, and
indicate if changes were made. This project modifies the text:
`scripts/normalize.py` strips the SBLGNT critical sigla (half-brackets and
related editorial marks) before translation. That modification is stated in
the notice block below.

## 3. Robinson–Pierpont Byzantine Majority Text

**Repository:** https://github.com/byztxt/byzantine-majority-text

**Status.** Public domain. `LICENSE.txt` is The Unlicense; the README's
Copyright section reads: "All the code and text contained in this folder is
in the Public Domain." The README describes the content as the 2018
Robinson–Pierpont edition, current as of 2023-07-20.

**`LICENSE.txt`, quoted in full:**

> This is free and unencumbered software released into the public domain.
>
> Anyone is free to copy, modify, publish, use, compile, sell, or
> distribute this software, either in source code form or as a compiled
> binary, for any purpose, commercial or non-commercial, and by any
> means.
>
> In jurisdictions that recognize copyright laws, the author or authors
> of this software dedicate any and all copyright interest in the
> software to the public domain. We make this dedication for the benefit
> of the public at large and to the detriment of our heirs and
> successors. We intend this dedication to be an overt act of
> relinquishment in perpetuity of all present and future rights to this
> software under copyright law.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
> EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
> MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
> IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
> OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
> ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
> OTHER DEALINGS IN THE SOFTWARE.
>
> For more information, please refer to <https://unlicense.org>

**Obligation.** None. As of this note no script in `scripts/` reads this
text; it is named in the README as a text available for consultation.

## 4. Septuagint, Swete's edition, via First1KGreek

**Repository:** https://github.com/OpenGreekAndLatin/First1KGreek, directory
`data/tlg0527` (TLG author 0527 = Septuaginta). `scripts/add_lxx.py`
downloads the per-book TEI XML files from
`https://raw.githubusercontent.com/OpenGreekAndLatin/First1KGreek/master/data/tlg0527`
into `sources/lxx/` (37 files locally) and attaches the verses to the
normalized Old Testament as the `lxx` field.

**Two layers of rights.**

1. The printed edition: Henry Barclay Swete (ed.), *The Old Testament in
   Greek according to the Septuagint*, Cambridge University Press, 3 vols.,
   first published 1887–1894, later editions through 1909. Swete died in
   1917. The edition is in the public domain (published before 1929, and
   more than 70 years after the editor's death).
2. The digital text: transcribed, corrected and TEI-encoded by the Open
   Greek and Latin project at the University of Leipzig (Digital Divide
   Data credited for correction and encoding; Gregory Crane and Monica
   Berti principals; 2015). Each file's TEI header states the license.

**TEI header of every `sources/lxx/*.xml` file (availability), quoted:**

> Available under a Creative Commons Attribution-ShareAlike 4.0 International License
> (`<licence target="https://creativecommons.org/licenses/by-sa/4.0/">`)

with `<publisher>University of Leipzig</publisher>`, `<date>2015</date>`,
`<editor>Henry Barclay Swete</editor>`, `<sponsor>University of Leipzig</sponsor>`,
`<funder>European Social Fund Saxony</funder>`. GitHub reports the repository
license as CC-BY-SA-4.0.

**Obligations and how they are met.** The Septuagint is a reference, never a
source: no translation is made from it, so the translations are not
derivatives of it. The encoded Greek is, however, reproduced in
`sources/normalized/*.json` and embedded in `site/index.html` (Septuagint
tab, LXX row in Compare). To the extent the Leipzig encoding is protected,
those copies must carry attribution and remain available under CC BY-SA 4.0.
The notice block below gives the attribution; the ShareAlike condition
applies to the reproduced Greek, not to the translations.

**Decision (2026-09-11, project owner).** The Septuagint stays in the
distributed product. Reasoning recorded for audit: Swete's edition is public
domain; the First1KGreek files reproduce that text faithfully with verse
markup and no editorial additions, and in the intended markets (United
States and Asia) a faithful reproduction of a public-domain text is not
regarded as creating a new copyright, so the ShareAlike condition is not
considered to attach to the plain verse text. The attribution to the
University of Leipzig / Open Greek and Latin project is given anyway, in
this file and in the reader's footer. The project's general rule (inputs
must be public domain or permissively licensed; no share-alike, non-
commercial or unlicensed material is read or shipped) applies to everything
else and to all future additions.

The reader (`site/index.html`) displays these attributions in its footer,
reached from the "Sources & licenses" link in its header.

## 4b. STEPBible data (word tags, lexicons, morphology codes)

**Repository:** https://github.com/STEPBible/STEPBible-Data — files used:
`Translators Amalgamated OT+NT/TAHOT *` (Hebrew OT: Leningrad text via
OpenScriptures with disambiguated Extended Strong's tags, ETCBC/OpenScriptures
morphology, glosses), `TAGNT *` (Greek NT: every word of the major editions,
each marked with the editions containing it — the SBLGNT words are selected),
`Lexicons/TBESH`, `Lexicons/TBESG` (brief lexicons), `Morphology codes/TEHMC`,
`TEGMC` (code expansions).

**Status.** CC BY 4.0. Each file begins with the statement "Data created by
www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)" and
the terms, quoted:

> This licence allows you to:
> * Include any part of this data in software or publications without requesting permission
> * Download the data and reformat it for your application, without changing the data
> * Send any proposed corrections to STEPBibleATGmail.com. to be verified
>   (You MAY make changes yourself, but you should include a note of changes that can be viewed by those who use your new data)
> * Refer others to github.com/STEPBible as the source of the data. Please do not redistribute it yourself.
>   (Updates or corrections are easier to implement when the data is distributed from a single source)

The repository README states the data "is based on other publically licenced
sources, and has been compared with non-public sources so that differences
can be checked by Tyndale scholars"; the released data is Tyndale House's own
work under CC BY.

**How it is used, and the obligations met.** `scripts/build_morph.py` reads
the files and writes a reformatted subset (`site/morph/*.js`: per-word tag,
morphology code, gloss, transliteration; lexicon headwords, glosses and
abbreviated meanings; code expansions). The STEPBible files themselves are
not committed or redistributed (`sources/` is ignored), honouring their
request; the reader's footer credits STEPBible.org and Tyndale House, states
CC BY 4.0, links to the repository, and says the data was reformatted. No
changes are made to the data beyond selection and reformatting.

## 4c. OpenBible.info cross-references

**Source:** https://www.openbible.info/labs/cross-references/ (file
`https://a.openbible.info/data/cross-references.zip`). The page states the
data is "licensed under a Creative Commons Attribution License"
(CC BY 4.0), and the data file's header row carries
`#www.openbible.info CC-BY`. The underlying reference set is the
*Treasury of Scripture Knowledge* (R. A. Torrey et al., 1830s), long in the
public domain; OpenBible.info added community voting to rank the references.

**How it is used.** `scripts/build_refs.py` keeps the links with a positive
vote count and writes them per book as `site/morph/xref_*.js`. The reader
credits the Treasury and OpenBible.info in its footer with the licence link.
The raw archive is not committed (`sources/openbible/` is ignored).

**Parallel passages are not taken from any harmony.** They are computed in
`scripts/build_refs.py` from the STEPBible word tags: verses within the
Gospels, within Samuel–Kings–Chronicles (with Isaiah, Jeremiah, Psalms and
Micah) and within the Torah are compared by the rare lexemes they share
(idf-weighted cosine). No text of Aland, Robertson or any modern harmony is
read. The reader states this.

## 4d. Geography (places and the base map)

**Places:** https://www.openbible.info/geo/ — the 2007 tab-delimited files
`merged.txt` and `places.txt`. The page states: "The dataset as a whole is
licensed under the Creative Commons Attribution license, meaning that you can
use them for any purpose you want as long as you credit OpenBible.info."

The same paragraph adds "Some data is from OpenStreetMap, which has its own
open license." OpenStreetMap is share-alike (ODbL), which this project's
provenance rule excludes, so **only the 2007 release is used** — name, the
location the coordinates belong to, latitude, longitude, the verses that
mention it, and a note. The newer GitHub dataset, which carries
OpenStreetMap-derived geometry, is deliberately not used. Coordinates
themselves are facts and not copyrightable; the attribution is given anyway.

**Base map:** Natural Earth vector data (50m coastline, 50m lakes, 50m
rivers). Its `LICENSE.md` states: "Everything here is public domain… No
permission is needed to use Natural Earth. Crediting the authors is
unnecessary." `scripts/build_places.py` clips it to the biblical world,
simplifies it and writes SVG paths, so the reader draws the map itself: no
tile server, no map API, nothing fetched at run time. The reader credits
Natural Earth anyway.

## 4e. Textual apparatus (editions, not manuscripts)

Built by `scripts/build_apparatus.py` from the STEPBible data already covered
in 4b (CC BY 4.0). The Greek data marks, for every word, which printed
editions contain it — Nestle-Aland 27 and 28, Tyndale House 2017, SBLGNT,
Westcott-Hort 1881, Tregelles, Scrivener's Textus Receptus 1894, and the
Robinson-Pierpont Byzantine text — and records spelling differences between
them; the Hebrew data marks the scribal Qere against the written Ketiv and the
meaning and spelling variants. 13,340 entries across 64 books.

**No manuscript is cited.** Manuscript-level apparatus (NA28, UBS5, BHQ) is
copyrighted, so this project asserts no manuscript sigla; the reader says so in
its footer and in the panel itself. If an openly licensed manuscript apparatus
becomes available (for example Tischendorf's 1872, whose digitisations would
need checking), it could be added under the same rule.

## 4a. Provenance rule for reference data and tools

Adopted 2026-09-11 so the finished product can be given away without
conditions beyond attribution:

- Anything the pipeline reads or ships must be public domain or under a
  permissive license (CC0, CC BY, MIT, Apache). Attribution is kept here and
  in the reader footer.
- No share-alike, non-commercial or no-derivatives material, and no
  unlicensed copyrighted text, is used even for checking. (The Septuagint
  decision above is the one recorded exception, on the grounds stated.)
- Reference datasets that qualify for the planned concordance, lexicon and
  commentary tools: Strong's numbering (1890, public domain); STEPBible data
  from Tyndale House (CC BY 4.0: Hebrew and Greek lemma, Strong's number and
  morphology per word, brief lexicons); Open Scriptures Hebrew Bible
  morphology (CC BY 4.0); the public-domain originals of Brown-Driver-Briggs,
  Thayer, Abbott-Smith and Matthew Henry, provided the digitization used is
  itself public domain or CC BY. MorphGNT (CC BY-SA 3.0) does not qualify.

## 5. Model and tooling (not redistributed here)

- **Translation model:** `qwen3:32b` served by Ollama (`config.json`).
  Qwen3 model weights are published by Alibaba Cloud under the Apache
  License 2.0 (https://huggingface.co/Qwen/Qwen3-32B). Ollama itself is MIT
  licensed (https://github.com/ollama/ollama). Neither is included in this
  repository; verify the current license text at those links before relying
  on it.
- **Desktop window:** pywebview (BSD-3-Clause, https://github.com/r0x0r/pywebview),
  installed with pip, not vendored.
- **Python** standard library only otherwise (PSF license).

## 6. The translations produced here

The translations in `output/` and `site/index.html` are generated by the
model from the public-domain WLC and the CC BY 4.0 SBLGNT. CC BY 4.0
permits adaptation, including translation, for any purpose provided the
attribution above is kept. The project owner has not yet declared a license
for the translations themselves; this repository has no `LICENSE` file.
That is a decision for the owner and is noted here so an audit does not
mistake the absence for an oversight.

## 7. Attribution notice (ready to paste into the reader, app, or a release)

> Hebrew and Aramaic text: Westminster Leningrad Codex (public domain), from
> the Open Scriptures Hebrew Bible, https://github.com/openscriptures/morphhb
> ("Original work of the Open Scriptures Hebrew Bible available at
> https://github.com/openscriptures/morphhb", CC BY 4.0 for lemma and
> morphology data).
>
> Greek New Testament: The SBL Greek New Testament, copyright 2010 Society
> of Biblical Literature and Logos Bible Software, licensed under CC BY 4.0
> (https://creativecommons.org/licenses/by/4.0/), https://github.com/LogosBible/SBLGNT.
> Modified: critical sigla removed.
>
> Byzantine text consulted: Robinson–Pierpont Byzantine Majority Text (2018),
> public domain, https://github.com/byztxt/byzantine-majority-text.
>
> Septuagint (reference only): H. B. Swete, The Old Testament in Greek
> according to the Septuagint (Cambridge, 1887–1909; public domain), digital
> edition by the Open Greek and Latin project, University of Leipzig, 2015,
> CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/),
> https://github.com/OpenGreekAndLatin/First1KGreek (data/tlg0527).

## 8. Re-verifying this record

```bash
for r in openscriptures/morphhb LogosBible/SBLGNT byztxt/byzantine-majority-text OpenGreekAndLatin/First1KGreek; do
  echo "$r: $(gh api repos/$r --jq '[.default_branch, .license.spdx_id] | join(" ")') @ $(gh api repos/$r/commits/HEAD --jq '.sha[0:10] + " " + .commit.committer.date')"
done
curl -sL https://raw.githubusercontent.com/openscriptures/morphhb/master/LICENSE.md
curl -sL https://raw.githubusercontent.com/LogosBible/SBLGNT/master/README.md
gh api repos/byztxt/byzantine-majority-text/license --jq .content | base64 -d
grep -m1 -A3 "<availability" sources/lxx/tlg0527.tlg001.1st1K-grc1.xml
```

Compare the output with the snapshots and quotations above; if a license
changed upstream, the texts already fetched remain under the terms that
applied when they were fetched (CC licenses are irrevocable; public-domain
dedications cannot be withdrawn).
