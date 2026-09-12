#!/usr/bin/env python3
"""Textual apparatus: where the printed editions and the scribal tradition differ.

    python scripts/build_apparatus.py       # -> site/morph/app_<Book>.js

Greek: the STEPBible Translators Amalgamated Greek NT (CC BY 4.0) carries every
word of the major printed editions with the list of editions that contain it.
Runs of adjacent words sharing an edition set become one apparatus entry: the
reading, the editions that have it, and the editions that do not — including
words omitted by our base text (SBLGNT), which the reader can then see. Spelling
differences between editions are recorded too.

Hebrew: the same data's Leningrad text carries the scribal Qere (what is read)
against the Ketiv (what is written), the meaning variants that translators
follow, and the spelling variants. Those become the Hebrew apparatus.

This is an apparatus of EDITIONS and the scribal tradition, not of manuscripts:
no manuscript sigla (P66, Aleph, B…) are asserted, because no openly licensed
manuscript apparatus is available to this project.

    APP["John"] = {ch: {v: [[kind, reading, have, lack, note], ...]}}
        kind: "var" (editions differ) | "sp" (spelling) | "qere" | "meaning"
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TA = ROOT / "sources" / "STEPBible-Data" / "Translators Amalgamated OT+NT"
OUT = ROOT / "site" / "morph"
TAHOT = ["TAHOT Gen-Deu", "TAHOT Jos-Est", "TAHOT Job-Sng", "TAHOT Isa-Mal"]
TAGNT = ["TAGNT Mat-Jhn", "TAGNT Act-Rev"]
ORDER = [c for c, m in sorted(BOOKS.items(), key=lambda x: x[1]["num"])]
OT, NT = ORDER[:39], ORDER[39:]
NAME = {c: m["name"] for c, m in BOOKS.items()}
ALL_ED = ["NA28", "NA27", "Tyn", "SBL", "WH", "Treg", "TR", "Byz"]
EDNAME = {"NA28": "Nestle-Aland 28", "NA27": "Nestle-Aland 27", "Tyn": "Tyndale House 2017", "SBL": "SBLGNT",
          "WH": "Westcott-Hort 1881", "Treg": "Tregelles", "TR": "Textus Receptus (Scrivener 1894)", "Byz": "Byzantine (Robinson-Pierpont)"}
REF = re.compile(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)(?:\((\d+)\.(\d+)\))?#(\d+)=(\S*)")


def find(prefix):
    return next(TA.glob(prefix + "*.txt"))


def parse_ref(field):
    m = REF.match(field)
    if not m:
        return None
    code, ech, ev, hch, hv, n, typ = m.groups()
    ch, v = (int(hch), int(hv)) if hch else (int(ech), int(ev))
    return code, ch, v, int(n), typ


def eds(field):
    return tuple(e.split("»")[0] for e in field.split("+") if e.split("»")[0] in ALL_ED)


def greek():
    per_book, order = defaultdict(lambda: defaultdict(lambda: defaultdict(list))), []
    for name in TAGNT:
        rows = defaultdict(list)
        for line in find(name).read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            r = parse_ref(f[0]) if f and "#" in f[0] else None
            if not r or len(f) < 8:
                continue
            code, ch, v, n, typ = r
            if code not in order:
                order.append(code)
            rows[(code, ch, v)].append((n, f[1].split(" (")[0], eds(f[5]), f[7].strip()))
        for (code, ch, v), ws in rows.items():
            ws.sort()
            entries, run = [], []
            for n, surface, e, sp in ws:
                if sp:
                    entries.append(["sp", surface, "", "", re.sub(r"\s+", " ", sp).strip(" ;")])
                if set(e) == set(ALL_ED) or not e:
                    if run:
                        entries.append(make(run))
                        run = []
                    continue
                if run and run[-1][2] == e and n == run[-1][0] + 1:
                    run.append((n, surface, e))
                else:
                    if run:
                        entries.append(make(run))
                    run = [(n, surface, e)]
            if run:
                entries.append(make(run))
            if entries:
                per_book[code][ch][v] = entries
    return per_book, order


def make(run):
    reading = " ".join(w[1] for w in run)
    have = [e for e in ALL_ED if e in run[0][2]]
    lack = [e for e in ALL_ED if e not in run[0][2]]
    return ["var", reading, "+".join(have), "+".join(lack), ""]


def hebrew():
    per_book, order = defaultdict(lambda: defaultdict(lambda: defaultdict(list))), []
    for name in TAHOT:
        for line in find(name).read_text(encoding="utf-8").splitlines():
            f = line.split("\t")
            r = parse_ref(f[0]) if f and "#" in f[0] else None
            if not r or len(f) < 9:
                continue
            code, ch, v, n, typ = r
            if not typ or typ[0] not in "LQ":
                continue
            if code not in order:
                order.append(code)
            surface = f[1].split("\\")[0].replace("/", "")
            if typ.startswith("Q"):
                note = re.sub(r"\s+", " ", f[6]).strip(" ;¦") or (re.sub(r"\s+", " ", f[7]).strip(" ;¦") if len(f) > 7 else "")
                per_book[code][ch][v].append(["qere", surface, "", "", note])
            mean = re.sub(r"\s+", " ", f[6]).strip(" ;¦") if len(f) > 6 else ""
            spell = re.sub(r"\s+", " ", f[7]).strip(" ;¦") if len(f) > 7 else ""
            if mean and not typ.startswith("Q"):
                per_book[code][ch][v].append(["meaning", surface, "", "", mean])
            if spell:
                per_book[code][ch][v].append(["sp", surface, "", "", spell])
    return per_book, order


def main():
    g, gorder = greek()
    h, horder = hebrew()
    step2ours = dict(zip(horder, OT)) | dict(zip(gorder, NT))
    total, books = 0, 0
    for stepcode, ours in step2ours.items():
        src = h if ours in OT else g
        data = src.get(stepcode)
        if not data:
            continue
        out = {str(ch): {str(v): e for v, e in verses.items() if e} for ch, verses in data.items()}
        out = {ch: vs for ch, vs in out.items() if vs}
        if not out:
            continue
        n = sum(len(e) for vs in out.values() for e in vs.values())
        total += n
        books += 1
        (OUT / f"app_{slug(NAME[ours])}.js").write_text(
            f"APP[{json.dumps(NAME[ours])}]=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (OUT / "app_meta.js").write_text("APPED=" + json.dumps(EDNAME, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.glob("app_*.js"))
    print(f"apparatus: {total} entries across {books} books, {size / 1e6:.1f} MB -> site/morph/app_*.js")


if __name__ == "__main__":
    main()
