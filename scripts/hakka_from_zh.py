#!/usr/bin/env python3
"""Hakka (Sixian) from our Mandarin: word replacement first, the model second.

    python scripts/hakka_from_zh.py John 1                 # draft by table, then the model mends it into Hakka
    python scripts/hakka_from_zh.py John 1 --table-only    # the replacement alone, no model
    python scripts/hakka_from_zh.py John 1 --show          # print Mandarin, draft and Hakka side by side
    python scripts/hakka_from_zh.py --all                  # the whole Bible, New Testament first (resumes)

The work is done by scripts/from_zh.py, which explains it. What is Hakka's
own: the hand-made table in targets/hak/replace.json, the table drawn from
the MOE Taiwan Hakka dictionary (Sixian, sources/hakka-dict/, not in git),
and the style in prompts/targets/hak.txt. It is the dashboard's hakka-text
job (TTS processing).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import from_zh                      # noqa: E402
from from_zh import *               # noqa: E402,F401,F403 - Converter, keep_better, ... for scripts that import this

from_zh.setup("hak")

if __name__ == "__main__":
    from_zh.main("hak")
