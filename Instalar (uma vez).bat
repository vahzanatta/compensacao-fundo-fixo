@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install --user pywin32 pywebview
pause
