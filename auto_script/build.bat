@echo off
setlocal
rem Validate an offline build in automatically cleaned temporary storage.
call conda run --no-capture-output -n bit python -B "%~dp0..\publisher.py" build %*
exit /b %errorlevel%
