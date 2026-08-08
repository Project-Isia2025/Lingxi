# 启动矩阵 API（加载 config/local.env）
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
$logFile = Join-Path $logDir ("api_{0:yyyyMMdd}.log" -f (Get-Date))

Write-Output "[$(Get-Date -Format o)] starting api_server" | Tee-Object -FilePath $logFile -Append
python api_server.py 2>&1 | Tee-Object -FilePath $logFile -Append
