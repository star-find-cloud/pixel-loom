@echo off
if exist "%~dp0app\PixelLoom.exe" (
    start "" "%~dp0app\PixelLoom.exe"
    exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0project\launch.ps1"
