# 卸载 Windows 计划任务
param([string]$TaskPrefix = "MatrixAgent")

$ErrorActionPreference = "Stop"
foreach ($name in @("$TaskPrefix-API", "$TaskPrefix-AdPoll", "$TaskPrefix-PublishWorker")) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "已移除: $name"
    } else {
        Write-Host "不存在: $name"
    }
}
