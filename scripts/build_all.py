#!/usr/bin/env python3
"""Rebuild every layer the reader uses, in order.

    python scripts/build_all.py            # everything
    python scripts/build_all.py --fast     # skip the slow ones (morphology, syntax)

Each step is independent and safe to re-run; the model-written lexicon is only
packed here, not generated (that is scripts/build_lexicon.py, which takes hours).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    ("morphology (STEPBible tags)", "build_morph.py", [], True),
    ("cross-references and parallels", "build_refs.py", [], False),
    ("textual apparatus", "build_apparatus.py", [], False),
    ("Greek syntax and domains", "build_syntax.py", [], True),
    ("places and map", "build_places.py", [], False),
    ("chronology", "build_chronology.py", [], False),
    ("search index", "build_index.py", [], False),
    ("lexicon (pack what exists)", "build_lexicon.py", ["--pack"], False),
    ("reader page", "build_site.py", [], False),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip the slow steps")
    a = ap.parse_args()
    t0 = time.time()
    for label, script, args, slow in STEPS:
        if a.fast and slow:
            print(f"-- skipped: {label}")
            continue
        print(f"-- {label}")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout + r.stderr).strip()
        if out:
            print("   " + out.replace("\n", "\n   "))
        if r.returncode:
            print(f"   FAILED ({r.returncode})", file=sys.stderr)
    print(f"-- done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
