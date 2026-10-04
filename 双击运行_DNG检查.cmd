@echo off
chcp 65001 >nul
setlocal
title DNG Evidence Check
if defined DNG_PYTHON (
  "%DNG_PYTHON%" -X utf8 -B "%~dp0run_dng_check.py" %*
  goto finished
)
set "DNG_CACHED_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%DNG_CACHED_PYTHON%" (
  "%DNG_CACHED_PYTHON%" -X utf8 -B "%~dp0run_dng_check.py" %*
  goto finished
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
  py -3 -X utf8 -B "%~dp0run_dng_check.py" %*
  goto finished
)
python --version >nul 2>&1
if not errorlevel 1 (
  python -X utf8 -B "%~dp0run_dng_check.py" %*
  goto finished
)
echo Python 3.9 or newer was not found. Set DNG_PYTHON to your Python executable.
pause
exit /b 1
:finished
set "DNG_EXIT_CODE=%ERRORLEVEL%"
if not "%DNG_EXIT_CODE%"=="0" echo Check failed. See the error above.
pause
exit /b %DNG_EXIT_CODE%
