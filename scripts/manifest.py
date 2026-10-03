"""A small record of what has been built, for the dashboard's progress bar.

Each builder calls `record(...)` when it finishes; the dashboard reads
site/morph/manifest.json and shows the layer, how much is in it, and how old it
is. Keeping the counts here means the dashboard never has to parse the large
data files to know what exists.
"""
import json
import time
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "site" / "morph" / "manifest.json"
LOCK = PATH.with_suffix(".lock")


def record(layer: str, count: int, unit: str = "", note: str = "", script: str = ""):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    except json.JSONDecodeError:
        data = {}
    data[layer] = {"count": int(count), "unit": unit, "note": note, "script": script,
                   "built": time.time()}
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
