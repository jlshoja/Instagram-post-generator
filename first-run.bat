@echo off
title LUXBAZ - First Run Setup
rem First-time setup: fresh full download + publish, using the Iranian PyPI mirror.
rem Edit the mirror URL below if it changes.
cd /d "%~dp0"
echo ============================================================
echo   FIRST RUN: fresh download + publish (with PyPI mirror)
echo ============================================================
echo.
call run.bat fresh https://mirror-pypi.runflare.com/simple
echo.
echo first-run.bat finished. If something failed above, fix it and
echo run again, or run:  .\run.bat retry
echo.
pause