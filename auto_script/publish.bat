@echo off
setlocal
rem Edit shared parameters in ..\config.json. Default: latest HTML report.
rem Examples: publish.bat --date 2026-08-23   /   publish.bat --all
call conda run --no-capture-output -n bit python -B "%~dp0..\publisher.py" publish %*
exit /b %errorlevel%
