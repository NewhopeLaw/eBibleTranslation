#!/usr/bin/env python3
"""The work queue: long model jobs, run one after another until they are done.

    python scripts/work.py                 # run the whole queue, resuming everything
    python scripts/work.py --list          # what is queued and how far along it is
    python scripts/work.py --only lexicon,domains
    python scripts/work.py --hours 8       # stop starting new jobs after this long

Every job here is resumable: each writes its results as it goes and skips what
is already written, so the queue can be stopped with Ctrl-C or a reboot and
started again. Nothing in the queue touches a translation run — if the
dashboard is translating, both share the GPU and simply go slower.

Progress is appended to logs/work.log; `--list` reads the same counts the jobs
themselves use, so it is accurate after an interrupted run.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import TARGETS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEX = ROOT / "targets" / "lexicon"
LOG = ROOT / "logs" / "work.log"
S = ROOT / "scripts"


def count_lines(p):
    return sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip()) if p.exists() else 0


def lexeme_total(min_count=2):
    f = ROOT / "site" / "morph" / "conc.js"
    if not f.exists():
        return 0
    s = f.read_text(encoding="utf-8")
    conc = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";\n").rstrip(";"))
    return sum(1 for v in conc.values() if len(v) >= min_count)


def jobs():
    """Each: name, what it does, how many are done, how many there are, the command."""
    out = [
        ("lexemes", "grow our own lexeme inventory from every word form in the text",
         count_lines(ROOT / "targets" / "lexemes" / "forms.jsonl"), 80894,
         [sys.executable, str(S / "build_lexemes.py")]),
        ("lexicon", "write a lexicon entry for every lexeme, from its occurrences",
         count_lines(LEX / "entries.jsonl"), lexeme_total(2),
         [sys.executable, str(S / "build_lexicon.py"), "--min-count", "2"]),
        ("domains", "sort every lexeme into this project's fields of meaning",
         count_lines(LEX / "domains.jsonl"), lexeme_total(1),
         [sys.executable, str(S / "build_domains.py")]),
    ]
    out.append(("themes", "read every chapter and say what it is about",
                count_lines(ROOT / "targets" / "themes" / "chapters.jsonl"), 1189,
                [sys.executable, str(S / "build_themes.py"), "--chapters", "--consolidate", "--pack"]))
    out.append(("theme-names", "name each theme in the language of the text",
                count_lines(ROOT / "targets" / "themes" / "faces.jsonl"), 300,
                [sys.executable, str(S / "build_themes.py"), "--faces", "--pack"]))
    out.append(("topics", "write the line that lets each verse be found by someone who cannot quote it",
                count_lines(ROOT / "targets" / "search" / "topics.jsonl"), 1189,
                [sys.executable, str(S / "build_topics.py")]))
    # build_people.py is not queued. It has been run on one chapter and nothing
    # reads what it writes yet, and a queue left running overnight should not
    # spend 1,189 calls on a job nobody has looked at the output of. Run it by
    # hand - python scripts/build_people.py --chapters --gather --pack - and put
    # it back here once a book's worth has been read and found right.
    out.append(("book-arguments", "say what each book argues, from its chapter themes",
                count_lines(ROOT / "targets" / "themes" / "books.jsonl"), 66,
                [sys.executable, str(S / "build_theology.py"), "--books", "--pack"]))
    out.append(("trajectories", "trace how each theme develops across the canon",
                count_lines(ROOT / "targets" / "themes" / "trajectories.jsonl"), 300,
                [sys.executable, str(S / "build_theology.py"), "--trajectories", "--pack"]))
    for code in TARGETS:
        if code == "en" or TARGETS[code].get("mt"):        # the chat model does not write an mt target (README)
            continue
        out.append((f"lexicon-{code}", f"translate the lexicon into {TARGETS[code]['name']}",
                    count_lines(LEX / f"{code}.jsonl"), count_lines(LEX / "entries.jsonl"),
                    [sys.executable, str(S / "translate_lexicon.py"), "--lang", code]))
    # A language the chat model cannot write is put through a translation model
    # taught for it (scripts/mt_translate.py), from our English. The job exists
    # once a taught model does; it resumes, so it is safe in the overnight queue,
    # and its progress is the chapters on disk, as for any translation.
    english = len(list((ROOT / "output" / "en" / "json").glob("*.json")))
    for code, t in TARGETS.items():
        if not t.get("mt"):
            continue
        taught = [m for m in (ROOT / "models" / f"madlad-{code}-names", ROOT / "models" / f"madlad-{code}")
                  if (m / "config.json").exists()]
        if not taught:
            continue
        out.append((f"translate-{code}", f"put our English into {t['name']} with the model taught from its Bible",
                    len(list((ROOT / "output" / code / "json").glob("*.json"))), english,
                    [sys.executable, str(S / "mt_translate.py"), "--lang", code, "--all", "--model", str(taught[0])]))
    out.append(("rebuild", "rebuild every layer and the reader page", 0, 1,
                [sys.executable, str(S / "build_all.py")]))
    total_left = sum(max(0, t - d) for _, _, d, t, _ in out if t)
    out.append(("queue", "every unfinished job, one after another",
                0 if total_left else 1, 1 if total_left else 1,
                [sys.executable, str(S / "work.py")]))
    return out


def log(line):
    LOG.parent.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")
    print(line, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated job names")
    ap.add_argument("--hours", type=float, default=0, help="stop starting new jobs after this many hours")
    a = ap.parse_args()
    todo = jobs()
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        todo = [j for j in todo if j[0] in want]
    if a.list:
        print(f"{'job':<16}{'done':>8}{'of':>9}   what it does")
        for name, what, done, total, _ in todo:
            left = max(0, total - done)
            print(f"{name:<16}{done:>8}{total:>9}   {what}" + ("" if left else "   [complete]"))
        return
    t0 = time.time()
    for name, what, done, total, cmd in todo:
        if a.hours and (time.time() - t0) / 3600 >= a.hours:
            log(f"stopping: {a.hours} h reached, {name} not started")
            break
        if total and done >= total and name != "rebuild":
            log(f"{name}: already complete ({done}/{total})")
            continue
        log(f"{name}: starting — {what} ({done}/{total} done)")
        started = time.time()
        r = subprocess.run(cmd, cwd=str(ROOT))
        mins = (time.time() - started) / 60
        log(f"{name}: finished in {mins:.0f} min (exit {r.returncode})")
    log("queue done")


if __name__ == "__main__":
    main()
