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
        # Check if already running using PID file
        $pidFile = "$workDir\data\bot.pid"
        $isRunning = $false
        $oldPid = $null
        if (Test-Path $pidFile) {
            $oldPid = Get-Content $pidFile -Raw
            if ($oldPid) {
                $oldPid = $oldPid.Trim()
                if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
                    $isRunning = $true
                }
            }
        }
        
        # Fallback to process search
        if (-not $isRunning) {
            $process = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $botScript}
            if ($process) {
                $oldPid = $process.ProcessId
                $isRunning = $true
                $oldPid | Out-File $pidFile -Force
            }
        }

        if ($isRunning) {
            Write-Host "[!] Bot is already running in background (PID: $oldPid)." -ForegroundColor Yellow
        } else {
            Write-Host "[+] Starting $botScript in background..." -ForegroundColor Green
            # Start process in background with output redirection and absolute script path
            $proc = Start-Process -FilePath "python.exe" -ArgumentList "$workDir\$botScript" -WorkingDirectory $workDir -WindowStyle Hidden -RedirectStandardOutput "$workDir\logs\bot_stdout.log" -RedirectStandardError "$workDir\logs\bot_stderr.log" -PassThru
            $proc.Id | Out-File $pidFile -Force
            Write-Host "[+] Bot started successfully (PID: $($proc.Id))." -ForegroundColor Green
        }
    }

    "stop" {
        $pidFile = "$workDir\data\bot.pid"
        $stopped = $false
        if (Test-Path $pidFile) {
            $oldPid = Get-Content $pidFile -Raw
            if ($oldPid) {
                $oldPid = $oldPid.Trim()
                if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
                    Write-Host "[-] Stopping bot process (PID: $oldPid)..." -ForegroundColor Red
                    Stop-Process -Id $oldPid -Force
                    $stopped = $true
                }
            }
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }

        # Fallback to search
        $processes = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $botScript}
        if ($processes) {
            foreach ($p in $processes) {
                Write-Host "[-] Stopping bot process (PID: $($p.ProcessId))..." -ForegroundColor Red
                Stop-Process -Id $p.ProcessId -Force
                $stopped = $true
            }
        }

        if ($stopped) {
            Write-Host "[+] Stopped successfully." -ForegroundColor Green
        } else {
            Write-Host "[-] No running bot process found ($botScript)." -ForegroundColor Cyan
        }
    }

    "status" {
        Write-Host "`n=== PROCESS STATUS ===`n" -ForegroundColor Cyan
        
        # Bot status
        $pidFile = "$workDir\data\bot.pid"
        $botProcess = $null
        $pidVal = ""
        if (Test-Path $pidFile) {
            $oldPid = Get-Content $pidFile -Raw
            if ($oldPid) {
                $oldPid = $oldPid.Trim()
                if ($oldPid) {
                    $botProcess = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
                    if ($botProcess) { $pidVal = $botProcess.Id }
                }
            }
        }
        
        # Fallback
        if (-not $botProcess) {
            $cimProcess = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $botScript}
            if ($cimProcess) {
                $botProcess = $cimProcess
                $pidVal = $cimProcess.ProcessId
            }
        }

        if ($botProcess) {
            Write-Host "Bot (run_multi.py):      [RUNNING] (PID: $pidVal)" -ForegroundColor Green
        } else {
            Write-Host "Bot (run_multi.py):      [STOPPED]" -ForegroundColor Red
        }

        # Dashboard status
        $dashProcess = Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match $dashboardScript}
        if ($dashProcess) {
            # Handle list if multiple dashboard processes exist
            $dp = $dashProcess | Select-Object -First 1
            $dPid = if ($dp.ProcessId) { $dp.ProcessId } else { $dp.Id }
            Write-Host "Dashboard (dashboard.py):  [RUNNING] (PID: $dPid)" -ForegroundColor Green
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
