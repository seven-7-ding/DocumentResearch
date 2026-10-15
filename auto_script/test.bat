@echo off
setlocal
call conda run --no-capture-output -n bit python -B "%~dp0..\tests\test_publisher.py"
exit /b %errorlevel%
