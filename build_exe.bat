@echo off
setlocal
title BgTextPresenter EXE Build
cd /d "%~dp0"

set LOG=build_log.txt
echo BgTextPresenter build log > "%LOG%"
date /t >> "%LOG%" 2>&1
time /t >> "%LOG%" 2>&1

echo ==================================================
echo   BgTextPresenter - EXE Build
echo ==================================================
echo.

echo [1/5] Checking Python...
python --version >> "%LOG%" 2>&1
if errorlevel 1 goto no_python
python --version
echo.

echo [2/5] Checking packages...
set MISSING=0
call :chk PySide6 PySide6
call :chk PIL Pillow
call :chk cv2 opencv-python
call :chk win32com.client pywin32
call :chk pypdfium2 pypdfium2
call :chk PyInstaller pyinstaller
if "%MISSING%"=="1" goto missing_pkg
echo.

echo [3/5] Checking source files...
python -m py_compile app.py main_window.py presenter_window.py thumbnail_utils.py text_engine.py ppt_engine.py subtitles.py music_player.py image_notes.py mix_bundle.py >> "%LOG%" 2>&1
if errorlevel 1 goto compile_error
echo   OK
echo.

echo [4/5] Closing running app if any...
taskkill /IM BgTextPresenter.exe /F >nul 2>&1
rem Old single-file build (slow to start) is replaced by the folder build below
if exist "dist\BgTextPresenter.exe" del /f /q "dist\BgTextPresenter.exe" >nul 2>&1
echo   OK
echo.

echo [5/5] Running PyInstaller...
echo   This takes several minutes. Progress is written to %LOG%
echo.
python -m PyInstaller --noconfirm BgTextPresenter.spec >> "%LOG%" 2>&1
if errorlevel 1 goto build_error

echo ==================================================
echo   BUILD OK
echo ==================================================
dir dist\BgTextPresenter\BgTextPresenter.exe
goto done

:chk
python -c "import %1" >> "%LOG%" 2>&1
if errorlevel 1 goto chk_missing
echo   OK       %1
goto :eof
:chk_missing
echo   MISSING  %1     ..  fix:  pip install %2
set MISSING=1
goto :eof

:tail
echo ---------------- last 40 lines of %LOG% ----------------
powershell -NoProfile -Command "if (Test-Path '%LOG%') { Get-Content -Path '%LOG%' -Tail 40 }"
echo --------------------------------------------------------
goto :eof

:no_python
echo.
echo [ERROR] Python not found in PATH.
echo         Install Python 3.10+ with "Add python.exe to PATH" checked.
goto fail

:missing_pkg
echo.
echo [ERROR] Missing packages. Run the pip commands listed above, then retry.
goto fail

:compile_error
echo.
echo [ERROR] A source file has a syntax error.
call :tail
goto fail

:build_error
echo.
echo [ERROR] PyInstaller failed.
call :tail
echo.
echo   Things to try:
echo     1. Delete the "build" folder, then run this again
echo     2. Make sure BgTextPresenter.exe is not running
echo     3. pip install --upgrade pyinstaller
echo     4. Send the whole %LOG% file for help
goto fail

:fail
echo.
pause
exit /b 1

:done
echo.
echo Output: dist\BgTextPresenter\BgTextPresenter.exe
echo   (Run the exe inside that folder. Keep the whole folder together -
echo    the _internal folder next to the exe is required.)
pause
exit /b 0
