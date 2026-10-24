@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0StudioGUI.ps1"
if errorlevel 1 pause
