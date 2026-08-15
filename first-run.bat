@echo off
rem First-time setup: fresh full download + publish, using the Iranian PyPI mirror.
rem Edit the mirror URL below if it changes.
cd /d "%~dp0"
call run.bat fresh https://mirror-pypi.runflare.com/simple