#!/usr/bin/env python3
"""Our own lexeme inventory, grown from the text by the local model.

    python scripts/build_lexemes.py --limit 400        # a first pass over the commonest forms
    python scripts/build_lexemes.py                    # every form, resuming
    python scripts/build_lexemes.py --pack             # consolidate and write site/morph/lexemes.js
    python scripts/build_lexemes.py --score            # how far our inventory agrees with the reference tagging

Rather than inherit a lexeme list from a published dictionary, this grows one
from the text: every distinct word form in the Hebrew, Aramaic and Greek is put
to qwen3:32b in context, and the model gives the dictionary form it belongs to,
the part of speech, a gloss and (for Hebrew) the consonantal root. Forms that
answer with the same dictionary form become one lexeme. Lexemes are then
numbered in order of first appearance in the canon — eH0001, eG0001 and so on —
so the numbering is stable, reproducible and ours.

81,000 distinct forms, batched; roughly four to six hours on one GPU. Every
answer is written as it is made, so the run resumes.

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
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(json.loads(r.read()).get("message", {}).get("content", "{}"))


def norm_lemma(s):
    return unicodedata.normalize("NFC", re.sub(r"\s+", "", str(s or ""))).strip("־-,.;:!?()[]{}\"'")


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
    a = ap.parse_args()
    DIR.mkdir(parents=True, exist_ok=True)
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
            lines = []
            for i, (_, form, count, ctx) in enumerate(chunk, 1):
                book, ch, v, text = ctx
                lines.append(f"{i}. {form}   ({count}×)\n   {book} {ch}:{v} — {text}")
            try:
                got = call(SYSTEM_HE if lang == "he" else SYSTEM_GR, "\n".join(lines) + "\n\nGive the dictionary word for each.")
            except Exception as ex:                                # noqa: BLE001
                print(f"  batch at {start}: FAILED {ex}", file=sys.stderr)
                continue
            for i, (_, form, count, ctx) in enumerate(chunk, 1):
                r = got.get(str(i)) or {}
                if not isinstance(r, dict) or not norm_lemma(r.get("lemma")):
                    continue
                fh.write(json.dumps({"form": form, "lang": lang, "count": count,
                                     "lemma": norm_lemma(r.get("lemma")), "pos": str(r.get("pos") or ""),
                                     "gloss": str(r.get("gloss") or ""), "root": norm_lemma(r.get("root"))},
                                    ensure_ascii=False) + "\n")
                n += 1
            fh.flush()
            el = time.time() - t0
            print(f"  {n}/{len(todo)} forms [{el / max(1, n):.2f}s each, {el / 60:.1f} min]", flush=True)
    pack()


if __name__ == "__main__":
    main()
