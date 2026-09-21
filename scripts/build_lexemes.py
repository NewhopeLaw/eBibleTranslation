#!/usr/bin/env python3
"""Our own lexeme inventory, grown from the text by the local model.

    python scripts/build_lexemes.py --limit 400        # a first pass over the commonest forms
    python scripts/build_lexemes.py                    # every form, resuming
    python scripts/build_lexemes.py --pack             # consolidate and write site/morph/lexemes.js
    python scripts/build_lexemes.py --score            # how far our inventory agrees with the reference tagging
    python scripts/build_lexemes.py --check-scripts    # how many rows have another alphabet in the lemma or root
    python scripts/build_lexemes.py --repair-scripts   # ask those rows again (only while the job is stopped)

Rather than inherit a lexeme list from a published dictionary, this grows one
from the text: every distinct word form in the Hebrew, Aramaic and Greek is put
to qwen3:32b in context, and the model gives the dictionary form it belongs to,
the part of speech, a gloss and (for Hebrew) the consonantal root. Forms that
answer with the same dictionary form become one lexeme. Lexemes are then
numbered in order of first appearance in the canon — eH0001, eG0001 and so on —
so the numbering is stable, reproducible and ours.

81,000 distinct forms, batched; roughly four to six hours on one GPU. Every
answer is written as it is made, so the run resumes.

Every answer is checked before it is written: a lemma or a root with another
alphabet in it is asked again, and if it is still wrong the field is left empty
and the row says so ("emptied": ["root"]), as does logs/lexemes_scripts.log.
Such a row counts as done, so the run does not keep returning to it;
--repair-scripts does.

    site/morph/lexemes.js:
        LEXEME = {id: [headword, pos, gloss, root, count]}
        FORM2LEX = {surface form: id}

--score compares our grouping with the STEPBible lemma tags we already hold
(CC BY 4.0). That is a yardstick only: no tag is copied into our inventory.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                     # noqa: E402
import manifest                                       # noqa: E402
from books import BOOKS, slug                             # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NORM = ROOT / "sources" / "normalized"
MORPH = ROOT / "site" / "morph"
DIR = ROOT / "targets" / "lexemes"
FORMS = DIR / "forms.jsonl"

SYSTEM_HE = """You are building a dictionary of Biblical Hebrew and Aramaic from the text itself.

For each numbered word form you are given — with the verse it stands in — say which dictionary word it belongs to.

Reply with JSON only:
{"1": {"lemma": "the dictionary form, pointed, in Hebrew script", "pos": "noun|verb|adjective|adverb|preposition|conjunction|pronoun|particle|numeral|proper noun", "gloss": "one to three English words", "root": "the three consonants of the root, in Hebrew, or \\"\\" if it has none"}, "2": {...}}

Rules:
- The lemma is the form a dictionary would list: verbs as the 3rd masculine singular perfect (Qal where possible), nouns in the absolute singular, adjectives masculine singular.
- Strip prefixes and suffixes that are not part of the word: the conjunction, the article, prepositions joined to the word, and pronominal endings. The lemma is what remains.
- Aramaic words are treated the same way; say so in the gloss if the word is Aramaic.
- A proper noun's lemma is the name itself.
- Judge from the verse in front of you. Where a form could belong to two different words, choose the one the verse requires.
- Never invent a form you cannot see. Give every numbered item an answer.

Worked examples:
- בְּרֵאשִׁית -> lemma רֵאשִׁית (noun, "beginning", root ראשׁ): the בְּ is a preposition, not part of the word.
- וַיֹּאמֶר -> lemma אָמַר (verb, "to say", root אמר): strip the conjunction and the prefix of the imperfect.
- פְּנֵי -> lemma פָּנִים (noun, "face", root פנה): this is the construct of a plural noun, not a word of its own.
- אֹתָם -> lemma אֵת (particle, object marker): the ־ָם is a pronominal suffix, "them".
- הָאָרֶץ -> lemma אֶרֶץ (noun, "land, earth", root ארץ): strip the article.
- מִמִּצְרַיִם -> lemma מִצְרַיִם (proper noun, "Egypt"): strip the preposition מִן.
Check yourself: if the lemma you were about to give is the form exactly as it stands, and the form carries a prefix, a suffix or a construct ending, think again."""

SYSTEM_GR = """You are building a dictionary of Koine Greek from the text itself.

For each numbered word form you are given — with the verse it stands in — say which dictionary word it belongs to.

Reply with JSON only:
{"1": {"lemma": "the dictionary form in Greek script", "pos": "noun|verb|adjective|adverb|preposition|conjunction|pronoun|particle|numeral|article|proper noun", "gloss": "one to three English words", "root": ""}, "2": {...}}

Rules:
- The lemma is the form a dictionary would list: verbs in the present active indicative first singular (or the form actually used as the head word for deponents), nouns in the nominative singular, adjectives in the masculine nominative singular.
- Keep the article as its own word.
- A proper noun's lemma is the name itself.
- Judge from the verse in front of you. Where a form could belong to two different words, choose the one the verse requires.
- Never invent a form you cannot see. Give every numbered item an answer.

Worked examples:
- λόγου -> lemma λόγος (noun, "word").
- ἐποίησεν -> lemma ποιέω (verb, "to make, do").
- τῷ -> lemma ὁ (article, "the").
- ἡμῖν -> lemma ἐγώ (pronoun, "I, we").
- ἐγένετο -> lemma γίνομαι (verb, "to become, happen").
Check yourself: if the lemma you were about to give is the inflected form as it stands, think again — give the form a dictionary would print."""


def tokens(text):
    out, cur = [], ""
    for c in text:
        if unicodedata.category(c)[0] in "LMN" or (c in "’ʼ'" and cur):
            cur += c
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def collect():
    """-> {'he'|'gr': {form: [count, (book, ch, v, text), first_order]}}"""
    data = {"he": {}, "gr": {}}
    order = 0
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        f = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
        if not f.exists():
            continue
        lang = "gr" if meta["testament"] == "NT" else "he"
        chapters = json.loads(f.read_text(encoding="utf-8"))["chapters"]
        for ch in sorted(chapters, key=int):
            for rec in chapters[ch]:
                for w in tokens(rec["text"]):
                    order += 1
                    d = data[lang].get(w)
                    if d:
                        d[0] += 1
                    else:
                        data[lang][w] = [1, (meta["name"], int(ch), rec["v"], rec["text"]), order]
    return data


def call(system, user):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": 0.1},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())
    T.log_work(resp, time.time() - t0, "lexemes")
    return json.loads(resp.get("message", {}).get("content", "{}"))


def norm_lemma(s):
    return unicodedata.normalize("NFC", re.sub(r"\s+", "", str(s or ""))).strip("־-,.;:!?()[]{}\"'")


# The model is multilingual and now and then its hand slips into another
# alphabet half way through a word: כiyor for כִּיּוֹר, the root of הָרֹעִים given as
# the Arabic رعى, a Korean gloss where the root should stand. About one row in
# two hundred. A lemma like that becomes a lexeme nobody can find, so a lemma
# and a root must be written wholly in the script of their language, and
# anything else is asked again.
#
# A root in Latin letters is refused as well. A few early rows carry a fair
# transliteration (šwb, brk), but the prompt has always asked for Hebrew, and
# most of what came back in Latin since is not a root at all but a word spelt
# out - matteh, milchem, sack(noroot. The full stop is let through because the
# model sometimes writes a root the way the grammars do, ש.מ.ע.
SCRIPT = {"he": ((0x0590, 0x05FF), (0xFB1D, 0xFB4F)),
          "gr": ((0x0370, 0x03FF), (0x1F00, 0x1FFF), (0x0300, 0x036F))}
JOINERS = " ,־-.’ʼ'"
# A word that draws the model into transliterating draws its neighbours in with
# it: זְמָן at the head of a batch came back zman, and the thirty-nine roots after
# it came back in Latin too, whatever the re-ask said. What frees them is
# smaller company, so each re-ask puts the bad rows in smaller batches than the
# last - eights, then fours, then one at a time.
REASK = (8, 4, 1)
BAD_LOG = ROOT / "logs" / "lexemes_scripts.log"
AGAIN = ("\n\nYour last answer for these put letters of another alphabet into the lemma or the root. "
         "Write both in {script} script only, every letter of them — no transliteration, no other language.")


def stray(s, lang):
    """The characters of s that do not belong in a word of this language; "" when it is clean."""
    return "".join(c for c in s if c not in JOINERS
                   and not any(lo <= ord(c) <= hi for lo, hi in SCRIPT[lang]))


def faults(row):
    """Which of a row's fields have another script in them."""
    return [k for k in ("lemma", "root") if stray(row.get(k) or "", row["lang"])]


def ask(lang, chunk, again=False):
    """One batch to the model -> {form: row}. The shape is checked here: an
    answer that is not an object, or has no lemma, is left out, and its form
    stays unanswered."""
    lines = []
    for i, (_, form, count, ctx) in enumerate(chunk, 1):
        book, ch, v, text = ctx
        lines.append(f"{i}. {form}   ({count}×)\n   {book} {ch}:{v} — {text}")
    user = "\n".join(lines) + "\n\nGive the dictionary word for each."
    if again:
        user += AGAIN.format(script="Hebrew" if lang == "he" else "Greek")
    got = call(SYSTEM_HE if lang == "he" else SYSTEM_GR, user)
    rows = {}
    for i, (_, form, count, ctx) in enumerate(chunk, 1):
        r = got.get(str(i)) if isinstance(got, dict) else None
        if not isinstance(r, dict) or not norm_lemma(r.get("lemma")):
            continue
        rows[form] = {"form": form, "lang": lang, "count": count,
                      "lemma": norm_lemma(r.get("lemma")), "pos": str(r.get("pos") or ""),
                      "gloss": str(r.get("gloss") or ""), "root": norm_lemma(r.get("root"))}
    return rows


def analyse(lang, chunk):
    """A batch asked, checked for script, and its bad rows asked again on their
    own, told what was wrong, in the smaller and smaller batches of REASK. A
    row that is still wrong after that is kept with the offending field
    emptied: an empty root is a gap, a wrong one is a mistake someone has to
    find. -> {form: row}; raises what the first call raises."""
    rows = ask(lang, chunk)
    for size in REASK:
        bad = [c for c in chunk if c[1] in rows and faults(rows[c[1]])]
        for start in range(0, len(bad), size):
            try:
                fresh = ask(lang, bad[start:start + size], again=True)
            except Exception as ex:                        # noqa: BLE001
                print(f"  re-ask of {len(bad[start:start + size])} forms: FAILED {ex}", file=sys.stderr)
                continue
            for form, r in fresh.items():
                if len(faults(r)) < len(faults(rows[form])):   # never trade a bad answer for a worse one
                    rows[form] = r
    for r in rows.values():
        empty(r)
    return rows


def empty(row):
    """Blank whatever is still in the wrong script, and say so in the row and in
    the log. The row carries the note itself - "emptied": ["root"] - because an
    empty root is otherwise what a word without a root looks like, and
    --repair-scripts could not tell which ones to come back to."""
    for k in faults(row):
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} {row['form']}: {k} {row[k]!r} "
                f"is not in its own script after {len(REASK)} re-asks; left empty")
        print("  " + line, file=sys.stderr)
        try:
            BAD_LOG.parent.mkdir(exist_ok=True)
            with BAD_LOG.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as e:                                # a log must never stop a job
            print(f"    scripts log: {e}", file=sys.stderr)
        row[k] = ""
        row["emptied"] = sorted(set(row.get("emptied", [])) | {k})
    return row


def read_forms():
    return [json.loads(line) for line in FORMS.read_text(encoding="utf-8").splitlines() if line.strip()]


def wanting(row):
    """The fields a repair would ask again: those with another script in them,
    and those already emptied for it."""
    return sorted(set(faults(row)) | set(row.get("emptied", [])))


def repair(batch, dry=False):
    """Ask again the rows already written with another script in them, and
    rewrite forms.jsonl with every row where it was. The job appends to that
    file, so this must not run beside it: the size is taken at the start and
    checked before the new file replaces the old, and if anything was added in
    between the repair is dropped rather than lose those rows."""
    if not FORMS.exists():
        print("lexemes: no forms.jsonl to repair")
        return
    size = FORMS.stat().st_size
    rows = read_forms()
    bad = [r for r in rows if wanting(r)]
    wrong = [r for r in bad if faults(r)]
    by_field = Counter(k for r in wrong for k in faults(r))
    print(f"lexemes: {len(rows)} rows, {len(wrong)} with another script in the lemma or root "
          f"({100 * len(wrong) / max(1, len(rows)):.2f}%: lemma {by_field['lemma']}, root {by_field['root']}), "
          f"{len(bad) - len(wrong)} with a field emptied for it")
    if dry or not bad:
        return
    data = collect()
    todo = []
    for r in bad:
        d = data[r["lang"]].get(r["form"])
        if d:
            todo.append((r["lang"], r["form"], d[0], d[1]))
    fixed = {}
    t0 = time.time()
    for lang in ("he", "gr"):
        mine = [c for c in todo if c[0] == lang]
        for start in range(0, len(mine), batch):
            try:
                fixed.update(analyse(lang, mine[start:start + batch]))
            except Exception as ex:                            # noqa: BLE001
                print(f"  batch at {start}: FAILED {ex}", file=sys.stderr)
            print(f"  {len(fixed)}/{len(todo)} forms asked again [{(time.time() - t0) / 60:.1f} min]", flush=True)
    # Where only the root was wrong, only the root is taken from the new answer:
    # the lemma that was already there is what other rows were grouped with. A
    # wrong lemma takes the whole new row, since the rest was said of that lemma.
    # A form the model would not answer this time keeps its old row, but not the
    # letters that were wrong in it.
    out, changed = [], 0
    for r in rows:
        new, want = fixed.get(r["form"]), wanting(r)
        if new and want:
            if "lemma" in want:
                r = new
            else:
                r = {k: v for k, v in dict(r, root=new["root"]).items() if k != "emptied"}
                if "root" in new.get("emptied", []):
                    r["emptied"] = ["root"]
            changed += 1
        out.append(empty(r))
    tmp = FORMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:             # as the job writes it, line for line
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    if FORMS.stat().st_size != size:
        tmp.unlink()
        print("lexemes: forms.jsonl grew while the repair ran — a job is writing to it. Nothing replaced; "
              "stop the job and run the repair again.", file=sys.stderr)
        sys.exit(1)
    tmp.replace(FORMS)
    print(f"lexemes: {changed} rows rewritten; {sum(1 for r in out if faults(r))} still with another script, "
          f"{sum(1 for r in out if r.get('emptied'))} with a field left empty")


def pack(score=False):
    data = collect()
    answers = {}
    if FORMS.exists():
        for line in FORMS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                answers[r["form"]] = r
    # group forms by the dictionary form the model gave them, in order of first appearance
    groups, order_of = {}, {}
    for lang in ("he", "gr"):
        for form, (count, _, order) in data[lang].items():
            a = answers.get(form)
            if not a or not a.get("lemma"):
                continue
            key = (lang, norm_lemma(a["lemma"]))
            g = groups.setdefault(key, {"forms": [], "count": 0, "pos": Counter(), "gloss": Counter(), "root": Counter()})
            g["forms"].append(form)
            g["count"] += count
            g["pos"][a.get("pos", "")] += count
            g["gloss"][(a.get("gloss") or "").strip()] += count
            g["root"][(a.get("root") or "").strip()] += count
            order_of[key] = min(order_of.get(key, 1 << 60), order)
    lexeme, form2lex = {}, {}
    counters = {"he": 0, "gr": 0}
    for key in sorted(groups, key=lambda k: order_of[k]):
        lang, head = key
        counters[lang] += 1
        lid = ("eH" if lang == "he" else "eG") + f"{counters[lang]:05d}"
        g = groups[key]
        lexeme[lid] = [head, g["pos"].most_common(1)[0][0], g["gloss"].most_common(1)[0][0],
                       g["root"].most_common(1)[0][0], g["count"]]
        for form in g["forms"]:
            form2lex[form] = lid
    MORPH.mkdir(parents=True, exist_ok=True)
    (MORPH / "lexemes.js").write_text(
        "LEXEME=" + json.dumps(lexeme, ensure_ascii=False, separators=(",", ":")) + ";\n"
        + "FORM2LEX=" + json.dumps(form2lex, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    manifest.record("lexeme-inventory", len(lexeme), "dictionary words", "our own lexeme inventory", "build_lexemes.py")
    print(f"lexemes: {len(lexeme)} dictionary words from {len(form2lex)} forms "
          f"({counters['he']} Hebrew/Aramaic, {counters['gr']} Greek) -> site/morph/lexemes.js")
    if score:
        report(form2lex)


def report(form2lex):
    """How often our grouping matches the reference tagging, token by token."""
    agree = total = 0
    pairs = defaultdict(Counter)
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        mf = MORPH / f"{slug(meta['name'])}.js"
        nf = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
        if not mf.exists() or not nf.exists():
            continue
        s = mf.read_text(encoding="utf-8")
        M = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";\n").rstrip(";"))
        chapters = json.loads(nf.read_text(encoding="utf-8"))["chapters"]
        for ch in chapters:
            for rec in chapters[ch]:
                tags = (M.get(ch) or {}).get(str(rec["v"])) or []
                for i, w in enumerate(tokens(rec["text"])):
                    ours = form2lex.get(w)
                    ref = tags[i] if i < len(tags) and tags[i] else None
                    if not ours or not ref:
                        continue
                    m = re.search(r"\{([^}]+)\}", ref[0])
                    reftag = m.group(1) if m else ref[0].split("/")[0]
                    pairs[ours][reftag] += 1
                    total += 1
    for ours, c in pairs.items():
        agree += c.most_common(1)[0][1]
    lines = ["# Our lexeme inventory against the reference tagging", "",
             f"- tokens compared: {total}",
             f"- tokens whose lexeme maps to that lexeme's most common reference tag: {agree} ({100 * agree / max(1, total):.1f}%)",
             f"- our lexemes: {len(pairs)}", "",
             "A lexeme that always lands on the same reference tag is a clean split; the figure is a",
             "measure, not a target. The reference tagging is STEPBible's (CC BY 4.0) and is used here",
             "only to score our own inventory; none of it is copied into it.", ""]
    (ROOT / "logs" / "lexeme_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:5]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new forms")
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--sample", type=int, default=0, help="take an evenly spread sample instead of the commonest forms")
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--pack", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--check-scripts", action="store_true", help="count the rows with another script in the lemma or root; asks nothing")
    ap.add_argument("--repair-scripts", action="store_true", help="ask those rows again and rewrite forms.jsonl; not while the job is running")
    a = ap.parse_args()
    DIR.mkdir(parents=True, exist_ok=True)
    if a.check_scripts or a.repair_scripts:
        repair(a.batch, dry=not a.repair_scripts)
        return
    if a.pack or a.score:
        pack(score=a.score)
        return
    data = collect()
    done = set()
    if FORMS.exists():
        for line in FORMS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["form"])
    todo = []
    for lang in ("he", "gr"):
        for form, (count, ctx, _) in sorted(data[lang].items(), key=lambda kv: -kv[1][0]):
            if count >= a.min_count and form not in done:
                todo.append((lang, form, count, ctx))
    if a.sample:
        step = max(1, len(todo) // a.sample)
        todo = todo[::step][:a.sample]
    if a.limit:
        todo = todo[:a.limit]
    print(f"lexemes: {len(done)} forms analysed, {len(todo)} to do, batches of {a.batch} (model {T.CONFIG['model']})")
    t0, n = time.time(), 0
    with FORMS.open("a", encoding="utf-8") as fh:
        for start in range(0, len(todo), a.batch):
            chunk = todo[start:start + a.batch]
            lang = chunk[0][0]
            chunk = [c for c in chunk if c[0] == lang]          # never mix languages in one batch
            try:
                rows = analyse(lang, chunk)
            except Exception as ex:                                # noqa: BLE001
                print(f"  batch at {start}: FAILED {ex}", file=sys.stderr)
                continue
            for _, form, _, _ in chunk:
                if form in rows:
                    fh.write(json.dumps(rows[form], ensure_ascii=False) + "\n")
                    n += 1
            fh.flush()
            el = time.time() - t0
            print(f"  {n}/{len(todo)} forms [{el / max(1, n):.2f}s each, {el / 60:.1f} min]", flush=True)
    pack()


if __name__ == "__main__":
    main()
