<#
.SYNOPSIS
    Lance toutes les instances du Trading Bot IA en arriere-plan (detachees).
    Utilise pythonw.exe (pas de console) pour un fonctionnement discret.

.DESCRIPTION
    Instances lancees:
    - EURUSD (M15, magic 73456)
    - GBPUSD (M15, magic 73457)
    - AUDUSD (M15, magic 73458)
    - USDJPY (M15, magic 73459)
    - USDCHF (M15, magic 73460)
    - XAUUSD (H1,   magic 73461) - timeframe H1 car l'or est plus volatil

    Chaque instance a sa propre base de donnees (data/{symbole}/trading.db)
    et ses propres logs (logs/{symbole}/trading-bot.log).
#>

param(
    [switch]$Stop,
    [switch]$Status
)

$rootDir = Split-Path -Parent $PSScriptRoot
$pythonw = "pythonw.exe"
$python = "python.exe"

# Configuration des instances
$instances = @(
    @{ Symbol = "EURUSD"; Timeframe = "M15"; Magic = "73456" },
    @{ Symbol = "GBPUSD"; Timeframe = "M15"; Magic = "73457" },
    @{ Symbol = "AUDUSD"; Timeframe = "M15"; Magic = "73458" },
    @{ Symbol = "USDJPY"; Timeframe = "M15"; Magic = "73459" },
    @{ Symbol = "USDCHF"; Timeframe = "M15"; Magic = "73460" },
    @{ Symbol = "XAUUSD"; Timeframe = "H1";   Magic = "73461" }
)

function Start-Instance {
    param($Instance)
    $sym = $Instance.Symbol
    $tf = $Instance.Timeframe
    $magic = $Instance.Magic

    # Variables d'environnement pour cette instance
    $envVars = @{
        "TRADING_SYMBOL" = $sym
        "TRADING_TIMEFRAME" = $tf
        "MT5_MAGIC_NUMBER" = $magic
    }

    $logFile = "$rootDir\logs\$($sym.ToLower())\launcher.log"
    New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

    # Verifier si l'instance tourne deja
    $procs = Get-CimInstance -ClassName Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
    $existing = $procs | Where-Object { $_.CommandLine -match "run\.py.*--symbol $sym" }
    if ($existing) {
        Write-Host "[$sym] Deja en cours (PID $($existing.ProcessId))" -ForegroundColor Yellow
        return
    }

    # Lancer avec pythonw.exe (pas de console) en mode detache
    $logFile = "$rootDir\logs\$($sym.ToLower())\launcher.log"
    New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "pythonw.exe"
    $startInfo.Arguments = "run.py --symbol $sym"
    $startInfo.WorkingDirectory = $rootDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables["TRADING_SYMBOL"] = $sym
    $startInfo.EnvironmentVariables["TRADING_TIMEFRAME"] = $tf
    $startInfo.EnvironmentVariables["MT5_MAGIC_NUMBER"] = $magic

    $proc = [System.Diagnostics.Process]::Start($startInfo)
    Write-Host "[$sym] Lancee (PID $($proc.Id)) - $tf, magic=$magic" -ForegroundColor Green
}

function Stop-All {
    Write-Host "Arret de toutes les instances..." -ForegroundColor Cyan
    $procs = Get-CimInstance -ClassName Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
    $running = $procs | Where-Object { $_.CommandLine -match "run\.py.*--symbol" }
    foreach ($p in $running) {
        Write-Host "  Arret PID $($p.ProcessId): $($p.CommandLine)" -ForegroundColor Red
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Show-Status {
    Write-Host "`n=== Instances du Trading Bot ===`n" -ForegroundColor Cyan
    $procs = Get-CimInstance -ClassName Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
    $running = $procs | Where-Object { $_.CommandLine -match "run\.py.*--symbol" }
    if (-not $running) {
        Write-Host "Aucune instance en cours." -ForegroundColor Yellow
        return
    }
    foreach ($p in $running) {
        $line = $p.CommandLine
        if ($line -match "--symbol ([A-Z]+)") {
            $sym = $matches[1]
            $startTime = $p.CreationDate
            if ($startTime) {
                $uptime = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 1)
                Write-Host "  [$sym] PID $($p.ProcessId) | uptime: ${uptime}min" -ForegroundColor Green
            } else {
                Write-Host "  [$sym] PID $($p.ProcessId)" -ForegroundColor Green
            }
        }
    }
}

# Action principale
if ($Stop) {
    Stop-All
} elseif ($Status) {
    Show-Status
} else {
    Write-Host "=== Demarrage Trading Bot IA - Instances Multi-Actifs ===" -ForegroundColor Cyan
    Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n" -ForegroundColor Gray

    foreach ($inst in $instances) {
        Start-Instance -Instance $inst
        Start-Sleep -Seconds 2  # Pause entre les lancements
    }

    Write-Host "`nUtilisation:" -ForegroundColor Cyan
    Write-Host "  .\scripts\start-all.ps1            # Lancer toutes les instances" -ForegroundColor White
    Write-Host "  .\scripts\start-all.ps1 -Stop      # Arreter toutes les instances" -ForegroundColor White
    Write-Host "  .\scripts\start-all.ps1 -Status    # Voir l'etat des instances" -ForegroundColor White
}
