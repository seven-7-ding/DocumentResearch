@echo off
setlocal
call conda run --no-capture-output -n bit python -B "%~dp0..\tests\test_publisher.py"
if errorlevel 1 exit /b %errorlevel%
call conda run --no-capture-output -n bit python -B "%~dp0..\tests\test_portal.py"
exit /b %errorlevel%
