@echo off
REM ============================================================
REM  Installer le demarrage automatique du Trading Bot IA
REM  (cree une tache planifiee Windows au demarrage)
REM  A executer en tant qu'administrateur.
REM ============================================================
echo ============================================================
echo  Installation auto-start Trading Bot IA
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
set "START_SCRIPT=%ROOT_DIR%\scripts\start-all.ps1"
set "TASK_NAME=TradingBot-IA"

REM Tuer la tache existante si elle existe (supprime les erreurs sur recreer)
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

REM Creer la tache planifiee (tout sur UNE ligne pour eviter les erreurs ^)
schtasks /Create /SC ONSTART /DELAY 0000:30 /TN "%TASK_NAME%" /TR "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%START_SCRIPT%\"" /RU "%USERNAME%" /F

if not errorlevel 1 goto :SUCCESS

echo [ERREUR] Impossible de creer la tache.
echo         Lancez ce script en tant qu'ADMINISTRATEUR.
echo         Clic droit sur le fichier -^> "Executer en tant qu'administrateur"
pause
exit /b 1

:SUCCESS
echo.
echo [OK] Tache planifiee creee avec succes : "%TASK_NAME%"
echo [OK] Le bot demarrera automatiquement au prochain demarrage de Windows.
echo [OK] 6 instances (EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD)
echo [OK] Timeframe M15 (XAUUSD: H1), demarrage differe de 30 secondes

echo.
echo --- Commandes utiles ---
echo   Lancer maintenant :     .\scripts\start-all.ps1
echo   Arreter:                .\scripts\start-all.ps1 -Stop
echo   Etat:                   .\scripts\start-all.ps1 -Status
echo   Desinstaller auto-start: schtasks /Delete /TN "%TASK_NAME%"
echo -------------------------

pause
