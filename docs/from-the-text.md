# From the text: building the word layers from scratch

*Decided 12 September 2026.*

## The decision

Every layer that says what the words are and what they mean will be built from
the text by the model, from the bottom up — forms, then words, then lexemes,
then meaning — and nothing published will enter the chain. The layers we have
today, which rest on the STEPBible tagging (CC BY 4.0), are kept as a yardstick:
at each step, what we build is compared with what the reference says, and the
disagreements are reported and read before the next step is built on top.

The reference data never enters our layers. It checks them.

## Why

The project's principle is that the reading is drawn out of the text, not
inherited from a tradition — the translation, the themes and the lexicon are all
made that way already. The word layers were the exception: to get the interlinear,
the concordance and the lexicon working, `build_morph.py` took the lexeme set
and every word's parse from the STEPBible tags, and our lexicon, the fields of
meaning and the translated lexicons were then built on those. The lexeme
inventory (`build_lexemes.py`) was begun afterwards as the replacement
foundation, but nothing had been moved onto it. This plan finishes the move.

Building every step ourselves and checking each against the reference gives two
things the inherited layers cannot: a chain with no attributed data in it, and a
measured account of where a model reading the text on its own agrees with a
century of scholarship and where it does not.

## The steps, in order

Each step is a job that writes its results as it goes and resumes; each ends
with a comparison against the reference before the next begins.

1. **Forms → lexemes: the inventory.** `build_lexemes.py` — every distinct form
   (80,894) to the model in its verse; the dictionary word, part of speech,
   gloss and root. Running now at about 40 forms per 35 seconds, roughly 19
   hours in all. *Compare:* `--score` (agreement with the reference tag by
   token), plus a report of the disagreements sorted by frequency, so the common
   words are read first. Not yet written; it reads only `forms.jsonl`, so it can
   be written while the run continues.

2. **Words: the parse.** A second pass asks the model, for every word in every
   verse, for its grammatical parse (Hebrew: stem, form, person, gender, number,
   state; Greek: tense, voice, mood, case, person, number). The inventory gives
   only the dictionary word; this gives what the interlinear and the grammar
   search need. New script. *Compare:* per-feature agreement with the reference
   parse, again with the disagreements listed.

3. **The swap.** `build_morph.py` writes the per-book word tags, `lex.js` and
   `conc.js` from our inventory and our parse instead of from STEPBible. The
   concordance is derived from `FORM2LEX`. The reference tags remain available to
   the reader as "the reference says …" beside our own, and as the basis of the
   comparison pages.

4. **Lexemes → entries.** `build_lexicon.py` rerun over our lexeme set — entries
   are written per lexeme from its occurrences, so a new lexeme set means new
   entries. About 8 GPU hours for lexemes occurring ten times or more, 33 for
   all. *Compare:* gloss and sense against the reference brief lexicon.

5. **Meaning.** `build_domains.py` (fields of meaning) and `translate_lexicon.py`
   rerun over the new entries. *Compare:* field membership against the MACULA
   domains where they exist.

Themes, book arguments, trajectories, parallels, places and chronology do not
depend on the lexeme set and are untouched.

## What the method is, and what it is not

The order of the steps is the old order of philology: the text fixed, then its
grammar, then a lexicon written from usage, then fields of meaning — the
Masoretes, then Ḥayyuj and Kimḥi, then Gesenius and BDB, then Louw–Nida. Writing
each entry from the lexeme's occurrences rather than from its root is the
correction Barr pressed in 1961. The shape is sound. But scholarship has never
been built quite this way, and five differences should be kept in mind when the
comparisons are read.

1. **Scholarship is a circle, not a ladder.** A parse depends on what the word
   means and where it stands — homographs, the vav-consecutive, the Aramaic of
   Daniel and Ezra are settled from above as much as from below — and a revised
   meaning sends scholars back to revise the parse. Our chain runs one way; for
   now the comparison against the reference is the only thing that looks back
   down it.

2. **Scholarship reads outside the text.** The modern lexicons lean on the
   cognate languages (Ugaritic, Akkadian, Arabic), on the Septuagint and the
   other ancient versions, and on inscriptions. Reading from the text alone is
   closer to the medieval grammarians than to HALOT. It is a choice we have made,
   and the place it will show is the hapax legomena — some 1,500 words in the
   Hebrew Bible that occur once, many of which the text by itself cannot explain.
   Where our reading of one of those differs from the reference, the difference
   may be the method's limit rather than the model's error.

3. **The model is not free of the tradition.** It learned its Hebrew and Greek
   from BDB, Strong's, the commentaries and the English Bibles. When it agrees
   with the reference, some of that agreement is remembered, not found, so the
   agreement rate overstates what reading the text on its own would give. The
   disagreements are the more telling half of every comparison, and a high score
   is not by itself evidence that the method works.

4. **Scholarship keeps its doubts on the page.** Lexicons print *dub.*, *cf.* and
   rival derivations; critical editions carry an apparatus. Our layers hold one
   answer per form, and a confident wrong answer looks the same as a right one
   (אֵלֹנ is Hebrew, and is not a word). Where the model is unsure, or offers more
   than one reading, that is worth keeping.

5. **Scholarship establishes the text first.** Textual criticism comes before
   grammar. We take the Masoretic text as morphhb gives it, as most translations
   do and as the versification already does; that is a decision, not a neutral
   starting point.

## Decisions made

- The parse comes from the model, not from the reference (step 2), so the chain
  has no attributed data in it.
- Each step is compared before the next is built. A comparison is a report in
  `logs/` and, where it helps a reader, a page in the site — not a gate that
  copies anything across.
- The reply format of the inventory job may be made terser (arrays rather than
  keyed objects) to cut its output by a third; if so, the parser validates shape
  strictly and re-asks on a bad batch. Results already written stay.

## Open

- Whether to restart the inventory now for the terser format (a few minutes
  lost, several hours gained) or let the current run finish.
- The parse prompt and its batch shape (step 2) — to be designed once the
  inventory's disagreement report shows how the model handles the hard forms.
- Total cost after the inventory: on the order of 60–70 GPU hours, most of it
  the lexicon.
- A pass back down the chain: once entries and fields exist, whether to put the
  parses the model was least sure of back to it with the meaning and the
  context in hand, as a scholar would revise them.
- Whether the inventory and the parse should record the model's alternatives or
  its confidence alongside its answer, so that doubt is not flattened into a
  single reading.

## Where things stand

*12 September 2026:* inventory at 3,649 of 80,894 forms; lexicon 1,080 of
16,967 entries and fields 1,080 of 16,967 (both on the reference lexeme set,
to be rerun); themes 391 of 1,189 chapters (unaffected). The dashboard's
work bar shows the live counts; `logs/work.jsonl` records what each call cost.

*21 September 2026:* inventory at 24,089 of 80,894 forms and running (268,100
of the text's words covered, since the commonest forms went first). Every line
parses and no form is written twice, but 110 rows (0.46%) have another script
leaking into the lemma or the root — Arabic, Cyrillic, Chinese or Latin letters
inside a Hebrew word (`כiyor`, `رعى`) — and the job has no check that would
catch and re-ask them. They need one before step 3 builds on the inventory.
No step has landed yet: the comparison for step 1 is still to be written.

*21 September 2026, later:* the job has that check now, and the rows already
written have been mended. `build_lexemes.py` holds a lemma and a root to the
script of their language before a row is written, asks the bad ones again —
up to three times, in eights, then fours, then singly — and if a field is
still wrong writes it empty, says so in the row (`"emptied": ["root"]`) and in
`logs/lexemes_scripts.log`. `--check-scripts` counts the faulty rows without
asking anything; `--repair-scripts` asks them again and rewrites `forms.jsonl`
in place, row for row, and refuses to replace a file that grew while it worked.
It is for when the job is stopped.

Measured on the inventory as it stood with the job stopped, 27,568 forms: 310
rows at fault (1.12%) — 8 lemmas and 304 roots. That is more than the 110
first counted, because a root wholly in Latin letters is now counted too. The
prompt has always asked for the root in Hebrew; some three dozen early rows
carry a fair transliteration (`šwb`, `brk`), but most of what has come back in
Latin since is a word spelt out, not a root (`matteh`, `milchem`,
`sack(noroot`), so none of it is let through. After the repair: none at fault,
every row where it was, no row touched that was clean, and no lemma changed on
a row whose only fault was its root. Five roots are left empty and marked
(three forms of נחל, מִנְחָתָהּ, and the Aramaic זִמְנִין), to be asked again by a
later repair. On 41 more the model, asked again, said the word has no root —
its answer, not our blank.

One thing learned on the way, which the parse (step 2) should expect: the
fault is catching. A word that draws the model into transliterating — זְמָן came
back `zman` — takes the rest of its batch with it, forty Latin roots in a row,
and telling the model what it did wrong changed nothing while the batch stayed
the same. Asking the same forms in fours freed them. A first repair that
re-asked in one batch left 80 roots empty; re-asking in shrinking batches
left 5.

The check is about script, not about whether the answer is right: בְּאֵלֹנֵי now
has the lemma אֵלֹנ, which is Hebrew and is not a word. That is the comparison's
work, still to be written. The queue on the PC runs the copy of the job on
`main`, so the check takes effect when this change is merged there and the job
next started.

The search box now reaches the concordance, the lexicon, the fields and the
themes, from any translated language, by tracing a reader's word through the
verses it stands in to the Hebrew and Greek words behind them. That concordance
is still the reference's. It becomes ours at step 3, and until then our own
lexemes can be found by name but cannot be expanded into their verses.

*3 October 2026:* the inventory is finished, every one of the 80,894 forms,
and step 1's comparison is written. `build_lexemes.py --score` now writes
`logs/lexeme_report.md`, the disagreements commonest first, and
`logs/lexeme_disagreements.json`, the full lists for a page in the reader.

On 442,251 words of the text, 89.0% stand in a lexeme of ours whose usual
reference word is theirs; 94.5% once the letter STEPBible adds to cut one
Strong's number into senses is set aside. The ceiling is 95.1%: 5,114
spellings stand for more than one word, and an inventory that answers once per
spelling loses 4.9% of the text to them before the model says anything. That
is the method's limit, and the parse, which works word by word in its verse,
is where it can be won back.

The figure flatters, because it looks in one direction only. Our 27,037
lexemes against the reference's 16,967 means many words are split, and the
split is mostly the model not doing what its prompt asks:

- 12.4% of the text sits in a lexeme whose headword is a spelling from the
  text handed back as it stands (הַמֶּלֶךְ, וַיְהִי; the Greek article as ὁ, ἡ
  and τό apart).
- 4.0% has a prefix left on the headword (וְכָל, לְמֶלֶךְ), 2.4% an ending
  (אֵלָיו).
- 4.7% differs from its fellows only in pointing or accents (כָּל beside כֹּל).
- 4.6% is a different headword, often another inflected form (יִהְיֶה beside
  הָיָה).

Merges are rarer, 5.6% of the text in a lexeme that also holds a different
reference word. Some are plain errors (וַתָּשָׁב, "she returned", under יָשַׁב
"to dwell"; אֶל "to" under אֵל "god"); some are the lexicons' own choices
(εἶπον under λέγω, as most modern lexicons have it; לֵבָב under לֵב).

So step 1 is not ready to build on as it stands. Before step 3, the split
forms should go back to the model in their verse, with the fault named,
the way `--repair-scripts` re-asks a bad script; the pointing-only splits may
not need the model at all. The lexicon's translations into other languages
are held in the queue meanwhile (`work.py`, `held()`): they translate entries
that step 4 will rewrite.
