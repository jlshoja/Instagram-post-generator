@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   LUXBAZ Instagram Post Generator
echo ============================================================

rem ---- mode selection ------------------------------------------------
set MODE=%1
set ARG2=%2
if not defined MODE call :menu
if /i "%MODE%"=="exit" exit /b 0
if "%MODE%"=="-h"    goto :usage
if "%MODE%"=="/?"    goto :usage
if "%MODE%"=="help"  goto :usage

for %%m in (update fresh dry resume retry publish sample until daemon) do (
    if /i "%MODE%"=="%%m" set VALID=1
)
if not defined VALID goto :usage

if /i "%MODE%"=="until" (
    for %%s in (detail media post publish) do (
        if /i "%ARG2%"=="%%s" set STAGE_OK=1
    )
    if not defined STAGE_OK goto :usage
)

rem ---- 1. python / venv ------------------------------------------------
if not exist venv\Scripts\python.exe (
    echo [setup] creating virtual environment...
    py -3.12 -m venv venv 2>nul || python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Python not found. Install Python 3.12+ and re-run.
        pause
        exit /b 1
    )
) else (
    echo [setup] venv found.
)

rem install deps if missing (normal, then auto-retry via Iranian mirror)
venv\Scripts\python check_setup.py deps >nul 2>&1
if errorlevel 1 (
    echo [setup] installing dependencies...
    venv\Scripts\python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [setup] normal PyPI unreachable - retrying via Iranian mirror...
        set PIP_INDEX_URL=https://mirror-pypi.runflare.com/simple
        venv\Scripts\python -m pip install -r requirements.txt
        if errorlevel 1 (
            echo [ERROR] pip install failed on both sources.
            echo          Check your connection and re-run.
            pause
            exit /b 1
        )
    )
) else (
    echo [setup] dependencies present.
)

rem ---- 2. .env ----------------------------------------------------------
if exist ".env" goto :env_ok
echo [setup] creating .env from config.example.env
copy config.example.env ".env" >nul
echo.
echo [WARN]  A fresh .env was created. You MUST edit it and set:
echo        TELEGRAM_BOT_TOKEN=your_bot_token
echo        TELEGRAM_CHAT_ID=-100xxxxxxxxx
echo        TELEGRAM_THREAD_PENDING=6
echo        then re-run.
echo.
pause
exit /b 1
:env_ok

set PYTHONPATH=src

rem ---- 3. telegram config check ----------------------------------------
venv\Scripts\python check_setup.py telegram >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Telegram is not configured. Edit .env - TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.
    pause
    exit /b 1
)

rem ---- 4. modes ----------------------------------------------------------
if /i "%MODE%"=="fresh" (
    echo [setup] fresh mode: resetting database and media...
    if exist data\bazarkif.db     del /q data\bazarkif.db
    if exist data\bazarkif.db-wal del /q data\bazarkif.db-wal
    if exist data\bazarkif.db-shm del /q data\bazarkif.db-shm
    if exist ".media" rmdir /s /q ".media"
    set MODE=update
)

if /i "%MODE%"=="update" (
    echo [run] full update + publish...
    venv\Scripts\python -m bazarkif.cli --publish run-once
    goto :done
)

if /i "%MODE%"=="dry" (
    echo [run] scan + build posts only - NOT publishing to Telegram...
    venv\Scripts\python -m bazarkif.cli run-once
    goto :done
)

if /i "%MODE%"=="resume" (
    echo [run] requeue pending / due failed jobs, then update + publish...
    venv\Scripts\python -m bazarkif.cli --publish resume
    goto :done
)

if /i "%MODE%"=="retry" (
    echo [run] force retry ALL failed jobs now, then update + publish...
    venv\Scripts\python -m bazarkif.cli --publish retry-failed
    goto :done
)

if /i "%MODE%"=="publish" (
    echo [run] send drafted POST_GENERATED cards to Telegram - no scan...
    venv\Scripts\python -m bazarkif.cli publish
    goto :done
)

if /i "%MODE%"=="sample" (
    set SAMPLE=3
    if not "%ARG2%"=="" set SAMPLE=%ARG2%
    echo [run] test mode: only %SAMPLE% products, update + publish...
    set SAMPLE_LIMIT=%SAMPLE%
    venv\Scripts\python -m bazarkif.cli --publish run-once
    goto :done
)

if /i "%MODE%"=="until" (
    if /i "%ARG2%"=="publish" (
        echo [run] partial run up to publish + publish...
        venv\Scripts\python -m bazarkif.cli --publish --until publish run-once
    ) else (
        echo [run] partial run up to stage %ARG2% - no publish...
        venv\Scripts\python -m bazarkif.cli --until %ARG2% run-once
    )
    goto :done
)

if /i "%MODE%"=="daemon" (
    echo [run] scheduler daemon - Ctrl+C to stop...
    venv\Scripts\python -m bazarkif.cli daemon
    goto :done
)

:done
set EXIT=%ERRORLEVEL%
echo.
if "%EXIT%"=="0" (
    echo [done] finished. See logs\app.log
) else (
    echo [FAILED] exit code %EXIT%. See logs\app.log for details.
    echo          Re-run and pick "retry" to retry failed items.
)
pause
exit /b %EXIT%

:usage
echo.
echo Usage:  run.bat [mode] [value]
echo.
echo   (no args)              show the interactive menu
echo   update                  full update: scan + build + publish all products
echo   fresh                   reset database + media first, then full update
echo   dry                     scan + build posts, do NOT send to Telegram
echo   resume                  requeue pending / due failed jobs, then update
echo   retry                   force retry ALL failed jobs now, then update
echo   publish                 send drafted POST_GENERATED cards only (no scan)
echo   sample [N]              test mode: process only N products (default 3)
echo   until ^<stage^>           partial run up to a stage (no publish), stage:
echo                             detail | media | post
echo   until publish            partial run through publish (sends cards)
echo   daemon                   run the daily scheduler daemon
echo.
echo Examples:
echo   run.bat                  interactive menu
echo   run.bat fresh            first-time full download on a new machine
echo   run.bat retry            retry every failed item
echo   run.bat sample 5         quick test with 5 products
echo   run.bat until post       stop after post generation
echo.
pause
exit /b 0

:menu
echo.
echo  Select a mode:
echo   1) update     normal daily scan + publish
echo   2) fresh      clean re-download of everything
echo   3) retry      retry all failed items
echo   0) exit
echo.
echo  Advanced modes are still available as arguments:
echo  run.bat dry / resume / publish / sample / until / daemon
echo.
choice /c 0123 /n /m "  Pick a number (0-3): "
if errorlevel 4 goto :m_retry
if errorlevel 3 goto :m_fresh
if errorlevel 2 goto :m_update
if errorlevel 1 goto :m_exit
goto :menu

:m_update
set MODE=update
goto :eof
:m_fresh
set MODE=fresh
goto :eof
:m_retry
set MODE=retry
goto :eof
:m_exit
set MODE=exit
goto :eof