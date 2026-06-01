@echo off
REM ============================================================
REM  Installer le demarrage automatique du Trading Bot
REM  (cree une tache planifiee Windows au demarrage)
REM ============================================================
echo ============================================================
echo  Installation auto-start Trading Bot IA
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
set "START_SCRIPT=%ROOT_DIR%\scripts\start-all.ps1"

REM Creer la tache planifiee
schtasks /Create /SC ONSTART /DELAY 0000:30 ^
    /TN "TradingBot-IA" ^
    /TR "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%START_SCRIPT%\"" ^
    /RU "%USERNAME%" ^
    /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] Tache planifiee creee avec succes.
    echo [OK] Le bot demarrera automatiquement au prochain demarrage de Windows.
    echo.
    echo Informations :
    echo   - 6 instances (EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD)
    echo   - Timeframe M15 (XAUUSD: H1)
    echo   - Demarrage differe de 30 secondes
) else (
    echo [ERREUR] Impossible de creer la tache. Lancez ce script en tant qu'administrateur.
    pause
    exit /b 1
)

echo.
echo Pour lancer maintenant sans attendre le demarrage :
echo   PowerShell .\scripts\start-all.ps1
echo.
echo Pour arreter :
echo   PowerShell .\scripts\start-all.ps1 -Stop
echo.
echo Pour voir l'etat :
echo   PowerShell .\scripts\start-all.ps1 -Status

pause
