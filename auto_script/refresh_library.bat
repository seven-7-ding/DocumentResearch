@echo off
setlocal
set "ENV_NAME=bit"
cd /d "%~dp0.."
call conda run --no-capture-output -n "%ENV_NAME%" python -B refresh_library.py %*
exit /b %errorlevel%
