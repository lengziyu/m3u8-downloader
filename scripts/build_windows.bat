@echo off
cd /d %~dp0\..
python scripts\build_oneclick.py %*
echo.
echo Build 完成，请查看 dist 目录产物
pause
