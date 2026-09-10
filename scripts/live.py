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
from books import BOOKS, slug               # noqa: E402

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
              "done": counts[c][0], "total": counts[c][1]}
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
        with LOCK:
            STATE["current"] = {"book": ev["book"], "chapter": ev["chapter"],
                                "verses": ev["verses"], "lang": ev["lang"],
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
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/state":
            self._json(snapshot())
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
        --warn:#c2782a; --err:#c23a3a; --card:#fff; --border:#e4ded4; --hl:#f3e8b8; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#181614; --fg:#e8e4dd; --muted:#948d82; --accent:#a98ee6; --ok:#5fbf8b;
          --warn:#e09a4a; --err:#e06060; --card:#221f1c; --border:#37322c; --hl:#4a4020; }
}
* { box-sizing:border-box; margin:0; }
body { background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif;
  display:flex; flex-direction:column; height:100vh; }
header { display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; padding:.6rem .9rem;
  border-bottom:1px solid var(--border); background:var(--card); }
header .brand { font-style:italic; color:var(--muted); margin-right:auto; }
header .brand b { color:var(--fg); font-style:normal; }
select, input, button { font:14px system-ui, sans-serif; padding:.4rem .6rem;
  border:1px solid var(--border); border-radius:8px; background:var(--bg); color:var(--fg); }
input#ch { width:6rem; } label { color:var(--muted); font-size:13px; }
button { cursor:pointer; } button:hover { border-color:var(--accent); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
button:disabled { opacity:.45; cursor:default; }
.pill { padding:.15rem .6rem; border-radius:999px; font-size:12px; font-weight:600;
  background:var(--border); color:var(--muted); }
.pill.run { background:var(--accent); color:#fff; animation:pulse 1.4s infinite; }
.pill.err { background:var(--err); color:#fff; }
@keyframes pulse { 50% { opacity:.55; } }
#stats { display:flex; flex-wrap:wrap; gap:1.2rem; padding:.5rem .9rem; font-size:13px;
  color:var(--muted); border-bottom:1px solid var(--border); align-items:center; }
#stats b { color:var(--fg); font-size:15px; font-variant-numeric:tabular-nums; }
#bar { flex:1; min-width:10rem; height:8px; background:var(--border); border-radius:4px; overflow:hidden; }
#bar i { display:block; height:100%; width:0; background:var(--accent); transition:width .4s; }
.layout { display:flex; flex:1; min-height:0; }
#text { flex:1; overflow:auto; padding:1.2rem 1.4rem 4rem; max-width:52rem;
  font:18px/1.75 Georgia, "Times New Roman", serif; white-space:pre-wrap; }
#text sup { color:var(--accent); font:600 11px system-ui; margin-right:.15rem; }
#text .caret { display:inline-block; width:.5em; height:1em; background:var(--accent);
  vertical-align:-.15em; animation:pulse .8s infinite; margin-left:2px; }
#text .empty { color:var(--muted); font:15px system-ui; }
#text .notes { color:var(--muted); font-size:15px; }
aside { width:300px; flex:none; border-left:1px solid var(--border); overflow:auto;
  padding:.8rem; font-size:13px; }
aside h3 { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:.4rem 0; }
.rec { padding:.35rem .5rem; border-radius:6px; display:flex; justify-content:space-between; gap:.5rem; }
.rec:nth-child(odd) { background:var(--card); }
.rec .ok { color:var(--ok); } .rec .warn { color:var(--warn); }
.rec small { color:var(--muted); }
#books { display:grid; grid-template-columns:1fr 1fr; gap:2px 8px; margin-top:.3rem; }
#books div { display:flex; justify-content:space-between; color:var(--muted); }
#books div.full { color:var(--ok); } #books div.part { color:var(--fg); }
@media (max-width:760px) { aside { display:none; } }
</style></head><body>
<header>
  <span class="brand"><b>eBible</b> live translation · <span id="model"></span></span>
  <span class="pill" id="pill">idle</span>
  <select id="book"><option value="ALL">All books (canonical order)</option></select>
  <input id="ch" placeholder="chapters 1-3">
  <label><input type="checkbox" id="force"> force</label>
  <button class="primary" id="start">Start</button>
  <button id="stop" disabled>Stop</button>
  <button id="rebuild" title="rebuild site/index.html reader">Rebuild reader</button>
  <a href="http://localhost:8765" target="_blank"><button>Open reader</button></a>
</header>
<div id="stats">
  <span>Chapter <b id="cur">—</b></span>
  <span>Verses <b id="vv">—</b></span>
  <span>Elapsed <b id="el">0s</b></span>
  <span>Tokens <b id="tok">0</b></span>
  <span>Speed <b id="tps">—</b> tok/s</span>
  <span>Book <b id="bprog">—</b></span>
  <span>Bible <b id="prog">—</b></span>
  <span id="bar"><i></i></span>
</div>
<div class="layout">
  <div id="text"><span class="empty">Pick a book (or leave "All books") and press Start. Text appears here as the model writes it.</span></div>
  <aside>
    <h3>Finished this session</h3>
    <div id="recent"></div>
    <h3 style="margin-top:1rem">Books (done/total)</h3>
    <div id="books"></div>
  </aside>
</div>
<script>
const $ = id => document.getElementById(id);
let S = null, raw = '', pending = false, cur = null, ticker = null;

function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function render(){
  pending = false;
  const box = $('text');
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  let html = esc(raw).replace(/^\[(\d+)\]\s*/gm, '<sup>$1</sup>');
  const i = html.indexOf('\n---');
  if (i >= 0) html = html.slice(0, i) + '<div class="notes">' + html.slice(i) + '</div>';
  if (!raw) html = '<span class="empty">' + (S && S.running ? 'Waiting for the model…' :
    'Pick a book (or leave "All books") and press Start. Text appears here as the model writes it.') + '</span>';
  box.innerHTML = html + (S && S.running && cur ? '<span class="caret"></span>' : '');
  if (atBottom) box.scrollTop = box.scrollHeight;
}
function schedule(){ if (!pending){ pending = true; requestAnimationFrame(render); } }

function tick(){
  if (!cur) return;
  const el = (Date.now()/1000 - cur.started);
  $('el').textContent = el < 60 ? el.toFixed(0)+'s' : Math.floor(el/60)+'m '+Math.floor(el%60)+'s';
  $('tok').textContent = cur.tokens;
  $('tps').textContent = el > 1 ? (cur.tokens/el).toFixed(1) : '—';
}

function applySnapshot(s){
  S = s;
  $('model').textContent = s.model;
  const pill = $('pill');
  pill.textContent = s.running ? s.status : (s.error ? 'error' : s.status);
  pill.className = 'pill' + (s.running ? ' run' : (s.error ? ' err' : ''));
  $('start').disabled = s.running; $('stop').disabled = !s.running;
  if (s.error) { raw = 'ERROR: ' + s.error; }
  cur = s.current;
  if (cur) { raw = cur.text; $('cur').textContent = cur.book+' '+cur.chapter; $('vv').textContent = cur.verses; }
  else if (!s.error && !raw) { $('cur').textContent = '—'; }
  $('prog').textContent = s.bible_done + ' / ' + s.bible_total;
  $('bar').firstElementChild.style.width = (100*s.bible_done/Math.max(1,s.bible_total)).toFixed(2)+'%';
  const sel = $('book'), keep = sel.value;
  sel.innerHTML = '<option value="ALL">All books (canonical order)</option>' +
    s.books.map(b => `<option value="${b.code}">${b.name} (${b.done}/${b.total})</option>`).join('');
  sel.value = keep || 'ALL';
  $('books').innerHTML = s.books.map(b => `<div class="${b.done>=b.total&&b.total?'full':(b.done?'part':'')}"><span>${b.name}</span><span>${b.done}/${b.total}</span></div>`).join('');
  const bn = cur ? cur.book : (s.recent[0] ? s.recent[0].book : null);
  if (bn) { const b = s.books.find(x => x.name === bn); if (b) $('bprog').textContent = b.done+' / '+b.total; }
  $('recent').innerHTML = s.recent.map(r =>
    `<div class="rec"><span>${r.book} ${r.chapter} <small>${r.got}/${r.expected} vv${r.attempts>1?' ·2 tries':''}</small></span>
     <span class="${r.status==='OK'?'ok':'warn'}">${r.status==='OK'?'OK':'WARN'} <small>${r.seconds}s${r.tps?' · '+r.tps+' t/s':''}</small></span></div>`).join('');
  schedule(); tick();
}

function connect(){
  const es = new EventSource('/events');
  es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.type === 'snapshot') applySnapshot(m);
    else if (m.type === 'token') { raw += m.t; if (cur) cur.tokens++; schedule(); }
    else if (m.type === 'start') { raw = ''; cur = {book:m.book, chapter:m.chapter, verses:m.verses, started:Date.now()/1000, tokens:0};
      $('cur').textContent = m.book+' '+m.chapter; $('vv').textContent = m.verses; $('pill').textContent = 'translating '+m.book+' '+m.chapter; $('pill').className='pill run'; schedule(); }
    else if (m.type === 'retry') { raw += '\n\n--- retry: missing '+JSON.stringify(m.missing)+' extra '+JSON.stringify(m.extra)+' ---\n\n'; schedule(); }
    else if (m.type === 'done' || m.type === 'skip' || m.type === 'run') refresh();
  };
  es.onerror = () => { es.close(); setTimeout(connect, 2000); };
}
async function refresh(){ applySnapshot(await (await fetch('/state')).json()); }
async function post(path, body){ const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}); return r.json(); }

$('start').onclick = async () => {
  const r = await post('/start', {book:$('book').value, chapters:$('ch').value, force:$('force').checked});
  if (!r.ok) alert(r.error); raw=''; schedule(); refresh();
};
$('stop').onclick = () => post('/stop');
$('rebuild').onclick = async () => { const r = await post('/rebuild'); alert(r.output || 'rebuilt'); };
ticker = setInterval(tick, 500);
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
