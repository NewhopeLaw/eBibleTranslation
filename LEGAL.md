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

**Open item for audit.** `site/index.html` (built by `scripts/build_site.py`)
does not yet display these attributions on the page. Until it does, this
file and the README are the notices.

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
