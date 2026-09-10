#!/usr/bin/env python3
"""Translation driver.

Usage:
  translate.py Gen            all chapters of Genesis
  translate.py Gen 1-3        chapters 1-3
  translate.py Gen 5          chapter 5 only
  translate.py --all          every book, canonical order

Skips chapters whose output already exists (resume); --force retranslates.
Writes:
  output/<Book>/<Book>_<NN>.md      readable chapter (superscript verse numbers)
  output/json/<Book>_<NN>.json      sidecar {verses, notes, raw} for verify.py
  logs/translate.jsonl              one line per chapter: timing + token counts
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, slug

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
NORM_DIR = ROOT / "sources" / "normalized"
OUT_DIR = ROOT / "output"
LOG_PATH = ROOT / "logs" / "translate.jsonl"

SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
VERSE_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")

LANG_NAME = {"hbo": "Hebrew", "arc": "Aramaic", "grc": "Greek"}

# Optional live hooks (set by scripts/live.py). When on_token is set the model
# is called with stream=True and every token is passed to it as it arrives;
# on_event receives dicts describing chapter start/retry/done/skip.
on_token = None
on_event = None


def emit(**ev):
    if on_event:
        on_event(ev)


def build_system_prompt() -> str:
    base = (ROOT / "prompts" / "system_prompt.txt").read_text(encoding="utf-8")
    glossary = json.loads((ROOT / "glossary.json").read_text(encoding="utf-8"))
    names = json.loads((ROOT / "names.json").read_text(encoding="utf-8"))

    def fmt(d):
        return "\n".join(f"- {k} -> {v}" for k, v in d.items() if not k.startswith("_"))

    return (base
            + "\n\nGLOSSARY — Hebrew/Aramaic\n" + fmt(glossary["hebrew"])
            + "\n\nGLOSSARY — Greek\n" + fmt(glossary["greek"])
            + "\n\nPROPER NAMES (use these English spellings)\n" + fmt(names["names"]))


def chapter_lang(book_meta, verses) -> str:
    if book_meta["testament"] == "NT":
        return "grc"
    langs = {v.get("lang", "hbo") for v in verses}
    return "arc" if langs == {"arc"} else ("hbo" if langs == {"hbo"} else "mixed")


def build_user_prompt(meta, ch, verses, prev_english):
    lang = chapter_lang(meta, verses)
    lang_label = LANG_NAME.get(lang, "Hebrew with an Aramaic section")
    lines = [f"Book: {meta['name']} — chapter {ch}. Source language: {lang_label}.", ""]
    if prev_english:
        lines += [f"YOUR TRANSLATION OF THE PREVIOUS CHAPTER (for continuity of tone and recurring phrases — do not re-output it):",
                  prev_english, ""]
    lines.append(f"SOURCE TEXT ({meta['name']} {ch}, {len(verses)} verses — translate ALL {len(verses)}):")
    for v in verses:
        tag = " [Aramaic]" if lang == "mixed" and v.get("lang") == "arc" else ""
        lines.append(f"{v['v']}.{tag} {v['text']}")
    return "\n".join(lines)


def call_model(system, user):
    payload = {
        "model": CONFIG["model"],
        "stream": on_token is not None,
        "think": CONFIG.get("think", False),
        "options": {"num_ctx": CONFIG["num_ctx"], "temperature": CONFIG["temperature"]},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(CONFIG["api_url"], data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=3600) as r:
                if on_token is None:
                    resp = json.loads(r.read())
                    return resp["message"]["content"], resp
                parts, resp = [], {}
                for line in r:                       # NDJSON, one chunk per line
                    chunk = json.loads(line)
                    tok = chunk.get("message", {}).get("content", "")
                    if tok:
                        parts.append(tok)
                        on_token(tok)
                    if chunk.get("done"):
                        resp = chunk
                return "".join(parts), resp
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            print(f"    api error ({e}), retry {attempt + 1}/3 in 15s", file=sys.stderr)
            time.sleep(15)
    raise last_err


def parse_output(raw, expected):
    """Split model output into verses dict and notes. Continuation lines
    (poetry) belong to the preceding verse."""
    verses, notes_lines, cur = {}, [], None
    in_notes = False
    for line in raw.splitlines():
        if line.strip() == "---":
            in_notes = True
            continue
        if in_notes:
            notes_lines.append(line)
            continue
        m = VERSE_RE.match(line.strip())
        if m:
            cur = int(m.group(1))
            verses[cur] = m.group(2)
        elif cur is not None and line.strip():
            verses[cur] += "\n" + line.rstrip()
        elif cur is not None and not line.strip():
            verses[cur] += "\n"        # paragraph/stanza break marker
    missing = [n for n in expected if n not in verses]
    extra = [n for n in verses if n not in expected]
    return verses, "\n".join(notes_lines).strip(), missing, extra


def render_md(meta, ch, verses, notes):
    """Superscript verse numbers; prose flows, poetry keeps its lines."""
    out = [f"# {meta['name']} {ch}", ""]
    para = []

    def flush():
        if para:
            out.append(" ".join(para))
            out.append("")
            para.clear()

    for n in sorted(verses):
        text = verses[n]
        chunks = [c for c in text.split("\n\n")]
        for i, chunk in enumerate(chunks):
            if i > 0:
                flush()
            chunk = chunk.strip("\n")
            if "\n" in chunk:  # poetry: keep line breaks (hard breaks in md)
                flush()
                first, *rest = chunk.split("\n")
                out.append(f"{str(n).translate(SUP)} {first}  ")
                out.extend(f"{line.strip()}  " for line in rest)
                out.append("")
            elif chunk:
                para.append(f"{str(n).translate(SUP)} {chunk}")
    flush()
    if notes:
        out += ["---", "", notes if notes.lower().startswith("notes") else "Notes\n" + notes, ""]
    return "\n".join(out)


def translate_chapter(meta, ch, verses, prev_english, system, force=False):
    name = slug(meta["name"])
    md_path = OUT_DIR / name / f"{name}_{int(ch):02d}.md"
    json_path = OUT_DIR / "json" / f"{name}_{int(ch):02d}.json"
    if md_path.exists() and not force:
        print(f"  {meta['name']} {ch}: exists, skipping")
        emit(type="skip", book=meta["name"], chapter=int(ch))
        return json.loads(json_path.read_text(encoding="utf-8"))["verses"] if json_path.exists() else None

    expected = [v["v"] for v in verses]
    user = build_user_prompt(meta, ch, verses, prev_english)
    emit(type="start", book=meta["name"], chapter=int(ch), verses=len(expected),
         lang=LANG_NAME.get(chapter_lang(meta, verses), "Hebrew + Aramaic"))
    t0 = time.time()
    raw, resp = call_model(system, user)
    parsed, notes, missing, extra = parse_output(raw, expected)

    attempts = 1
    if missing or extra:
        fix = (f"Your translation of {meta['name']} {ch} had a problem: "
               + (f"missing verses {missing}. " if missing else "")
               + (f"unexpected verse numbers {extra}. " if extra else "")
               + "Output the COMPLETE chapter again, every verse from "
               f"{expected[0]} to {expected[-1]}, same format.")
        emit(type="retry", book=meta["name"], chapter=int(ch), missing=missing, extra=extra)
        raw, resp = call_model(system, user + "\n\n" + fix)
        parsed, notes, missing, extra = parse_output(raw, expected)
        attempts = 2

    dt = time.time() - t0
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_md(meta, ch, parsed, notes), encoding="utf-8")
    json_path.write_text(json.dumps(
        {"book": meta["name"], "chapter": int(ch),
         "verses": {str(k): v for k, v in sorted(parsed.items())},
         "notes": notes, "raw": raw}, ensure_ascii=False, indent=1), encoding="utf-8")

    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "book": meta["name"], "chapter": int(ch),
            "model": CONFIG["model"], "seconds": round(dt, 1), "attempts": attempts,
            "prompt_tokens": resp.get("prompt_eval_count"), "output_tokens": resp.get("eval_count"),
            "missing": missing, "extra": extra}) + "\n")
    status = "OK" if not (missing or extra) else f"WARN missing={missing} extra={extra}"
    print(f"  {meta['name']} {ch}: {len(parsed)}/{len(expected)} vv, {dt:.0f}s, "
          f"{resp.get('eval_count')} tokens out [{status}]")
    emit(type="done", book=meta["name"], chapter=int(ch), got=len(parsed), expected=len(expected),
         seconds=round(dt, 1), tokens=resp.get("eval_count"), attempts=attempts, status=status)
    return parsed


def prev_chapter_english(parsed_verses):
    if not parsed_verses:
        return None
    text = "\n".join(f"[{n}] {t}" for n, t in sorted(parsed_verses.items()))
    limit = CONFIG.get("max_prev_chars", 4000)
    return text[-limit:] if len(text) > limit else text


def run_book(code, chapters_arg, system, force):
    meta = BOOKS[code]
    src = json.loads((NORM_DIR / f"{meta['num']:02d}_{slug(meta['name'])}.json").read_text(encoding="utf-8"))
    all_ch = sorted(src["chapters"], key=int)
    if chapters_arg:
        if "-" in chapters_arg:
            a, b = chapters_arg.split("-")
            wanted = [c for c in all_ch if int(a) <= int(c) <= int(b)]
        else:
            wanted = [chapters_arg]
    else:
        wanted = all_ch
    print(f"{meta['name']}: chapters {wanted[0]}-{wanted[-1]}")
    prev = None
    for ch in wanted:
        parsed = translate_chapter(meta, ch, src["chapters"][ch], prev_chapter_english(prev),
                                   system, force)
        prev = parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS book code, e.g. Gen")
    ap.add_argument("chapters", nargs="?", help="chapter or range, e.g. 1-3")
    ap.add_argument("--all", action="store_true", help="translate every book in order")
    ap.add_argument("--force", action="store_true", help="retranslate existing chapters")
    args = ap.parse_args()

    system = build_system_prompt()
    if args.all:
        for code in sorted(BOOKS, key=lambda c: BOOKS[c]["num"]):
            run_book(code, None, system, args.force)
    elif args.book:
        run_book(args.book, args.chapters, system, args.force)
    else:
        ap.error("give a book code or --all")


if __name__ == "__main__":
    main()
