@echo off
setlocal
set "ENV_NAME=bit"
cd /d "%~dp0.."
call conda run --no-capture-output -n "%ENV_NAME%" python -B publish_space.py %*
exit /b %errorlevel%
