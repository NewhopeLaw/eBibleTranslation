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
    for code in TARGETS:
        if code == "en":
            continue
        out.append((f"lexicon-{code}", f"translate the lexicon into {TARGETS[code]['name']}",
                    count_lines(LEX / f"{code}.jsonl"), count_lines(LEX / "entries.jsonl"),
                    [sys.executable, str(S / "translate_lexicon.py"), "--lang", code]))
    out.append(("rebuild", "rebuild every layer and the reader page", 0, 1,
                [sys.executable, str(S / "build_all.py")]))
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
