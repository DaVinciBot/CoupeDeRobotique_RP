@echo off
rem Lance la simulation et ouvre les graphes (double-clic ou depuis un terminal)
set "PATH=C:\w64devkit\bin;%PATH%"
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1"
if errorlevel 1 (
    pause
    exit /b 1
)
start "" "%~dp0tmp\normal.png"
start "" "%~dp0tmp\blocage.png"
start "" "%~dp0tmp\recalage.png"
