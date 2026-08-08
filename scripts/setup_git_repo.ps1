# One-time git repo bootstrap for Lingxi Engine
# Usage: .\scripts\setup_git_repo.ps1 -RemoteUrl https://github.com/YOUR_ORG/YOUR_REPO.git
param(
    [Parameter(Mandatory = $true)]
    [string]$RemoteUrl,
    [string]$BaseBranch = "main"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Find-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $paths = @(
        "$env:LOCALAPPDATA\Programs\MinGit\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe",
        "C:\Program Files\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$GitExe = Find-GitExe
if (-not $GitExe) {
    Write-Error "git not found. Run: .\scripts\install_git_portable.ps1"
}

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & $GitExe @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

if (Test-Path (Join-Path $Root ".git")) {
    Write-Host ".git already exists. Skipping init."
} else {
    Invoke-Git init -b $BaseBranch
    Invoke-Git remote add origin $RemoteUrl
    Write-Host "Initialized repo and added remote: $RemoteUrl"
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  git add -A"
Write-Host "  git commit -m `"chore: engineering review fixes baseline`""
Write-Host "  git push -u origin $BaseBranch"
Write-Host "  .\scripts\create_engineering_prs.ps1 -Push"
