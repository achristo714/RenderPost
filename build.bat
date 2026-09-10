@echo off
REM Builds RenderPost.exe from RenderPost.py. Keep this folder OUTSIDE Dropbox.
REM Put RenderPost.py and (optionally) RenderPost.ico next to this file. Python + pip on PATH.
cd /d "%~dp0"
if not exist RenderPost.py (echo RenderPost.py is not in this folder. Check the filename ends in .py exactly. & pause & exit /b 1)
python -m pip install --quiet --upgrade -r requirements.txt
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
set ICON=
if exist RenderPost.ico (set ICON=--icon RenderPost.ico) else (echo No RenderPost.ico here, building with the default icon.)
python -m PyInstaller --onefile --noconsole --name RenderPost --collect-all fal_client --collect-all httpx --collect-all imageio_ffmpeg --add-data "web;web" %ICON% RenderPost.py
if errorlevel 1 (echo Build failed. & pause & exit /b 1)
echo.
echo Done: dist\RenderPost.exe
pause
