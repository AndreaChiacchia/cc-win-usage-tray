@echo off
setlocal

cd /d "%~dp0"

echo Building ClaudeUsageTray.exe...
pyinstaller ClaudeUsageTray.spec --distpath dist --workpath build --noconfirm

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build FAILED.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\ClaudeUsageTray.exe

set /p LAUNCH="Launch ClaudeUsageTray.exe now? [Y/N]: "
if /i "%LAUNCH%"=="Y" (
    start "" "dist\ClaudeUsageTray.exe"
) else (
    pause
)
