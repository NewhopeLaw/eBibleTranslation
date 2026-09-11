#!/usr/bin/env python3
"""eBible as a desktop app: the live dashboard (with the reader built in) in its own window.

    pythonw scripts/app.py            # dashboard window (start_dashboard.cmd / Desktop shortcut)
    pythonw scripts/app.py --reader   # reader only, no server (start_reader.cmd)
    python  scripts/app.py            # same, with a console for log output

Runs live.py's server in-process (same driver, outputs, logs) and shows it in
a native window (pywebview on top of the system WebView2) instead of a browser
tab. If a dashboard is already listening on the port, the window simply
attaches to it. Closing the window stops the server it started; if a
translation is running it asks first. Hiding the dashboard's side panel turns
the same window into the reader (site/index.html); the tab at the edge brings
the translation back.

--reader shows only the reader: one offline HTML file, no server at all.

Without pywebview (`pip install pywebview`) it falls back to Edge's app mode,
and failing that to the default browser.
"""
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "app.log"
if sys.stdout is None or sys.stderr is None:          # pythonw: no console, keep a log instead
    LOG.parent.mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)

sys.path.insert(0, str(Path(__file__).parent))
import live                                                   # noqa: E402
from http.server import ThreadingHTTPServer                   # noqa: E402

URL = f"http://127.0.0.1:{live.PORT}/"
TITLE = "eBible — live translation"
READER = ROOT / "site" / "index.html"
READER_TITLE = "eBible — reader"
STORAGE = str(ROOT / "logs" / "webview")   # private_mode would wipe the page's remembered view/language on every start


def port_in_use() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", live.PORT)) == 0


def start_server():
    """-> the server we own, or None when one is already up on the port."""
    if port_in_use():
        print(f"dashboard already on {URL}, attaching")
        return None
    srv = ThreadingHTTPServer(("127.0.0.1", live.PORT), live.Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="dashboard").start()
    print(f"dashboard on {URL} (model {live.T.CONFIG['model']})")
    return srv


def run_window(srv) -> bool:
    try:
        import webview
    except ImportError:
        return False
    win = webview.create_window(TITLE, URL, width=1320, height=880, min_size=(760, 520), text_select=True)

    def closing():
        if srv is not None and live.STATE["running"]:
            ok = win.create_confirmation_dialog(
                "Translation in progress",
                "A translation is running. Closing the app stops it: the chapter in progress "
                "is discarded, finished chapters are kept. Close anyway?")
            if not ok:
                return False
        live.STOP.set()
        return True

    win.events.closing += closing
    webview.start(private_mode=False, storage_path=STORAGE)
    return True


def run_reader_window() -> bool:
    try:
        import webview
    except ImportError:
        return False
    webview.create_window(READER_TITLE, READER.as_uri(), width=1200, height=860, min_size=(640, 480), text_select=True)
    webview.start(private_mode=False, storage_path=STORAGE)
    return True


def edge_path():
    return next((p for p in (
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")) if os.path.exists(p)), None)


def run_fallback(url, keep_serving):
    edge = edge_path()
    if edge:
        print("pywebview not installed (pip install pywebview); using Edge app mode")
        subprocess.run([edge, f"--app={url}", "--new-window"])       # returns when the window closes
    else:
        print("pywebview not installed (pip install pywebview); opening the browser")
        webbrowser.open(url)
        if keep_serving:
            threading.Event().wait()                               # keep serving until killed


def main():
    if "--reader" in sys.argv[1:]:
        if not READER.exists():
            print(f"no reader yet: {READER} — run scripts/build_site.py (or Rebuild in the dashboard)")
            return
        if not run_reader_window():
            run_fallback(READER.as_uri(), keep_serving=False)
        return
    srv = start_server()
    try:
        if not run_window(srv):
            run_fallback(URL, keep_serving=True)
    finally:
        if srv is not None:
            live.STOP.set()
            srv.shutdown()
            print("dashboard stopped")


if __name__ == "__main__":
    main()
