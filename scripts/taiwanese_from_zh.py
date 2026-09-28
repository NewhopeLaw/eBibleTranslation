#!/usr/bin/env python3
"""Taiwanese Hokkien (台語) from our Mandarin: word replacement first, the model second.

    python scripts/taiwanese_from_zh.py John 1                 # draft by table, then the model mends it
    python scripts/taiwanese_from_zh.py John 1 --table-only    # the replacement alone, no model
    python scripts/taiwanese_from_zh.py John 1 --show          # print Mandarin, draft and Taiwanese side by side
    python scripts/taiwanese_from_zh.py --all                  # the whole Bible, New Testament first (resumes)

Made the way the Hakka is (scripts/from_zh.py explains it). What is
Taiwanese's own: the hand-made table in targets/nan/replace.json, the table
drawn from the MOE dictionary of Taiwan Southern Min (臺灣閩南語常用詞辭典,
as g0v keeps it; sources/taigi-dict/, not in git), and the style in
prompts/targets/nan.txt. Written in the MOE recommended characters, as the
style asks, so scripts/taiwanese_speech.py can look each word up in the same
dictionary for its Tâi-lô reading. It is the dashboard's taiwanese-text job
(TTS processing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import from_zh                      # noqa: E402
from from_zh import *               # noqa: E402,F401,F403

from_zh.setup("nan")

if __name__ == "__main__":
    from_zh.main("nan")
