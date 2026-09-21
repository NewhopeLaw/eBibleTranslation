#!/usr/bin/env python3
"""Translation driver.

Usage:
  translate.py Gen                 all chapters of Genesis (into English)
  translate.py Gen 1-3             chapters 1-3
  translate.py Gen 5 --lang zh     chapter 5 into Chinese
  translate.py --all --lang en,es  the whole Bible, canonical order, two targets
  translate.py --all --lang all    every target language

Skips chapters whose output already exists (resume); --force retranslates.
Writes, per target language <lang>:
  output/<lang>/<Book>/<Book>_<NN>.md   readable chapter (superscript verse numbers)
  output/<lang>/json/<Book>_<NN>.json   sidecar {verses, notes, raw} for verify.py
  logs/translate.jsonl                  one line per chapter: timing + token counts
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from books import BOOKS, DEFAULT_TARGET, LANGS, TARGETS, chapter_lang, parse_targets, slug

ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
PIVOT_LANG = "en"          # the translation the per-chapter name list is looked up through
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
NORM_DIR = ROOT / "sources" / "normalized"
LOG_PATH = ROOT / "logs" / "translate.jsonl"
WORK_LOG_PATH = ROOT / "logs" / "work.jsonl"   # one line per model call made by a study job
WORK_JOB = None                                # which queue job is calling; the builder sets it

SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
VERSE_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")

# Degenerate-repetition guard. A model can fall into "and barley, and meal,
# and roasted grain, and barley, and meal, ..." and never stop (2 Sam 17:28,
# whose Hebrew itself lists roasted grain twice, did exactly that). A stretch
# of text is a loop when its tail is one unit repeated back to back at least
# LOOP_MIN_REPEATS times, and the repeated stretch is at least LOOP_MIN_SPAN
# characters long — long enough that genuine scriptural refrains ("holy,
# holy, holy", "precept upon precept, precept upon precept") stay clear of it.
LOOP_MIN_REPEATS = 4
LOOP_MIN_SPAN = 150
LOOP_MAX_UNIT = 400
LOOP_WINDOW = LOOP_MAX_UNIT * LOOP_MIN_REPEATS + 200


class LoopError(Exception):
    """The model's output fell into a repeating loop; carries the unit."""

    def __init__(self, unit, text):
        super().__init__(f"output loops on {unit!r}")
        self.unit, self.text = unit, text


def loop_period(text):
    """Length of the unit the tail of `text` repeats, or 0 if it is not a
    degenerate loop. Checks every unit length up to LOOP_MAX_UNIT against the
    last LOOP_WINDOW characters, so it is cheap enough to run while streaming."""
    tail = text[-LOOP_WINDOW:]
    n = len(tail)
    for p in range(2, min(LOOP_MAX_UNIT, n // LOOP_MIN_REPEATS) + 1):
        unit = tail[-p:]
        if not unit.strip():
            continue
        reps = 1
        while reps * p + p <= n and tail[-(reps + 1) * p:-reps * p] == unit:
            reps += 1
        if reps >= LOOP_MIN_REPEATS and reps * p >= LOOP_MIN_SPAN:
            return p
    return 0


def loop_start(text, p):
    """Index where the period-p repetition at the end of `text` sets in."""
    k = len(text) - 1
    while k - p >= 0 and text[k - p] == text[k]:
        k -= 1
    return k - p + 1


def find_loop(text):
    """The unit `text` trails off repeating (its first pass, so it reads as
    the model first wrote it), or None if the text is not looping."""
    p = loop_period(text)
    if not p:
        return None
    k0 = loop_start(text, p)
    return text[k0:k0 + p]


def loop_verse(raw, unit):
    """Verse number in whose text the loop sets in, or '?'."""
    head = raw[:loop_start(raw, len(unit))]
    nums = [int(m.group(1)) for m in re.finditer(r"^\[(\d+)\]", head, re.M)]
    return nums[-1] if nums else "?"


def trim_loop(text, unit):
    """Cut a looping verse back to where the repetition sets in, keeping one
    pass of the repeated unit."""
    p = len(unit)
    k0 = loop_start(text, p)
    return text[:k0 + p].rstrip(" ,;:") + " […]"


LANG_NAME = {code: info["name"] for code, info in LANGS.items()}

# Optional live hooks (set by scripts/live.py). When on_token is set the model
# is called with stream=True and every token is passed to it as it arrives;
# on_event receives dicts describing chapter start/retry/done/skip.
on_token = None
on_event = None


def emit(**ev):
    if on_event:
        on_event(ev)


# ---------------------------------------------------------------- targets
def out_dir(lang):
    return ROOT / "output" / lang


def json_dir(lang):
    return ROOT / "output" / lang / "json"


def target_files(lang):
    return {"rules": ROOT / "prompts" / "targets" / f"{lang}.txt",
            "glossary": ROOT / "targets" / lang / "glossary.json",
            "names": ROOT / "targets" / lang / "names.json"}


def build_system_prompt(lang=DEFAULT_TARGET) -> str:
    if lang not in TARGETS:
        raise SystemExit(f"unknown target language {lang!r}")
    files = target_files(lang)
    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        raise SystemExit("target files missing: " + ", ".join(missing))
    core = (ROOT / "prompts" / "system_prompt.txt").read_text(encoding="utf-8")
    rules = files["rules"].read_text(encoding="utf-8").strip()
    glossary = json.loads(files["glossary"].read_text(encoding="utf-8"))
    names = json.loads(files["names"].read_text(encoding="utf-8"))

    def fmt(d):
        return "\n".join(f"- {k} -> {v}" for k, v in d.items() if not k.startswith("_"))

    return (core.replace("{LANGUAGE}", TARGETS[lang]["name"]).replace("{TARGET_RULES}", rules)
            + "\n\nGLOSSARY — Hebrew/Aramaic\n" + fmt(glossary["hebrew"])
            + "\n\nGLOSSARY — Greek\n" + fmt(glossary["greek"])
            + f"\n\nPROPER NAMES (use these {TARGETS[lang]['name']} spellings)\n" + fmt(names["names"]))


# ------------------------------------------------------------------ prompt
_name_map = {}


def chapter_names(meta, ch, lang):
    """The established spellings for the names in THIS chapter, or {}.

    The names a reader knows number in the thousands, and the whole list
    cannot be pasted into every prompt - it would crowd out the chapter. But
    one chapter holds a few dozen at most, and those are knowable in advance:
    our English is the pivot, so the names in the English of this chapter are
    the names in this chapter, whatever language it is going into.

    Without this the model invents a spelling per chapter with no memory of
    the last one, and the same man is 司提反 here and 斯提反 overleaf.
    targets/<lang>/names.map.json is written by scripts/build_names.py.
    """
    if lang == PIVOT_LANG:
        return {}
    if lang not in _name_map:
        f = ROOT / "targets" / lang / "names.map.json"
        _name_map[lang] = json.loads(f.read_text(encoding="utf-8"))["names"] if f.exists() else {}
    table = _name_map[lang]
    if not table:
        return {}
    pivot = ROOT / "output" / PIVOT_LANG / "json" / f"{slug(meta['name'])}_{int(ch):02d}.json"
    if not pivot.exists():
        return {}                       # not translated into the pivot yet; nothing to look up
    text = " ".join(json.loads(pivot.read_text(encoding="utf-8"))["verses"].values())
    found = {n: table[n] for n in set(re.findall(r"[A-Z][a-z]+(?:-[A-Z]?[a-z]+)*", text)) if n in table}
    return dict(sorted(found.items()))


def rough_tokens(text):
    """A deliberately pessimistic token count.

    Hebrew with its points, and Greek with its breathings, run at about a
    token a character - nothing like the four-to-one of English prose. Any
    estimate that is too generous here is worse than useless, so ASCII counts
    at a quarter and everything else at one.
    """
    ascii_n = sum(1 for c in text if c.isascii())
    return ascii_n // 4 + (len(text) - ascii_n)


def want_lxx(lines, verses, lang):
    """Whether the Septuagint column still fits beside the chapter.

    It is a reference, and the chapter is the text: when both will not fit,
    the reference goes. Past num_ctx the server drops the front of the prompt,
    which is where the instructions are - and a model that has lost them
    answers in the wrong language or copies the source back out. Psalm 119 and
    1 Kings 8, the two longest chapters here, failed that way in every
    language and left empty files behind that still counted as translated.
    """
    if not CONFIG.get("consult_lxx", True):
        return False
    budget = CONFIG["num_ctx"] - CONFIG.get("num_predict", 8192) - 1200   # reply, and the system prompt
    used = rough_tokens(NL.join(lines))
    extra = rough_tokens(NL.join(v["lxx"] for v in verses if v.get("lxx")))
    if used + extra <= budget:
        return True
    print(f"    (chapter too long for the Septuagint column as well: "
          f"{used}+{extra} tokens over a budget of {budget} - translating from the source alone)")
    return False


def build_user_prompt(meta, ch, verses, prev_translation, lang):
    src_lang = chapter_lang(meta, verses)
    lang_label = "Hebrew with an Aramaic section" if src_lang == "mixed" else LANG_NAME[src_lang]
    lines = [f"Book: {meta['name']} — chapter {ch}. Source language: {lang_label}. "
             f"Target language: {TARGETS[lang]['name']}.", ""]
    if prev_translation:
        lines += ["YOUR TRANSLATION OF THE PREVIOUS CHAPTER (for continuity of tone and recurring phrases — do not re-output it):",
                  prev_translation, ""]
    fixed = chapter_names(meta, ch, lang)
    if fixed:
        lines += [f"NAMES IN THIS CHAPTER — use exactly these {TARGETS[lang]['name']} spellings "
                  "(they are what readers of this language already know; do not invent your own):",
                  "; ".join(f"{k} = {v}" for k, v in fixed.items()), ""]
    lines.append(f"SOURCE TEXT ({meta['name']} {ch}, {len(verses)} verses — translate ALL {len(verses)}):")
    for v in verses:
        tag = " [Aramaic]" if src_lang == "mixed" and v.get("lang") == "arc" else ""
        lines.append(f"{v['v']}.{tag} {v['text']}")
    if want_lxx(lines, verses, lang) and any(v.get("lxx") for v in verses):
        lines += ["", "=== REFERENCE ONLY — NOT SOURCE TEXT ===",
                  "Below is the Septuagint, the ancient Greek version of this chapter. It is a reference "
                  "witness, not the text you are translating. The SOURCE TEXT above is the only basis of "
                  "the translation. Do not translate from the Greek, and do not let its wording, word "
                  "order, or additions shape your rendering where the Hebrew/Aramaic is clear. Consult it "
                  "only at a genuinely ambiguous, rare, or damaged reading in the Hebrew, and if you then "
                  "follow the Greek against the Hebrew, say so in the notes. Verse numbering may differ; "
                  "a missing number means no aligned verse.", ""]
        lines += [f"{v['v']}. {v['lxx']}" for v in verses if v.get("lxx")]
        lines += ["", "=== END OF REFERENCE. Translate the SOURCE TEXT. ==="]
    return "\n".join(lines)


def model_options(extra=None):
    """Ollama sampling options: num_ctx/temperature from config, plus any of
    repeat_penalty, repeat_last_n, presence_penalty, frequency_penalty, seed
    and num_predict that config sets. num_predict defaults to a ceiling well
    above the longest chapter, so a runaway generation cannot fill the
    context even when nothing else stops it."""
    opts = {"num_ctx": CONFIG["num_ctx"], "temperature": CONFIG["temperature"],
            "num_predict": CONFIG.get("num_predict", 8192)}
    for k in ("repeat_penalty", "repeat_last_n", "presence_penalty", "frequency_penalty", "seed"):
        if k in CONFIG:
            opts[k] = CONFIG[k]
    opts.update(extra or {})
    return opts


def log_work(resp, seconds, job=None):
    """Record one model call made by a study job (the lexicon, the fields of
    meaning, the themes...) in logs/work.jsonl, so the dashboard can count what
    the analysis costs apart from the translation."""
    try:
        WORK_LOG_PATH.parent.mkdir(exist_ok=True)
        with WORK_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "t": round(time.time(), 3),
                                "job": job or WORK_JOB or "work", "model": CONFIG["model"],
                                "seconds": round(seconds, 1),
                                "prompt_tokens": resp.get("prompt_eval_count"),
                                "output_tokens": resp.get("eval_count")}) + "\n")
    except OSError as e:                                    # a log must never stop a job
        print(f"    work log: {e}", file=sys.stderr)


def call_model(system, user, options=None):
    """Call the model. Raises LoopError as soon as the output is seen to be
    looping: mid-stream when streaming (the connection is dropped, which makes
    Ollama stop generating), otherwise once the reply is in."""
    payload = {
        "model": CONFIG["model"],
        "stream": on_token is not None,
        "think": CONFIG.get("think", False),
        "options": model_options(options),
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
                    text = resp["message"]["content"]
                    unit = find_loop(text)
                    if unit:
                        raise LoopError(unit, text)
                    return text, resp
                parts, resp, since_check = [], {}, 0
                for line in r:                       # NDJSON, one chunk per line
                    chunk = json.loads(line)
                    tok = chunk.get("message", {}).get("content", "")
                    if tok:
                        parts.append(tok)
                        on_token(tok)
                        since_check += len(tok)
                        if since_check >= 64:        # look for a loop every ~64 chars
                            since_check = 0
                            text = "".join(parts)
                            unit = find_loop(text)
                            if unit:
                                raise LoopError(unit, text)   # closes the connection
                    if chunk.get("done"):
                        resp = chunk
                text = "".join(parts)
                unit = find_loop(text)
                if unit:
                    raise LoopError(unit, text)
                return text, resp
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


RUBY_RE = re.compile(r"\{([^{}|\]]+)\|([^{}\]]+)[}\]]")      # {漢字|かんじ} furigana notation (Easy Japanese)


def render_md(meta, ch, verses, notes):
    """Superscript verse numbers; prose flows, poetry keeps its lines.
    Furigana notation becomes 漢字（かんじ） in the markdown."""
    verses = {n: RUBY_RE.sub(r"\1（\2）", t) for n, t in verses.items()}
    notes = RUBY_RE.sub(r"\1（\2）", notes or "")
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


def translate_chapter(meta, ch, verses, prev_translation, system, force=False, lang=DEFAULT_TARGET):
    name = slug(meta["name"])
    md_path = out_dir(lang) / name / f"{name}_{int(ch):02d}.md"
    json_path = json_dir(lang) / f"{name}_{int(ch):02d}.json"
    if md_path.exists() and not force:
        print(f"  {meta['name']} {ch} [{lang}]: exists, skipping")
        emit(type="skip", book=meta["name"], chapter=int(ch), target=lang)
        return json.loads(json_path.read_text(encoding="utf-8"))["verses"] if json_path.exists() else None

    expected = [v["v"] for v in verses]
    user = build_user_prompt(meta, ch, verses, prev_translation, lang)
    emit(type="start", book=meta["name"], chapter=int(ch), verses=len(expected),
         lang=chapter_lang(meta, verses), target=lang)
    t0 = time.time()
    max_attempts = CONFIG.get("max_attempts", 3)
    attempts, fix, options, looped = 0, "", None, None
    best = None                      # (score, raw, resp, parsed, notes, missing, extra, loop)
    while attempts < max_attempts:
        attempts += 1
        try:
            raw, resp = call_model(system, user + ("\n\n" + fix if fix else ""), options)
            loop = None
        except LoopError as e:
            raw, resp, loop = e.text, {}, e.unit
        parsed, notes, missing, extra = parse_output(raw, expected)
        if loop is None:
            # a loop the guard could not cut short (e.g. num_predict hit first)
            loop = next((u for t in parsed.values() for u in [find_loop(t)] if u), None)
        problems = (len(missing) + len(extra), 1 if loop else 0)
        if best is None or problems < best[0]:
            best = (problems, raw, resp, parsed, notes, missing, extra, loop)
        if problems == (0, 0):
            break
        if attempts >= max_attempts:
            break
        if loop:
            at = loop_verse(raw, loop)
            looped = loop
            fix = (f"Your translation of {meta['name']} {ch} broke off: at verse {at} it fell into "
                   f"repeating the same words over and over ({loop.strip()[:80]!r}). Translate the "
                   f"chapter again from the start. Render each word of the source once, in order; when "
                   f"a list ends, move on to the next verse. Every verse from {expected[0]} to "
                   f"{expected[-1]}, same format.")
            # stronger anti-repeat sampling for the retry only
            options = dict(CONFIG.get("loop_retry_options",
                                      {"repeat_penalty": 1.15, "presence_penalty": 1.0}))
        else:
            fix = (f"Your translation of {meta['name']} {ch} had a problem: "
                   + (f"missing verses {missing}. " if missing else "")
                   + (f"unexpected verse numbers {extra}. " if extra else "")
                   + "Output the COMPLETE chapter again, every verse from "
                   f"{expected[0]} to {expected[-1]}, same format.")
        print(f"    {meta['name']} {ch} [{lang}]: attempt {attempts} "
              + (f"looped on {loop.strip()[:60]!r}" if loop else f"missing={missing} extra={extra}")
              + f", retrying ({attempts + 1}/{max_attempts})", file=sys.stderr)
        emit(type="retry", book=meta["name"], chapter=int(ch), missing=missing, extra=extra,
             loop=(loop.strip()[:80] if loop else None), attempt=attempts, target=lang)
    _, raw, resp, parsed, notes, missing, extra, loop = best
    if loop:
        # keep the chapter (resume would otherwise never move on) but cut the
        # looping verse back to its first pass, so the file stays readable
        for n, t in list(parsed.items()):
            if find_loop(t):
                parsed[n] = trim_loop(t, loop)
    dt = time.time() - t0
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_md(meta, ch, parsed, notes), encoding="utf-8")
    json_path.write_text(json.dumps(
        {"book": meta["name"], "chapter": int(ch), "lang": lang,
         "verses": {str(k): v for k, v in sorted(parsed.items())},
         "notes": notes, "raw": raw}, ensure_ascii=False, indent=1), encoding="utf-8")

    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "book": meta["name"], "chapter": int(ch),
            "lang": lang, "model": CONFIG["model"], "seconds": round(dt, 1), "attempts": attempts,
            "prompt_tokens": resp.get("prompt_eval_count"), "output_tokens": resp.get("eval_count"),
            "missing": missing, "extra": extra, "loop": (loop.strip()[:80] if loop else None)}) + "\n")
    status = "OK" if not (missing or extra or loop) else (
        "WARN " + (f"missing={missing} extra={extra} " if missing or extra else "")
        + (f"loop={loop.strip()[:40]!r}" if loop else "")).strip()
    print(f"  {meta['name']} {ch} [{lang}]: {len(parsed)}/{len(expected)} vv, {dt:.0f}s, "
          f"{resp.get('eval_count')} tokens out [{status}]")
    emit(type="done", book=meta["name"], chapter=int(ch), got=len(parsed), expected=len(expected),
         seconds=round(dt, 1), tokens=resp.get("eval_count"), attempts=attempts, status=status, target=lang)
    return parsed


def prev_chapter_text(parsed_verses):
    if not parsed_verses:
        return None
    text = "\n".join(f"[{n}] {t}" for n, t in sorted(parsed_verses.items()))
    limit = CONFIG.get("max_prev_chars", 4000)
    return text[-limit:] if len(text) > limit else text


def run_book(code, chapters_arg, system, force, lang=DEFAULT_TARGET):
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
    print(f"{meta['name']} [{lang}]: chapters {wanted[0]}-{wanted[-1]}")
    prev = None
    for ch in wanted:
        parsed = translate_chapter(meta, ch, src["chapters"][ch], prev_chapter_text(prev),
                                   system, force, lang)
        prev = parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", nargs="?", help="OSIS book code, e.g. Gen")
    ap.add_argument("chapters", nargs="?", help="chapter or range, e.g. 1-3")
    ap.add_argument("--all", action="store_true", help="translate every book in order")
    ap.add_argument("--force", action="store_true", help="retranslate existing chapters")
    ap.add_argument("--lang", default=CONFIG.get("target", DEFAULT_TARGET),
                    help="target language code(s): en, zh, es, ja, th, a comma list, or 'all'")
    ap.add_argument("--keep-going", action="store_true",
                    help="never give up: on any error wait and retry the same book (resume skips "
                         "finished chapters) until everything requested is done or Ctrl-C")
    args = ap.parse_args()
    if not (args.all or args.book):
        ap.error("give a book code or --all")

    langs = parse_targets(args.lang)
    systems = {lang: build_system_prompt(lang) for lang in langs}
    books = sorted(BOOKS, key=lambda c: BOOKS[c]["num"])
    # language-major: the whole request in the first language before the next
    jobs = [(code, None if args.all else args.chapters, lang)
            for lang in langs for code in (books if args.all else [args.book])]
    i, wait = 0, 15
    while i < len(jobs):
        code, chapters, lang = jobs[i]
        try:
            run_book(code, chapters, systems[lang], args.force, lang)
            i, wait = i + 1, 15
        except KeyboardInterrupt:
            print("\nstopped", file=sys.stderr)
            sys.exit(130)
        except Exception as e:                   # noqa: BLE001
            if not args.keep_going:
                raise
            print(f"  {BOOKS[code]['name']} [{lang}]: {type(e).__name__}: {e} — retrying in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
            wait = min(wait * 2, 300)


if __name__ == "__main__":
    main()
