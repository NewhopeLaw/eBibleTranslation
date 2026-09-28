#!/usr/bin/env python3
"""Sgaw Karen spelled as sound: the phonetic notation any voice can be fed.

    python "NGAW KAREN TTS/karen_phonemes.py" "ဒီးယွၤစံးဝဲဒၣ်"              # IPA with tone letters
    python "NGAW KAREN TTS/karen_phonemes.py" Gen 1 1-3 --style piper     # for a phoneme-driven neural voice
    python "NGAW KAREN TTS/karen_phonemes.py" Matt 6 9-13 --style ascii   # plain letters, one syllable per token

Karen spelling is a sound table, not a history: every syllable is one
consonant, an optional medial, one vowel sign and one tone mark, each with a
single value (Wade's grammar of 1861; the same table on Wikipedia). So the
step from letters to sounds is a lookup, and once a text is written as sounds
with its tones, the voice is a separate question: a formant synthesiser, a
neural voice trained on another tone language, a singing bank in a Vocaloid
editor with the tones as notes. Each of those takes phonemes and pitch; this
module makes them, and the engines in karen_speech.py consume them.

Three spellings of the same sounds:

  ipa     kə.ɲɔ˧ kjo˥˩  - consonant, vowel, then the tone as Chao letters
  ascii   ka nyo3 kyo51 - the same in plain letters, tones as digits
  piper   k ə ɲ ˈɔ ː ...  - what a Piper voice trained by espeak-ng on
          Vietnamese was fed: IPA with espeak's Vietnamese tone marks, so
          Karen's six tones ride on the six Vietnamese ones it knows.

The tones are the part still to be measured, not read (the vocabulary test
in karen_voice_test.py is measuring them): Wade's words are the only public
description, and they are impressions. TONES below is where a measured
table replaces them. The Vietnamese mapping is likewise a first guess by
nearest contour, one line per tone.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))   # books.py and friends
from books import BOOKS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent          # the project
HERE = Path(__file__).resolve().parent                 # NGAW KAREN TTS
VERSES = ROOT / "sources" / "ksw-mason" / "verses.jsonl"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

CONSONANTS = {"က": "k", "ခ": "kʰ", "ဂ": "ɣ", "ဃ": "x", "င": "ŋ", "စ": "s", "ဆ": "sʰ", "ၡ": "ʃ", "ည": "ɲ",
              "တ": "t", "ထ": "tʰ", "ဒ": "d", "န": "n", "ပ": "p", "ဖ": "pʰ", "ဘ": "b", "မ": "m",
              "ယ": "j", "ရ": "r", "လ": "l", "ဝ": "w", "သ": "θ", "ဟ": "h", "အ": "ʔ", "ဧ": "ɦ"}
MEDIALS = {"ှ": "ɣ", "ၠ": "j", "ျ": "l", "ြ": "r", "ွ": "w"}
# ျ is /l/ in Wade's Karen, and /l/ in Emma Htoo's: her lesson 5 makes it from
# လ and gives ကျဲ, road, /klɛ/ (phonics-emma-htoo.md). The "modern" /j/ that
# was taken here from the language article is Burmese's value for the sign,
# not Karen's; the medial /j/ is ၠ (her ကၠိ, school). ကၠ is still the
# affricate the article lists.
MODERN = {}
AFFRICATE = {("k", "j"): "tʃ", ("kʰ", "j"): "tʃʰ"}
VOWELS = {"": "a", "ါ": "a", "ာ": "a", "ံ": "i", "ၢ": "ə", "်": "ə", "ု": "ɨ", "ူ": "u", "့": "e", "ဲ": "ɛ", "ိ": "o", "ီ": "ɔ"}
# The six tones. "name" is Wade's 1861 description, kept as the label; "chao"
# and "digits" are what modern speakers were measured doing (Emma Htoo's
# lessons and the vocabulary speaker, phonics-emma-htoo.md). Best evidence is
# her whole paradigm on eighteen consonants (video 11): on the vowel a, ၣ် sits
# highest, then ၢ် high and level, ၤ and း in the middle (ၤ long, း short and
# falling), the unmarked syllable low and level, ာ် lowest. A range of under
# three semitones in isolation; length tells them apart as much as pitch.
# Then the espeak
# Vietnamese tone symbol a Piper Vietnamese voice was trained on (none = ngang,
# ɜ = sắc, 2 = huyền, 4 = hỏi, 5 = ngã, 6 = nặng) with the vowel length to
# give it. "long" is Wade's description; "vi" and "vi_long" are what fitted a
# Karen speaker's words best, all six adjusted together and scored on whole
# words (logs/tune_tones_joint.json, the vais1000 voice; 0.20 -> 0.42 mean
# pitch correlation): on the 17 corpus-confirmed words of one lesson, so ၢ်
# rests on one word and ာ် on none. To be refitted on the syllabary.
TONES = {
    "":   {"name": "rising",           "chao": "˨", "digits": "22", "vi": "4", "vi_long": False, "long": False, "cut": False},
    "ၤ":  {"name": "level, prolonged", "chao": "˧˨", "digits": "32", "vi": "4", "vi_long": True, "long": True,  "cut": False},
    "ၢ်": {"name": "heavy falling",    "chao": "˦",  "digits": "44", "vi": "6", "vi_long": False,  "long": True,  "cut": False},
    "ၣ်": {"name": "circumflex",       "chao": "˦˥˦", "digits": "454", "vi": "4", "vi_long": True, "long": False, "cut": False},
    "ာ်": {"name": "abrupt, low",      "chao": "˨˩",  "digits": "21", "vi": "4", "vi_long": True, "long": False, "cut": True},
    "း":  {"name": "abrupt, mid",      "chao": "˧˨", "digits": "32", "vi": "6", "vi_long": True, "long": False, "cut": True},
}
SYLLABLE = re.compile(r"([က-အဧၡ])([ှၠျြွ]*)([ါာံၢုူ့ဲိီ](?!်)|်)?(ၢ်|ာ်|ၣ်|း|ၤ)?")
ASCII = {"kʰ": "kh", "ɣ": "gh", "x": "x", "ŋ": "ng", "sʰ": "sh", "ʃ": "sy", "ɲ": "ny", "tʰ": "th", "pʰ": "ph",
         "θ": "th", "ʔ": "'", "ɦ": "hh", "tʃ": "ch", "tʃʰ": "chh", "ə": "eu", "ɨ": "ue", "ɛ": "ae", "ɔ": "aw", "j": "y"}


def syllables(text):
    """Text -> list of items: ("syl", {onset, medial, vowel, tone, mark}) or ("break", char).
    Anything that is not a Karen syllable - a space, a stop, a digit - is a break."""
    out, i = [], 0
    while i < len(text):
        m = SYLLABLE.match(text, i)
        if not m:
            ch = text[i]
            if not ch.isspace() or not (out and out[-1] == ("break", " ")):
                out.append(("break", " " if ch.isspace() else ch))
            i += 1
            continue
        cons, meds, vowel, mark = m.group(1), m.group(2) or "", m.group(3) or "", m.group(4) or ""
        onset = CONSONANTS[cons]
        medial = "".join(MODERN.get(x, MEDIALS[x]) for x in meds)
        if (onset, medial) in AFFRICATE:
            onset, medial = AFFRICATE[(onset, medial)], ""
        out.append(("syl", {"onset": onset, "medial": medial, "vowel": VOWELS[vowel], "tone": TONES[mark]["name"],
                            "mark": mark, "short": vowel == "်"}))
        i = m.end()
    return out


def ipa(items, sep=" "):
    parts = []
    for kind, s in items:
        if kind == "break":
            parts.append(s if s != " " else sep)
            continue
        t = TONES[s["mark"]]
        parts.append(s["onset"] + s["medial"] + s["vowel"] + ("ː" if t["long"] and not s["short"] else "") + t["chao"])
    return re.sub(r" +", " ", "".join(p if p in ".,;:!?။၊" else p + " " for p in parts)).strip()


def ascii_(items):
    def a(ph):
        return "".join(ASCII.get(c, c) for c in re.findall(r"tʃʰ|tʃ|.ʰ|.", ph))
    parts = []
    for kind, s in items:
        if kind == "break":
            parts.append(s)
            continue
        t = TONES[s["mark"]]
        parts.append(a(s["onset"]) + a(s["medial"]) + a(s["vowel"]) + t["digits"] + ("'" if t["cut"] else ""))
    return re.sub(r" +", " ", "".join(p if p in ".,;:!?။၊" else p + " " for p in parts)).strip()


def piper(items):
    """Phoneme symbols for a Piper voice trained from espeak-ng's Vietnamese:
    onset, medial, stressed vowel, length, then the Vietnamese tone symbol; an
    abrupt tone ends in a glottal stop. Returns a list of symbol strings, one
    per phoneme, with " " between syllables and "." at a stop."""
    out = []
    for kind, s in items:
        if kind == "break":
            out.append("." if s in ".။" else "," if s in ",၊;" else " ")
            continue
        t = TONES[s["mark"]]
        for ph in re.findall(r"tʃʰ|tʃ|.ʰ|.", s["onset"] + s["medial"]):
            out += list(ph) if ph.endswith("ʰ") else [ph]
        out += ["ˈ", s["vowel"]]
        if t["vi_long"] and not s["short"]:
            out.append("ː")
        if t["vi"]:
            out.append(t["vi"])
        if t["cut"]:
            out.append("ʔ")
        out.append(" ")
    return out


def karen_verses(book, chapter, verses):
    name = BOOKS[book]["name"]
    want = set(verses)
    rows = [json.loads(l) for l in VERSES.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r["ksw"] for r in rows if r["book"] == name and r["chapter"] == chapter and r["verse"] in want]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="+", help="Karen text, or a book code, chapter and verse range")
    ap.add_argument("--style", choices=["ipa", "ascii", "piper"], default="ipa")
    a = ap.parse_args()
    if a.what[0] in BOOKS and len(a.what) >= 2:
        lo, _, hi = (a.what[2] if len(a.what) > 2 else "1-200").partition("-")
        texts = karen_verses(a.what[0], int(a.what[1]), range(int(lo), int(hi or lo) + 1))
    else:
        texts = [" ".join(a.what)]
    for t in texts:
        items = syllables(t)
        print(t)
        print("  " + ({"ipa": ipa, "ascii": ascii_}[a.style](items) if a.style != "piper" else "".join(piper(items))))


if __name__ == "__main__":
    main()
