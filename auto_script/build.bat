@echo off
setlocal
rem Offline build; output path is printed. Shared parameters: ..\config.json
call conda run --no-capture-output -n bit python -B "%~dp0..\publisher.py" build %*
exit /b %errorlevel%
