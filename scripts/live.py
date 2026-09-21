#!/usr/bin/env python3
"""Live translation dashboard.

    python scripts/live.py            # http://localhost:8766

Runs the same driver as translate.py (same prompts, outputs, resume, logs)
but streams every token from Ollama to a browser page as it is generated,
with progress, tokens/sec and a log of finished chapters. Start/stop runs
from the page in any target language; while idle the page is a browser for
every chapter's original text and whatever translations exist.
Pure standard library, no server beyond this one file.
"""
import hashlib
import json
import os
import queue
import re
import sys
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                                                  # noqa: E402
from books import BOOKS, DEFAULT_TARGET, LANGS, MIXED, TARGETS, slug, verse_lang   # noqa: E402
import readaloud as RA                                                 # noqa: E402
import ask as ASK                                                      # noqa: E402

PORT = 8766
ROOT = T.ROOT
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)      # never flash a console at the user


class StopRun(Exception):
    pass


# ---------------------------------------------------------------- state / bus
LOCK = threading.Lock()
SUBS: list[queue.Queue] = []
STOP = threading.Event()
STATE = {
    "running": False, "model": T.CONFIG["model"], "status": "idle", "target": None,
    "current": None,        # {book, chapter, verses, lang, target, src, started, text, tokens}
    "recent": [],           # last finished chapters, newest first
    "last": None,           # the most recently finished chapter (same shape as current)
    "session": {"chapters": 0, "tokens": 0, "seconds": 0.0},   # since this server started
    "error": None,
}
NAME2META = {m["name"]: m for m in BOOKS.values()}
_norm_cache = {}
STARTED = time.time()          # so the work counter can say what this session cost


def publish(ev: dict):
    data = json.dumps(ev, ensure_ascii=False)
    with LOCK:
        dead = []
        for q in SUBS:
            try:
                q.put_nowait(data)
            except queue.Full:
                dead.append(q)
        for q in dead:
            SUBS.remove(q)


def norm_chapters(meta):
    key = slug(meta["name"])
    if key not in _norm_cache:
        f = ROOT / "sources" / "normalized" / f"{meta['num']:02d}_{key}.json"
        _norm_cache[key] = json.loads(f.read_text(encoding="utf-8"))["chapters"] if f.exists() else {}
    return _norm_cache[key]


def source_verses(book_name, ch):
    """[{v, text, lang}] of the original-language chapter (comparison view)."""
    meta = NAME2META.get(book_name)
    if not meta:
        return []
    return [{"v": v["v"], "text": v["text"], "lang": verse_lang(meta, v), **({"lxx": v["lxx"]} if v.get("lxx") else {})}
            for v in norm_chapters(meta).get(str(ch), [])]


def translated_chapters(meta, lang):
    name = slug(meta["name"])
    return sorted(int(f.stem.rsplit("_", 1)[1]) for f in T.json_dir(lang).glob(f"{name}_*.json"))


def chapter_counts(lang):
    """{code: (done, total)} for one target language."""
    return {code: (len(translated_chapters(meta, lang)), len(norm_chapters(meta)))
            for code, meta in BOOKS.items()}


_life = {"mtime": None, "data": None}


def lifetime():
    """Totals over every chapter ever logged in logs/translate.jsonl."""
    p = T.LOG_PATH
    if not p.exists():
        return {"chapters": 0, "output_tokens": 0, "prompt_tokens": 0, "seconds": 0, "tps": None, "by_lang": {}}
    m = p.stat().st_mtime
    if _life["mtime"] != m:
        d = {"chapters": 0, "output_tokens": 0, "prompt_tokens": 0, "seconds": 0.0, "by_lang": {}}
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            lg = r.get("lang", "en")
            d["chapters"] += 1
            d["output_tokens"] += r.get("output_tokens") or 0
            d["prompt_tokens"] += r.get("prompt_tokens") or 0
            d["seconds"] += r.get("seconds") or 0
            d["by_lang"][lg] = d["by_lang"].get(lg, 0) + 1
        d["tps"] = round(d["output_tokens"] / d["seconds"], 1) if d["seconds"] else None
        _life.update(mtime=m, data=d)
    return _life["data"]


def snapshot(lang=DEFAULT_TARGET):
    lang = lang if lang in TARGETS else DEFAULT_TARGET
    counts = chapter_counts(lang)
    books = [{"code": c, "name": BOOKS[c]["name"], "num": BOOKS[c]["num"],
              "testament": BOOKS[c]["testament"], "done": counts[c][0], "total": counts[c][1]}
             for c in sorted(BOOKS, key=lambda c: BOOKS[c]["num"])]
    with LOCK:
        s = dict(STATE)
        s["current"] = dict(STATE["current"]) if STATE["current"] else None
    s["lang"] = lang
    s["books"] = books
    s["bible_done"] = sum(b["done"] for b in books)
    s["bible_total"] = sum(b["total"] for b in books)
    s["targets"] = {c: {"name": t["name"], "native": t["native"],
                        "done": len(list(T.json_dir(c).glob("*.json")))} for c, t in TARGETS.items()}
    s["lifetime"] = lifetime()
    ss = s["session"]
    ss["tps"] = round(ss["tokens"] / ss["seconds"], 1) if ss["seconds"] else None
    return s


# ------------------------------------------------------------- driver hooks
def on_token(tok: str):
    if STOP.is_set():
        raise StopRun()
    with LOCK:
        cur = STATE["current"]
        if cur:
            cur["text"] += tok
            cur["tokens"] += 1
    publish({"type": "token", "t": tok})


def on_event(ev: dict):
    kind = ev["type"]
    if kind == "start":
        if STOP.is_set():
            raise StopRun()
        ev["src"] = source_verses(ev["book"], ev["chapter"])
        meta = NAME2META[ev["book"]]
        ev["chapters"] = sorted(norm_chapters(meta), key=int)          # for the chapter strip
        ev["translated"] = translated_chapters(meta, ev["target"])
        with LOCK:
            STATE["current"] = {"book": ev["book"], "chapter": ev["chapter"], "target": ev["target"],
                                "verses": ev["verses"], "lang": ev["lang"], "src": ev["src"],
                                "chapters": ev["chapters"], "translated": ev["translated"],
                                "started": time.time(), "text": "", "tokens": 0}
            STATE["status"] = f"translating {ev['book']} {ev['chapter']} → {TARGETS[ev['target']]['name']}"
    elif kind == "retry":
        with LOCK:
            cur = STATE["current"]
            if cur:
                cur["text"] += "\n\n--- retry: " + (
                    f"looped on {ev['loop']!r} " if ev.get("loop") else "") + (
                    f"missing {ev['missing']} " if ev["missing"] else "") + (
                    f"extra {ev['extra']}" if ev["extra"] else "") + "---\n\n"
    elif kind == "done":
        with LOCK:
            rec = {k: ev[k] for k in ("book", "chapter", "got", "expected", "seconds",
                                      "tokens", "attempts", "status", "target")}
            rec["tps"] = round(ev["tokens"] / ev["seconds"], 1) if ev.get("tokens") and ev["seconds"] else None
            STATE["recent"].insert(0, rec)
            del STATE["recent"][40:]
            ss = STATE["session"]
            ss["chapters"] += 1
            ss["tokens"] += ev.get("tokens") or 0
            ss["seconds"] += ev["seconds"]
            STATE["last"] = STATE["current"]     # keeps the comparison viewable after the run
            STATE["current"] = None
    publish(ev)


def worker(book, chapters, all_books, force, lang):
    """One run. A whole-Bible run keeps going until Stop: every chapter of
    every book (and, with lang == "all", the whole Bible in each target
    language in turn, English first), skipping what exists; a failure (Ollama
    down, bad output) is reported, waited out and retried rather than ending
    the run."""
    T.on_token, T.on_event = on_token, on_event
    langs = list(TARGETS) if lang == "all" else [lang]
    systems = {}
    try:
        for lg in langs:
            systems[lg] = T.build_system_prompt(lg)
        books = sorted(BOOKS, key=lambda c: BOOKS[c]["num"])
        # language-major: finish the whole Bible in the first language before the next
        jobs = [(code, lg) for lg in langs for code in (books if all_books else [book])]
        i, failures, wait = 0, 0, 15
        while i < len(jobs):
            if STOP.is_set():
                raise StopRun()
            code, lg = jobs[i]
            try:
                T.run_book(code, None if all_books else (chapters or None), systems[lg], force, lg)
                i, failures, wait = i + 1, 0, 15
            except StopRun:
                raise
            except Exception as e:               # noqa: BLE001 — keep going, resume skips finished chapters
                failures += 1
                msg = f"{BOOKS[code]['name']} [{lg}]: {type(e).__name__}: {e} — retry {failures} in {wait}s"
                print("run error:", msg, file=sys.stderr)
                with LOCK:
                    STATE["status"] = "retrying"
                    STATE["current"] = None
                publish({"type": "warn", "message": msg})
                if STOP.wait(wait):
                    raise StopRun()
                wait = min(wait * 2, 300)
        final = "finished"
    except StopRun:
        final = "stopped"
    except Exception as e:                       # noqa: BLE001 — only setup failures land here
        final = "error"
        with LOCK:
            STATE["error"] = f"{type(e).__name__}: {e}"
        print(f"run error: {e!r}", file=sys.stderr)
    finally:
        T.on_token = T.on_event = None
        with LOCK:
            STATE["running"] = False
            STATE["status"] = final
            STATE["current"] = None
        publish({"type": "run", "status": final, "error": STATE["error"]})


def start_run(req: dict) -> str | None:
    with LOCK:
        if STATE["running"]:
            return "already running"
        book = req.get("book") or ""
        lang = req.get("lang") or DEFAULT_TARGET
        all_books = book in ("", "ALL")
        if not all_books and book not in BOOKS:
            return f"unknown book {book!r}"
        if lang != "all" and lang not in TARGETS:
            return f"unknown target language {lang!r}"
        STOP.clear()
        STATE.update(running=True, status="starting", error=None, current=None, target=lang,
                     run={"book": "all books" if all_books else book, "chapters": req.get("chapters") or "",
                          "lang": "all languages" if lang == "all" else TARGETS[lang]["name"]})
    threading.Thread(target=worker, daemon=True,
                     args=(book, (req.get("chapters") or "").strip(), all_books,
                           bool(req.get("force")), lang)).start()
    publish({"type": "run", "status": "starting"})
    return None


def chapter_payload(code, ch, lang):
    """Source + every existing translation of one chapter, for browsing."""
    meta = BOOKS.get(code)
    if not meta:
        return None
    src = source_verses(meta["name"], ch)
    if not src:
        return None
    langs = {s["lang"] for s in src}
    name = slug(meta["name"])
    translations = {}
    for t in TARGETS:
        jp = T.json_dir(t) / f"{name}_{int(ch):02d}.json"
        if jp.exists():
            d = json.loads(jp.read_text(encoding="utf-8"))
            translations[t] = {"verses": d["verses"], "notes": d.get("notes", "")}
    return {"code": code, "book": meta["name"], "chapter": int(ch),
            "chapters": sorted(norm_chapters(meta), key=int),
            "translated": translated_chapters(meta, lang if lang in TARGETS else DEFAULT_TARGET),
            "lang": next(iter(langs)) if len(langs) == 1 else "mixed",
            "src": src, "verses": len(src), "translations": translations}


# The study layers, smallest unit of language first: the written forms, then
# words, then the dictionary words behind them, then meaning, then the notes
# that hang off a verse. Each entry: key in the manifest or the work queue.
LAYERS = [
    ("forms", "letters and forms", [
        ("lexeme-inventory", "word forms analysed", "job:lexemes"),
    ]),
    ("words", "words", [
        ("morphology", "every word parsed and glossed", None),
        ("clause-data", "each word's part in its clause", None),
        ("search-index", "every word found in every verse", None),
        ("topics", "the words a verse does not use, so it can still be found", "job:topics"),
        ("entries", "the study layers, reachable from the search box", None),
    ]),
    ("lexemes", "lexemes", [
        ("concordance", "every occurrence of every lexeme", None),
        ("lexicon-brief", "the reference lexicon", None),
        ("lexicon", "our own lexicon, written from the text", "job:lexicon"),
    ]),
    ("meaning", "meaning", [
        ("fields", "lexemes sorted into fields of meaning", "job:domains"),
        ("lexicon-translated", "our lexicon in the target languages", "job:lexicon-translations"),
    ]),
    ("themes", "themes", [
        ("themes", "what the chapters are about", "job:themes"),
        ("theme-names", "each theme named in the language of the text", "job:theme-names"),
    ]),
    ("arguments", "arguments", [
        ("book-arguments", "what each book argues", "job:book-arguments"),
        ("trajectories", "how a theme develops across the canon", "job:trajectories"),
    ]),
    ("notes", "notes on a verse", [
        ("text-notes", "readings of the editions and the scribes", None),
        ("cross-references", "verses that speak to each other", None),
        ("parallels", "passages that share their wording", None),
        ("places", "where it happens", None),
        ("people", "who everyone is, and who they came from", "job:people"),
        ("chronology", "what the text counts", None),
    ]),
]


WORKERS: dict = {}                      # job name -> Popen, for the jobs this dashboard started


def work_jobs():
    """The queue's job table: {name: (what, done, total, command)}."""
    import importlib
    try:
        w = importlib.import_module("work")
        importlib.reload(w)
        return {name: (what, done, total, cmd) for name, what, done, total, cmd in w.jobs()}
    except Exception as e:                                  # noqa: BLE001
        print(f"work queue unavailable: {e}")
        return {}


# A job can also have been started from a terminal or by start_work.cmd. The
# dashboard finds those by looking at what the running python processes are, so
# the buttons can stop them too — the point of the buttons is to free the GPU.
SCRIPT_JOB = {"build_lexemes.py": "lexemes", "build_lexicon.py": "lexicon", "build_domains.py": "domains",
              "build_themes.py": "themes", "build_index.py": "search-index",
              "build_topics.py": "topics", "build_people.py": "people",
              "build_entries.py": "entries"}
_scan = {"at": 0.0, "found": {}}


def foreign_jobs():
    """{job name: [pid, ...]} for our jobs running outside this dashboard.

    Read in-process with psutil so nothing is spawned: shelling out here would
    flash a console window at the user every time the bar refreshed.
    """
    if time.time() - _scan["at"] < 10:
        return _scan["found"]
    found = {}
    try:
        import psutil
    except ImportError:
        _scan.update(at=time.time(), found=found)
        return found
    mine = {proc.pid for proc in WORKERS.values() if proc.poll() is None}
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info
            if info["pid"] in mine or info["pid"] == me:
                continue
            if not (info["name"] or "").lower().startswith("python"):
                continue
            cmd = " ".join(info["cmdline"] or ())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        # A job started from a terminal inside the project is run as
        # "python scripts/build_topics.py", and its command line never mentions
        # the project at all. Matching on the text alone made those jobs
        # invisible here: the bar showed nothing and the stop button, whose
        # whole purpose is to free the GPU, had nothing to stop. Where the
        # process is running says it when the command line does not.
        if "eBibleTranslation" not in cmd:
            try:
                if not str(proc.cwd()).startswith(str(ROOT)):
                    continue
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        job = None
        for script, name in SCRIPT_JOB.items():
            if script in cmd:
                job = name
                break
        if "build_theology.py" in cmd:
            job = "trajectories" if "--trajectories" in cmd else "book-arguments"
        elif "translate_lexicon.py" in cmd:
            m = re.search(r"--lang\s+(\S+)", cmd)
            job = f"lexicon-{m.group(1)}" if m else None
        elif "work.py" in cmd and "--only" not in cmd and "--list" not in cmd:
            job = "queue"
        if job:
            found.setdefault(job, []).append(info["pid"])
    _scan.update(at=time.time(), found=found)
    return found


def worker_running(job):
    proc = WORKERS.get(job)
    if proc is not None and proc.poll() is None:
        return True
    return bool(foreign_jobs().get(job))


def work_start(job):
    """Run one job in its own process, so it can be stopped on its own."""
    if worker_running(job):
        return "already running"
    table = work_jobs()
    if job not in table:
        return f"unknown job {job!r}"
    cmd = table[job][3]
    log = ROOT / "logs" / f"job_{job}.log"
    log.parent.mkdir(exist_ok=True)
    fh = open(log, "a", encoding="utf-8", buffering=1)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | NO_WINDOW
    WORKERS[job] = subprocess.Popen(cmd, cwd=str(ROOT), stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                                    creationflags=flags)
    print(f"job {job}: started (pid {WORKERS[job].pid}) -> {log.name}")
    return None


def work_stop(job=None):
    """Stop one job, or every job — whether this dashboard started it or not."""
    stopped = []
    for name, proc in list(WORKERS.items()):
        if job and name != job:
            continue
        if proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
            stopped.append(name)
        WORKERS.pop(name, None)
    for name, pids in foreign_jobs().items():              # started from a terminal or start_work.cmd
        if job and name != job:
            continue
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
            stopped.append(name)
    _scan["at"] = 0.0
    if stopped:
        print(f"jobs stopped: {', '.join(sorted(set(stopped)))}")
    return sorted(set(stopped))


_wtok = {"mtime": None, "size": None, "data": None}


def work_tokens():
    """What the analysis has cost the model, counted apart from the
    translation: every call the study jobs logged in logs/work.jsonl, and the
    part of it that belongs to this session of the dashboard."""
    empty = {"calls": 0, "output_tokens": 0, "prompt_tokens": 0, "seconds": 0.0, "tps": None, "by_job": {},
             "session": {"calls": 0, "output_tokens": 0, "prompt_tokens": 0, "seconds": 0.0, "tps": None}}
    p = T.WORK_LOG_PATH
    if not p.exists():
        return empty
    st = p.stat()
    if (_wtok["mtime"], _wtok["size"]) != (st.st_mtime, st.st_size):
        d = json.loads(json.dumps(empty))                   # a fresh copy of the shape above
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out, pro, sec = r.get("output_tokens") or 0, r.get("prompt_tokens") or 0, r.get("seconds") or 0
            job = r.get("job") or "work"
            for t in (d, d["session"]) if (r.get("t") or 0) >= STARTED else (d,):
                t["calls"] += 1
                t["output_tokens"] += out
                t["prompt_tokens"] += pro
                t["seconds"] += sec
            b = d["by_job"].setdefault(job, {"calls": 0, "output_tokens": 0})
            b["calls"] += 1
            b["output_tokens"] += out
        for t in (d, d["session"]):
            t["seconds"] = round(t["seconds"], 1)
            t["tps"] = round(t["output_tokens"] / t["seconds"], 1) if t["seconds"] else None
        _wtok.update(mtime=st.st_mtime, size=st.st_size, data=d)
    return _wtok["data"]


# ------------------------------------------------------------------ the Android reader APK
# scripts/build_apk.py does the work and keeps logs/apk_build.json current; the
# dashboard only starts it, reads that file, and opens the folder at the end.
APK = {"proc": None, "checked": 0.0, "toolchain": None}


def apk_toolchain(fresh=False):
    """What build_apk.py would find: a JDK 17, the Android SDK, Gradle. Cached a minute."""
    import importlib
    if fresh or APK["toolchain"] is None or time.time() - APK["checked"] > 60:
        try:
            b = importlib.import_module("build_apk")
            importlib.reload(b)
            APK["toolchain"] = b.check()
        except Exception as e:                                # noqa: BLE001
            APK["toolchain"] = {"ready": False, "missing": [f"build_apk.py: {e}"]}
        APK["checked"] = time.time()
    return APK["toolchain"]


def apk_running_elsewhere():
    """A build started from a terminal, not from here - it keeps the same state file."""
    if time.time() - APK.get("scanned", 0.0) < 5:
        return APK.get("foreign", False)
    found = False
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if "build_apk.py" in " ".join(p.info["cmdline"] or ()) and p.pid != os.getpid():
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        pass
    APK.update(scanned=time.time(), foreign=found)
    return found


def apk_status():
    f = ROOT / "logs" / "apk_build.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        st = {}
    proc = APK["proc"]
    running = (proc is not None and proc.poll() is None) or apk_running_elsewhere()
    if st.get("state") == "running" and not running:
        # The file says running but nothing is: the build was killed or the
        # dashboard restarted under it. Say so rather than spin forever.
        st.update(state="failed", error=st.get("error") or "the build stopped before it finished - see logs/apk_build.log")
    return {**st, "running": running, "toolchain": apk_toolchain()}


def apk_start(setup=False, full=False):
    # Two Gradle builds in the same folder fight over its locks and its output,
    # so one at a time - including one started from a terminal.
    if APK["proc"] is not None and APK["proc"].poll() is None:
        return "an APK is already being built"
    APK["scanned"] = 0.0
    if apk_running_elsewhere():
        return "an APK is already being built, from a terminal"
    cmd = [sys.executable, str(ROOT / "scripts" / "build_apk.py")]
    if full:
        cmd.append("--full")
    if setup:
        # Only ever passed after the user said yes to the licence in the dashboard.
        cmd += ["--setup", "--accept-android-sdk-license"]
    log = ROOT / "logs" / "apk_build.log"
    log.parent.mkdir(exist_ok=True)
    fh = open(log, "w", encoding="utf-8", buffering=1)
    APK["proc"] = subprocess.Popen(cmd, cwd=str(ROOT), stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | NO_WINDOW)
    APK["checked"] = 0.0                     # a setup changes the answer
    print(f"apk: {'full' if full else 'reader'} build started (pid {APK['proc'].pid})"
          f"{' with setup' if setup else ''} -> {log.name}")
    return None


def apk_stop():
    """Stop a build this dashboard started - Gradle and its Java with it."""
    proc = APK["proc"]
    if proc is None or proc.poll() is not None:
        return "no build of ours is running"
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
    APK["proc"] = None
    APK["scanned"] = 0.0
    # The build cannot write its own ending once it is killed, and a state file
    # left saying "running" would be read as a crash. Say what really happened.
    f = ROOT / "logs" / "apk_build.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    st.update(state="stopped", step="", error="", finished=time.time())
    f.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print("apk: build stopped")
    return None


def apk_open():
    apk = apk_status().get("apk")
    if apk and Path(apk).exists():
        subprocess.Popen(f'explorer /select,"{apk}"', creationflags=NO_WINDOW)
    else:
        (ROOT / "dist").mkdir(exist_ok=True)
        os.startfile(str(ROOT / "dist"))                      # noqa: S606 - our own folder
    return apk


def work_progress():
    """Every layer, in order from the smallest unit of language to the largest."""
    import importlib
    manifest = {}
    f = ROOT / "site" / "morph" / "manifest.json"
    if f.exists():
        try:
            manifest = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    table = work_jobs()
    jobs = {name: (v[1], v[2]) for name, v in table.items()}
    tr_done = sum(d for n, (d, t) in jobs.items() if n.startswith("lexicon-"))
    tr_total = sum(t for n, (d, t) in jobs.items() if n.startswith("lexicon-")) or 1
    jobs["lexicon-translations"] = (tr_done, tr_total)
    out = []
    for gkey, glabel, items in LAYERS:
        entries = []
        for key, what, job in items:
            m = manifest.get(key) or {}
            done = total = 0
            if job and job.startswith("job:"):
                done, total = jobs.get(job[4:], (0, 0))
            elif m:
                done = total = m.get("count", 0)
            jobname = job[4:] if job and job.startswith("job:") else None
            entries.append({"key": key, "what": what, "done": done, "total": total,
                            "unit": m.get("unit", ""), "count": m.get("count", 0),
                            "built": m.get("built"), "job": jobname,
                            "running": bool(jobname) and worker_running(jobname),
                            "mine": bool(jobname) and jobname in WORKERS and WORKERS[jobname].poll() is None,
                            "startable": bool(jobname) and jobname in table})
        out.append({"group": gkey, "label": glabel, "items": entries})
    running = [i["key"] for g in out for i in g["items"] if i["running"]]
    return {"groups": out, "now": time.time(), "anyrunning": bool(running), "running": running,
            "tokens": work_tokens()}


REBUILD_LOCK = threading.Lock()


def rebuild_site() -> str:
    with REBUILD_LOCK:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW)
    return (r.stdout + r.stderr).strip()


def reader_stale() -> bool:
    """site/index.html missing, or older than any translation, source or the builder."""
    out = ROOT / "site" / "index.html"
    if not out.exists():
        return True
    built = out.stat().st_mtime
    newest = (ROOT / "scripts" / "build_site.py").stat().st_mtime
    for f in list((ROOT / "output").glob("*/json/*.json")) + list((ROOT / "sources" / "normalized").glob("*.json")):
        newest = max(newest, f.stat().st_mtime)
    return newest > built


# --------------------------------------------------------------- alignment
# Word alignment for the Side by side view: the page sends the word lists of
# one verse (original + translation), the model answers with index pairs.
# Cached per verse under logs/align/<lang>/, keyed by a hash of the words, so
# each verse costs one short model call ever. Same model and num_ctx as the
# translation run so Ollama never reloads the model for it.
ALIGN_LOCK = threading.Lock()
ALIGN_SYSTEM = """You align the words of a Bible verse in its original language with the words of a translation of it.
You get two numbered word lists. Reply with JSON only, of the form {"pairs": [[s, t], ...]}, where s is a source word number and t is the number of a translation word that renders it (or part of it).
Link every word that has a counterpart. A source word may link to several translation words and a translation word to several source words. Leave out words with no counterpart: articles, particles, object markers, conjunctions rendered by punctuation, helper words the translation added. Use only numbers that appear in the lists."""


def align_path(lang, book, ch):
    return ROOT / "logs" / "align" / lang / f"{slug(book)}_{int(ch):02d}.json"


def _parse_pairs(content, ns, nt):
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
    raw = data.get("pairs", data.get("alignment", [])) if isinstance(data, dict) else data
    pairs, seen = [], set()
    for pr in raw or []:
        if not isinstance(pr, (list, tuple)) or len(pr) != 2:
            continue
        try:
            a, b = (int(re.sub(r"\D", "", str(x)) or 0) for x in pr)
        except ValueError:
            continue
        if 1 <= a <= ns and 1 <= b <= nt and (a, b) not in seen:
            seen.add((a, b))
            pairs.append([a, b])
    return pairs


def align_verse(req):
    """-> (payload, http status). Reads the cache, else asks the model."""
    book, lang = req.get("book"), req.get("lang")
    src, tgt = req.get("src") or [], req.get("tgt") or []
    try:
        ch, v = int(req.get("chapter")), int(req.get("v"))
    except (TypeError, ValueError):
        return {"error": "bad chapter/verse"}, 400
    if book not in NAME2META or lang not in TARGETS:
        return {"error": "unknown book or language"}, 400
    if not src or not tgt or len(src) > 200 or len(tgt) > 400 or not all(isinstance(w, str) for w in src + tgt):
        return {"error": "bad word lists"}, 400
    names = {l["name"] for l in LANGS.values()}
    slang = req.get("slang") if req.get("slang") in names else ("Greek" if NAME2META[book]["testament"] == "NT" else "Hebrew")
    h = hashlib.sha1(json.dumps([src, tgt], ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    path = align_path(lang, book, ch)
    with ALIGN_LOCK:                       # one model call at a time; cache file consistent
        cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        e = cache.get(str(v))
        if e and e.get("h") == h:
            return {"pairs": e["pairs"], "cached": True}, 200
        user = (f"{book} {ch}:{v}\n\nSource ({slang}):\n"
                + "\n".join(f"s{i} {w}" for i, w in enumerate(src, 1))
                + f"\n\nTranslation ({TARGETS[lang]['name']}):\n"
                + "\n".join(f"t{i} {w}" for i, w in enumerate(tgt, 1))
                + '\n\nReply with JSON only: {"pairs": [[s, t], ...]} using the numbers.')
        payload = {"model": T.CONFIG["model"], "stream": False, "think": False, "format": "json",
                   "options": {"num_ctx": T.CONFIG["num_ctx"], "temperature": 0},
                   "messages": [{"role": "system", "content": ALIGN_SYSTEM},
                                {"role": "user", "content": user}]}
        rq = urllib.request.Request(T.CONFIG["api_url"], data=json.dumps(payload).encode("utf-8"),
                                    headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(rq, timeout=1800) as r:      # may queue behind a running chapter
                resp = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as ex:
            return {"error": f"model call failed: {ex}"}, 502
        pairs = _parse_pairs(resp.get("message", {}).get("content", ""), len(src), len(tgt))
        cache[str(v)] = {"h": h, "pairs": pairs, "model": T.CONFIG["model"], "seconds": round(time.time() - t0, 1)}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        return {"pairs": pairs, "cached": False, "seconds": cache[str(v)]["seconds"]}, 200


# ------------------------------------------------------------ the PC's search
# The reader served from here can put a question to the model (scripts/ask.py
# has the how and the why). It asks first whether there is a model to put it
# to, and is told at the same time whether the model is busy: a question takes
# its turn between a running job's requests, and the reader is owed the reason
# a five-second answer is taking forty.
def ask_status():
    with LOCK:
        busy = "a translation" if STATE["running"] else None
    if not busy:
        jobs = [j for j, proc in WORKERS.items() if proc.poll() is None] + [j for j, pids in foreign_jobs().items() if pids]
        busy = f"the {jobs[0]} job" if jobs else None
    return {"ok": True, "model": T.CONFIG["model"], "busy": busy}


# ------------------------------------------------------------------ server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):       # quiet; keep errors only
        if args and str(args[1]) not in ("200", "204"):
            super().log_message(fmt, *args)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _query(self):
        return {k: v[0] for k, v in parse_qs(self.path.split("?", 1)[1]).items()} if "?" in self.path else {}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        q = self._query()
        if path in ("/", "/index.html"):
            body = (PAGE.replace("__LANGS__", json.dumps({**LANGS, "mixed": MIXED}, ensure_ascii=False))
                        .replace("__TARGETS__", json.dumps({c: {"name": t["name"], "native": t["native"], "dir": t.get("dir", "ltr")}
                                                            for c, t in TARGETS.items()}, ensure_ascii=False))
                        .replace("__DEFAULT__", DEFAULT_TARGET)
                        .replace("__READALOUD_CSS__", RA.CSS)
                        .replace("__READALOUD_JS__", RA.js('#text', '.grid .o, .grid .e, .cmp .row .txt, p.ov, .notes, #text'))).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/state":
            self._json(snapshot(q.get("lang", DEFAULT_TARGET)))
        elif path == "/source":
            p = chapter_payload(q.get("book", ""), q.get("ch", "1"), q.get("lang", DEFAULT_TARGET))
            self._json(p or {"error": "no such chapter"}, 200 if p else 404)
        elif path == "/events":
            self.sse(q.get("lang", DEFAULT_TARGET))
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif path.startswith("/morph/") and re.fullmatch(r"/morph/[A-Za-z0-9_]+\.js", path):   # word tags, lexicon, concordance for the reader
            f = ROOT / "site" / "morph" / path.split("/")[-1]
            if not f.exists():
                self._json({"error": "not built — run scripts/build_morph.py"}, 404)
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/work":
            self._json(work_progress())
        elif path == "/apk":
            self._json(apk_status())
        elif path == "/reader-stale":
            self._json({"stale": reader_stale()})
        elif path == "/ask":
            self._json(ask_status())
        elif path in ("/reader", "/compare"):          # the offline reader; rebuilt first when translations are newer
            if path == "/reader" and reader_stale():
                print("reader: " + rebuild_site())
            f = ROOT / "site" / ("index.html" if path == "/reader" else "compare.html")
            if not f.exists():
                self._json({"error": f"{f.name} could not be built — see the console"}, 404)
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")            # a rebuilt reader must not be served from the browser cache
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"error": "not found"}, 404)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == "/start":
            err = start_run(self._body())
            self._json({"ok": err is None, "error": err}, 409 if err else 200)
        elif self.path == "/stop":
            STOP.set()
            self._json({"ok": True})
        elif self.path == "/work/start":
            err = work_start((self._body().get("job") or "").strip())
            self._json({"ok": err is None, "error": err}, 409 if err else 200)
        elif self.path == "/work/stop":
            self._json({"ok": True, "stopped": work_stop((self._body().get("job") or "").strip() or None)})
        elif self.path == "/apk/build":
            body = self._body()
            err = apk_start(bool(body.get("setup")), bool(body.get("full")))
            self._json({"ok": err is None, "error": err}, 409 if err else 200)
        elif self.path == "/apk/stop":
            err = apk_stop()
            self._json({"ok": err is None, "error": err}, 409 if err else 200)
        elif self.path == "/apk/open":
            self._json({"ok": True, "apk": apk_open()})
        elif self.path == "/rebuild":
            self._json({"ok": True, "output": rebuild_site()})
        elif self.path == "/align":
            payload, code = align_verse(self._body())
            self._json(payload, code)
        elif self.path == "/ask":
            req = self._body()
            payload, code = ASK.ask(req.get("q"), req.get("lang") or DEFAULT_TARGET, bool(req.get("fresh")))
            self._json(payload, code)
        else:
            self._json({"error": "not found"}, 404)

    def sse(self, lang):
        q: queue.Queue = queue.Queue(maxsize=5000)
        with LOCK:
            SUBS.append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._send("data: " + json.dumps({"type": "snapshot", **snapshot(lang)}, ensure_ascii=False))
            while True:
                try:
                    self._send("data: " + q.get(timeout=15))
                except queue.Empty:
                    self._send(": keepalive")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with LOCK:
                if q in SUBS:
                    SUBS.remove(q)

    def _send(self, line):
        self.wfile.write((line + "\n\n").encode("utf-8"))
        self.wfile.flush()


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>eBible — live translation</title>
<style>
:root { --bg:#faf8f4; --fg:#22201c; --muted:#7a736a; --accent:#7c5cbf; --ok:#2f8f5b;
        --warn:#c2782a; --err:#c23a3a; --card:#fff; --border:#e4ded4; --hl:#f3e8b8; --soft:#f1ede6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#181614; --fg:#e8e4dd; --muted:#948d82; --accent:#a98ee6; --ok:#5fbf8b;
          --warn:#e09a4a; --err:#e06060; --card:#221f1c; --border:#37322c; --hl:#4a4020; --soft:#1f1c19; }
}
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--fg); font:14px/1.5 system-ui, sans-serif;
  display:flex; flex-direction:column; height:100vh; }
header { display:flex; flex-wrap:wrap; gap:.6rem 1rem; align-items:center; padding:.55rem .9rem;
  border-bottom:1px solid var(--border); background:var(--card); }
.brand { display:flex; align-items:center; gap:.5rem; margin-right:auto; }
.brand b { font:600 17px Georgia, serif; } .brand span.sub { color:var(--muted); font-style:italic; }
.pill { padding:.15rem .6rem; border-radius:999px; font-size:12px; font-weight:600;
  background:var(--soft); color:var(--muted); border:1px solid var(--border); white-space:nowrap; }
.pill.run { background:var(--accent); color:#fff; border-color:var(--accent); animation:pulse 1.4s infinite; }
.pill.err { background:var(--err); color:#fff; border-color:var(--err); }
@keyframes pulse { 50% { opacity:.55; } }
.group { display:flex; align-items:center; gap:.35rem; padding:.25rem .4rem; border:1px solid var(--border);
  border-radius:10px; background:var(--bg); }
#mode { gap:.15rem; padding:.2rem; border-radius:999px; }
#mode span { padding:.3rem .8rem; border-radius:999px; cursor:pointer; color:var(--muted); font-size:13px; }
#mode span.on { background:var(--accent); color:#fff; }
.group .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:0 .25rem; }
select, input, button { font:13px system-ui, sans-serif; padding:.38rem .55rem; border:1px solid var(--border);
  border-radius:8px; background:var(--card); color:var(--fg); }
select { max-width:12rem; } input#ch { width:5.2rem; text-align:center; }
button { cursor:pointer; } button:hover:not(:disabled) { border-color:var(--accent); }
button.icon { width:2rem; padding:.38rem 0; }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); font-weight:600; }
button.stop { color:var(--err); }
button:disabled { opacity:.4; cursor:default; }
label.chk { display:flex; align-items:center; gap:.25rem; color:var(--muted); font-size:12px; }
/* Two areas, each its own rectangle with a line drawn between them: above, the
   translation (what the run is doing and what it has cost); below, the model
   work — the analysis jobs and their own token counter. */
.pane { flex:none; margin:.5rem .85rem; border:1px solid var(--border); border-radius:12px; overflow:hidden; background:var(--card); }
#split { flex:none; height:1px; margin:.1rem .85rem .45rem; background:var(--border); }
#work { display:block; padding:.4rem .9rem .5rem; margin-top:0; background:var(--soft); font-size:12px; color:var(--muted); }
#work .grp { display:flex; flex-wrap:wrap; align-items:center; gap:.25rem .8rem; padding:.1rem 0; }
#work .gl { width:6.6rem; flex:none; font-size:10px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); text-align:right; }
#work .j { display:flex; align-items:center; gap:.3rem; }
#work .j b { color:var(--fg); font-weight:600; font-variant-numeric:tabular-nums; }
#work .j .nm { cursor:pointer; text-decoration:underline dotted var(--border); text-underline-offset:2px; }
#work .j .nm:hover { color:var(--accent); text-decoration-color:var(--accent); }
#work .j .b { width:3.6rem; height:5px; background:var(--border); border-radius:3px; overflow:hidden; }
#work .j .b i { display:block; height:100%; background:var(--accent); transition:width .4s; }
#work .j.full .b i { background:var(--ok); }
#work .j.run b { color:var(--accent); } #work .j.run .b i { animation:pulse 1.4s infinite; }
#work .j.none { opacity:.45; }
/* What a job has cost, on its own rung. It used to be readable only by resting
   the pointer on the totals underneath, which on a touch screen meant not at
   all, and the one number a long job is judged by should not be behind a
   hover.

   The muted grey these secondary figures usually take comes to 4.01:1 against
   the panel in the light theme, under the 4.5:1 a reader is owed, so this one
   keeps the foreground colour and steps back by weight and size instead. */
#work .j .tk { color:var(--fg); font-weight:400; font-variant-numeric:tabular-nums; font-size:11px; }
#work .j button { font:11px system-ui,sans-serif; line-height:1; padding:.15rem .3rem; min-width:1.3rem; border:1px solid var(--border);
  border-radius:5px; background:var(--card); color:var(--muted); cursor:pointer; }
#work .j button:hover { border-color:var(--accent); color:var(--fg); }
#work .j button.on { background:var(--err); border-color:var(--err); color:#fff; }
#work .hd { display:flex; align-items:center; gap:.5rem; padding:0 0 .2rem; }
#work .hd b { font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); font-weight:600; }
#work .hd button { font:11px system-ui,sans-serif; padding:.15rem .5rem; border:1px solid var(--border); border-radius:6px;
  background:var(--card); color:var(--fg); cursor:pointer; }
#work .hd button.stopall { color:var(--err); border-color:var(--err); }
#work .wtot { display:flex; flex-wrap:wrap; gap:.2rem 1.6rem; margin:.35rem -.9rem -.5rem; padding:.35rem .9rem .45rem;
  border-top:1px solid var(--border); background:var(--card); }
#work .wtot small { font-size:10px; text-transform:uppercase; letter-spacing:.06em; margin-right:.5rem; }
#work .wtot b { color:var(--fg); font-variant-numeric:tabular-nums; font-weight:600; }
body.reading #work { display:none; }
#tpane { margin-bottom:.35rem; }
#stats { display:flex; flex-wrap:wrap; gap:.4rem .5rem; padding:.5rem .9rem; align-items:stretch;
  border-bottom:1px solid var(--border); background:var(--bg); }
.stat { display:flex; flex-direction:column; min-width:5.4rem; padding:.3rem .65rem; border-radius:8px; background:var(--card);
  border:1px solid var(--border); }
.stat small { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
.stat b { font-size:15px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.stat.wide { flex:1; min-width:12rem; justify-content:center; }
#bar { height:6px; background:var(--border); border-radius:3px; overflow:hidden; margin-top:.25rem; }
#bar i { display:block; height:100%; width:0; background:var(--accent); transition:width .4s; }
.tabs { display:flex; flex-wrap:wrap; gap:.25rem; align-self:center; margin-left:auto; align-items:center; }
.tabs span { padding:.3rem .7rem; border:1px solid var(--border); border-radius:999px; cursor:pointer;
  color:var(--muted); font-size:12px; user-select:none; background:var(--card); }
.tabs span.on { color:var(--fg); border-color:var(--accent); box-shadow:inset 0 0 0 1px var(--accent); }
.tabs span.off { opacity:.4; cursor:default; }
.tabs i.sep { width:1px; height:1.1rem; background:var(--border); margin:0 .2rem; }
#totals { display:flex; flex-wrap:wrap; gap:.3rem 2rem; padding:.3rem .9rem;
  font-size:12px; color:var(--muted); background:var(--card); }
#totals small { font-size:10px; text-transform:uppercase; letter-spacing:.06em; margin-right:.5rem; }
#totals b { color:var(--fg); font-variant-numeric:tabular-nums; font-weight:600; }
#strip { display:flex; flex-wrap:wrap; gap:.22rem; padding:.45rem .9rem; border-top:1px solid var(--border);
  background:var(--soft); align-items:center; }
#strip a.on { animation:none; }
#strip a.on.live { animation:pulse 1.4s infinite; }
#strip .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-right:.4rem; }
#strip a { font-size:12px; min-width:1.9rem; text-align:center; padding:.1rem .35rem; border:1px dashed var(--border);
  border-radius:6px; cursor:pointer; color:var(--muted); }
#strip a.tr { color:var(--fg); border-style:solid; background:var(--card); }
#strip a.on { background:var(--accent); color:#fff; border-color:var(--accent); }
.layout { display:flex; flex:1; min-height:0; }
.layout.left { flex-direction:row-reverse; }
#handle { flex:none; width:14px; display:flex; align-items:center; justify-content:center; cursor:pointer;
  background:var(--card); border-left:1px solid var(--border); color:var(--muted); font:11px system-ui; user-select:none; }
#handle:hover { background:var(--soft); color:var(--fg); }
.layout #handle { margin-left:auto; }                  /* spare width (capped plain view) goes to the far side of the text */
.layout.left #handle { margin-left:0; border-left:0; border-right:1px solid var(--border); }
.layout.left #text { margin-right:auto; }
.layout.closed aside { display:none; }
#reader { flex:1; min-width:0; border:0; background:var(--bg); }   /* the offline reader: read mode fills the layout with it */
.layout.reading #text, .layout.reading aside, .layout.reading #handle { display:none; }
body.reading #tpane, body.reading #split { display:none; }   /* read mode: no translation indicators */
body.reading #run { visibility:hidden; }       /* keeps its space, so the header and the toggle do not move between modes */
.phead { display:flex; justify-content:flex-end; gap:.25rem; margin:-.2rem 0 .1rem; }
.phead button { font-size:12px; padding:.15rem .45rem; color:var(--muted); }
#text { flex:1; overflow:auto; padding:1.2rem 1.6rem 4rem; font:17px/1.7 Georgia, "Times New Roman", serif; white-space:pre-wrap; }
#text.plain { max-width:54rem; }
#text sup { color:var(--accent); font:600 11px system-ui; margin-right:.2rem; }
#text .caret { display:inline-block; width:.5em; height:1em; background:var(--accent);
  vertical-align:-.15em; animation:pulse .8s infinite; margin-left:2px; }
.empty { color:var(--muted); font:15px system-ui; white-space:normal; }
.empty h3 { font:600 18px Georgia, serif; color:var(--fg); margin-bottom:.4rem; }
.notes { color:var(--muted); font-size:14px; margin-top:1.2rem; padding:.8rem 1rem; background:var(--card);
  border:1px solid var(--border); border-radius:10px; white-space:pre-wrap; }
.orig { font-family:"SBL Hebrew","Ezra SIL","Taamey Frank CLM","Times New Roman",serif; font-size:1.12em; line-height:2; }
.orig.greek { font-family:"Gentium Plus","SBL Greek","Palatino Linotype","Times New Roman",serif; font-size:1.05em; }
.orig[dir=rtl] { text-align:right; }
.lt { font:600 10px system-ui,sans-serif; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin:0 .3em; vertical-align:.5em; }
p.ov { margin:0 0 .5em; white-space:normal; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:0 2rem; align-items:start; white-space:normal; }
.grid > div { padding:.5rem .3rem; border-bottom:1px solid var(--border); }
.grid .e { white-space:pre-wrap; border-radius:6px; }
.grid .e.todo { color:var(--muted); }
.grid .e.active { background:var(--hl); }
#text .w { cursor:pointer; border-radius:3px; transition:background .12s; }
#text .w:hover, #text .w.hov { background:var(--soft); box-shadow:0 0 0 2px var(--soft); }
#text .w.link { background:var(--hl); box-shadow:0 0 0 2px var(--hl); }
#text .w.sel { background:var(--accent); color:#fff; box-shadow:0 0 0 2px var(--accent); }
.chhead .astat { margin-left:auto; font-style:italic; }
.chhead .astat.busy { color:var(--accent); animation:pulse 1.4s infinite; }
.grid .notes { grid-column:1 / -1; }
.cmp { border-bottom:1px solid var(--border); padding:.5rem 0; white-space:normal; }
.cmp .row { display:grid; grid-template-columns:5.5rem 1fr; gap:.6rem; padding:.12rem 0; align-items:baseline; }
.cmp .row .lab { font:600 11px system-ui,sans-serif; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; text-align:right; }
.cmp .row .txt { white-space:pre-wrap; } .cmp .row .txt.active { background:var(--hl); border-radius:6px; }
[lang="zh"], [lang="ja"] { font-family:Georgia, "Noto Serif CJK SC", "Noto Serif CJK JP", "Source Han Serif", "Yu Mincho", "MS Mincho", "SimSun", "Songti SC", serif; line-height:1.9; }
[lang="th"] { font-family:"Noto Serif Thai", "Leelawadee UI", "Tahoma", sans-serif; line-height:2; }
[lang="yue"], [lang="nan"], [lang="hak"] { font-family:Georgia, "Noto Serif CJK TC", "Source Han Serif TC", "PMingLiU", "Microsoft JhengHei", "Songti TC", serif; line-height:1.95; }
[lang="ja-easy"] { font-family:Georgia, "Noto Serif CJK JP", "Source Han Serif", "Yu Mincho", "MS Mincho", serif; line-height:2.3; }
ruby rt { font-size:.55em; color:var(--muted); letter-spacing:0; }
[lang="ko"] { font-family:"Noto Serif KR", "Batang", "Malgun Gothic", "Apple SD Gothic Neo", serif; line-height:1.9; }
[lang="fa"] { font-family:"Vazirmatn", "Noto Naskh Arabic", "Tahoma", "Segoe UI", serif; line-height:2.1; font-size:1.06em; }
[dir="rtl"] { text-align:right; }
.chhead { display:flex; align-items:baseline; gap:.7rem; margin-bottom:.9rem; white-space:normal; }
.chhead h2 { font:400 24px Georgia, serif; } .chhead small { color:var(--muted); font:13px system-ui; }
aside { width:290px; flex:none; border-left:0; overflow:auto; padding:.7rem .8rem; font-size:13px; background:var(--card); }
aside h3 { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:.5rem 0 .35rem; }
.tg { display:flex; flex-wrap:wrap; gap:.25rem; margin-bottom:.4rem; }
.tg span { font-size:11px; padding:.1rem .5rem; border-radius:999px; border:1px solid var(--border); color:var(--muted); cursor:pointer; }
.tg span.on { border-color:var(--accent); color:var(--fg); }
.rec { padding:.3rem .45rem; border-radius:6px; display:flex; justify-content:space-between; gap:.5rem; cursor:pointer; }
.rec:hover { background:var(--soft); }
.rec .ok { color:var(--ok); } .rec .warn { color:var(--warn); } .rec small { color:var(--muted); }
.bk { display:grid; grid-template-columns:1fr 3.2rem 2.6rem; align-items:center; gap:.4rem; padding:.16rem .45rem; border-radius:6px; cursor:pointer; color:var(--muted); }
.bk:hover { background:var(--soft); } .bk.on { background:var(--accent); color:#fff; }
.bk.part { color:var(--fg); } .bk.full { color:var(--ok); }
.bk .b { height:5px; background:var(--border); border-radius:3px; overflow:hidden; }
.bk .b i { display:block; height:100%; background:var(--accent); } .bk.full .b i { background:var(--ok); }
.bk.on .b i { background:#fff; }
.bk .ct { text-align:right; font-variant-numeric:tabular-nums; font-size:11px; }
@media (max-width:820px) { aside, #handle { display:none; } .grid { grid-template-columns:1fr; } .grid .o { border-bottom:0; padding-bottom:.1rem; } }
/* mobile preview: the content area becomes a 390x844 phone screen (scaled to fit), so the reader's own
   responsive rules fire as on a phone; the dashboard view gets its narrow-layout rules by class */
#app { display:flex; flex-direction:column; flex:1; min-height:0; }
body.mobile #app { flex:none; width:410px; height:864px; margin:.6rem auto 0; border:10px solid #15130f; border-radius:30px;   /* 390 x 844 inside the bezel: header, stats and content */
  box-shadow:0 0 0 1px #3a352e, 0 12px 40px rgba(0,0,0,.35); overflow:hidden; background:var(--bg); transform-origin:top center; }
body.mobile { background:var(--soft); }
body.mobile .layout aside, body.mobile .layout #handle { display:none; }
body.mobile .grid { grid-template-columns:1fr; } body.mobile .grid .o { border-bottom:0; padding-bottom:.1rem; }
body.mobile .pane { margin:.35rem .45rem; } body.mobile #split { margin:.05rem .45rem .3rem; }
body.mobile #text.plain { max-width:none; } body.mobile #text { padding:.9rem 1rem 3rem; }
#device { gap:.15rem; padding:.2rem; border-radius:999px; }
#device span { padding:.3rem .8rem; border-radius:999px; cursor:pointer; color:var(--muted); font-size:13px; }
#device span.on { background:var(--accent); color:#fff; }
/* The APK button sits with the other window-wide controls, so it is there in
   read and translate mode alike; its status line says what the build is doing. */
#apk { gap:.45rem; }
#apkKind { display:flex; gap:.15rem; padding:.15rem; border:1px solid var(--border); border-radius:999px; }
#apkKind span { padding:.25rem .6rem; border-radius:999px; cursor:pointer; color:var(--muted); font-size:12px; white-space:nowrap; }
#apkKind span.on { background:var(--accent); color:#fff; }
#apkKind.busy span { cursor:default; opacity:.5; }
#apk button { white-space:nowrap; }
#apkMsg { font-size:12px; color:var(--muted); max-width:24rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#apkMsg.err { color:var(--err); }
#apkMsg.ok { color:var(--fg); }
__READALOUD_CSS__
</style></head><body>
<div id="app">
<header>
  <div class="brand"><b>eBible</b><span class="sub">live translation</span><span class="pill" id="pill">idle</span><span class="pill" id="model"></span></div>
  <div class="group" id="run"><span class="lbl">Run</span>
    <select id="book"><option value="ALL">All books (canonical order)</option></select>
    <button class="icon" id="prev" title="previous chapter (←)">&#9664;</button>
    <input id="ch" placeholder="ch / 1-3">
    <button class="icon" id="next" title="next chapter (→)">&#9654;</button>
    <select id="lang" title="target language"></select>
    <label class="chk"><input type="checkbox" id="force"> force</label>
    <button class="primary" id="start">Start</button>
    <button class="stop" id="stop" disabled>Stop</button>
  </div>
  <div class="group" id="mode" title="read: the window becomes the reader (rebuilt when translations are newer) · translate: the live dashboard, with the side panel">
    <span data-m="read">read</span><span data-m="translate" class="on">translate</span>
  </div>
  <div class="group" id="device" title="mobile: preview the screen at phone size (390 x 844) for UI testing">
    <span data-d="pc" class="on">PC</span><span data-d="mobile">mobile</span>
  </div>
  <div class="group" id="apk" title="Build an Android app holding the reader alone - larger type, no study tools. It carries only the languages the whole Bible has been translated into; one still in progress is left out until it is finished">
    <span id="apkKind" role="group" aria-label="What goes in the APK">
      <span data-k="reader" class="on" title="The text alone, in every finished language: about a 11 MB APK, 26 MB on the phone">reader</span>
      <span data-k="full" title="The reader with every study layer built so far - word tags, lexicon, concordance, syntax, cross-references, apparatus, themes, places, chronology: about a 26 MB APK, 78 MB on the phone. The layers are frozen as they stand when it is built.">+ study tools</span>
    </span>
    <button id="apkBtn">Make Android APK</button>
    <span id="apkMsg" role="status"></span>
    <button id="apkStop" hidden title="Stop this build and free the machine">stop</button>
    <button id="apkOpen" hidden title="Show the APK in its folder">open folder</button>
  </div>
</header>
<div class="pane" id="tpane">
<div id="stats">
  <div class="stat"><small>Chapter</small><b id="cur">—</b></div>
  <div class="stat"><small>Verses</small><b id="vv">—</b></div>
  <div class="stat"><small>Elapsed</small><b id="el">—</b></div>
  <div class="stat"><small>Tokens</small><b id="tok">—</b></div>
  <div class="stat"><small>Speed</small><b><span id="tps">—</span> <span style="font-weight:400;font-size:11px;color:var(--muted)">tok/s</span></b></div>
  <div class="stat"><small>Book</small><b id="bprog">—</b></div>
  <div class="stat wide"><small><span id="tlname">English</span> <span id="prog"></span></small><div id="bar"><i></i></div></div>
  <span class="tabs" id="tabs"></span>
</div>
<div id="totals">
  <span><small>Session</small><b id="ss_ch">0</b> chapters · <b id="ss_tok">0</b> tokens · <b id="ss_time">0s</b> · <b id="ss_tps">—</b> tok/s</span>
  <span><small>Lifetime</small><b id="lt_ch">0</b> chapters · <b id="lt_tok">0</b> tokens out · <b id="lt_ptok">0</b> in · <b id="lt_time">0s</b> · <b id="lt_tps">—</b> tok/s avg</span>
</div>
<div id="strip" hidden></div>
</div>
<div id="split" hidden></div>
<div class="pane" id="work" hidden></div>
<div class="layout" id="layout">
  <div id="text" class="plain"></div>
  <iframe id="reader" title="eBible reader" hidden></iframe>
  <div id="handle" title="Hide / show the panel">&#9666;</div>
  <aside>
    <div class="phead"><button id="dock" title="Move the panel to the other side">&#8644; move</button><button id="hide" title="Hide the panel so the translation gets the whole width (the tab at the edge brings it back)">&#215; hide</button></div>
    <h3>Translations</h3>
    <div class="tg" id="targets"></div>
    <h3>This session</h3>
    <div id="recent"><div class="empty" style="font-size:12px;padding:.2rem .45rem">Nothing translated yet.</div></div>
    <h3 style="margin-top:.9rem">Books · translated / total</h3>
    <div id="books"></div>
  </aside>
</div>
</div>
<script>
const $ = id => document.getElementById(id);
const LANGS = __LANGS__, TARGETS = __TARGETS__, TCODES = Object.keys(TARGETS);
const NL = String.fromCharCode(10);
let S = null, cur = null, browsing = null, lastActive = null, translatedSet = new Set(), pending = false, browseSeq = 0;
let texts = {};                                   // {target code: "[1] ...\n[2] ..." text} for the chapter on screen
let tl = localStorage.getItem('liveTl'); if (!TARGETS[tl]) tl = '__DEFAULT__';
let view = localStorage.getItem('liveView') || 'par';   // tr | orig | par | all
let panel = {side: 'right', open: true};              // the Translations / Books panel: docked side, shown or collapsed
let mode = localStorage.getItem('liveMode') === 'read' ? 'read' : 'translate';   // read: the reader fills the window
try { panel = {...panel, ...JSON.parse(localStorage.getItem('livePanel') || '{}')}; } catch (e) {}
function applyPanel(){
  $('layout').classList.toggle('left', panel.side === 'left');
  $('layout').classList.toggle('closed', !panel.open);
  const towardsPanel = panel.side === 'left' ? '\u25c2' : '\u25b8';       // arrow points where the panel hides
  $('handle').innerHTML = panel.open ? towardsPanel : (panel.side === 'left' ? '\u25b8' : '\u25c2');
  $('handle').title = panel.open ? 'Hide the panel: the translation gets the whole width' : 'Show the panel';
  localStorage.setItem('livePanel', JSON.stringify(panel));
}
function applyMode(){
  const reading = mode === 'read';
  $('layout').classList.toggle('reading', reading);
  document.body.classList.toggle('reading', reading);
  $('reader').hidden = !reading;
  if (reading) showReader();
  $('mode').querySelectorAll('span').forEach(x => x.classList.toggle('on', x.dataset.m === mode));
  localStorage.setItem('liveMode', mode);
  applyDevice();
}
let device = localStorage.getItem('liveDevice') === 'mobile' ? 'mobile' : 'pc';   // PC | mobile preview of the content area
function applyDevice(){
  const mobile = device === 'mobile', app = $('app');
  document.body.classList.toggle('mobile', mobile);
  if (mobile) {                                          // scale the phone down when the window is too short for it
    app.style.transform = `scale(${Math.min(1, (window.innerHeight - 20) / 864).toFixed(3)})`;
  } else app.style.transform = '';
  $('device').querySelectorAll('span').forEach(x => x.classList.toggle('on', x.dataset.d === device));
  localStorage.setItem('liveDevice', device);
}
$('device').querySelectorAll('span').forEach(x => x.onclick = () => { device = x.dataset.d; applyDevice(); });
window.addEventListener('resize', () => { if (device === 'mobile') applyDevice(); });
async function showReader(){                       // loaded once and kept; reloaded when translations are newer
  const rd = $('reader');
  if (!rd.src) { rd.src = '/reader'; return; }
  try { if ((await (await fetch('/reader-stale')).json()).stale) rd.contentWindow.location.reload(); } catch (e) {}
}
$('handle').onclick = () => { panel.open = !panel.open; applyPanel(); };
$('mode').querySelectorAll('span').forEach(x => x.onclick = () => { mode = x.dataset.m; applyMode(); });
$('hide').onclick = () => { panel.open = false; applyPanel(); };
applyMode();
$('dock').onclick = () => { panel.side = panel.side === 'left' ? 'right' : 'left'; applyPanel(); };
applyPanel();

function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function ruby(h){ return h.replace(/\{([^{}|\]]+)\|([^{}\]]+)[}\]]/g, '<ruby>$1<rt>$2</rt></ruby>'); }   // {漢字|かんじ} furigana notation
function tdir(t){ return (TARGETS[t] && TARGETS[t].dir) || 'ltr'; }

/* ---------- word alignment (Side by side): click a word, its counterparts light up ---------- */
const SEG = (typeof Intl !== 'undefined' && Intl.Segmenter) ? new Intl.Segmenter(undefined, {granularity:'word'}) : null;
const WRE = /[\p{L}\p{M}\p{N}]+(?:['’][\p{L}\p{M}\p{N}]+)*/gu;
const segCache = new Map();
function segs(text, useSeg){                 // -> [{t, w}], w = is a word. Source: regex (Hebrew splits at maqaf); targets: Intl.Segmenter (zh/ja/th)
  const ck = (useSeg ? '1' : '0') + text; if (segCache.has(ck)) return segCache.get(ck);
  const out = [];
  if (useSeg && SEG) { for (const s of SEG.segment(text)) out.push({t: s.segment, w: !!s.isWordLike}); }
  else { let i = 0; for (const m of text.matchAll(WRE)) { if (m.index > i) out.push({t: text.slice(i, m.index), w:false}); out.push({t: m[0], w:true}); i = m.index + m[0].length; }
         if (i < text.length) out.push({t: text.slice(i), w:false}); }
  if (segCache.size > 3000) segCache.clear();
  segCache.set(ck, out); return out;
}
function wrap(text, side, v, useSeg){ let i = 0; return segs(text, useSeg).map(x => x.w ? `<span class="w" data-k="${side}:${v}:${++i}">${esc(x.t)}</span>` : esc(x.t)).join(''); }
function wordsOf(text, useSeg){ return segs(text, useSeg).filter(x => x.w).map(x => x.t); }
let sel = null, hov = null, alignStatus = '', statusKey = '';   // sel/hov: {side:'s'|'t', v, i}
const aligned = {}, aligning = new Set();       // chapKey|v -> [[s,t],...]
function chapKey(){ return cur ? `${cur.book}|${cur.chapter}|${tl}` : ''; }
function alignKey(v){ return chapKey() + '|' + v; }
function setAlignStatus(s, busy){ alignStatus = s; statusKey = chapKey(); const el = $('astat'); if (el) { el.textContent = s || 'click a word to see its counterpart'; el.className = 'astat' + (busy ? ' busy' : ''); } }
function paint(){
  const box = $('text');
  box.querySelectorAll('.w.sel,.w.link,.w.hov').forEach(x => x.classList.remove('sel','link','hov'));
  if (sel && sel.ck !== chapKey()) sel = null;
  const mark = (p, self, other) => {
    const me = box.querySelector(`.w[data-k="${p.side}:${p.v}:${p.i}"]`); if (me) me.classList.add(self);
    const pairs = aligned[alignKey(p.v)]; if (!pairs) return;
    const os = p.side === 's' ? 't' : 's';
    for (const [a, b] of pairs) { const mine = p.side === 's' ? a : b, theirs = p.side === 's' ? b : a;
      if (mine === p.i) { const o = box.querySelector(`.w[data-k="${os}:${p.v}:${theirs}"]`); if (o) o.classList.add(other); } }
  };
  if (hov) mark(hov, 'hov', 'hov');
  if (sel) mark(sel, 'sel', 'link');
}
async function ensureAlign(v){
  const key = alignKey(v); if (aligned[key] || aligning.has(key)) return;
  const s = cur.src.find(x => x.v === v), {vs, n} = parseVerses(texts[tl]), e = vs[v];
  if (!s || e === undefined) return;
  const running = !!(S && S.running);
  if (running && !browsing && cur.target === tl && n === v) { setAlignStatus(`verse ${v} is still being written`); return; }
  aligning.add(key);
  setAlignStatus(`aligning verse ${v}` + (running ? ' (waits for the running translation)' : '') + '…', true);
  try {
    const r = await post('/align', {book: cur.book, chapter: cur.chapter, v, lang: tl, slang: (LANGS[s.lang] || {}).name,
                                    src: wordsOf(s.text, false), tgt: wordsOf(e, true)});
    if (!r.pairs) throw new Error(r.error || 'no alignment');
    aligned[key] = r.pairs;
    setAlignStatus(r.pairs.length ? (r.cached ? '' : `verse ${v} aligned in ${r.seconds}s`) : `no word links found for verse ${v}`);
    paint();
  } catch (err) { setAlignStatus('alignment failed: ' + err.message); }
  finally { aligning.delete(key); }
}
$('text').addEventListener('click', e => {
  const w = e.target.closest('.w');
  if (!w) { if (sel) { sel = null; paint(); } return; }
  const [side, v, i] = w.dataset.k.split(':');
  if (sel && sel.side === side && sel.v === +v && sel.i === +i) { sel = null; paint(); return; }
  sel = {side, v:+v, i:+i, ck: chapKey()}; paint(); ensureAlign(+v);
});
$('text').addEventListener('mouseover', e => {
  const w = e.target.closest('.w'); if (!w) return;
  const [side, v, i] = w.dataset.k.split(':');
  if (!aligned[alignKey(+v)]) return;
  hov = {side, v:+v, i:+i}; paint();
});
$('text').addEventListener('mouseout', e => { if (hov && e.target.closest('.w')) { hov = null; paint(); } });
function schedule(){ if (!pending){ pending = true; requestAnimationFrame(render); } }
function setView(v){ view = v; localStorage.setItem('liveView', v); lastActive = null; render(); }
/* The live stream carries one language's counts. Switching language without
   reopening it left the old language's snapshot arriving over the new one, so
   a language with nothing translated wore English's numbers and looked
   finished - until the app was restarted and the stream opened on it. The
   stream follows the switch now, and the counts are re-read either way.
   A switch that came from the stream itself (a run started in another
   language) leaves the stream alone: closing it mid-run would drop tokens. */
function setTl(t, fromStream){ tl = t; localStorage.setItem('liveTl', t); $('lang').value = t; $('tlname').textContent = TARGETS[t].name;
  if (!fromStream) connect();
  refresh();
  if (browsing) browse(); else render(); }
$('lang').innerHTML = TCODES.map(t => `<option value="${t}">${TARGETS[t].native}</option>`).join('') + '<option value="all">All languages</option>';
$('lang').value = tl; $('tlname').textContent = TARGETS[tl].name;
$('lang').onchange = () => { if ($('lang').value !== 'all') setTl($('lang').value); };

function textFrom(t){ return t ? Object.keys(t.verses).map(Number).sort((a,b)=>a-b).map(n => '[' + n + '] ' + t.verses[n]).join(NL) + (t.notes ? NL + '---' + NL + t.notes : '') : ''; }
function parseVerses(text){           // {vs: {n: text}, notes, n: verse being written}
  const vs = {}, notesL = []; let n = null, inNotes = false;
  for (const line of (text || '').split(NL)) {
    if (line.trim() === '---') { inNotes = true; continue; }
    if (inNotes) { notesL.push(line); continue; }
    const m = line.trim().match(/^\[(\d+)\]\s*(.*)$/);
    if (m) { n = +m[1]; vs[n] = m[2]; }
    else if (n !== null && line.trim()) vs[n] += NL + line.trim();
  }
  return {vs, notes: notesL.join(NL).trim(), n};
}

function renderTabs(v, avail, L){
  const hasLxx = cur && cur.src && cur.src.some(s => s.lxx);
  let html = `<span data-v="orig" class="${v==='orig'?'on':''}">${cur ? L.name : 'Original'}</span>`;
  if (hasLxx) html += `<span data-v="lxx" class="${v==='lxx'?'on':''}" title="Swete's Septuagint">Septuagint</span>`;
  html += `<i class="sep"></i>`;
  for (const t of TCODES) html += `<span data-v="tr" data-t="${t}" class="${v==='tr'&&tl===t?'on':''} ${avail.includes(t)?'':'off'}">${TARGETS[t].native}</span>`;
  html += `<i class="sep"></i><span data-v="par" class="${v==='par'?'on':''} ${avail.includes(tl)?'':'off'}">Side by side</span>`;
  html += `<span data-v="all" class="${v==='all'?'on':''} ${avail.length>1?'':'off'}">Compare</span>`;
  $('tabs').innerHTML = html;
  $('tabs').querySelectorAll('span').forEach(t => t.onclick = () => { if (t.classList.contains('off')) return;
    if (t.dataset.t) { setTl(t.dataset.t); } setView(t.dataset.v); });
}

function render(){
  pending = false;
  const box = $('text');
  const running = !!(S && S.running);
  const src = cur && cur.src && cur.src.length ? cur.src : null;
  const L = LANGS[(cur && cur.lang) || 'hbo'] || LANGS.hbo;
  const rtl = L.dir === 'rtl', ocls = 'orig ' + L.script.toLowerCase();
  const mixed = cur && cur.lang === 'mixed';
  const tag = s => mixed ? `<span class="lt">${LANGS[s.lang].name}</span>` : '';
  const avail = TCODES.filter(t => texts[t] !== undefined && (texts[t] || (running && cur && cur.target === t)));
  const hasLxx = !!(src && src.some(s => s.lxx));
  $('strip').hidden = !browsing && !(running && cur && cur.chapters);
  let v = view;
  if (!src) v = 'tr';
  if (v === 'lxx' && !hasLxx) v = 'orig';
  if (v === 'all' && avail.length + (hasLxx ? 1 : 0) < 2) v = avail.includes(tl) ? 'par' : 'orig';
  if ((v === 'tr' || v === 'par') && !avail.includes(tl)) v = hasLxx && view === 'lxx' ? 'lxx' : 'orig';
  renderTabs(v, avail, L);
  box.className = (v === 'par' || v === 'all') ? '' : 'plain';
  box.setAttribute('lang', (v === 'orig' || v === 'lxx') ? '' : tl);
  box.setAttribute('dir', (v === 'tr') ? tdir(tl) : 'ltr');
  const live = running && cur && cur.target === tl;
  const caret = live ? '<span class="caret"></span>' : '';
  if (alignStatus && statusKey !== chapKey()) alignStatus = '';   // status belongs to another chapter/language
  const astat = v === 'par' ? `<small class="astat${aligning.size ? ' busy' : ''}" id="astat">${esc(alignStatus || 'click a word to see its counterpart')}</small>` : '';
  const head = cur ? `<div class="chhead"><h2>${cur.book} ${cur.chapter}</h2><small>${L.name}${running ? ' → ' + TARGETS[cur.target].name + ' · translating' : (avail.length ? ' → ' + avail.map(t => TARGETS[t].native).join(' · ') : ' · not translated yet')}</small>${astat}</div>` : '';
  if (!cur) {
    box.innerHTML = `<div class="empty"><h3>Nothing selected</h3>Pick a book in the list on the right (or the Run box) to read its original text and any translations, or choose a target language and press Start. Text appears here as the model writes it.</div>`;
    return;
  }
  if (v === 'orig') {
    box.innerHTML = head + src.map(s => `<p class="ov ${ocls}" dir="${rtl?'rtl':'ltr'}"><sup>${s.v}</sup>${tag(s)}${esc(s.text)}</p>`).join('');
    return;
  }
  if (v === 'lxx') {
    box.innerHTML = head + src.map(s => `<p class="ov orig greek"><sup>${s.v}</sup>${s.lxx ? esc(s.lxx) : '<i class="empty">— no aligned verse</i>'}</p>`).join('');
    return;
  }
  if (v === 'par') {
    const {vs, notes, n} = parseVerses(texts[tl]);
    let html = head + '<div class="grid">';
    for (const s of src) {
      const e = vs[s.v], writing = live && s.v === n;
      const cls = e === undefined ? 'e todo' : (writing ? 'e active' : 'e');
      html += `<div class="o ${ocls}" dir="${rtl?'rtl':'ltr'}"><sup>${s.v}</sup>${tag(s)}${wrap(s.text, 's', s.v, false)}</div>
        <div class="${cls}" id="row-${s.v}" dir="${tdir(tl)}"><sup>${s.v}</sup>${e === undefined ? '…' : (writing ? ruby(esc(e)) + caret : (tl === 'ja-easy' ? ruby(esc(e)) : wrap(e, 't', s.v, true)))}</div>`;
    }
    if (notes) html += `<div class="notes">${ruby(esc(notes))}</div>`;
    box.innerHTML = html + '</div>';
    paint();
    if (live && n !== lastActive) { lastActive = n; const r = document.getElementById('row-' + n); if (r) r.scrollIntoView({block:'center', behavior:'smooth'}); }
    return;
  }
  if (v === 'all') {
    const parsed = {}; for (const t of avail) parsed[t] = parseVerses(texts[t]);
    let html = head;
    for (const s of src) {
      html += `<div class="cmp" id="row-${s.v}"><div class="row"><span class="lab">${L.name} ${s.v}</span><span class="txt ${ocls}" dir="${rtl?'rtl':'ltr'}">${tag(s)}${esc(s.text)}</span></div>`;
      if (s.lxx) html += `<div class="row"><span class="lab">LXX</span><span class="txt orig greek">${esc(s.lxx)}</span></div>`;
      for (const t of avail) {
        const e = parsed[t].vs[s.v], act = running && cur.target === t && parsed[t].n === s.v;
        html += `<div class="row"><span class="lab">${TARGETS[t].native}</span><span class="txt ${act?'active':''}" lang="${t}" dir="${tdir(t)}">${e === undefined ? '…' : ruby(esc(e)) + (act ? '<span class="caret"></span>' : '')}</span></div>`;
      }
      html += '</div>';
    }
    box.innerHTML = html;
    if (running && cur) { const n = parsed[cur.target] && parsed[cur.target].n; if (n !== lastActive) { lastActive = n; const r = document.getElementById('row-' + n); if (r) r.scrollIntoView({block:'center', behavior:'smooth'}); } }
    return;
  }
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  const raw = texts[tl] || '';
  let html = ruby(esc(raw)).replace(/^\[(\d+)\]\s*/gm, '<sup>$1</sup>');
  const i = html.indexOf(NL + '---');
  if (i >= 0) html = html.slice(0, i) + '<div class="notes">' + html.slice(i + 4).trim() + '</div>';
  if (!raw) html = '<span class="empty">Waiting for the model…</span>';
  box.innerHTML = head + html + caret;
  if (live && atBottom) box.scrollTop = box.scrollHeight;
}

function tick(){
  if (!cur || !(S && S.running) || !cur.started) return;
  const el = (Date.now()/1000 - cur.started);
  $('el').textContent = el < 60 ? el.toFixed(0)+'s' : Math.floor(el/60)+'m '+Math.floor(el%60)+'s';
  $('tok').textContent = cur.tokens;
  $('tps').textContent = el > 1 ? (cur.tokens/el).toFixed(1) : '—';
}
function bookProgress(name){ const b = S && S.books.find(x => x.name === name || x.code === name); if (b) $('bprog').textContent = b.done + ' / ' + b.total; }
const fmtN = n => n >= 1e6 ? (n/1e6).toFixed(2) + 'M' : n >= 1e4 ? (n/1e3).toFixed(0) + 'k' : String(n || 0);
const fmtT = s => { s = Math.round(s || 0); const h = Math.floor(s/3600), m = Math.floor(s%3600/60); return h ? `${h}h ${m}m` : m ? `${m}m ${s%60}s` : `${s}s`; };
const fmtAge = t => { if (!t) return ''; const m = (Date.now()/1000 - t)/60;
  return m < 60 ? `built ${Math.round(m)} min ago` : (m < 1440 ? `built ${Math.round(m/60)} h ago` : `built ${Math.round(m/1440)} d ago`); };
/* The model work has its own token counter, kept apart from the translation's:
   what the analysis jobs have spent, in this session and over all of them. */
function workTotals(t){
  if (!t || !t.session) return '';
  const row = (lab, x, tip) => `<span title="${esc(tip)}"><small>${lab}</small><b>${fmtN(x.calls)}</b> calls · <b>${fmtN(x.output_tokens)}</b> tokens out`
    + ` · <b>${fmtN(x.prompt_tokens)}</b> in · <b>${fmtT(x.seconds)}</b> · <b>${x.tps || '—'}</b> tok/s</span>`;
  const byJob = Object.entries(t.by_job || {}).sort((a, b) => b[1].output_tokens - a[1].output_tokens)
    .map(([j, x]) => `${j.replace(/-/g, ' ')}: ${fmtN(x.output_tokens)} tokens in ${fmtN(x.calls)} calls`).join(NL);
  return `<div class="wtot">`
    + row('Session', t.session, 'what the analysis has asked of the model since this dashboard started')
    + row('Analysis', t, 'every call the analysis jobs have made, counted apart from the translation above'
          + (byJob ? NL + NL + byJob : '')) + `</div>`;
}
async function workBar(){
  let w;
  try { w = await (await fetch('/work')).json(); } catch (e) { return; }
  const el = $('work');
  const groups = (w.groups || []).filter(g => g.items.some(i => i.done || i.count));
  if (!groups.length) { el.hidden = $('split').hidden = true; return; }
  el.hidden = $('split').hidden = false;
  const anyrun = !!w.anyrunning;
  const byJob = (w.tokens && w.tokens.by_job) || {};
  el.innerHTML = `<div class="hd"><b>Model work</b>${anyrun ? `<button class="stopall" onclick="workStop()">stop all — free the GPU</button>`
      : `<button onclick="workStart('queue')" title="run every unfinished job, one after another">run the queue</button>`}
      <span style="font-size:11px">${anyrun ? "using the GPU now" : "idle"}</span></div>`
    + groups.map(g => `<div class="grp"><span class="gl">${esc(g.label)}</span>` + g.items.map(it => {
    const total = it.total || it.count || 0, done = it.done || it.count || 0;
    const pct = total ? Math.min(100, 100 * done / total) : 0;
    const cls = !done ? 'none' : (it.running ? 'run' : (done >= total ? 'full' : ''));
    const num = it.running || done < total ? `<b>${fmtN(done)}</b>/${fmtN(total)}` : `<b>${fmtN(done)}</b>`;
    const tip = `${it.what}${it.unit ? ' — ' + fmtN(it.count) + ' ' + it.unit : ''}${it.built ? ' · ' + fmtAge(it.built) : ''}${it.running ? ' · running now' : ''}`;
    const btn = it.startable ? (it.running
        ? `<button class="on" title="stop this job" onclick="workStop('${it.job}')">\u25a0</button>`
        : (done >= total ? "" : `<button title="start this job" onclick="workStart('${it.job}')">\u25b6</button>`)) : "";
    const spent = it.job && byJob[it.job];
    const tok = spent ? ` <span class="tk" title="${esc(fmtN(spent.output_tokens) + ' tokens out over ' + fmtN(spent.calls) + ' calls')}">${fmtN(spent.output_tokens)} tok</span>` : "";
    return `<span class="j ${cls}" title="${esc(tip)}"><span class="nm" onclick="showLayer('${it.key}')" title="show what this has produced">${esc(it.key.replace(/-/g, ' '))}</span> <span class="b"><i style="width:${pct.toFixed(1)}%"></i></span> ${num}${tok}${btn}</span>`;
  }).join('') + `</div>`).join('')
    + workTotals(w.tokens);                 // the counter closes the area, under the last rung
}
async function showLayer(key){          // open, in the reader, whatever this layer has produced
  mode = 'read'; applyMode();
  const rd = $('reader');
  for (let i = 0; i < 60 && !(rd.contentWindow && rd.contentWindow.openView); i++) await new Promise(r => setTimeout(r, 200));
  try { await rd.contentWindow.openView(key); } catch (e) { console.warn(e); }
}
async function workStart(job){
  const r = await post('/work/start', {job: job === 'queue' ? 'queue' : job});
  if (!r.ok) alert(r.error || 'could not start');
  setTimeout(workBar, 700);
}
async function workStop(job){ await post('/work/stop', job ? {job} : {}); setTimeout(workBar, 700); }
setInterval(workBar, 8000);
workBar();

function totals(s){
  const ss = s.session, lt = s.lifetime;
  $('ss_ch').textContent = ss.chapters; $('ss_tok').textContent = fmtN(ss.tokens); $('ss_time').textContent = fmtT(ss.seconds); $('ss_tps').textContent = ss.tps || '—';
  $('lt_ch').textContent = lt.chapters; $('lt_tok').textContent = fmtN(lt.output_tokens); $('lt_ptok').textContent = fmtN(lt.prompt_tokens);
  $('lt_time').textContent = fmtT(lt.seconds); $('lt_tps').textContent = lt.tps || '—';
  $('lt_ch').title = Object.entries(lt.by_lang || {}).map(([k,v]) => `${TARGETS[k] ? TARGETS[k].native : k}: ${v}`).join(' · ');
}

function applySnapshot(s){
  S = s;
  $('model').textContent = s.model;
  const pill = $('pill');
  pill.textContent = s.running ? s.status : (s.error ? 'error' : s.status);
  pill.className = 'pill' + (s.running ? ' run' : (s.error ? ' err' : ''));
  pill.title = s.run ? `run: ${s.run.book} ${s.run.chapters} → ${s.run.lang}` : '';
  $('start').disabled = s.running; $('stop').disabled = !s.running;
  $('prev').disabled = s.running; $('next').disabled = s.running;
  if (s.current) { cur = s.current; texts = {[cur.target]: cur.text}; if (cur.target !== tl) setTl(cur.target); browsing = null; runStrip(cur);
    if (view === 'orig' || view === 'lxx') { view = 'par'; localStorage.setItem('liveView', view); } }
  else if (!cur && s.last) { cur = s.last; texts = {[cur.target]: cur.text}; }
  if (s.error) texts[tl] = 'ERROR: ' + s.error;
  if (!s.running && !browsing && cur && cur.book) {          // a run just ended (or the page loaded after one): hand the
    const b = (s.books || []).find(x => x.name === cur.book);  // chapter to browse mode so the strip is clickable again
    if (b) { $('book').value = b.code; $('ch').value = cur.chapter; browse(); }
  }
  if (cur) {
    $('cur').textContent = cur.book + ' ' + cur.chapter; $('vv').textContent = cur.verses; bookProgress(cur.book);
    if (!s.running && cur.started) { $('tok').textContent = cur.tokens; const r = s.recent[0];
      if (r && r.book === cur.book && r.chapter === cur.chapter) { $('el').textContent = r.seconds + 's'; $('tps').textContent = r.tps || '—'; } }
  }
  totals(s);
  $('prog').textContent = s.bible_done + ' / ' + s.bible_total + ' chapters';
  $('bar').firstElementChild.style.width = (100*s.bible_done/Math.max(1,s.bible_total)).toFixed(2)+'%';
  $('targets').innerHTML = TCODES.map(t => `<span data-t="${t}" class="${t===tl?'on':''}" title="${TARGETS[t].name}">${TARGETS[t].native} ${s.targets[t].done}</span>`).join('');
  $('targets').querySelectorAll('span').forEach(x => x.onclick = () => setTl(x.dataset.t));
  const sel = $('book'), keep = sel.value;
  sel.innerHTML = '<option value="ALL">All books (canonical order)</option>' +
    s.books.map(b => `<option value="${b.code}">${b.name} (${b.done}/${b.total})</option>`).join('');
  sel.value = keep || 'ALL';
  const curCode = browsing ? browsing.code : (cur ? (s.books.find(x => x.name === cur.book) || {}).code : null);
  let html = '', lastT = '';
  for (const b of s.books) {
    if (b.testament !== lastT) { html += `<h3>${b.testament === 'OT' ? 'Old Testament' : 'New Testament'}</h3>`; lastT = b.testament; }
    const cls = b.code === curCode ? 'on' : (b.total && b.done >= b.total ? 'full' : (b.done ? 'part' : ''));
    html += `<div class="bk ${cls}" data-code="${b.code}"><span>${b.name}</span><span class="b"><i style="width:${b.total?100*b.done/b.total:0}%"></i></span><span class="ct">${b.done}/${b.total}</span></div>`;
  }
  $('books').innerHTML = html;
  document.querySelectorAll('#books .bk').forEach(d => d.onclick = () => { if (S.running) return; $('book').value = d.dataset.code; $('ch').value = '1'; browse(); });
  if (s.recent.length) $('recent').innerHTML = s.recent.map(r =>
    `<div class="rec" data-b="${r.book}" data-c="${r.chapter}" data-t="${r.target}"><span>${r.book} ${r.chapter} <small>${TARGETS[r.target].native} · ${r.got}/${r.expected} vv${r.attempts>1?' · 2 tries':''}</small></span>
     <span class="${r.status==='OK'?'ok':'warn'}">${r.status==='OK'?'OK':'WARN'} <small>${r.seconds}s${r.tps?' · '+r.tps+' t/s':''}</small></span></div>`).join('');
  document.querySelectorAll('#recent .rec').forEach(d => d.onclick = () => { if (S.running) return;
    const b = S.books.find(x => x.name === d.dataset.b); if (b) { $('book').value = b.code; $('ch').value = d.dataset.c; if (d.dataset.t !== tl) setTl(d.dataset.t); else browse(); } });
  if (!s.running && !s.current && !browsing && !cur) browse();
  schedule(); tick();
}

/* ---------- chapter strip: browse control when idle, progress display during a run ---------- */
function renderStrip(book, target, chapters, current, doneSet, clickable){
  const strip = $('strip'); strip.hidden = false;
  strip.innerHTML = `<span class="lbl">${book} · ${TARGETS[target].native}</span>` + chapters.map(c =>
    `<a class="${+c === +current ? 'on' : (doneSet.has(String(c)) ? 'tr' : '')}" data-c="${c}">${c}</a>`).join('');
  if (clickable) strip.querySelectorAll('a').forEach(a => a.onclick = () => { $('ch').value = a.dataset.c; browse(); });
  const on = strip.querySelector('a.on'); if (on) { if (!clickable) on.classList.add('live'); on.scrollIntoView({block:'nearest', inline:'nearest'}); }
}
function runStrip(c){ if (c && c.chapters) renderStrip(c.book, c.target, c.chapters.map(String), c.chapter, new Set((c.translated || []).map(String)), false); }

/* ---------- browse mode: any chapter's original + translations while idle ---------- */
async function browse(){
  if (S && S.running) return;
  const code = $('book').value; if (code === 'ALL') { $('strip').hidden = true; return; }
  const ch = parseInt(($('ch').value || '1').split('-')[0], 10) || 1;
  const seq = ++browseSeq;
  const r = await fetch(`/source?book=${encodeURIComponent(code)}&ch=${ch}&lang=${tl}`);
  if (!r.ok || seq !== browseSeq || (S && S.running)) return;   // superseded, or a run began meanwhile
  const d = await r.json();
  browsing = {code, chapter: d.chapter, chapters: d.chapters};
  translatedSet = new Set((d.translated || []).map(String));
  cur = {book: d.book, chapter: d.chapter, verses: d.verses, lang: d.lang, src: d.src, target: tl, started: 0, tokens: 0};
  texts = {}; for (const t of TCODES) if (d.translations[t]) texts[t] = textFrom(d.translations[t]);
  lastActive = null;
  $('cur').textContent = d.book + ' ' + d.chapter; $('vv').textContent = d.verses;
  $('el').textContent = '—'; $('tok').textContent = '—'; $('tps').textContent = '—';
  bookProgress(code);
  renderStrip(d.book, tl, d.chapters, d.chapter, translatedSet, true);
  const i = d.chapters.indexOf(String(d.chapter));
  $('prev').disabled = i <= 0; $('next').disabled = i >= d.chapters.length - 1;
  document.querySelectorAll('#books .bk').forEach(b => b.classList.toggle('on', b.dataset.code === code));
  $('text').scrollTop = 0;
  schedule();
}
function step(dir){
  if (S && S.running) return;
  if (!browsing) return browse();
  const i = browsing.chapters.indexOf(String(browsing.chapter)) + dir;
  if (i < 0 || i >= browsing.chapters.length) return;
  $('ch').value = browsing.chapters[i]; browse();
}
$('prev').onclick = () => step(-1);
$('next').onclick = () => step(1);
$('book').onchange = () => { $('ch').value = ''; browse(); };
$('ch').onchange = browse;
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || (S && S.running)) return;
  if (e.key === 'ArrowLeft') step(-1); if (e.key === 'ArrowRight') step(1);
});

/* ---------- live stream ---------- */
let ES = null;
function connect(){
  if (ES) { try { ES.close(); } catch (e) {} }        // one stream at a time, for the language on screen
  const es = ES = new EventSource('/events?lang=' + tl);
  es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === 'snapshot') applySnapshot(m);
    else if (m.type === 'token') { if (cur) { texts[cur.target] = (texts[cur.target] || '') + m.t; cur.tokens++; } schedule(); }
    else if (m.type === 'start') { lastActive = null; browsing = null;
      if (m.target !== tl) setTl(m.target, true);
      if (view === 'orig' || view === 'lxx') setView('par');      // always watch the text arrive
      cur = {book:m.book, chapter:m.chapter, verses:m.verses, lang:m.lang, src:m.src, target:m.target,
             chapters:m.chapters, translated:m.translated, started:Date.now()/1000, tokens:0};
      texts = {[m.target]: ''}; runStrip(cur);
      $('cur').textContent = m.book+' '+m.chapter; $('vv').textContent = m.verses; bookProgress(m.book);
      $('pill').textContent = 'translating '+m.book+' '+m.chapter+' → '+TARGETS[m.target].name; $('pill').className='pill run'; schedule(); }
    else if (m.type === 'retry') { if (cur) texts[cur.target] += NL + NL + '--- retry: ' + (m.loop ? 'looped on '+JSON.stringify(m.loop)+' ' : '') + (m.missing && m.missing.length ? 'missing '+JSON.stringify(m.missing)+' ' : '') + (m.extra && m.extra.length ? 'extra '+JSON.stringify(m.extra)+' ' : '') + '---' + NL + NL; schedule(); }
    else if (m.type === 'warn') { $('pill').textContent = 'retrying'; $('pill').className = 'pill err'; $('pill').title = m.message; console.warn(m.message); }
    else if (m.type === 'done' || m.type === 'skip') { const a = $('strip').querySelector(`a[data-c="${m.chapter}"]`); if (a && cur && cur.book === m.book) { a.classList.remove('on'); a.classList.add('tr'); } refresh(); }
    else if (m.type === 'run') refresh();
  };
  es.onerror = () => { es.close(); if (ES === es) setTimeout(connect, 2000); };
}
async function refresh(){ applySnapshot(await (await fetch('/state?lang=' + tl)).json()); }
/* ---------- the Android APK: the reader alone, or the study tools with it ---------- */
let apkT = null;
let apkKind = localStorage.getItem('apkKind') === 'full' ? 'full' : 'reader';
for (const el of document.querySelectorAll('#apkKind span')) el.onclick = () => {
  if ($('apkKind').classList.contains('busy')) return;     // not while one is being built
  apkKind = el.dataset.k; localStorage.setItem('apkKind', apkKind); apkBar();
};
async function apkBar(){
  let s;
  try { s = await (await fetch('/apk')).json(); } catch (e) { apkT = setTimeout(apkBar, 20000); return; }
  const b = $('apkBtn'), m = $('apkMsg'), o = $('apkOpen'), tc = s.toolchain || {};
  b.disabled = !!s.running;
  b.textContent = s.running ? 'Building APK…' : 'Make Android APK';
  $('apkKind').classList.toggle('busy', !!s.running);
  for (const el of $('apkKind').children) el.classList.toggle('on', el.dataset.k === apkKind);
  m.className = ''; m.title = '';
  $('apkStop').hidden = !s.running;
  if (s.running) m.textContent = (s.variant === 'full' ? 'with study tools · ' : '') + (s.step || 'working');
  else if (s.state === 'done' && s.apk) {
    const name = s.apk.split(/[\\/]/).pop(), mins = Math.round((Date.now() / 1000 - (s.finished || 0)) / 60);
    m.textContent = `ready: ${name} · ${(s.size / 1048576).toFixed(1)} MB · ${mins < 1 ? 'just now' : mins < 90 ? mins + ' min ago' : new Date(s.finished * 1000).toLocaleString()}`;
    m.className = 'ok'; m.title = s.apk + (s.chapters ? '\ntranslated chapters: ' + s.chapters : '');
  } else if (s.state === 'failed') {
    m.textContent = 'failed: ' + (s.error || 'see logs/apk_build.log'); m.className = 'err';
    m.title = (s.error || '') + '\n\nThe whole story is in logs/apk_build.log';
  } else if (s.state === 'stopped') m.textContent = 'stopped';
  else if (!tc.ready) m.textContent = 'first time: needs the Android build tools';
  else m.textContent = '';
  o.hidden = !(s.state === 'done' && s.apk && !s.running);
  clearTimeout(apkT);
  apkT = setTimeout(apkBar, s.running ? 2500 : 30000);
}
$('apkBtn').onclick = async () => {
  let s = {};
  try { s = await (await fetch('/apk')).json(); } catch (e) {}
  const tc = s.toolchain || {};
  let setup = false;
  if (!tc.ready) {
    // Fetching the SDK is a download of about a gigabyte and an agreement to
    // Google's licence, so it happens only on an explicit yes, here.
    const ok = confirm(
      'Building an APK needs the Android build tools, which are not on this PC yet'
      + (tc.missing && tc.missing.length ? ' (missing: ' + tc.missing.join(', ') + ')' : '') + '.\n\n'
      + 'Install them once, into tools/android/ inside this project? About 1 GB is downloaded:\n'
      + '  • JDK 17 (Eclipse Temurin, adoptium.net)\n'
      + '  • Gradle 8.13 (gradle.org)\n'
      + '  • Android command-line tools and the Android 16 SDK platform (Google)\n\n'
      + 'Installing the Android SDK means accepting the Android SDK License:\n'
      + 'https://developer.android.com/studio/terms\n\n'
      + 'OK: I accept that licence - install the tools, then build the APK.\n'
      + 'Cancel: do nothing.');
    if (!ok) return;
    setup = true;
  }
  const r = await post('/apk/build', {setup, full: apkKind === 'full'});
  if (!r.ok) alert(r.error || 'could not start the build');
  apkBar();
};
$('apkStop').onclick = async () => { const r = await post('/apk/stop', {}); if (!r.ok) alert(r.error); apkBar(); };
$('apkOpen').onclick = () => post('/apk/open', {});
apkBar();

async function post(path, body){ const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}); return r.json(); }

$('start').onclick = async () => {
  const r = await post('/start', {book:$('book').value, chapters:$('ch').value, force:$('force').checked, lang:$('lang').value});
  if (!r.ok) { alert(r.error); return; }
  browsing = null; schedule(); refresh();
};
$('stop').onclick = () => post('/stop');
setInterval(tick, 500);
connect();
__READALOUD_JS__
</script></body></html>
"""


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print(f"live dashboard: http://localhost:{PORT}  (model {T.CONFIG['model']}, "
          f"targets {', '.join(TARGETS)}, Ctrl-C to quit)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        STOP.set()


if __name__ == "__main__":
    main()
