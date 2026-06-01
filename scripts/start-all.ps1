<#
.SYNOPSIS
    Lance le Trading Bot IA en multi-symboles (un seul processus, 6 actifs).
    Utilise pythonw.exe (pas de console).
#>

param([switch]$Stop,[switch]$Status)

$rootDir = Split-Path -Parent $PSScriptRoot

function Start-Multi {
    $procs = Get-CimInstance -ClassName Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
    $existing = $procs | Where-Object { $_.CommandLine -match "run_multi\.py" }
    if ($existing) {
        Write-Host "[MULTI] Deja en cours (PID $($existing.ProcessId))" -ForegroundColor Yellow
        return
    }
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "pythonw.exe"
    $startInfo.Arguments = "run_multi.py"
    $startInfo.WorkingDirectory = $rootDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($startInfo)
    Write-Host "[MULTI] Lancee (PID $($proc.Id)) - 6 symboles" -ForegroundColor Green
}

function Stop-All {
    $procs = Get-CimInstance -ClassName Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
    $running = $procs | Where-Object { $_.CommandLine -match "run_multi\.py" }
    foreach ($p in $running) {
        Write-Host "Arret PID $($p.ProcessId)" -ForegroundColor Red
        Stop-Process -Id $p.ProcessId -Force
    }
}

function Show-Status {
    $procs = Get-CimInstance -ClassName Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue
    $proc = $procs | Where-Object { $_.CommandLine -match "run_multi\.py" } | Select-Object -First 1
    if (-not $proc) {
        Write-Host "`n=== Trading Bot ==="
        Write-Host "Aucune instance en cours." -ForegroundColor Yellow
        return
    }
    $uptime = [math]::Round(((Get-Date) - $proc.CreationDate).TotalMinutes, 1)
    Write-Host "`n=== Trading Bot IA ===" -ForegroundColor Cyan
    Write-Host "  PID $($proc.ProcessId) | uptime: ${uptime}min" -ForegroundColor Green
    Write-Host "  6 actifs: EURUSD, GBPUSD, AUDUSD, USDJPY, USDCHF, XAUUSD"
}

if ($Stop) { Stop-All }
elseif ($Status) { Show-Status }
else { Write-Host "Demarrage Multi..."; Start-Multi }
