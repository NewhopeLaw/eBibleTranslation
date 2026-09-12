@echo off
rem Run the long model jobs (lexicon, fields of meaning, lexicon translations)
rem one after another until they are done. Everything is resumable: close this
rem window or reboot, then start it again and it picks up where it stopped.
rem
rem   start_work.cmd            run the whole queue
rem   start_work.cmd --list     show what is queued and how far along it is
rem   start_work.cmd --hours 8  stop starting new jobs after eight hours
setlocal
cd /d "%~dp0"
python scripts\work.py %*
echo.
echo Queue finished. Press a key to close.
pause >nul
