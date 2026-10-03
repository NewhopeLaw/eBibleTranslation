@echo off
rem Open the eBible reader (site\index.html) as a desktop app in its own
rem window: search, reference finder, chapter reader. No server, no browser.
rem Double-click this file, or the "eBible reader" Desktop shortcut.
rem Runs windowless; errors go to logs\app.log.
setlocal
set "ROOT=%~dp0"
start "eBible reader" /d "%ROOT%" pythonw scripts\app.py --reader
exit /b 0
