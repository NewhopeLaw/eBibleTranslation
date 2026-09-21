#!/usr/bin/env python3
"""Learn the proper names a language's readers already know, from a reference Bible.

Usage:
  build_names.py --lang zh --ref "CCCPBible/和合本_新标点_简体.json"
  build_names.py --lang zh --ref ... --write      write targets/zh/names.map.json

Why this exists
---------------
targets/<lang>/names.json holds a few dozen names and is pasted into every
prompt, so it cannot grow to the few thousand the Bible actually has. Every
other name is invented by the model, chapter by chapter, with no memory of the
last one - so Stephen is 司提反 in one chapter and 斯提反 in the next, and a
reader who knows the traditional Bible of their language meets a stranger.

The names that language's readers know are already written down, in the
translation they grew up with. This pairs our own English - the pivot, because
its proper names can be picked out mechanically - against that reference, and
learns the mapping from the two texts alone, with no list to maintain by hand.

How the pairing works
---------------------
A name is not a translation, it is a habit: it turns up in the same chapters in
both Bibles and almost nowhere else. So for each English name we take the set
of chapters it appears in, and for each candidate string in the reference the
same, and score the overlap (Dice). A name scores near 1; an ordinary word like
律法 is spread over the whole canon and scores near 0 against everything. The
filtering falls out of the measure, so no stop-list is needed.

For a language written without spaces there is the further question of where a
name starts and ends. It is bootstrapped: begin from the handful of names
already pinned in names.json, take the characters they are made of, read every
run of those characters out of the reference, and whenever a run sits next to
another character in the same place every time, that character belongs to the
name too. Three rounds is enough to go from the pinned names to a few thousand.

Nothing here is copied into the output: what is learned is a list of spellings,
which is a convention, and the reference text itself never leaves this machine.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, TARGETS, slug

ROOT = Path(__file__).resolve().parent.parent
PIVOT = "en"

# Capitalised words that open a sentence rather than name anyone.
STOP = {
    "The", "And", "But", "Then", "When", "Now", "For", "God", "Lord", "You",
    "Your", "They", "She", "His", "Her", "Him", "Its", "This", "That", "There",
    "These", "Those", "Let", "May", "All", "Who", "What", "Why", "How", "From",
    "Into", "After", "Before", "While", "Notes", "Chapter", "Yes", "See",
    "Look", "Listen", "Take", "Come", "Because", "Since", "Every", "Each",
    "Here", "Where", "With", "Behold", "Therefore", "Surely", "Indeed", "Woe",
    "Blessed", "Hear", "Speak", "Say", "Go", "Do", "Have", "Will", "Shall",
    "One", "Two", "Three", "Son", "Sons", "Daughter", "King", "Kings", "Priest",
    "Lord's", "So", "If", "As", "At", "In", "On", "By", "Of", "To",
    "It", "He", "We", "Our", "Their", "My", "Me", "I", "Us", "Am", "Is", "Are",
    "Was", "Were", "Be", "Been", "Not", "No", "Nor", "Or", "Yet", "Still",
    "Again", "Also", "Even", "Only", "Just", "Such", "Same", "Other", "Another",
}
WORD = re.compile(r"[A-Z][a-z]+(?:-[A-Z]?[a-z]+)*")
# The characters a transliteration can be written with. Han for Chinese;
# katakana for Japanese, where a foreign name is katakana and almost
# nothing else in the sentence is, which makes the names easy to see;
# the prolonged mark and the middle dot, which belong inside a Japanese
# name (ヨハネ, ペテロ, バル・テマイ) rather than separating words.
CJK = re.compile(r"[㐀-鿿ァ-ヺー・ก-๛가-힣]")


def pivot_chapters():
    """{(book, chapter, verse|None): {English names in it}} from our own English.

    A capital at the start of a sentence is not a name, and no stop-list is
    ever long enough to know which. The corpus says it instead: a real name is
    never written lower-case anywhere in the Bible, while Truly, Beloved and
    Honor all are. Anything that appears lower-case even once is dropped.
    """
    raw, lower = {}, Counter()
    for f in sorted((ROOT / "output" / PIVOT / "json").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        bk, ch = d["book"], int(d["chapter"])
        lower.update(w.lower() for w in re.findall(r"[A-Za-z][a-z]+", " ".join(d["verses"].values()))
                     if w[0].islower())
        raw[(bk, ch, None)] = {m.group() for m in WORD.finditer(" ".join(d["verses"].values()))}
        for n, t in d["verses"].items():
            raw[(bk, ch, str(n))] = {m.group() for m in WORD.finditer(t)}
    return {k: {n for n in v if n not in STOP and lower[n.lower()] == 0}
            for k, v in raw.items()}


def reference_chapters(path):
    """{(book, chapter, verse|None): text} from a reference Bible.

    Both the chapter and the single verses, because the twelve tribes are
    listed together in the same chapters and chapters alone cannot tell them
    apart. Verse numbering differs between the traditions in known places, so
    the verse rows are evidence where they line up and the chapter rows are
    what is left to fall back on.
    """
    alias = {"esther": "Esther", "Hebrew": "Hebrews", "Song of Solomon": "Song of Songs"}
    out = defaultdict(str)
    for b in json.loads(Path(path).read_text(encoding="utf-8")):
        name = alias.get(b["english"], b["english"])
        for v in b["verses"]:
            out[(name, v["chapter"], None)] += v["text"]
            out[(name, v["chapter"], str(v["verse"]))] = v["text"]
    return dict(out)


def seed_characters(lang):
    """The characters the already-pinned names are written with."""
    f = ROOT / "targets" / lang / "names.json"
    chars = set()
    for v in json.loads(f.read_text(encoding="utf-8"))["names"].values():
        for part in v.split("/"):
            chars.update(c for c in part.strip() if CJK.match(c))
    return chars


TOKEN = re.compile(r"[^\W\d_]+(?:[-‐-―'’][^\W\d_]+)*", re.UNICODE)
HANGUL = re.compile(r"[가-힣]")


def is_spaced(ref):
    """Does this language put spaces between its words?

    Chinese and Japanese do not, and a name has to be found by reading runs of
    the characters names are written with. Korean, Vietnamese and Persian do,
    and there the words are already marked out - which is better evidence, so
    it is used where it exists rather than guessed at.
    """
    sample = "".join(list(ref.values())[:300])
    return sample.count(" ") > len(sample) / 25


def candidates(text, chars, spaced):
    """The strings in this passage that could be a name."""
    if not spaced:
        return set(runs_of(text, chars))
    out = set()
    for m in TOKEN.finditer(text):
        w = m.group()
        if len(w) < 2:
            continue
        out.add(w)
        # Korean glues its grammar onto the end of a name - 모세가, 모세를,
        # 모세야 are all Moses - so the name is a prefix of the word rather
        # than the word. Every prefix is offered and the scoring decides: the
        # bare stem keeps company with all of them and wins on that.
        if HANGUL.match(w):
            for i in range(2, len(w)):
                out.add(w[:i])
    return out


def runs_of(text, chars, lo=2, hi=6):
    out, cur = [], []
    for ch in text + " ":
        if ch in chars:
            cur.append(ch)
        else:
            if lo <= len(cur) <= hi:
                out.append("".join(cur))
            cur = []
    return out


def grow_characters(ref, chars, rounds=4):
    """A character that always sits beside a name is part of the name.

    以法 turns up only ever followed by 莲, so 莲 is not the next word - it is
    the rest of 以法莲. Each round reads the runs out again with the larger
    alphabet, which lengthens them, which finds the next character along.

    The guard is frequency. 的, 说 and 人 follow a name often enough to look
    like part of one, and admitting a single common character floods every
    later round with ordinary prose. A character carried by the whole language
    cannot be a transliteration, so anything above a fraction of a percent of
    the reference is refused however well it scores.
    """
    freq = Counter()
    for text in ref.values():
        freq.update(c for c in text if CJK.match(c))
    total_chars = sum(freq.values())
    cap = 0.0025 * total_chars                  # above this it is a word of the language
    for _ in range(rounds):
        after, before, seen = Counter(), Counter(), Counter()
        for text in ref.values():
            pad = text + " "
            start = None
            for i, ch in enumerate(pad):
                if ch in chars:
                    if start is None:
                        start = i
                    continue
                if start is not None and 2 <= i - start <= 6:
                    run = pad[start:i]
                    seen[run] += 1
                    nxt, prv = pad[i:i + 1], pad[start - 1:start] if start else ""
                    if CJK.match(nxt or " "):
                        after[(run, nxt)] += 1
                    if CJK.match(prv or " "):
                        before[(run, prv)] += 1
                start = None
        added = set()
        for (run, ch), n in list(after.items()) + list(before.items()):
            if ch in chars or n < 5 or freq[ch] > cap:
                continue
            if n >= 0.95 * seen[run]:            # it is always there; it is part of the word
                added.add(ch)
        if not added:
            break
        chars |= added
    return chars


def learn(pivot, ref, chars, min_chapters, min_score, spaced=False):
    """Pair each English name with the reference string that shadows it."""
    eng_ch, eng_books = defaultdict(set), defaultdict(set)
    for key, names in pivot.items():
        if key not in ref:
            continue
        for n in names:
            eng_ch[n].add(key)
            if key[2] is None:                 # the chapter row, not its verses
                eng_books[n].add((key[0], key[1]))

    cand_ch = defaultdict(set)
    for key, text in ref.items():
        for run in candidates(text, chars, spaced):
            cand_ch[run].add(key)

    # Only compare things that could plausibly pair: walk chapter by chapter.
    pairs = Counter()
    for key, names in pivot.items():
        if key not in ref:
            continue
        cands = candidates(ref[key], chars, spaced)
        for n in names:
            # Distinct chapters, not rows. Both the chapter and each of its
            # verses are rows, so a name in one chapter of five verses looked
            # like six chapters' worth of evidence - which let the whole
            # wilderness itinerary of Numbers 33 in, where every stop is named
            # once, in one verse, beside forty others it can be confused with.
            if len(eng_books[n]) < min_chapters:
                continue
            for c in cands:
                pairs[(n, c)] += 1

    ranked = defaultdict(list)
    for (n, c), both in pairs.items():
        ranked[n].append((2 * both / (len(eng_ch[n]) + len(cand_ch[c])), c, both))

    best = {}
    for n, rows in ranked.items():
        # Equal evidence, longer string: a prefix of a name keeps exactly the
        # company the name does, so Môi would score as well as Môi-se.
        rows.sort(key=lambda r: (-r[0], -len(r[1]), r[1]))
        score, c, both = rows[0]
        if score < min_score:
            continue
        # Asher, Dan and Issachar are named in the same breath everywhere they
        # are named at all, so the best match for one of them is often another
        # one. When the winner is not clearly ahead of the next candidate the
        # evidence cannot tell them apart, and a wrong spelling in the prompt
        # is worse than none: it is dropped rather than guessed.
        runner = next((r[0] for r in rows[1:] if r[1] not in c and c not in r[1]), 0.0)
        if runner > 0.75 * score:
            continue
        best[n] = (c, score, both, len(eng_ch[n]))
    return best


def drop_impure(best, ref, cap_frac=0.0025):
    """Throw out anything made of ordinary words. NOT USED - see below.

    Tried and rejected: it takes 摩西 and 大流士 with it. A transliteration is
    not built from rare characters, only from characters used for their sound,
    and 西, 大 and 流 are among the commonest in the language. The filter drops
    more than half the names to remove a handful of phrases, so the phrases are
    left in and verify.py reports the disagreements for a person to judge.

    Kept here because the idea is an obvious one to have twice.

    The pairing measures which strings shadow a name, and a phrase that always
    surrounds one shadows it just as faithfully: Yahweh came back as
    起誓所应许, which is not a name but the clause it kept company with. A
    transliteration is built from characters the language otherwise has little
    use for, so every character of a learned name must be a rare one. This is
    the same frequency cap the alphabet was grown under, applied to the answer.
    """
    freq = Counter()
    for k, text in ref.items():
        if k[2] is None:
            freq.update(c for c in text if CJK.match(c))
    cap = cap_frac * sum(freq.values())
    return {n: row for n, row in best.items() if all(freq[c] <= cap for c in row[0])}


SUSPECT = re.compile(r"[aeiouAEIOUăâêôơư][ùøûõï]")


def drop_suspect(best):
    """Leave out a spelling the reference itself cannot be trusted on.

    The Vietnamese edition carries a pre-Unicode artifact: Aùp-ra-ham where
    every Vietnamese Bible prints Áp-ra-ham. The mapping looks obvious, but it
    cannot be checked - the corrected form appears nowhere in the text - and
    guessing at it would be guessing at 17 names. A vowel followed by one of
    those tone letters is not Vietnamese orthography, so those entries are
    dropped. A name the model is never given it can at least invent once;
    a name it is given wrongly it will write wrongly every time.
    """
    return {n: row for n, row in best.items() if not SUSPECT.search(row[0])}


def drop_collisions(best):
    """Two names that came out with one spelling are two guesses, not one fact.

    Cappadocia and Pontus are named in the same breath in Acts 2 and nowhere
    else, so the evidence cannot separate them and both came back as 多家 -
    which is neither of them. Where a spelling is claimed by two unrelated
    names, both are dropped. Jew and Jews, Israel and Israelite share a
    spelling honestly, and share a stem to prove it.
    """
    by_form = defaultdict(list)
    for n, row in best.items():
        by_form[row[0]].append(n)
    out = {}
    for form, names in by_form.items():
        if len(names) > 1:
            stem = min(len(a) for a in names)
            same = all(a[:4].lower() == names[0][:4].lower() for a in names) and stem >= 4
            if not same:
                continue
        for n in names:
            out[n] = best[n]
    return out


def untruncate(best, ref):
    """Give back the characters the run-reading cut off.

    The alphabet is grown until it stops growing, and one round short of the
    end leaves 逾越节 as 越节 - a string that is not the name and would teach
    the model to write half of it. Whatever always stands next to a learned
    name in the reference belongs to it, so it is put back, however common
    that character is elsewhere.
    """
    text = "\n".join(v for k, v in ref.items() if k[2] is None)
    fixed = {}
    for n, (c, score, both, tot) in best.items():
        for _ in range(3):
            hits = [m.start() for m in re.finditer(re.escape(c), text)]
            if len(hits) < 5:
                break
            nxt = Counter(text[i + len(c)] for i in hits if i + len(c) < len(text))
            prv = Counter(text[i - 1] for i in hits if i)
            ch, k = (nxt.most_common(1) or [(None, 0)])[0]
            if ch and CJK.match(ch) and k >= 0.95 * len(hits):
                c = c + ch
                continue
            ch, k = (prv.most_common(1) or [(None, 0)])[0]
            if ch and CJK.match(ch) and k >= 0.95 * len(hits):
                c = ch + c
                continue
            break
        fixed[n] = (c, score, both, tot)
    return fixed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", required=True, help="target code, e.g. zh")
    ap.add_argument("--ref", required=True, action="append",
                    help="reference Bible .json in that language; repeat it to use more than "
                         "one, and an earlier one wins where they disagree")
    ap.add_argument("--min-chapters", type=int, default=3,
                    help="ignore names appearing in fewer chapters than this (default 3)")
    ap.add_argument("--min-score", type=float, default=0.55,
                    help="Dice overlap a pairing must reach to be believed (default 0.55)")
    ap.add_argument("--write", action="store_true", help="write targets/<lang>/names.map.json")
    a = ap.parse_args()
    if a.lang not in TARGETS:
        raise SystemExit(f"unknown target language {a.lang!r}")

    pivot = pivot_chapters()
    # Where a language has more than one reference worth reading, each is
    # learned from on its own and the first one given wins. Japanese needs
    # this: the only complete public-domain Bible is a new one whose Greek
    # and Latin names are not the ones readers know (アジア for アジヤ), while
    # the translation that does keep them is the New Testament alone.
    best, chars = {}, set()
    for path in a.ref:
        ref = reference_chapters(path)
        shared = sum(1 for k in pivot if k in ref)
        print(f"pivot ({PIVOT}) {len(pivot)} rows, {Path(path).name} {len(ref)}, shared {shared}")
        spaced = is_spaced(ref)
        mine = set() if spaced else grow_characters(ref, set(seed_characters(a.lang)))
        chars |= mine
        found = learn(pivot, ref, mine, a.min_chapters, a.min_score, spaced)
        if not spaced:                     # run-reading can cut a name short; tokens cannot
            found = untruncate(found, ref)
        found = drop_collisions(drop_suspect(found))
        print(f"  ({'words are spaced' if spaced else 'no spaces: reading character runs'})")
        print(f"  {Path(path).name}: {len(found)} names")
        for n, row in found.items():
            best.setdefault(n, row)               # the first reference given keeps the name
    ref = reference_chapters(a.ref[-1])           # the fullest one, for the report below
    print(f"names paired: {len(best)}")

    # Does it recover what we already knew? names.json was written by hand and
    # is the only ground truth there is, so the learner is checked against it
    # before anything it says about the rest is believed.
    pinned = json.loads((ROOT / "targets" / a.lang / "names.json").read_text(encoding="utf-8"))["names"]
    known = {v.strip() for val in pinned.values() for v in val.split("/")}
    got = {c for c, *_r in best.values()}
    hit = len(known & got)
    print(f"sanity: recovers {hit}/{len(known)} of the spellings pinned by hand in names.json")

    # How much of this does our own translation already agree with?
    ours = {}
    for f in sorted((ROOT / "output" / a.lang / "json").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        ours[(d["book"], int(d["chapter"]))] = "".join(d["verses"].values())
    agree = disagree = 0
    examples = []
    for n, (c, score, both, tot) in sorted(best.items(), key=lambda kv: -kv[1][3]):
        hit = sum(1 for k, names in pivot.items()
                  if k[2] is None and n in names and c in ours.get((k[0], k[1]), ""))
        seen = sum(1 for k, names in pivot.items()
                   if k[2] is None and n in names and (k[0], k[1]) in ours)
        if not seen:
            continue
        if hit >= 0.9 * seen:
            agree += 1
        else:
            disagree += 1
            if len(examples) < 30:
                examples.append((tot, n, c, hit, seen))
    print(f"\nour {a.lang} already uses the reference spelling for {agree} of {agree + disagree}")
    print(f"drifts from the reference in {disagree}:")
    for tot, n, c, hit, seen in sorted(examples, reverse=True)[:25]:
        print(f"   {n:<18} reference {c:<8} ours uses it in {hit:>3}/{seen:<3} chapters")

    if a.write:
        out = ROOT / "targets" / a.lang / "names.map.json"
        payload = {
            "_comment": (f"English name -> {TARGETS[a.lang]['name']} spelling, learned from a reference "
                         "Bible by scripts/build_names.py. Injected per chapter by translate.py, not "
                         "wholesale: only the names in the chapter being translated go into the prompt. "
                         "Spellings are a convention, not text: no reference wording is reproduced."),
            "_source": [Path(r).name for r in a.ref],
            "_pairs": len(best),
            "names": {n: c for n, (c, *_r) in sorted(best.items())},
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwrote {out} ({len(best)} names)")


if __name__ == "__main__":
    main()
