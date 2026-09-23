#!/usr/bin/env python3
"""Mend a verse: ask the model for the one verse that is wrong, not the chapter.

    python scripts/mend.py --lang th                 # every verse the verifier flags
    python scripts/mend.py --lang th 2Kgs 5          # the flagged verses of one chapter
    python scripts/mend.py --lang th 2Kgs 5:1,20     # these verses, flagged or not
    python scripts/mend.py --lang th --dry           # say what would be asked, ask nothing

The first Thai run left a Korean syllable inside the name Aram in four verses
of Isaiah 7. Re-running the chapter to mend them cost three thousand tokens,
took a minute and a half beside the other jobs, and brought the syllable back;
re-running 1 Kings 20 for one stray character lost verse 43. A chapter is the
wrong unit for a fault that is one word wide.

This asks for the verse alone. The model is given the same system prompt the
chapter had - glossary, names, the rules of the language - the verses around
it as they already stand, so the mended verse keeps their voice, and the
source of the one verse. It answers with that verse, which is checked the way
the verifier checks it: its own script present, no other script in it, no
Latin word left over, no loop, not empty. A verse that fails is asked for
again, three times; one that still fails is left as it was and named, because
a wrong verse silently replaced by another wrong verse would be no mending.

The chapter's JSON and Markdown are rewritten with the verse in place;
everything else in them stays as it was. What was asked and what came back
goes to logs/mend.jsonl, and the cost to logs/work.jsonl under the job "mend".
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                                  # noqa: E402
from books import BOOKS, TARGETS, slug                                 # noqa: E402
from verify import HEBREW, GREEK, LATIN_WORD, MARKS, OTHERS, SCRIPTS, load_source   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "mend.jsonl"
TRIES = 3
AROUND = 2                        # verses on either side, given for the voice of the passage


def faults(text, lang):
    """Why this rendering will not do, or [] when it will."""
    out = []
    if not text.strip():
        return ["empty"]
    if HEBREW.search(text) or GREEK.search(text):
        out.append("source script left in")
    own = SCRIPTS.get(lang)
    if own:
        if not re.search(f"[{own[0]}]", text):
            out.append(f"no {own[1]}")
        alien = re.findall(f"[{OTHERS}]", re.sub(f"[{own[0]}]", "", text))
        if alien:
            out.append("other script: " + "".join(alien[:6]))
        words = LATIN_WORD.findall(text)
        if words:
            out.append("Latin: " + ", ".join(words[:3]))
    if T.find_loop(text):
        out.append("loop")
    return out


def flagged(lang):
    """{(book, chapter): {verse, ...}} from the verifier's last report."""
    rep = ROOT / "logs" / f"verify_{lang}.md"
    if not rep.exists():
        raise SystemExit(f"no {rep.name} yet - run scripts/verify.py --lang {lang} first")
    out = {}
    for line in rep.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- (.+?) (\d+):(\d+): (SCRIPT|EMPTY|LOOP|UNTRANSLATED)", line)
        if m:
            out.setdefault((m.group(1), int(m.group(2))), set()).add(int(m.group(3)))
            continue
        m = re.match(r"- (.+?) (\d+): MISSING verses \[([\d, ]+)\]", line)
        if m:
            out.setdefault((m.group(1), int(m.group(2))), set()).update(int(x) for x in m.group(3).split(","))
    return out


_names = {}


def names_in(text, lang):
    """The target's own spellings for the names this verse contains. The
    system prompt lists every name the language has a spelling for, but that
    list stands thousands of characters from the verse, and Aram came back in
    Korean four times with it there. The ones this verse needs are put beside
    it, where the model is looking."""
    if lang not in _names:
        f = ROOT / "targets" / lang / "names.json"
        _names[lang] = json.loads(f.read_text(encoding="utf-8"))["names"] if f.exists() else {}
    # Whole words, allowing the one- or two-letter prefixes Hebrew hangs on a
    # name (and-, in-, to-, from-, the-): a bare substring match found Ham
    # inside a verb in Isaiah 7:1.
    words = {MARKS.sub("", w) for w in re.split(r"[\s־]+", text) if w}   # split at the maqaf before the marks go: MARKS takes it too
    out = {}
    for k, v in _names[lang].items():
        for alt in k.split("/"):
            alt = alt.strip()
            if alt and any(w == alt or (w.endswith(alt) and 1 <= len(w) - len(alt) <= 2
                                        and set(w[:-len(alt)]) <= set("ובכלמהש")) for w in words):
                out[alt] = v
    return out


def prompt(meta, ch, n, src_verses, have, lang, why):
    src = {v["v"]: v for v in src_verses}
    name = TARGETS[lang]["name"]
    lines = [f"Book: {meta['name']} — chapter {ch}. Target language: {name}.", "",
             f"One verse of this chapter needs translating again: verse {n}. "
             + (f"The rendering it has is unusable ({'; '.join(why)}). " if why else "")
             + f"Write every word, and every name, in {name} letters only.", ""]
    fixed = T.chapter_names(meta, ch, lang)
    if fixed:
        lines += [f"NAMES IN THIS CHAPTER — use exactly these {name} spellings:",
                  "; ".join(f"{k} = {v}" for k, v in fixed.items()), ""]
    around = [k for k in sorted(have, key=int) if 0 < abs(int(k) - n) <= AROUND and int(k) in src]
    if around:
        lines += ["THE VERSES AROUND IT, AS ALREADY TRANSLATED (keep their voice; do not re-output them):"]
        lines += [f"[{k}] {have[k].strip()}" for k in around]
        lines.append("")
    tag = " [Aramaic]" if src[n].get("lang") == "arc" else ""
    here = names_in(src[n]["text"], lang)
    if here:
        lines += [f"NAMES IN THIS VERSE, in {name} letters - use these spellings exactly:",
                  "; ".join(f"{k} = {v}" for k, v in here.items()), ""]
    lines += [f"SOURCE TEXT of verse {n}{tag}:", src[n]["text"], "",
              f"Output verse {n} only, as one line beginning [{n}], and nothing else - no notes, no other verse."]
    return "\n".join(lines)


def mend(code, ch, wanted, lang, system, dry=False, force=False):
    meta = BOOKS[code]
    jpath = ROOT / "output" / lang / "json" / f"{slug(meta['name'])}_{ch:02d}.json"
    mpath = ROOT / "output" / lang / slug(meta["name"]) / f"{slug(meta['name'])}_{ch:02d}.md"
    if not jpath.exists():
        print(f"  {meta['name']} {ch} [{lang}]: not translated yet, nothing to mend")
        return 0
    rec = json.loads(jpath.read_text(encoding="utf-8"))
    src_verses = load_source(code)["chapters"][str(ch)]
    have = rec["verses"]
    mended = 0
    for n in sorted(wanted):
        if n not in {v["v"] for v in src_verses}:
            print(f"  {meta['name']} {ch}:{n}: the source has no such verse")
            continue
        old = have.get(str(n), "")
        why = faults(old, lang) if old else ["missing"]
        if not why and not force:
            print(f"  {meta['name']} {ch}:{n}: reads as it should, left alone")
            continue
        if not why:
            why = []                    # asked for by number: the checks passed it, a reader did not
        user = prompt(meta, ch, n, src_verses, have, lang, why)
        if dry:
            print(f"  {meta['name']} {ch}:{n}: would ask ({'; '.join(why)})")
            continue
        got, said, tries, t0 = None, [], 0, time.time()
        for tries in range(1, TRIES + 1):
            # Each try after the first is told what the last one did wrong -
            # the model that wrote Aram in Korean wrote it in Arabic next, and
            # then Chinese for the disease - and is sampled colder, so it
            # keeps to the spellings it was given rather than reaching for
            # another alphabet's.
            ask = user if not said else user + (
                f"\n\nYOUR LAST ATTEMPT WAS REJECTED ({said[-1]}). Every letter of the verse must be "
                f"{TARGETS[lang]['name']}: spell each name with {TARGETS[lang]['name']} letters, "
                f"and use a plain {TARGETS[lang]['name']} word where you had a foreign one.")
            try:
                raw, resp = T.call_model(system, ask, {"temperature": 0.2} if said else None)
            except T.LoopError:
                said.append("loop")
                continue
            T.log_work(resp, time.time() - t0, job="mend")
            m = re.search(rf"^\[{n}\]\s*(.*)$", raw.strip(), re.M)
            text = (m.group(1) if m else raw).strip()
            bad = faults(text, lang)
            if not bad and text:
                got = text
                break
            said.append("; ".join(bad) or "empty")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "lang": lang, "book": meta["name"],
                                "chapter": ch, "verse": n, "was": why, "tries": tries, "ok": got is not None,
                                "old": old, "new": got, "failed_with": said}, ensure_ascii=False) + "\n")
        if got is None:
            print(f"  {meta['name']} {ch}:{n}: still wrong after {TRIES} tries ({' / '.join(said)}) - left as it was")
            continue
        have[str(n)] = got
        mended += 1
        print(f"  {meta['name']} {ch}:{n}: mended in {tries} ({'; '.join(why)}) -> {got[:60]}")
    if mended:
        rec["verses"] = {str(k): v for k, v in sorted(have.items(), key=lambda kv: int(kv[0]))}
        rec.setdefault("mended", []).extend(sorted(wanted))
        jpath.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(T.render_md(meta, ch, {int(k): v for k, v in rec["verses"].items()}, rec.get("notes")),
                         encoding="utf-8")
    return mended


def main():
    # A Windows console is cp1252 unless told otherwise, and the line that
    # reports a mended Chinese verse raised there - after the model had
    # answered and before the chapter was written, so the verse was lost.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("book", nargs="?", help="OSIS book code, e.g. 2Kgs")
    ap.add_argument("where", nargs="?", help="chapter, or chapter:verses, e.g. 5 or 5:1,20")
    ap.add_argument("--lang", default=T.DEFAULT_TARGET)
    ap.add_argument("--dry", action="store_true", help="say what would be asked and ask nothing")
    a = ap.parse_args()
    lang = a.lang
    force = bool(a.book and a.where and ":" in a.where)     # verses named by number are mended whatever the checks say
    if force:
        ch, vs = a.where.split(":", 1)
        todo = {(BOOKS[a.book]["name"], int(ch)): {int(x) for x in vs.split(",")}}
    else:
        todo = flagged(lang)
        if a.book:
            todo = {k: v for k, v in todo.items() if k[0] == BOOKS[a.book]["name"]
                    and (not a.where or k[1] == int(a.where))}
    if not todo:
        print(f"[{lang}] nothing to mend")
        return
    code_of = {m["name"]: c for c, m in BOOKS.items()}
    system = None if a.dry else T.build_system_prompt(lang)
    total = sum(len(v) for v in todo.values())
    print(f"[{lang}] {total} verse(s) in {len(todo)} chapter(s)")
    done = 0
    for (book, ch), verses in sorted(todo.items(), key=lambda kv: (BOOKS[code_of[kv[0][0]]]["num"], kv[0][1])):
        done += mend(code_of[book], ch, verses, lang, system, a.dry, force)
    print(f"[{lang}] {done} of {total} mended" + (" (dry run)" if a.dry else ""))


if __name__ == "__main__":
    main()
