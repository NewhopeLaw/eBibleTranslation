#!/usr/bin/env python3
"""Who everyone is, and who they came from, read out of the text itself.

    python scripts/build_people.py --chapters --limit 20   # phase 1 on a few chapters
    python scripts/build_people.py --chapters              # every chapter, resuming
    python scripts/build_people.py --gather                # phase 2: one person per person
    python scripts/build_people.py --pack                  # -> site/morph/people.js

A reader who searches "Zechariah" should not be handed 51 verses to sort out.
There are more than thirty men of that name in the Bible - a prophet, a king of
Israel, a doorkeeper, the father of John - and the only thing the search box can
tell them apart by today is which chapter they stand in.

The text says who they are. Genealogies state descent outright, and narrative
states it in passing: son of, daughter of, wife of, the brother of. This reads
those statements chapter by chapter and builds a family graph out of them, with
the verse behind every edge, so the reader can be shown a tree and check it.

  1. Chapter by chapter: every person named here, what the chapter says they
     are, and every relation it states, each with the verse it stands in.
  2. Gathering: the same name is not the same person. Candidates are grouped by
     name first - a small, well-posed question for each - and the model is asked
     only to split one name's occurrences into the people they belong to, using
     the relations and the books they appear in. The themes pass learned this
     the hard way: matching against a long list of bare labels drifts, and one
     wrong index silently welds two unrelated things together. A name plus its
     relations is enough context to judge, and nothing here is ever matched
     against a numbered list.
  3. Packing writes the people with their edges and the verses behind them.

    PEOPLE = {id: [name, what, [[kind, other id, "Book c:v"], ...], [refs]]}
    PNAME  = {name folded: [id, ...]}

Genealogy is interpretation as much as the themes are - the text does not
always say whether two Azariahs are one man - so every edge cites the verse
that states it, and the reader is told this is read from the text rather than
taken from a chronology. Where the text is silent the graph stays silent.

This is a PC job: it needs Ollama and the model named in config.json.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                           # noqa: E402
import translate as T                                     # noqa: E402
from books import BOOKS, slug                             # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "output" / "en" / "json"
NORM = ROOT / "sources" / "normalized"
MORPH = ROOT / "site" / "morph"
DIR = ROOT / "targets" / "people"
CHAPTERS = DIR / "chapters.jsonl"
GATHERED = DIR / "gathered.jsonl"

KINDS = ("father", "mother", "son", "daughter", "husband", "wife", "brother", "sister")

SYSTEM_CH = """You read one chapter of the Bible and say who is in it and how they are related.

You get the chapter verse by verse, each verse in its original language with the English translation under it.

Reply with JSON only:
{"people": [{"name": "Jehoiada", "what": "one short phrase: who this chapter says he is", "verses": "4, 7-9",
             "relations": [{"kind": "father", "of": "Zechariah", "verse": "20"}]}]}

Rules:
- Name everyone the chapter names. Leave out people it only refers to as "the king" or "his servant" without naming them.
- "kind" is exactly one of: father, mother, son, daughter, husband, wife, brother, sister. Give the relation from this person to the other: {"kind": "father", "of": "Zechariah"} means this person is Zechariah's father.
- Every relation must carry the verse of this chapter that states it. If the chapter does not state a relation, do not give one: what you know from elsewhere in the Bible does not belong here.
- Spell a name as this chapter spells it. Do not normalise Jehoiachin to Jeconiah, or Saul to Paul.
- "what" describes this person from this chapter alone, in a few words: "high priest under Joash", "the third son of Jesse". No interpretation of their character.
- A genealogy is a chapter like any other: give every name in it and the descent it states."""

SYSTEM_SPLIT = """You are deciding how many different people share one name in the Bible.

You get one name and every place the text names it, each with what the chapter said and the relations it stated.

Reply with JSON only:
{"people": [{"who": "a short phrase telling this one apart", "occurrences": [1, 4, 5]}]}

The numbers are the occurrence numbers you were given. Every occurrence must appear in exactly one person.

Rules:
- Two occurrences are the same person when the text gives you a reason to join them: the same parent, the same spouse, the same office, the same stretch of narrative. Separated by centuries, or given different fathers, they are different people.
- When the text gives no reason either way, keep them apart and say so in "who". Wrongly joining two people invents a family that does not exist; leaving them apart only leaves the reader where the text does.
- "who" is what distinguishes this person: "son of Jehoiada, the priest", "king of Israel, son of Jeroboam". It is not a biography."""


def call(system, user, temp=0.2):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": temp},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())
    T.log_work(resp, time.time() - t0)
    return json.loads(resp.get("message", {}).get("content", "{}"))


def fold(name):
    """A name as a key: accents off, case down, so Jehoiada and JEHOIADA meet."""
    n = unicodedata.normalize("NFD", str(name or "").strip())
    return unicodedata.normalize("NFC", "".join(c for c in n if unicodedata.category(c) != "Mn")).lower()


def chapter_files():
    out = []
    for meta in sorted(BOOKS.values(), key=lambda m: m["num"]):
        for f in sorted(EN.glob(f"{slug(meta['name'])}_*.json")):
            out.append((meta, f))
    return out


def source_chapter(meta, ch):
    f = NORM / f"{meta['num']:02d}_{slug(meta['name'])}.json"
    if not f.exists():
        return {}
    chapters = json.loads(f.read_text(encoding="utf-8"))["chapters"]
    return {rec["v"]: rec["text"] for rec in chapters.get(str(ch), [])}


def read_jsonl(p):
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def phase_chapters(limit=0, only=None):
    T.WORK_JOB = "people"
    DIR.mkdir(parents=True, exist_ok=True)
    done = {(r["book"], int(r["chapter"])) for r in read_jsonl(CHAPTERS)}
    todo = [(m, f) for m, f in chapter_files()
            if (m["name"], int(f.stem.rsplit("_", 1)[1])) not in done]
    if only:
        book, ch = only
        todo = [(m, f) for m, f in chapter_files()
                if m["name"].lower() == book.lower() and int(f.stem.rsplit("_", 1)[1]) == ch]
    if limit:
        todo = todo[:limit]
    print(f"people, chapter pass: {len(done)} done, {len(todo)} to do")
    t0, n = time.time(), 0
    with CHAPTERS.open("a", encoding="utf-8") as fh:
        for meta, f in todo:
            d = json.loads(f.read_text(encoding="utf-8"))
            src = source_chapter(meta, d["chapter"])
            lang = "Greek" if meta["testament"] == "NT" else "Hebrew or Aramaic"
            body = "\n".join((f"[{v}] {src[int(v)]}\n     {t}" if int(v) in src else f"[{v}] {t}")
                             for v, t in sorted(d["verses"].items(), key=lambda kv: int(kv[0])))
            user = (f"{d['book']} {d['chapter']} — each verse in {lang}, with the translation under it\n\n"
                    f"{body}\n\nWho is named in this chapter, and what does it say they are to each other?")
            try:
                got = call(SYSTEM_CH, user)
                people = [p for p in (got.get("people") or got.get("persons") or [])
                          if isinstance(p, dict) and str(p.get("name", "")).strip()]
            except Exception as e:                            # noqa: BLE001
                print(f"  {d['book']} {d['chapter']}: FAILED {e}", file=sys.stderr)
                continue
            rows = []
            for p in people[:80]:
                rel = [{"kind": str(r.get("kind", "")).lower()[:10], "of": str(r.get("of", ""))[:60],
                        "verse": str(r.get("verse", ""))[:12]}
                       for r in (p.get("relations") or []) if isinstance(r, dict)
                       and str(r.get("kind", "")).lower() in KINDS and str(r.get("of", "")).strip()]
                rows.append({"name": str(p["name"])[:60], "what": str(p.get("what", ""))[:140],
                             "verses": str(p.get("verses", ""))[:40], "relations": rel[:20]})
            fh.write(json.dumps({"book": d["book"], "chapter": d["chapter"], "people": rows},
                                ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 10 == 0 or n == len(todo):
                el = time.time() - t0
                print(f"  {n}/{len(todo)} chapters [{el / n:.1f}s each, "
                      f"{(len(todo) - n) * el / n / 3600:.1f} h left]", flush=True)
    print(f"chapter pass done: {n} chapters")


def occurrences_by_name():
    """{folded name: [(book, chapter, record), ...]} over everything read so far."""
    by = defaultdict(list)
    for r in read_jsonl(CHAPTERS):
        for p in r["people"]:
            by[fold(p["name"])].append((r["book"], int(r["chapter"]), p))
    return by


def phase_gather(limit=0):
    """One name at a time: how many people is this?

    The question is asked per name and never against a list of everything
    gathered so far, which is what kept the themes consolidation honest only in
    theory. A name with one occurrence needs no model at all.
    """
    T.WORK_JOB = "people"
    DIR.mkdir(parents=True, exist_ok=True)
    done = {r["name"] for r in read_jsonl(GATHERED)}
    by = occurrences_by_name()
    todo = [(k, v) for k, v in sorted(by.items()) if k not in done]
    if limit:
        todo = todo[:limit]
    single = [k for k, v in todo if len(v) == 1]
    print(f"people, gathering: {len(by)} names, {len(done)} settled, {len(todo)} to do "
          f"({len(single)} of them named once, which needs no call)")
    t0, n = time.time(), 0
    with GATHERED.open("a", encoding="utf-8") as fh:
        for name, occ in todo:
            if len(occ) == 1:
                book, ch, p = occ[0]
                fh.write(json.dumps({"name": name, "people": [{"who": p.get("what", ""),
                                                               "occurrences": [0]}]}, ensure_ascii=False) + "\n")
                continue
            listing = "\n".join(
                f"{i}. {book} {ch} — {p.get('what', '')}"
                + ("; " + "; ".join(f"{r['kind']} of {r['of']}" for r in p["relations"]) if p["relations"] else "")
                for i, (book, ch, p) in enumerate(occ))
            spelled = occ[0][2]["name"]
            try:
                got = call(SYSTEM_SPLIT, f"NAME: {spelled}\n\nOCCURRENCES:\n{listing}\n\n"
                                         f"How many different people are these?")
                people = [p for p in (got.get("people") or []) if isinstance(p, dict)]
            except Exception as e:                            # noqa: BLE001
                print(f"  {name}: FAILED {e}", file=sys.stderr)
                continue
            # Every occurrence must land somewhere. One the model forgot becomes
            # a person of its own rather than being dropped: a reader missing a
            # verse is worse served than one given an extra person to look at.
            placed, clean = set(), []
            for p in people:
                nums = sorted({int(x) for x in (p.get("occurrences") or [])
                               if str(x).isdigit() and 0 <= int(x) < len(occ)} - placed)
                if nums:
                    placed |= set(nums)
                    clean.append({"who": str(p.get("who", ""))[:140], "occurrences": nums})
            for i in range(len(occ)):
                if i not in placed:
                    clean.append({"who": occ[i][2].get("what", ""), "occurrences": [i]})
            fh.write(json.dumps({"name": name, "people": clean}, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 20 == 0:
                el = time.time() - t0
                print(f"  {n} names asked [{el / n:.1f}s each]", flush=True)
    print(f"gathering done: {n} names asked of the model")


def pack():
    """The graph, with the verse behind every edge."""
    by = occurrences_by_name()
    gathered = {r["name"]: r["people"] for r in read_jsonl(GATHERED)}
    ids, people, byname = {}, {}, defaultdict(list)
    for name, groups in gathered.items():
        occ = by.get(name) or []
        for gi, g in enumerate(groups):
            pid = f"p{len(people):04d}"
            refs = []
            for i in g["occurrences"]:
                if i < len(occ):
                    book, ch, p = occ[i]
                    ids[(name, i)] = pid
                    refs.append(f"{book} {ch}")
            spelled = occ[g["occurrences"][0]][2]["name"] if g["occurrences"] and occ else name
            people[pid] = [spelled, g.get("who", ""), [], sorted(set(refs))]
            byname[name].append(pid)
    # Edges last, once every person has an id: an edge names a person by the
    # name the chapter used, so it can only be resolved when the name is one
    # person or the chapter says which.
    for name, occ in by.items():
        for i, (book, ch, p) in enumerate(occ):
            pid = ids.get((name, i))
            if not pid:
                continue
            for r in p["relations"]:
                other = byname.get(fold(r["of"])) or []
                if len(other) != 1:            # ambiguous, and the text has not said: leave it out
                    continue
                people[pid][2].append([r["kind"], other[0], f"{book} {ch}:{r['verse']}"])
    MORPH.mkdir(parents=True, exist_ok=True)
    body = ("PEOPLE=" + json.dumps(people, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "PNAME=" + json.dumps(byname, ensure_ascii=False, separators=(",", ":")) + ";\n")
    p = MORPH / "people.js"
    p.write_text(body, encoding="utf-8")
    edges = sum(len(v[2]) for v in people.values())
    print(f"people: {len(people)} people over {len(byname)} names, {edges} stated relations "
          f"-> {p.name} ({p.stat().st_size / 1e6:.1f} MB)")
    manifest.record("people", len(people), "people", "who everyone is, read from the text", "build_people.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--chapters", action="store_true", help="phase 1: read every chapter")
    ap.add_argument("--gather", action="store_true", help="phase 2: one person per person")
    ap.add_argument("--pack", action="store_true", help="write site/morph/people.js")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs=2, metavar=("BOOK", "CHAPTER"))
    a = ap.parse_args()
    if a.chapters:
        phase_chapters(a.limit, (a.only[0], int(a.only[1])) if a.only else None)
    if a.gather:
        phase_gather(a.limit)
    if a.pack or not (a.chapters or a.gather):
        pack()


if __name__ == "__main__":
    main()
