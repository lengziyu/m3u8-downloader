@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0\..
python scripts\build_oneclick.py %*
if errorlevel 1 (
  echo.
  echo Build failed. See error logs above.
  pause
  exit /b 1
)
echo.
echo Build succeeded. Output: dist\M3U8Downloader.exe
pause
