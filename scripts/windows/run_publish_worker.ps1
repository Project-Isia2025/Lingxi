# 独立发布队列 Worker（当 API 进程未启用 PUBLISH_QUEUE_ENABLED 时使用）
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

$envFile = Join-Path $Root "config\local.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        if ($_ -match '^([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $val = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $val, "Process")
        }
    }
}

$logDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("publish_worker_{0:yyyyMMdd}.log" -f (Get-Date))

Write-Output "[$(Get-Date -Format o)] starting publish worker" | Tee-Object -FilePath $logFile -Append
python (Join-Path $Root "scripts\run_publish_worker.py") 2>&1 | Tee-Object -FilePath $logFile -Append
