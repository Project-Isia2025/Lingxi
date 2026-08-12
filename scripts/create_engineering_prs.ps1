# Create 4 PR branches per docs/pr/ENGINEERING_FIXES.md
# Usage: .\scripts\create_engineering_prs.ps1 [-BaseBranch main] [-Push] [-RemoteUrl <url>]
param(
    [string]$BaseBranch = "main",
    [switch]$Push,
    [string]$RemoteUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Find-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\MinGit\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe",
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files\Git\bin\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$GitExe = Find-GitExe
if (-not $GitExe) {
    Write-Host ""
    Write-Host "ERROR: git is not installed or not in PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install (pick one):"
    Write-Host "  1. No admin (recommended):  .\scripts\install_git_portable.ps1"
    Write-Host "  2. Chocolatey (admin shell): choco install git -y"
    Write-Host "  3. Download: https://git-scm.com/download/win"
    Write-Host ""
    Write-Host "After install, close and reopen PowerShell, then run:"
    Write-Host "  git --version"
    Write-Host "  .\scripts\setup_git_repo.ps1 -RemoteUrl https://github.com/YOUR_ORG/YOUR_REPO.git"
    Write-Host "  .\scripts\create_engineering_prs.ps1 -Push"
    Write-Host ""
    exit 1
}

function Invoke-Git {
    param(
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Args,
        [switch]$AllowFailure
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $GitExe @Args 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if (-not $AllowFailure -and $code -ne 0) {
        throw "git $($Args -join ' ') failed with exit code $code"
    }
    return $code
}

function Get-GitOutput {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & $GitExe @Args 2>$null
    $ErrorActionPreference = $prev
    return $out
}

if (-not (Test-Path (Join-Path $Root ".git"))) {
    Write-Host ""
    Write-Host "ERROR: this folder is not a git repository (no .git)." -ForegroundColor Red
    Write-Host ""
    Write-Host "Run first:"
    Write-Host "  .\scripts\setup_git_repo.ps1 -RemoteUrl https://github.com/YOUR_ORG/YOUR_REPO.git"
    Write-Host ""
    exit 1
}

if ($Push -and -not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Warning "gh (GitHub CLI) not found. Branches will be pushed; create PRs on GitHub web UI."
    $script:CreatePr = $false
} else {
    $script:CreatePr = [bool]$Push
}

$status = Get-GitOutput status --porcelain
if (-not $status) {
    Write-Warning "Working tree clean. Commits may already exist; script will skip empty branches."
}

function New-PrBranch {
    param(
        [string]$Branch,
        [string[]]$Paths,
        [string]$Message
    )
    [void](Invoke-Git checkout $BaseBranch -AllowFailure)
    if ($LASTEXITCODE -ne 0) {
        [void](Invoke-Git checkout -b $BaseBranch)
    }
    [void](Invoke-Git checkout -B $Branch)

    $existing = @()
    foreach ($p in $Paths) {
        if (Test-Path (Join-Path $Root $p)) { $existing += $p }
    }
    if (-not $existing) {
        Write-Host "Skip $Branch (no files found)"
        return
    }

    [void](Invoke-Git add @existing)
    [void](Invoke-Git diff --cached --quiet -AllowFailure)
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Skip $Branch (no staged changes vs $BaseBranch)"
        return
    }
    [void](Invoke-Git commit -m $Message)
    if ($Push) {
        [void](Invoke-Git push -u origin $Branch)
        if ($script:CreatePr) {
            gh pr create --title $Message --body "See docs/pr/ENGINEERING_FIXES.md"
        }
    }
    Write-Host "OK: $Branch"
}

New-PrBranch "fix/p0-celery-datasource" @(
    "docker-compose.yml",
    "infra/worker_health.py",
    "infra/readiness.py",
    "services/workers/runtime.py",
    "docs/ops.md"
) "fix: align Celery deployment with default worker backend"

New-PrBranch "fix/p1-security-hardening" @(
    "api/auth_policy.py",
    "api/auth.py",
    "config/settings.py",
    "services/rpa_ingest.py",
    "config/local.env.example"
) "fix: harden production auth, CORS, and RPA webhook"

New-PrBranch "fix/p1-sqlite-wal" @(
    "core/db.py"
) "fix: enable SQLite WAL and busy_timeout for multi-process access"

New-PrBranch "fix/p2-ops-cleanup" @(
    "infra/celery_schedule.py",
    "infra/celery_tasks.py",
    "services/workers/alert_cleanup_scheduler.py",
    "tests/test_celery_workers.py",
    "tests/test_engineering_review_fixes.py",
    "tests/test_phase3_observability.py",
    "tests/test_phase3_features.py",
    "tests/test_phase6_features.py",
    "docs/pr/ENGINEERING_FIXES.md",
    "scripts/create_engineering_prs.ps1",
    "scripts/setup_git_repo.ps1"
) "fix: independent task cleanup schedule and decouple from ROI alert cleanup"

Write-Host ""
Write-Host "Done. Return to base: git checkout $BaseBranch"
