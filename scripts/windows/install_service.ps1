# 安装 Windows 计划任务：矩阵 API + 投流轮询 + 发布队列守护（开机自启）
# 用法（管理员 PowerShell）: .\scripts\windows\install_service.ps1
param(
    [string]$TaskPrefix = "MatrixAgent",
    [switch]$ApiOnly,
    [switch]$WithPublishWorker
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { throw "未找到 python，请先安装并加入 PATH" }

$ApiScript = Join-Path $Root "scripts\windows\run_api.ps1"
$PollScript = Join-Path $Root "scripts\poll_ad_reports.py"

function Register-MatrixTask {
    param(
        [string]$Name,
        [string]$Description,
        [string]$Execute,
        [string]$Argument,
        [string]$WorkDir
    )
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $Name -Confirm:$false }

    $action = New-ScheduledTaskAction -Execute $Execute -Argument $Argument -WorkingDirectory $WorkDir
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $Name -Description $Description -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest | Out-Null
    Write-Host "已注册计划任务: $Name"
}

$psExe = (Get-Command powershell).Source
Register-MatrixTask `
    -Name "$TaskPrefix-API" `
    -Description "五层AI智能体矩阵 API 服务" `
    -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ApiScript`"" `
    -WorkDir $Root

if (-not $ApiOnly) {
    Register-MatrixTask `
        -Name "$TaskPrefix-AdPoll" `
        -Description "投流报表轮询（守护）" `
        -Execute $Python `
        -Argument "`"$PollScript`" --daemon" `
        -WorkDir $Root
}

if ($WithPublishWorker) {
    $QueueScript = Join-Path $Root "scripts\windows\run_publish_worker.ps1"
    Register-MatrixTask `
        -Name "$TaskPrefix-PublishWorker" `
        -Description "发布队列 Worker（独立守护，API 未启用队列时可选）" `
        -Execute $psExe `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$QueueScript`"" `
        -WorkDir $Root
}

Write-Host ""
Write-Host "安装完成。管理命令："
Write-Host "  启动 API:  Start-ScheduledTask -TaskName '$TaskPrefix-API'"
Write-Host "  停止 API:  Stop-ScheduledTask -TaskName '$TaskPrefix-API'"
Write-Host "  卸载:      .\scripts\windows\uninstall_service.ps1"
Write-Host "  可选 Worker:  .\scripts\windows\install_service.ps1 -WithPublishWorker"
Write-Host "  API 地址:  http://127.0.0.1:9200/docs"
