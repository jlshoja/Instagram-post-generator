@echo off
title LUXBAZ - First Run Setup
rem First-time setup: fresh full download + publish.
rem Sets the Iranian PyPI mirror via PIP_INDEX_URL (edit below if needed);
rem pip reads this env var natively, no fragile argument parsing.
cd /d "%~dp0"
set PIP_INDEX_URL=https://mirror-pypi.runflare.com/simple
echo ============================================================
echo   FIRST RUN: fresh download + publish (with PyPI mirror)
echo ============================================================
echo.
call run.bat fresh
echo.
echo first-run.bat finished. If something failed above, fix it and
echo run again, or run:  .\run.bat retry
echo.
pause