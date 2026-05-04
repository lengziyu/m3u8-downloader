@echo off
setlocal
chcp 65001 >nul
cd /d %~dp0\..
python scripts\build_installer.py %*
if errorlevel 1 (
  echo.
  echo Installer build failed. See logs above.
  pause
  exit /b 1
)
echo.
echo Installer build succeeded. Output: dist\Taoying-Setup.exe
pause
