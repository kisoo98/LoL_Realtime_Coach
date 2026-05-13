@echo off
REM ============================================================================
REM LoLCoach packaging build script
REM   - Runs inside conda env 'lolcoach'
REM   - Installs PyInstaller if missing
REM   - Builds onedir with LoLCoach.spec
REM   - Copies sidecar resources (configs / models / .env / .env.example)
REM ============================================================================
setlocal enableextensions

cd /d "%~dp0"

call conda activate lolcoach
if errorlevel 1 (
    echo [ERROR] Failed to activate conda env 'lolcoach'.
    exit /b 1
)

where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not found - installing via pip.
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller install failed.
        exit /b 1
    )
)

if exist build (
    echo [INFO] Removing previous build\
    rmdir /s /q build
)
if exist dist (
    echo [INFO] Removing previous dist\
    rmdir /s /q dist
)

echo [BUILD] pyinstaller LoLCoach.spec --noconfirm
pyinstaller LoLCoach.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

echo [COPY] sidecar resources
if exist configs (
    xcopy /e /i /y configs dist\LoLCoach\configs >nul
)
if exist models (
    xcopy /e /i /y models dist\LoLCoach\models >nul
)
if exist .env (
    copy /y .env dist\LoLCoach\.env >nul
)
if exist .env.example (
    copy /y .env.example dist\LoLCoach\.env.example >nul
)

echo.
echo ============================================================================
echo  Build complete
echo ----------------------------------------------------------------------------
echo  EXE      : dist\LoLCoach\LoLCoach.exe
echo  Sidecar  : dist\LoLCoach\configs\ , dist\LoLCoach\models\ , dist\LoLCoach\.env
echo ----------------------------------------------------------------------------
echo  Test     : cd dist\LoLCoach  ^&^&  LoLCoach.exe
echo  Distrib  : zip the whole dist\LoLCoach\ folder
echo ============================================================================

endlocal
