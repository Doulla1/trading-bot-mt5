# PowerShell Management Helper for Trading Bot
param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("start", "stop", "status", "dashboard", "backtest", "query", "help")]
    [string]$Action,

    [Parameter(Mandatory=$false)]
    [string]$Symbol = "EURUSD",

    [Parameter(Mandatory=$false)]
    [string]$From = "2026-05-01",

    [Parameter(Mandatory=$false)]
    [string]$To = "2026-05-31"
)

$botScript = "run_multi.py"
$dashboardScript = "dashboard.py"
$workDir = $PSScriptRoot

if (-not $workDir) {
    $workDir = Get-Location
}

function Show-Help {
    Write-Host @"

  TRADING BOT - Powershell Command Helper
  ======================================
  Usage: .\manage.ps1 <Action> [Arguments]

  Actions:
    start       Start the multi-symbol bot (run_multi.py) in the background.
    stop        Stop the background bot process.
    status      Check if the bot or streamlit dashboard processes are running.
    dashboard   Launch the Streamlit dashboard (using python -m streamlit).
    query       Display closed trades stats from all symbol databases.
    backtest    Run a backtest for a specific symbol.
                Arguments: -Symbol <NAME> -From <YYYY-MM-DD> -To <YYYY-MM-DD>
    help        Show this help screen.

  Examples:
    .\manage.ps1 start
    .\manage.ps1 status
    .\manage.ps1 dashboard
    .\manage.ps1 backtest -Symbol EURUSD -From 2026-05-01 -To 2026-05-31
    .\manage.ps1 query

"@
}

switch ($Action) {
    "help" {
        Show-Help
    }

    "start" {
        # Check if already running
        $process = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $botScript}
        if ($process) {
            Write-Host "[!] Bot is already running in background (PID: $($process.ProcessId))." -ForegroundColor Yellow
        } else {
            Write-Host "[+] Starting $botScript in background..." -ForegroundColor Green
            # Start process in background with explicit working directory
            $proc = Start-Process -FilePath "pythonw.exe" -ArgumentList $botScript -WorkingDirectory $workDir -WindowStyle Hidden -PassThru
            Write-Host "[+] Bot started successfully (PID: $($proc.Id))." -ForegroundColor Green
        }
    }

    "stop" {
        $processes = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $botScript}
        if (-not $processes) {
            Write-Host "[-] No running bot process found ($botScript)." -ForegroundColor Cyan
        } else {
            foreach ($p in $processes) {
                Write-Host "[-] Stopping bot process (PID: $($p.ProcessId))..." -ForegroundColor Red
                Stop-Process -Id $p.ProcessId -Force
                Write-Host "[+] Stopped successfully." -ForegroundColor Green
            }
        }
    }

    "status" {
        Write-Host "`n=== PROCESS STATUS ===`n" -ForegroundColor Cyan
        
        # Bot status
        $botProcess = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $botScript}
        if ($botProcess) {
            Write-Host "Bot (run_multi.py):      [RUNNING] (PID: $($botProcess.ProcessId))" -ForegroundColor Green
        } else {
            Write-Host "Bot (run_multi.py):      [STOPPED]" -ForegroundColor Red
        }

        # Dashboard status
        $dashProcess = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $dashboardScript}
        if ($dashProcess) {
            Write-Host "Dashboard (dashboard.py):  [RUNNING] (PID: $($dashProcess.ProcessId))" -ForegroundColor Green
        } else {
            Write-Host "Dashboard (dashboard.py):  [STOPPED]" -ForegroundColor Red
        }
        Write-Host ""
    }

    "dashboard" {
        Write-Host "[+] Starting Streamlit dashboard..." -ForegroundColor Green
        python -m streamlit run $dashboardScript
    }

    "query" {
        Write-Host "[+] Querying recent trades..." -ForegroundColor Green
        python query_trades.py
    }

    "backtest" {
        Write-Host "[+] Starting backtest for $Symbol from $From to $To..." -ForegroundColor Green
        python backtest.py --symbol $Symbol --from $From --to $To
    }
}
