@echo off
chcp 65001 >nul
cd /d "%~dp0"
py fundo_fixo.py diagnostico
pause
