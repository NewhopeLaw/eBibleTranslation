#!/usr/bin/env python3
"""Our own semantic domains: every lexeme sorted into fields of meaning by the model.

    python scripts/build_domains.py --limit 200      # a first pass
    python scripts/build_domains.py                  # everything, resuming
    python scripts/build_domains.py --pack           # only rebuild site/morph/domains.js

Replaces the semantic-domain data of published lexicons, which is not licensed
to this project (see LEGAL.md 4f). The taxonomy below is this project's own
wording. Lexemes are sent to qwen3:32b in batches with their glosses and, where
we have written one, the senses from our own lexicon; the model assigns one to
three domains from the list and may say "other" when nothing fits.

Assignments append to targets/lexicon/domains.jsonl (resumable) and --pack
writes site/morph/domains.js:

    DOMAINS = {domain: [[tag, headword, gloss], ...]}
    DOMTAG  = {tag: [domain, ...]}
"""
import argparse
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import manifest                                       # noqa: E402
import translate as T                                    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MORPH = ROOT / "site" / "morph"
DIR = ROOT / "targets" / "lexicon"
OUT = DIR / "domains.jsonl"

TAXONOMY = [
    "God and the divine", "gods and idols", "spirits and the unseen", "worship and sacrifice", "priesthood and temple",
    "festivals and sacred time", "purity and defilement", "sin and guilt", "forgiveness and atonement", "covenant and oath",
    "law and command", "justice and judgement", "kingship and rule", "government and officials", "war and weapons",
    "peace and alliance", "nations and peoples", "family and kinship", "marriage and sex", "birth and childhood",
    "death and burial", "the body", "health and disease", "food and drink", "clothing and adornment",
    "houses and building", "cities and villages", "land and territory", "roads and travel", "ships and the sea",
    "farming and herding", "plants and trees", "animals", "birds", "fish and sea creatures", "insects and small creatures",
    "weather and sky", "water and rivers", "mountains and terrain", "fire and light", "metals and minerals",
    "crafts and tools", "trade and money", "weights and measures", "numbers and counting", "time and seasons",
    "speech and language", "writing and records", "knowledge and learning", "wisdom and folly", "thought and intention",
    "emotion: joy", "emotion: sorrow", "emotion: fear", "emotion: anger", "love and loyalty", "hatred and enmity",
    "desire and longing", "pride and humility", "truth and falsehood", "deceit and treachery", "help and rescue",
    "gift and reward", "poverty and wealth", "work and rest", "music and song", "dance and celebration",
    "movement: coming and going", "movement: rising and falling", "carrying and sending", "giving and taking",
    "making and destroying", "keeping and guarding", "seeking and finding", "beginning and ending", "size and quantity",
    "shape and appearance", "colour", "sound and silence", "existence and being", "possession and belonging",
    "cause and result", "ability and power", "necessity and permission", "similarity and difference",
    "place and position", "direction", "grammatical particle", "pronoun and reference", "conjunction and connection",
    "proper name: person", "proper name: place", "proper name: people or nation", "proper name: other",
]

SYSTEM = """You sort Hebrew, Aramaic and Greek biblical words into fields of meaning.

You get a numbered list of lexemes, each with a gloss and sometimes its senses. For each one, choose one to three fields from the list below — the ones a reader would expect to find that word under. Use "other" only when nothing fits.

FIELDS:
{TAXONOMY}

Reply with JSON only: {"assign": {"1": ["field", ...], "2": ["field", ...], ...}} using the numbers from the list. Use the field wording exactly as given. Proper names go under the matching "proper name" field. Particles, pronouns and conjunctions go under their grammatical field."""


def load_js(path, var):
    s = path.read_text(encoding="utf-8")
    i = s.index(var + "=") + len(var) + 1
    if var == "LEX":
        return json.loads(s[i:s.index(";\nMORPHX=", i)])
    return json.loads(s[i:].rstrip().rstrip(";\n").rstrip(";"))


def call(system, user):
    payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
               "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": 0.1},
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(json.loads(r.read()).get("message", {}).get("content", "{}"))


def pack():
    by_dom, by_tag = defaultdict(list), {}
    brief = load_js(MORPH / "lex.js", "LEX")
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            by_tag[r["tag"]] = r["domains"]
            e = brief.get(r["tag"]) or ["", "", "", ""]
            for d in r["domains"]:
                by_dom[d].append([r["tag"], e[0], e[3]])
    for d in by_dom:
        by_dom[d].sort(key=lambda x: x[1])
    body = ("DOMAINS=" + json.dumps(by_dom, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "DOMTAG=" + json.dumps(by_tag, ensure_ascii=False, separators=(",", ":")) + ";\n"
            + "DOMLIST=" + json.dumps(TAXONOMY, ensure_ascii=False, separators=(",", ":")) + ";\n")
    (MORPH / "domains.js").write_text(body, encoding="utf-8")
    manifest.record("fields", len(by_tag), "lexemes sorted", "fields of meaning", "build_domains.py")
    print(f"packed {len(by_tag)} lexemes into {len(by_dom)} fields -> site/morph/domains.js")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new lexemes")
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--pack", action="store_true")
    a = ap.parse_args()
    DIR.mkdir(parents=True, exist_ok=True)
    if a.pack:
        pack()
        return
    brief = load_js(MORPH / "lex.js", "LEX")
    conc = load_js(MORPH / "conc.js", "CONC")
    ours = {}
    f = DIR / "entries.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                ours[e["tag"]] = e
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["tag"])
    todo = [t for t, refs in sorted(conc.items(), key=lambda kv: -len(kv[1]))
            if len(refs) >= a.min_count and t not in done and t in brief]
    if a.limit:
        todo = todo[:a.limit]
    system = SYSTEM.replace("{TAXONOMY}", "\n".join("- " + d for d in TAXONOMY))
    valid = set(TAXONOMY) | {"other"}
    print(f"domains: {len(done)} assigned, {len(todo)} to do, batches of {a.batch} (model {T.CONFIG['model']})")
    t0, n = time.time(), 0
    with OUT.open("a", encoding="utf-8") as fh:
        for start in range(0, len(todo), a.batch):
            chunk = todo[start:start + a.batch]
            lines = []
            for i, tag in enumerate(chunk, 1):
                e = brief[tag]
                senses = ours.get(tag, {}).get("senses") or []
                extra = ("; senses: " + ", ".join(s.get("sense", "") for s in senses[:4])) if senses else ""
                lines.append(f"{i}. {e[0]} ({e[1]}) — {e[3]}{extra}")
            try:
                got = call(system, "\n".join(lines) + "\n\nAssign each.")
                assign = got.get("assign") or {}
            except Exception as ex:                                   # noqa: BLE001
                print(f"  batch at {start}: FAILED {ex}", file=sys.stderr)
                continue
            for i, tag in enumerate(chunk, 1):
                got_d = assign.get(str(i)) or []
                if isinstance(got_d, str):
                    got_d = [got_d]
                doms = [d for d in got_d if d in valid][:3]
                if not doms:
                    doms = ["other"]
                fh.write(json.dumps({"tag": tag, "domains": doms}, ensure_ascii=False) + "\n")
                n += 1
            fh.flush()
            el = time.time() - t0
            print(f"  {n}/{len(todo)} [{el / max(1, n) * 1000:.0f} ms each, {el / 60:.1f} min]")
    pack()


if __name__ == "__main__":
    main()
