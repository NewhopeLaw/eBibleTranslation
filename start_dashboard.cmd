@echo off
rem Start the eBible live dashboard (scripts\live.py on http://localhost:8766)
rem without Claude Code. Double-click this file, or run it from any terminal.
rem If the dashboard is already up it just opens the browser tab.
setlocal
set "ROOT=%~dp0"
set "PORT=8766"
set "URL=http://localhost:%PORT%/"

call :listening && goto open

rem Own console window so the server outlives whatever launched it;
rem cmd /k keeps the window open if live.py exits so the error is readable.
start "eBible dashboard" /min /d "%ROOT%" cmd /k python scripts\live.py

rem wait up to ~30 s for the port to answer
for /l %%i in (1,1,30) do (
    call :listening && goto open
    timeout /t 1 /nobreak >nul
)
echo Dashboard did not start on %URL% - see the "eBible dashboard" window.
pause
exit /b 1

:open
start "" "%URL%"
exit /b 0

:listening
netstat -ano -p tcp | findstr /r /c:":%PORT% .*LISTENING" >nul
exit /b %errorlevel%
