#!/usr/bin/env python3
"""Live translation dashboard.

    python scripts/live.py            # http://localhost:8766

Runs the same driver as translate.py (same prompts, outputs, resume, logs)
but streams every token from Ollama to a browser page as it is generated,
with progress, tokens/sec and a log of finished chapters. Start/stop runs
from the page. Pure standard library, no server beyond this one file.
"""
import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import translate as T                       # noqa: E402
from books import BOOKS, LANGS, MIXED, slug, verse_lang   # noqa: E402

PORT = 8766
ROOT = T.ROOT
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class StopRun(Exception):
    pass


# ---------------------------------------------------------------- state / bus
LOCK = threading.Lock()
SUBS: list[queue.Queue] = []
STOP = threading.Event()
STATE = {
    "running": False, "model": T.CONFIG["model"], "status": "idle",
    "current": None,        # {book, chapter, verses, lang, started, text, tokens}
    "recent": [],           # last finished chapters, newest first
    "last": None,           # the most recently finished chapter (same shape as current)
    "error": None,
}


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


NAME2META = {m["name"]: m for m in BOOKS.values()}
_norm_cache = {}


def source_verses(book_name, ch):
    """[{v, text, lang}] of the original-language chapter (comparison view)."""
    meta = NAME2META.get(book_name)
    if not meta:
        return []
    key = slug(meta["name"])
    if key not in _norm_cache:
        f = ROOT / "sources" / "normalized" / f"{meta['num']:02d}_{key}.json"
        _norm_cache[key] = json.loads(f.read_text(encoding="utf-8"))["chapters"] if f.exists() else {}
    return [{"v": v["v"], "text": v["text"], "lang": verse_lang(meta, v)}
            for v in _norm_cache[key].get(str(ch), [])]


def chapter_counts():
    """{book name: (done, total)} from output/json vs sources/normalized."""
    out = {}
    for code, meta in BOOKS.items():
        name = slug(meta["name"])
        src = ROOT / "sources" / "normalized" / f"{meta['num']:02d}_{name}.json"
        total = len(json.loads(src.read_text(encoding="utf-8"))["chapters"]) if src.exists() else 0
        done = len(list((ROOT / "output" / "json").glob(f"{name}_*.json")))
        out[code] = (done, total)
    return out


def snapshot():
    counts = chapter_counts()
    books = [{"code": c, "name": BOOKS[c]["name"], "num": BOOKS[c]["num"],
              "testament": BOOKS[c]["testament"], "done": counts[c][0], "total": counts[c][1]}
             for c in sorted(BOOKS, key=lambda c: BOOKS[c]["num"])]
    with LOCK:
        s = dict(STATE)
        s["current"] = dict(STATE["current"]) if STATE["current"] else None
    s["books"] = books
    s["bible_done"] = sum(b["done"] for b in books)
    s["bible_total"] = sum(b["total"] for b in books)
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
        with LOCK:
            STATE["current"] = {"book": ev["book"], "chapter": ev["chapter"],
                                "verses": ev["verses"], "lang": ev["lang"], "src": ev["src"],
                                "started": time.time(), "text": "", "tokens": 0}
            STATE["status"] = f"translating {ev['book']} {ev['chapter']}"
    elif kind == "retry":
        with LOCK:
            cur = STATE["current"]
            if cur:
                cur["text"] += "\n\n--- retry: " + (
                    f"missing {ev['missing']} " if ev["missing"] else "") + (
                    f"extra {ev['extra']}" if ev["extra"] else "") + " ---\n\n"
    elif kind == "done":
        with LOCK:
            rec = {k: ev[k] for k in ("book", "chapter", "got", "expected", "seconds",
                                      "tokens", "attempts", "status")}
            rec["tps"] = round(ev["tokens"] / ev["seconds"], 1) if ev.get("tokens") and ev["seconds"] else None
            STATE["recent"].insert(0, rec)
            del STATE["recent"][40:]
            STATE["last"] = STATE["current"]     # keeps the comparison viewable after the run
            STATE["current"] = None
    publish(ev)


def worker(book, chapters, all_books, force):
    T.on_token, T.on_event = on_token, on_event
    try:
        system = T.build_system_prompt()
        if all_books:
            for code in sorted(BOOKS, key=lambda c: BOOKS[c]["num"]):
                if STOP.is_set():
                    raise StopRun()
                T.run_book(code, None, system, force)
        else:
            T.run_book(book, chapters or None, system, force)
        final = "finished"
    except StopRun:
        final = "stopped"
    except Exception as e:                       # noqa: BLE001
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
        all_books = book in ("", "ALL")
        if not all_books and book not in BOOKS:
            return f"unknown book {book!r}"
        STOP.clear()
        STATE.update(running=True, status="starting", error=None, current=None)
    threading.Thread(target=worker, daemon=True,
                     args=(book, (req.get("chapters") or "").strip(), all_books,
                           bool(req.get("force")))).start()
    publish({"type": "run", "status": "starting"})
    return None


def chapter_payload(code, ch):
    """Source + any existing translation of one chapter, for browsing."""
    meta = BOOKS.get(code)
    if not meta:
        return None
    src = source_verses(meta["name"], ch)
    if not src:
        return None
    langs = {s["lang"] for s in src}
    lang = next(iter(langs)) if len(langs) == 1 else "mixed"
    name = slug(meta["name"])
    jp = ROOT / "output" / "json" / f"{name}_{int(ch):02d}.json"
    tr = json.loads(jp.read_text(encoding="utf-8")) if jp.exists() else None
    chapters = sorted(_norm_cache[name], key=int)
    translated = sorted((int(f.stem.rsplit("_", 1)[1]) for f in (ROOT / "output" / "json").glob(f"{name}_*.json")))
    return {"code": code, "book": meta["name"], "chapter": int(ch), "chapters": chapters, "translated": translated,
            "lang": lang, "src": src, "verses": len(src),
            "english": tr["verses"] if tr else None, "notes": tr["notes"] if tr else ""}


def rebuild_site() -> str:
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout + r.stderr).strip()


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

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.replace("__LANGS__", json.dumps({**LANGS, "mixed": MIXED})).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/state":
            self._json(snapshot())
        elif self.path.startswith("/source?"):
            from urllib.parse import parse_qs
            q = parse_qs(self.path.split("?", 1)[1])
            p = chapter_payload(q.get("book", [""])[0], q.get("ch", ["1"])[0])
            self._json(p or {"error": "no such chapter"}, 200 if p else 404)
        elif self.path == "/events":
            self.sse()
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/start":
            err = start_run(self._body())
            self._json({"ok": err is None, "error": err}, 409 if err else 200)
        elif self.path == "/stop":
            STOP.set()
            self._json({"ok": True})
        elif self.path == "/rebuild":
            self._json({"ok": True, "output": rebuild_site()})
        else:
            self._json({"error": "not found"}, 404)

    def sse(self):
        q: queue.Queue = queue.Queue(maxsize=5000)
        with LOCK:
            SUBS.append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._send("data: " + json.dumps({"type": "snapshot", **snapshot()}, ensure_ascii=False))
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
#stats { display:flex; flex-wrap:wrap; gap:.4rem .5rem; padding:.5rem .9rem; align-items:stretch;
  border-bottom:1px solid var(--border); }
.stat { display:flex; flex-direction:column; min-width:5.4rem; padding:.3rem .65rem; border-radius:8px; background:var(--card);
  border:1px solid var(--border); }
.stat small { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
.stat b { font-size:15px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.stat.wide { flex:1; min-width:12rem; justify-content:center; }
#bar { height:6px; background:var(--border); border-radius:3px; overflow:hidden; margin-top:.25rem; }
#bar i { display:block; height:100%; width:0; background:var(--accent); transition:width .4s; }
.tabs { display:flex; gap:.25rem; align-self:center; margin-left:auto; }
.tabs span { padding:.3rem .7rem; border:1px solid var(--border); border-radius:999px; cursor:pointer;
  color:var(--muted); font-size:12px; user-select:none; background:var(--card); }
.tabs span.on { color:var(--fg); border-color:var(--accent); box-shadow:inset 0 0 0 1px var(--accent); }
.tabs span.off { opacity:.4; cursor:default; }
#strip { display:flex; flex-wrap:wrap; gap:.22rem; padding:.45rem .9rem; border-bottom:1px solid var(--border);
  background:var(--soft); align-items:center; }
#strip .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin-right:.4rem; }
#strip a { font-size:12px; min-width:1.9rem; text-align:center; padding:.1rem .35rem; border:1px dashed var(--border);
  border-radius:6px; cursor:pointer; color:var(--muted); }
#strip a.tr { color:var(--fg); border-style:solid; background:var(--card); }
#strip a.on { background:var(--accent); color:#fff; border-color:var(--accent); }
.layout { display:flex; flex:1; min-height:0; }
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
.grid .notes { grid-column:1 / -1; }
.chhead { display:flex; align-items:baseline; gap:.7rem; margin-bottom:.9rem; white-space:normal; }
.chhead h2 { font:400 24px Georgia, serif; } .chhead small { color:var(--muted); font:13px system-ui; }
aside { width:290px; flex:none; border-left:1px solid var(--border); overflow:auto; padding:.7rem .8rem; font-size:13px; background:var(--card); }
aside h3 { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:.5rem 0 .35rem; }
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
@media (max-width:820px) { aside { display:none; } .grid { grid-template-columns:1fr; } .grid .o { border-bottom:0; padding-bottom:.1rem; } }
</style></head><body>
<header>
  <div class="brand"><b>eBible</b><span class="sub">live translation</span><span class="pill" id="pill">idle</span><span class="pill" id="model"></span></div>
  <div class="group"><span class="lbl">Run</span>
    <select id="book"><option value="ALL">All books (canonical order)</option></select>
    <button class="icon" id="prev" title="previous chapter (←)">&#9664;</button>
    <input id="ch" placeholder="ch / 1-3">
    <button class="icon" id="next" title="next chapter (→)">&#9654;</button>
    <label class="chk"><input type="checkbox" id="force"> force</label>
    <button class="primary" id="start">Start</button>
    <button class="stop" id="stop" disabled>Stop</button>
  </div>
  <div class="group"><span class="lbl">Reader</span>
    <button id="rebuild" title="rebuild site/index.html">Rebuild</button>
    <a href="http://localhost:8765" target="_blank"><button>Open</button></a>
  </div>
</header>
<div id="stats">
  <div class="stat"><small>Chapter</small><b id="cur">—</b></div>
  <div class="stat"><small>Verses</small><b id="vv">—</b></div>
  <div class="stat"><small>Elapsed</small><b id="el">—</b></div>
  <div class="stat"><small>Tokens</small><b id="tok">—</b></div>
  <div class="stat"><small>Speed</small><b><span id="tps">—</span> <span style="font-weight:400;font-size:11px;color:var(--muted)">tok/s</span></b></div>
  <div class="stat"><small>Book</small><b id="bprog">—</b></div>
  <div class="stat wide"><small>Bible <span id="prog"></span></small><div id="bar"><i></i></div></div>
  <span class="tabs" id="tabs"><span data-v="en">English</span><span data-v="orig" id="origTab">Original</span><span data-v="par">Side by side</span></span>
</div>
<div id="strip" hidden></div>
<div class="layout">
  <div id="text" class="plain"></div>
  <aside>
    <h3>This session</h3>
    <div id="recent"><div class="empty" style="font-size:12px;padding:.2rem .45rem">Nothing translated yet.</div></div>
    <h3 style="margin-top:.9rem">Books · translated / total</h3>
    <div id="books"></div>
  </aside>
</div>
<script>
const $ = id => document.getElementById(id);
const LANGS = __LANGS__;
const NL = String.fromCharCode(10);
let S = null, raw = '', pending = false, cur = null, browsing = null, lastActive = null, translatedSet = new Set();
let view = localStorage.getItem('liveView') || 'par';

function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function schedule(){ if (!pending){ pending = true; requestAnimationFrame(render); } }
function setView(v){ view = v; localStorage.setItem('liveView', v); lastActive = null; render(); }
document.querySelectorAll('#tabs span').forEach(t => t.onclick = () => { if (!t.classList.contains('off')) setView(t.dataset.v); });

function parseVerses(text){           // {vs: {n: english}, notes, n: verse being written}
  const vs = {}, notesL = []; let n = null, inNotes = false;
  for (const line of text.split(NL)) {
    if (line.trim() === '---') { inNotes = true; continue; }
    if (inNotes) { notesL.push(line); continue; }
    const m = line.trim().match(/^\[(\d+)\]\s*(.*)$/);
    if (m) { n = +m[1]; vs[n] = m[2]; }
    else if (n !== null && line.trim()) vs[n] += NL + line.trim();
  }
  return {vs, notes: notesL.join(NL).trim(), n};
}

function render(){
  pending = false;
  const box = $('text');
  const running = !!(S && S.running);
  const src = cur && cur.src && cur.src.length ? cur.src : null;
  const hasEn = running || !!raw;
  let v = src ? view : 'en';
  if (!hasEn && v !== 'orig') v = 'orig';                 // nothing English to show yet
  const L = LANGS[(cur && cur.lang) || 'hbo'] || LANGS.hbo;
  const rtl = L.dir === 'rtl', ocls = 'orig ' + L.script.toLowerCase();
  const mixed = cur && cur.lang === 'mixed';
  const tag = s => mixed ? `<span class="lt">${LANGS[s.lang].name}</span>` : '';
  document.querySelectorAll('#tabs span').forEach(t => {
    t.classList.toggle('on', t.dataset.v === v);
    t.classList.toggle('off', !src ? t.dataset.v !== 'en' : (!hasEn && t.dataset.v !== 'orig'));
  });
  $('origTab').textContent = cur ? L.name : 'Original';
  box.className = v === 'par' ? '' : 'plain';
  const caret = running && cur ? '<span class="caret"></span>' : '';
  const head = cur ? `<div class="chhead"><h2>${cur.book} ${cur.chapter}</h2><small>${L.name}${running ? ' · translating' : (raw ? '' : ' · not translated yet')}</small></div>` : '';
  if (!cur) {
    box.innerHTML = `<div class="empty"><h3>Nothing selected</h3>Pick a book in the list on the right (or the Run box) to read its original text, or press Start to begin translating. Text appears here as the model writes it.</div>`;
    return;
  }
  if (v === 'orig') {
    box.innerHTML = head + src.map(s => `<p class="ov ${ocls}" dir="${rtl?'rtl':'ltr'}"><sup>${s.v}</sup>${tag(s)}${esc(s.text)}</p>`).join('');
    return;
  }
  if (v === 'par') {
    const {vs, notes, n} = parseVerses(raw);
    let html = head + '<div class="grid">';
    for (const s of src) {
      const e = vs[s.v];
      const cls = e === undefined ? 'e todo' : (s.v === n && running ? 'e active' : 'e');
      html += `<div class="o ${ocls}" dir="${rtl?'rtl':'ltr'}"><sup>${s.v}</sup>${tag(s)}${esc(s.text)}</div>
        <div class="${cls}" id="row-${s.v}"><sup>${s.v}</sup>${e === undefined ? '…' : esc(e) + (s.v === n ? caret : '')}</div>`;
    }
    if (notes) html += `<div class="notes">${esc(notes)}</div>`;
    box.innerHTML = html + '</div>';
    if (running && n !== lastActive) { lastActive = n; const r = document.getElementById('row-' + n); if (r) r.scrollIntoView({block:'center', behavior:'smooth'}); }
    return;
  }
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  let html = esc(raw).replace(/^\[(\d+)\]\s*/gm, '<sup>$1</sup>');
  const i = html.indexOf(NL + '---');
  if (i >= 0) html = html.slice(0, i) + '<div class="notes">' + html.slice(i + 4).trim() + '</div>';
  if (!raw) html = '<span class="empty">Waiting for the model…</span>';
  box.innerHTML = head + html + caret;
  if (running && atBottom) box.scrollTop = box.scrollHeight;
}

function tick(){
  if (!cur || !(S && S.running) || !cur.started) return;
  const el = (Date.now()/1000 - cur.started);
  $('el').textContent = el < 60 ? el.toFixed(0)+'s' : Math.floor(el/60)+'m '+Math.floor(el%60)+'s';
  $('tok').textContent = cur.tokens;
  $('tps').textContent = el > 1 ? (cur.tokens/el).toFixed(1) : '—';
}

function bookProgress(name){ const b = S && S.books.find(x => x.name === name || x.code === name); if (b) $('bprog').textContent = b.done + ' / ' + b.total; }

function applySnapshot(s){
  S = s;
  $('model').textContent = s.model;
  const pill = $('pill');
  pill.textContent = s.running ? s.status : (s.error ? 'error' : s.status);
  pill.className = 'pill' + (s.running ? ' run' : (s.error ? ' err' : ''));
  $('start').disabled = s.running; $('stop').disabled = !s.running;
  $('prev').disabled = s.running; $('next').disabled = s.running;
  if (s.error) raw = 'ERROR: ' + s.error;
  if (s.current) { cur = s.current; raw = cur.text; browsing = null; $('strip').hidden = true; }
  else if (!cur && s.last) { cur = s.last; raw = cur.text; }
  if (cur) {
    $('cur').textContent = cur.book + ' ' + cur.chapter; $('vv').textContent = cur.verses; bookProgress(cur.book);
    if (!s.running && cur.started) { $('tok').textContent = cur.tokens; const r = s.recent[0];
      if (r && r.book === cur.book && r.chapter === cur.chapter) { $('el').textContent = r.seconds + 's'; $('tps').textContent = r.tps || '—'; } }
  }
  $('prog').textContent = s.bible_done + ' / ' + s.bible_total + ' chapters';
  $('bar').firstElementChild.style.width = (100*s.bible_done/Math.max(1,s.bible_total)).toFixed(2)+'%';
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
    `<div class="rec" data-b="${r.book}" data-c="${r.chapter}"><span>${r.book} ${r.chapter} <small>${r.got}/${r.expected} vv${r.attempts>1?' · 2 tries':''}</small></span>
     <span class="${r.status==='OK'?'ok':'warn'}">${r.status==='OK'?'OK':'WARN'} <small>${r.seconds}s${r.tps?' · '+r.tps+' t/s':''}</small></span></div>`).join('');
  document.querySelectorAll('#recent .rec').forEach(d => d.onclick = () => { if (S.running) return;
    const b = S.books.find(x => x.name === d.dataset.b); if (b) { $('book').value = b.code; $('ch').value = d.dataset.c; browse(); } });
  if (!s.running && !s.current && !browsing && !cur) browse();
  schedule(); tick();
}

/* ---------- browse mode: any chapter's original (and translation) while idle ---------- */
async function browse(){
  if (S && S.running) return;
  const code = $('book').value; if (code === 'ALL') { $('strip').hidden = true; return; }
  const ch = parseInt(($('ch').value || '1').split('-')[0], 10) || 1;
  const r = await fetch(`/source?book=${encodeURIComponent(code)}&ch=${ch}`);
  if (!r.ok) return;
  const d = await r.json();
  browsing = {code, chapter: d.chapter, chapters: d.chapters};
  translatedSet = new Set((d.translated || []).map(String));
  cur = {book: d.book, chapter: d.chapter, verses: d.verses, lang: d.lang, src: d.src, started: 0, tokens: 0};
  raw = d.english ? Object.keys(d.english).map(Number).sort((a,b)=>a-b).map(n => '[' + n + '] ' + d.english[n]).join(NL)
                    + (d.notes ? NL + '---' + NL + d.notes : '') : '';
  lastActive = null;
  $('cur').textContent = d.book + ' ' + d.chapter; $('vv').textContent = d.verses;
  $('el').textContent = '—'; $('tok').textContent = '—'; $('tps').textContent = '—';
  bookProgress(code);
  const strip = $('strip'); strip.hidden = false;
  strip.innerHTML = `<span class="lbl">${d.book}</span>` + d.chapters.map(c =>
    `<a class="${+c === d.chapter ? 'on' : (translatedSet.has(String(c)) ? 'tr' : '')}" data-c="${c}">${c}</a>`).join('');
  strip.querySelectorAll('a').forEach(a => a.onclick = () => { $('ch').value = a.dataset.c; browse(); });
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
function connect(){
  const es = new EventSource('/events');
  es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === 'snapshot') applySnapshot(m);
    else if (m.type === 'token') { raw += m.t; if (cur) cur.tokens++; schedule(); }
    else if (m.type === 'start') { raw = ''; lastActive = null; browsing = null; $('strip').hidden = true;
      cur = {book:m.book, chapter:m.chapter, verses:m.verses, lang:m.lang, src:m.src, started:Date.now()/1000, tokens:0};
      $('cur').textContent = m.book+' '+m.chapter; $('vv').textContent = m.verses; bookProgress(m.book);
      $('pill').textContent = 'translating '+m.book+' '+m.chapter; $('pill').className='pill run'; schedule(); }
    else if (m.type === 'retry') { raw += NL + NL + '--- retry: missing '+JSON.stringify(m.missing)+' extra '+JSON.stringify(m.extra)+' ---' + NL + NL; schedule(); }
    else if (m.type === 'done' || m.type === 'skip' || m.type === 'run') refresh();
  };
  es.onerror = () => { es.close(); setTimeout(connect, 2000); };
}
async function refresh(){ applySnapshot(await (await fetch('/state')).json()); }
async function post(path, body){ const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}); return r.json(); }

$('start').onclick = async () => {
  const r = await post('/start', {book:$('book').value, chapters:$('ch').value, force:$('force').checked});
  if (!r.ok) { alert(r.error); return; }
  raw = ''; browsing = null; $('strip').hidden = true; schedule(); refresh();
};
$('stop').onclick = () => post('/stop');
$('rebuild').onclick = async () => { const r = await post('/rebuild'); alert(r.output || 'rebuilt'); };
setInterval(tick, 500);
connect();
</script></body></html>
"""


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print(f"live dashboard: http://localhost:{PORT}  (model {T.CONFIG['model']}, Ctrl-C to quit)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        STOP.set()


if __name__ == "__main__":
    main()
