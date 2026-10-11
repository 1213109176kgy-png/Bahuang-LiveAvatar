@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Merge-Package.ps1"
if errorlevel 1 echo 合并失败，请查看上方提示。
pause
