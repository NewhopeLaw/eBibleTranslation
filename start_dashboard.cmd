@echo off
rem Start eBible as a desktop app: the live dashboard (scripts\live.py on
rem http://localhost:8766) in its own window, no browser or console.
rem Double-click this file, or the "eBible dashboard" Desktop shortcut.
rem If a dashboard is already up the window just attaches to it.
rem Runs windowless; errors go to logs\app.log.
setlocal
set "ROOT=%~dp0"
start "eBible" /d "%ROOT%" pythonw scripts\app.py
exit /b 0
