#!/usr/bin/env python3
"""The interface in the reader's own language, and the books under their own names.

    python scripts/build_ui.py                 # every language, every string still missing
    python scripts/build_ui.py --lang th
    python scripts/build_ui.py --list          # what is marked and what is translated
    python scripts/build_ui.py --redo          # ask again for everything

A reader who is handed a Bible in Thai should not have to read English to open
it. The text has been Thai since the translation finished; the buttons around
it, the headings in the trays and the names of the books were still English, so
the first screen of a shared copy asked for a language the reader may not have.

Two kinds of string, and they are not alike:

  the interface   what the reader's own words for a control are - Books,
                  Search, Reading language. Short, and wrong if they are
                  literal: a heading is not a sentence, and a translation that
                  reads as a translation is worse than English.
  the books       the sixty-six names. These are not to be invented. Every
                  language with Bible readers already has names for them, the
                  ones printed in the Bibles those readers grew up with, and a
                  reader looking for Psalms wants the word their own Bible uses.

The English string is its own key, so a string nobody has translated yet still
reads as English in the reader rather than as a blank or a key. That also makes
this resumable in the only way that matters: whatever is missing is asked for,
whatever is there is left alone.

What is marked for translation is read out of scripts/build_site.py - t("...")
in the page's own code, and data-t="..." on the chrome the browser renders
itself - so this cannot drift from what the reader actually says.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                          # noqa: E402
import translate as T                                    # noqa: E402
from books import BOOKS, TARGETS                         # noqa: E402
from verify import OTHERS, SCRIPTS                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "scripts" / "build_site.py"
OUT = ROOT / "targets" / "ui" / "ui.json"
BATCH = 25                     # strings per call: small enough that one bad reply costs little
TRIES = 3


def marked():
    """The English the reader shows, read out of the page that shows it."""
    s = SITE.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"""(?<![\w.])t\((['"])(.+?)\1\)""", s):
        out.append(m.group(2))
    for m in re.finditer(r'data-t="([^"]+)"', s):
        out.append(m.group(1))
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def book_names():
    return [m["name"] for m in sorted(BOOKS.values(), key=lambda m: m["num"])]


def load():
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {"_comment": "The reader's interface and the names of the books, per display language. "
                        "The English string is the key; anything missing falls back to it. "
                        "Written by scripts/build_ui.py."}


def save(table):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# Words a book's own name is dressed in depending how the question lands - "the
# book of," "the book," an initial "the" - which are not part of the name and
# must not decide whether two answers "agree." Stripped only for comparing;
# the surviving answer is kept as the model actually wrote it.
BOOK_DRESSING = re.compile(r"^(?:the\s+)?(?:book\s+of\s+|\u0e2b\u0e19\u0e31\u0e07\u0e2a\u0e37\u0e2d|\u0e1e\u0e23\u0e30\u0e18\u0e23\u0e23\u0e21|\u0e40\u0e28\u0e40\u0e1f\u0e2d\u0e23\s+|s\u00e1ch\s+|book\s+)",
                            re.IGNORECASE)


def core(name):
    return BOOK_DRESSING.sub("", name).strip().lower()


def ask_book(lang, name):
    """One book's name in the reader's language, or None when it is not certain.

    Asked one at a time, because a list of twenty-five invited the model to
    free-associate down the page: Song of Songs came back as the demon king of
    the Ramayana singing of love, Daniel as David, and 1 Thessalonians as
    Philadelphia. Alone, most answers were already right.

    Asked three times and sampled, not asked once at zero temperature: at zero
    the same call twice is the same call twice, and agrees with itself about
    anything, wrong names included. Sampled, the answers agree on a name the
    language really has and scatter where the model is guessing - Genesis comes
    back the same every time; Song of Songs does not, until it is checked by a
    person. Two agreeing out of three is kept; less than that is left in
    English, which a reader can still match against a printed Bible, rather
    than risk a second invented name doing what the first one did.
    """
    tname = TARGETS[lang]["name"]
    testament = "New Testament" if BOOKS[next(c for c, m in BOOKS.items() if m["name"] == name)]["testament"] == "NT" \
        else "Old Testament"
    system = (f"You know the {tname} Bible as its readers know it, and you answer with a name and "
              f"nothing else.")
    user = (f"In a {tname} Bible, what is the book of {name} called? It is the {testament} book of that "
            f"name.\n\nGive the name exactly as it is printed in the table of contents of a {tname} "
            f"Bible - the name a {tname} reader would look for. Many book names in {tname} are ordinary "
            f"{tname} words that translate the meaning of the title rather than spellings of the English "
            f"sound, so give whichever of the two that language actually uses.\n\nAnswer with the name "
            f"alone. Do not number it and do not put any list marker in front of it. No English, no "
            f"explanation, no quotation marks.")
    answers = []
    for _ in range(5):
        t0 = time.time()
        try:
            raw, resp = T.call_model(system, user, {"temperature": 0.6})
        except T.LoopError:
            continue
        T.log_work(resp, time.time() - t0, job="ui")
        got = raw.strip().splitlines()[-1].strip().strip('"\u201c\u201d') if raw.strip() else ""
        got = re.sub(r"^\s*\d+\s*[.)]\s*", "", got).strip()      # a list marker it was told not to use
        if got and len(got) <= 40 and not bad_script(got, lang):
            answers.append(got)
    if len(answers) < 2:
        return None
    groups = {}
    for a in answers:
        groups.setdefault(core(a), []).append(a)
    key, members = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(members) < 2:
        return None
    # Kept as the fullest form among the agreeing answers - "\u0e2b\u0e19\u0e31\u0e07\u0e2a\u0e37\u0e2d\u0e1b\u0e10\u0e21\u0e01\u0e32\u0e25"
    # over "\u0e1b\u0e10\u0e21\u0e01\u0e32\u0e25" when both were given - since that is closer to how the
    # book is actually printed in a table of contents.
    return max(members, key=len)


def bad_script(text, lang):
    """True when another writing system has leaked into the name."""
    own = SCRIPTS.get(lang)
    if not own:
        return False
    if not re.search(f"[{own[0]}]", text):
        return True
    return bool(re.findall(f"[{OTHERS}]", re.sub(f"[{own[0]}]", "", text)))


def ask(lang, kind, items):
    """-> {english: translated} for one batch, or {} when the reply will not do."""
    name = TARGETS[lang]["name"]
    if kind == "books":
        what = (f"These are the names of books of the Bible. Give the name each one is known by to "
                f"{name} readers - the name printed in the Bibles they already read. Do not invent a "
                f"name and do not transliterate the English if a settled {name} name exists.")
    else:
        what = (f"These are the words on the buttons and headings of a Bible reading app, to be shown "
                f"to a {name} reader. Translate each as an interface would say it in {name}: short, "
                f"plain, and idiomatic. A heading is not a sentence. Keep any ellipsis or trailing "
                f"punctuation. Where the English is a whole sentence of explanation, give a whole "
                f"sentence that reads naturally in {name} rather than word for word.")
    lines = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(items))
    user = (f"{what}\n\nAnswer with one line per item, numbered the same way, as\n"
            f"  <number>. <the {name}>\n"
            f"and nothing else - no English, no notes, no explanation.\n\n{lines}")
    system = (f"You translate the interface of a Bible reader into {name}. You answer only with the "
              f"numbered lines asked for.")
    for attempt in range(1, TRIES + 1):
        t0 = time.time()
        try:
            raw, resp = T.call_model(system, user, {"temperature": 0.2} if attempt > 1 else None)
        except T.LoopError:
            continue
        T.log_work(resp, time.time() - t0, job="ui")
        got = {}
        for line in raw.splitlines():
            m = re.match(r"\s*(\d+)[.)]\s*(.+)", line.strip())
            if not m:
                continue
            n = int(m.group(1))
            if 1 <= n <= len(items):
                got[items[n - 1]] = m.group(2).strip()
        # Every line back, and none of them still in English: a reply that
        # echoes the prompt is worse than no reply, because it looks translated.
        if len(got) == len(items) and not any(v == k for k, v in got.items() if len(k) > 3):
            return got
        print(f"    {lang}/{kind}: reply gave {len(got)} of {len(items)}, asking again ({attempt}/{TRIES})",
              file=sys.stderr)
    return {}


def run(langs, redo=False):
    table = load()
    ui_items, book_items = marked(), book_names()
    for lang in langs:
        have = table.setdefault(lang, {})
        for kind, items in (("ui", ui_items), ("books", book_items)):
            done = {} if redo else dict(have.get(kind) or {})
            todo = [s for s in items if s not in done]
            # A string the reader no longer shows is dropped, so the file says
            # what the page says and nothing else.
            done = {k: v for k, v in done.items() if k in items}
            if not todo:
                print(f"  {lang}/{kind}: {len(done)} already, nothing to ask")
                have[kind] = done
                continue
            print(f"  {lang}/{kind}: {len(done)} already, {len(todo)} to ask")
            if kind == "books":
                unsure = []
                for n, name in enumerate(todo, 1):
                    got = ask_book(lang, name)
                    if got:
                        done[name] = got
                    else:
                        unsure.append(name)
                    have[kind] = done
                    if n % 10 == 0 or n == len(todo):
                        save(table)
                        print(f"    {lang}/books: {len(done)}/{len(items)}, {len(unsure)} left in English")
                if unsure:
                    print(f"    {lang}: no settled name for {', '.join(unsure)} - "
                          f"the reader shows the English for these", file=sys.stderr)
                continue
            for i in range(0, len(todo), BATCH):
                batch = todo[i:i + BATCH]
                got = ask(lang, kind, batch)
                if not got:
                    print(f"    {lang}/{kind}: gave up on {len(batch)} after {TRIES} tries", file=sys.stderr)
                    continue
                done.update(got)
                have[kind] = done
                save(table)          # written as it goes, so a stop loses one batch at most
                print(f"    {lang}/{kind}: {len(done)}/{len(items)}")
            have[kind] = done
    save(table)
    total = sum(len(v.get("ui", {})) + len(v.get("books", {})) for k, v in table.items() if not k.startswith("_"))
    print(f"ui: {total} strings in {len([k for k in table if not k.startswith('_')])} languages -> {OUT}")
    manifest.record("interface", total, "strings",
                    "the reader's own words, and the books' names", "build_ui.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", default="", help="comma list; default is every complete target but English")
    ap.add_argument("--redo", action="store_true", help="ask again for strings already translated")
    ap.add_argument("--list", action="store_true", help="say what is marked and what is translated")
    a = ap.parse_args()
    ui_items, book_items = marked(), book_names()
    if a.list:
        table = load()
        print(f"marked in the reader: {len(ui_items)} interface strings, {len(book_items)} book names")
        for lang in sorted(k for k in table if not k.startswith("_")):
            u, b = table[lang].get("ui", {}), table[lang].get("books", {})
            print(f"  {lang}: ui {len(u)}/{len(ui_items)}, books {len(b)}/{len(book_items)}")
        missing = [s for s in ui_items if len(s) > 90]
        if missing:
            print(f"\n{len(missing)} marked strings are long prose:")
            for s in missing[:5]:
                print(f"   {s[:80]}…")
        return
    langs = [x.strip() for x in a.lang.split(",") if x.strip()] if a.lang else \
            [c for c in TARGETS if c != "en"]
    bad = [l for l in langs if l not in TARGETS]
    if bad:
        raise SystemExit(f"unknown language(s): {', '.join(bad)}")
    run(langs, a.redo)


if __name__ == "__main__":
    main()
