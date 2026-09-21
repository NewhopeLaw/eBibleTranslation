# CCCPBible — 中英对照圣经 (CCC&TSPM CD-ROM) text extraction

Plain-text extraction of the four Bible versions bundled with the
**《中英对照圣经》CD-ROM 1.0** distributed by the China Christian Council &
Three-Self Patriotic Movement (中国基督教两会).

- **Source download:** <https://www.ccctspm.org/bibleload>
- **Installer build date:** 2005-04-08
- **Extracted:** 2026-09-20

---

## Extracted text

| File | Version | Verses |
|---|---|---|
| `和合本_新标点_简体.*` | 新标点和合本（简体字·神版）— Chinese Union Version with New Punctuation | 31,031 |
| `现代中文译本.*` | 现代中文译本 — Today's Chinese Version | 30,156 |
| `NRSV.*` | New Revised Standard Version | 31,103 |
| `GNT.*` | Good News Translation | 30,167 |
| `对照_CUNP-NRSV.*` | Parallel 和合本 / NRSV | 31,176 rows |

Each version ships in three formats:

- **`.txt`** — UTF-8. Book and chapter headers, then one verse per line as
  `chapter:verse<TAB>text`.
- **`.csv`** — UTF-8 with BOM (opens cleanly in Excel).
  Columns: `book_id, book_zh, book_en, chapter, verse, text`.
- **`.json`** — array of 66 book objects:
  `{id, name, english, chapters, verses:[{chapter, verse, text}]}`.

The parallel edition is `.txt` + `.csv` only. Its CSV columns are
`book_id, book_zh, book_en, chapter, verse, 和合本, NRSV`.

### Notes on the text

- **Versification.** 70 verses in the 和合本 are merged ranges (`民1:20-21`,
  `创24:29-30`, …). These are preserved verbatim in the `verse` field as
  `"20-21"` rather than split or renumbered.
- **Parallel alignment.** 30,941 verses align exactly between 和合本 and NRSV.
  The remaining 90 Chinese-only and 145 English-only rows are genuine
  versification differences between the two traditions — where one merges what
  the other splits. Unmatched cells are left blank; nothing is dropped.
- **神版 spacing.** The ideographic space (U+3000) that precedes 神 in the
  神版 convention is preserved (`起初　神创造天地。`). Strip it if your
  pipeline doesn't want it.
- **Completeness.** All 66 books, all chapters present, no empty verse rows.

---

## How the extraction worked

The download is a nested archive:

```
bible.EXE          RAR self-extracting archive, 23 MB
└── Setup.EXE      InstallShield 5.x installer (13 KB stub + 23.6 MB
                   compressed overlay — no CAB/ZIP inside, proprietary format)
```

The overlay can't be unpacked with standard tools, so the installer has to be
run. Once installed, the payload turns out to be unremarkable:

```
cbible/
├── cBible.exe             main application
├── Chn.dll / Eng.dll      UI resources
├── Unwise32.exe           uninstaller
└── data/
    ├── cBible.idx         book metadata, outlines, cross-references
    ├── Chinese/Cunp.idx   和合本      (Jet 4, Unicode)
    ├── Chinese/Tcv.idx    现代中文译本 (Jet 4, Unicode)
    ├── General/Cunp.idx   和合本      (Jet 3, GB2312)
    ├── General/Tcv.idx    现代中文译本 (Jet 3, GB2312)
    ├── NRSV.idx
    └── Gnt.idx
```

Despite the `.idx` extension, these are **Microsoft Access databases** — the
header reads `Standard Jet DB`. No encryption, no password. Each holds one
table per book (`genesis`, `exodus`, …) with columns `Id`, `Chpver`
(`"1:1"`), `Content`, plus parallel `P_*` tables carrying section headings and
paragraph groupings.

Read them with [mdbtools](https://github.com/mdbtools/mdbtools):

```bash
mdb-tables data/Chinese/Cunp.idx
mdb-export data/Chinese/Cunp.idx genesis | head

# Jet 3 files (data/General/*, cBible.idx) need an explicit charset:
MDB_JET3_CHARSET=cp936 mdb-export data/cBible.idx Volume
```

The `Chinese/` and `General/` folders hold the same text; the former is Jet 4
Unicode, the latter Jet 3 GB2312. These extractions used the Unicode copies.
Book names, canonical order and chapter counts come from the `Volume` table in
`cBible.idx`.

---

## Licensing

- **和合本 (CUV/CUNP)** — public domain. The 1919 translation's contributors
  died well before the relevant copyright terms expired.
- **现代中文译本** — © United Bible Societies.
- **NRSV** — © National Council of the Churches of Christ in the USA.
- **GNT** — © American Bible Society.

Extracting the copyrighted three from software you hold a license to is fine
for personal study and research, which is what they are here for: a published
translation to read a chapter of ours against when it needs checking. Nothing
in the pipeline reads any of them - the translation is made from the Hebrew
and the Greek, and these are for a person to compare it with afterwards.

**They are not redistributed.** What is committed from this folder is this
file and the three 和合本 extractions, which are public domain; the
现代中文译本, the NRSV, the GNT, the parallel file built from the NRSV, the
installers and the Access databases are all in `.gitignore` and stay on this
machine. The repository (`NewhopeLaw/eBibleTranslation`) is private in any
case, so nothing here is published; that is the position to keep, and adding
a collaborator would be the thing that changes it.

---

## Also in this folder

| File | What it is |
|---|---|
| `bible.EXE` | Original download from ccctspm.org |
| `Setup.EXE` | Installer, unpacked from the RAR layer |
| `圣经.rar` | |
| `聖經_(和合本).epub` | Wikisource CUV export — volunteer transcription, traditional characters, independent of this CD-ROM |
| `China Christian Network.url` | Shortcut to the download page |
| `cbible/` | Copy of the installed program (the original install remains at `C:\Program Files (x86)\cbible`) |
