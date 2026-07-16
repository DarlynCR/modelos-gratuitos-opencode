# setup_scheduled_task.ps1
# Creates a Windows Scheduled Task to run generador_modelos.py daily at 6:00 AM

$TaskName = "OpenCodeZen-FreeModelsGenerator"
$ScriptPath = Join-Path -Path $PSScriptRoot -ChildPath "generador_modelos.py"
$PythonCmd = "python"
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c cd /d `"$PSScriptRoot`" && $PythonCmd `"$ScriptPath`""
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00AM"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Write-Host "=== OpenCode Zen — Setup Scheduled Task ===" -ForegroundColor Cyan
Write-Host "Task Name : $TaskName" -ForegroundColor Gray
Write-Host "Script    : $ScriptPath" -ForegroundColor Gray
Write-Host "Schedule  : Daily at 6:00 AM" -ForegroundColor Gray
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = & $PythonCmd --version 2>&1
    Write-Host "[OK] Python detected: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python not found in PATH. Please install Python 3.8+ and try again." -ForegroundColor Red
    exit 1
}

# Check for required packages
Write-Host "[INFO] Checking Python dependencies..." -ForegroundColor Yellow
try {
    & $PythonCmd -c "import requests; import bs4" 2>&1 | Out-Null
    Write-Host "[OK] Required packages (requests, beautifulsoup4) are installed." -ForegroundColor Green
} catch {
    Write-Host "[INFO] Installing required packages via pip..." -ForegroundColor Yellow
    & $PythonCmd -m pip install -r (Join-Path -Path $PSScriptRoot -ChildPath "requirements.txt") 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Packages installed successfully." -ForegroundColor Green
    } else {
        Write-Host "[WARN] Some packages could not be installed. Run 'pip install -r requirements.txt' manually." -ForegroundColor Yellow
    }
}

# Test the script before scheduling
Write-Host "[INFO] Running test execution (dry run without notify)..." -ForegroundColor Yellow
try {
    $testResult = & $PythonCmd $ScriptPath "--no-notify" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Script test passed." -ForegroundColor Green
    } else {
        Write-Host "[WARN] Script test had issues (exit code: $LASTEXITCODE). Check output above." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[ERROR] Script test failed: $_" -ForegroundColor Red
    exit 1
}

# Check if task already exists and remove it
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] Task '$TaskName' already exists. Removing and recreating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "OpenCode Zen Free Models Generator — Scrapes pricing page daily at 6:00 AM and updates infografia_interactiva.html" `
        -Force

    Write-Host ""
    Write-Host "[SUCCESS] Scheduled task '$TaskName' created successfully!" -ForegroundColor Green
    Write-Host "  The script will run daily at 6:00 AM." -ForegroundColor Gray
    Write-Host "  It will:" -ForegroundColor Gray
    Write-Host "    - Scrape https://opencode.ai/docs/zen/#pricing" -ForegroundColor Gray
    Write-Host "    - Detect changes in free models" -ForegroundColor Gray
    Write-Host "    - Update infografia_interactiva.html dynamically" -ForegroundColor Gray
    Write-Host "    - Send a desktop notification if changes are found" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To run immediately without waiting for 6:00 AM:" -ForegroundColor Cyan
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
    Write-Host ""
    Write-Host "To view task properties:" -ForegroundColor Cyan
    Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | fl" -ForegroundColor White
} catch {
    Write-Host "[ERROR] Failed to create scheduled task: $_" -ForegroundColor Red
    exit 1
}
