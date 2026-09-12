#!/usr/bin/env python3
"""Morphology layer for the reader: every Hebrew, Aramaic and Greek word tagged.

    python scripts/build_morph.py            # -> site/morph/*.js + logs/morph_report.md

Reads the STEPBible data (CC BY 4.0, sources/STEPBible-Data): the Translators
Amalgamated Hebrew OT (TAHOT: Leningrad text via OSHB, Extended Strong's tags,
ETCBC/OpenScriptures morphology, glosses) and Greek NT (TAGNT: every word of
the major editions with the editions that contain it, so the SBLGNT word
sequence can be selected), the brief lexicons (TBESH, TBESG) and the
morphology-code expansions (TEHMC, TEGMC). Aligns the tagged words to the
verse text in sources/normalized/ (same tokenizer as the reader page) and
writes, for lazy loading by <script src>, which works from file:// and inside
an Android asset bundle:

    site/morph/<Book>.js   MORPH["Book"] = {ch: {v: [[tags, morph, gloss, translit], ...]}}   one entry per token, null if unaligned
    site/morph/lex.js      LEX = {strong: [headword, translit, pos, gloss, meaning]}, MORPHX = {code: phrase}
    site/morph/conc.js     CONC = {strong: [[bookNum, ch, v, tokenIdx], ...]}

The data is reformatted, not redistributed as STEPBible's files; the reader
credits STEPBible / Tyndale House and links to github.com/STEPBible.
"""
import difflib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STEP = ROOT / "sources" / "STEPBible-Data"
TA = STEP / "Translators Amalgamated OT+NT"
OUT = ROOT / "site" / "morph"
NORM = ROOT / "sources" / "normalized"

TAHOT_FILES = ["TAHOT Gen-Deu", "TAHOT Jos-Est", "TAHOT Job-Sng", "TAHOT Isa-Mal"]
TAGNT_FILES = ["TAGNT Mat-Jhn", "TAGNT Act-Rev"]
ORDER = [c for c, m in sorted(BOOKS.items(), key=lambda x: x[1]["num"])]
OT, NT = ORDER[:39], ORDER[39:]


def find(prefix):
    return next(TA.glob(prefix + "*.txt"))


# ------------------------------------------------------------ tokenizer (mirrors the page's regex: runs of L/M/N joined across ' or ’)
def is_word_char(c):
    return unicodedata.category(c)[0] in "LMN"


def tokens(text):
    out, i, n = [], 0, len(text)
    while i < n:
        if not is_word_char(text[i]):
            i += 1
            continue
        j = i
        while j < n and (is_word_char(text[j]) or (text[j] in "'\u2019" and j + 1 < n and is_word_char(text[j + 1]))):
            j += 1
        out.append(text[i:j])
        i = j
    return out


def skeleton(w):
    """Consonants/base letters only, lower case: what two spellings of one word share."""
    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c)[0] == "L").lower()


# ------------------------------------------------------------ STEPBible parsers
REF = re.compile(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)(?:\((\d+)\.(\d+)\))?#(\d+)=(\S*)")


def parse_ref(field):
    m = REF.match(field)
    if not m:
        return None
    code, ech, ev, hch, hv, n, typ = m.groups()
    ch, v = (int(hch), int(hv)) if hch else (int(ech), int(ev))   # Hebrew versification when it differs
    return code, ch, v, int(n), typ


def load_tahot():
    """-> {stepcode: {ch: {v: [word, ...]}}}, word = dict(surface, translit, gloss, tags, morph)"""
    data, order = defaultdict(lambda: defaultdict(lambda: defaultdict(list))), []
    for name in TAHOT_FILES:
        for line in find(name).read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            r = parse_ref(f[0]) if f and "#" in f[0] else None
            if not r or len(f) < 7:
                continue
            code, ch, v, n, typ = r
            if not typ or typ[0] not in "LQ":        # R (restored) and X (from the LXX) are not in the Leningrad text we use
                continue
            if code not in order:
                order.append(code)
            surface = f[1].split("\\")[0].replace("/", "")
            data[code][ch][v].append({"surface": surface, "translit": f[2].replace("/", ""), "gloss": f[3].replace("/ ", " ").replace("/", " ").strip(),
                                      "tags": f[4].split("\\")[0], "morph": f[5]})
    return data, order


def load_tagnt():
    data, order = defaultdict(lambda: defaultdict(lambda: defaultdict(list))), []
    for name in TAGNT_FILES:
        for line in find(name).read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            r = parse_ref(f[0]) if f and "#" in f[0] else None
            if not r or len(f) < 10:
                continue
            code, ch, v, n, typ = r
            if "SBL" not in f[5].split("+"):          # only the words the SBLGNT has
                continue
            if code not in order:
                order.append(code)
            surface = f[1].split(" (")[0]
            strong, _, morph = f[3].partition("=")
            lemma, _, lgloss = f[4].partition("=")
            data[code][ch][v].append({"surface": surface, "gloss": f[2].strip(), "tags": strong, "morph": morph,
                                      "lemma": lemma, "sub": f[9].strip()})
    return data, order


def load_lexicon(name):
    lex = {}
    for line in (STEP / "Lexicons" / name).read_text(encoding="utf-8").splitlines():
        f = line.split("\t")
        if len(f) < 8 or not re.match(r"^[HG]\d{4}", f[0]):
            continue
        key = f[1].split("=")[0].strip()          # the disambiguated tag used in the texts, e.g. H0430G, G3056
        meaning = re.sub(r"<[^>]+>", " ", f[7]).replace("&nbsp;", " ")
        meaning = re.sub(r"\s+", " ", meaning).strip()
        lex[key] = [f[3], f[4], f[5], f[6], meaning[:320]]
    return lex


def load_morph_codes(name):
    """'$'-separated blocks: CODE<tab>elements / <tab>phrase / <tab>description / example."""
    text = (STEP / "Morphology codes" / name).read_text(encoding="utf-8")
    text = text.split("FULL MORPHOLOGY CODES:", 1)[-1]
    out = {}
    for block in text.split("\n$\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        code = lines[0].split("\t")[0].strip().strip('"')
        if not code or " " in code or len(code) > 24 or not re.match(r"^[A-Za-z]", code):
            continue
        out[code] = lines[1].strip().strip('"').strip()
    return out


# ------------------------------------------------------------ alignment
def align(our_tokens, words, greek):
    """-> list (len our_tokens) of word dicts or None."""
    ours = [skeleton(t.replace("\u02bc", "")) for t in our_tokens]
    theirs = [skeleton(w["surface"].replace("\u1fbd", "").replace("\u2019", "").replace("'", "")) for w in words]
    if greek:
        strip = lambda s: "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()
        ours, theirs = [strip(x) for x in ours], [strip(x) for x in theirs]
    result = [None] * len(our_tokens)
    if len(ours) == len(theirs) and sum(a == b for a, b in zip(ours, theirs)) >= max(1, len(ours) - 1):
        return list(words), 0
    sm = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            result[a + k] = words[b + k]
            matched += 1
    return result, len(our_tokens) - matched


def compact(w, greek):
    if w is None:
        return None
    if greek:
        return [w["tags"], w["morph"], w["gloss"], w["sub"]]
    return [w["tags"], w["morph"], w["gloss"], w["translit"]]


def root_tag(tags, greek):
    if greek:
        return tags.split("/")[0]
    m = re.search(r"\{([^}]+)\}", tags)
    return m.group(1) if m else tags.split("/")[0]


def js(name, value):
    return f"{name}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))};\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    heb, heb_order = load_tahot()
    grk, grk_order = load_tagnt()
    assert len(heb_order) == 39 and len(grk_order) == 27, (len(heb_order), len(grk_order))
    step2ours = dict(zip(heb_order, OT)) | dict(zip(grk_order, NT))
    conc = defaultdict(list)
    report = ["# Morphology alignment report", "", "| book | tokens | aligned | unaligned | verses missing tags |", "|---|---|---|---|---|"]
    totals = [0, 0, 0]
    for stepcode, ours in step2ours.items():
        meta = BOOKS[ours]
        greek = meta["testament"] == "NT"
        src = heb if not greek else grk
        f = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
        if not f.exists():
            continue
        chapters = json.loads(f.read_text(encoding="utf-8"))["chapters"]
        book_out, ntok, nun, missing = {}, 0, 0, 0
        for ch, verses in chapters.items():
            book_out[ch] = {}
            for verse in verses:
                toks = tokens(verse["text"])
                words = src[stepcode].get(int(ch), {}).get(verse["v"], [])
                if not words:
                    missing += 1
                    book_out[ch][str(verse["v"])] = [None] * len(toks)
                    continue
                aligned, un = align(toks, words, greek)
                ntok += len(toks)
                nun += un
                book_out[ch][str(verse["v"])] = [compact(w, greek) for w in aligned]
                for i, w in enumerate(aligned):
                    if w:
                        conc[root_tag(w["tags"], greek)].append([meta["num"], int(ch), verse["v"], i])
        (OUT / f"{slug(meta['name'])}.js").write_text(f"MORPH[{json.dumps(meta['name'])}]=" + json.dumps(book_out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
        report.append(f"| {meta['name']} | {ntok} | {ntok - nun} | {nun} | {missing} |")
        totals[0] += ntok
        totals[1] += nun
        totals[2] += missing
    report.append(f"| **total** | {totals[0]} | {totals[0] - totals[1]} | {totals[1]} | {totals[2]} |")
    lex = load_lexicon("TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt")
    lex.update(load_lexicon("TBESG - Translators Brief lexicon of Extended Strongs for Greek - STEPBible.org CC BY.txt"))
    morphx = load_morph_codes("TEHMC - Translators Expansion of Hebrew Morphology Codes - STEPBible.org CC BY.txt")
    morphx.update(load_morph_codes("TEGMC - Translators Expansion of Greek Morphhology Codes - STEPBible.org CC BY.txt"))
    (OUT / "lex.js").write_text(js("LEX", lex) + js("MORPHX", morphx), encoding="utf-8")
    (OUT / "conc.js").write_text(js("CONC", conc), encoding="utf-8")
    (ROOT / "logs" / "morph_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.glob("*.js"))
    print(f"morphology: {totals[0]} tokens, {totals[0] - totals[1]} aligned ({100 * (totals[0] - totals[1]) / max(1, totals[0]):.2f}%), "
          f"{totals[2]} verses without tags; lexicon {len(lex)} entries, {len(morphx)} morphology codes, "
          f"concordance {len(conc)} lemmas; {size / 1e6:.1f} MB in {OUT}")


if __name__ == "__main__":
    main()
