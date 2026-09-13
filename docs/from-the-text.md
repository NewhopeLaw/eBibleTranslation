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

## Where things stand

*12 September 2026:* inventory at 3,649 of 80,894 forms; lexicon 1,080 of
16,967 entries and fields 1,080 of 16,967 (both on the reference lexeme set,
to be rerun); themes 391 of 1,189 chapters (unaffected). The dashboard's
work bar shows the live counts; `logs/work.jsonl` records what each call cost.
