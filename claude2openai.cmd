@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0claude2openai.ps1" %*
exit /b %ERRORLEVEL%
